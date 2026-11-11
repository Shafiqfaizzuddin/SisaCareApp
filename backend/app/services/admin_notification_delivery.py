"""Administrator-only report event messages and independent channel delivery."""
from __future__ import annotations

import hashlib
import html
import http.client
import json
import logging
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.parse import quote, urlparse

from app.core.config import Settings, get_settings
from app.repositories.admin_notifications import claim_pending, finish
from app.services.report_email import _send, channel_ready

logger = logging.getLogger(__name__)


class TelegramDeliveryError(Exception):
    def __init__(self, retry_after: int | None = None):
        super().__init__('Telegram delivery failed.')
        self.retry_after = retry_after


def report_url(event: dict, settings: Settings) -> str:
    return f"{settings.email_public_base_url.rstrip('/')}/admin/reports/{quote(event['report_id'], safe='')}"


def _labels(event: dict) -> tuple[str, str]:
    previous = event['previous_status'].replace('_', ' ').title() or 'New'
    current = event['new_status'].replace('_', ' ').title()
    headline = 'New report submitted' if current == 'Submitted' else (
        'Assignment updated' if previous == current == 'Assigned' else f'Report {current.lower()}')
    return headline, f'{previous} → {current}'


def build_admin_email(event: dict, settings: Settings) -> EmailMessage:
    sender = settings.admin_smtp_from.strip()
    if not sender or not parseaddr(sender)[1]:
        raise ValueError('Administrator SMTP sender is invalid.')
    headline, transition = _labels(event)
    url = report_url(event, settings)
    reference = str(event['reference']).replace('\r', ' ').replace('\n', ' ')
    title = str(event['title'])
    category = str(event['category'])
    event_at = str(event['event_at'])
    safe = {name: html.escape(value, quote=True) for name, value in {
        'headline': headline, 'transition': transition, 'reference': reference,
        'title': title, 'category': category, 'event_at': event_at, 'url': url,
    }.items()}
    body = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:24px 12px;background:#edf3ee;font-family:Arial,sans-serif;color:#173327">
<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px;margin:auto;background:#fff;border:1px solid #d1ddd4;border-radius:12px">
<tr><td style="padding:24px 30px;background:#123b29;color:#fff;font-size:20px;font-weight:bold">SisaCare.AI · Administrator alert</td></tr>
<tr><td style="padding:30px"><h1 style="margin:0 0 12px;font-size:23px">{safe['headline']}</h1>
<p style="color:#46564d;line-height:1.6">A report event is ready for your review. Sign in to view the current report and its status history.</p>
<table role="presentation" style="width:100%;border-top:1px solid #d1ddd4;border-bottom:1px solid #d1ddd4;padding:12px 0">
<tr><td style="padding:6px 0">Reference</td><td><strong>{safe['reference']}</strong></td></tr>
<tr><td style="padding:6px 0">Status</td><td><strong>{safe['transition']}</strong></td></tr>
<tr><td style="padding:6px 0">Report</td><td>{safe['title']}</td></tr>
<tr><td style="padding:6px 0">Category</td><td>{safe['category']}</td></tr>
<tr><td style="padding:6px 0">Event time</td><td>{safe['event_at']}</td></tr></table>
<p style="margin:28px 0"><a href="{safe['url']}" style="display:inline-block;padding:13px 20px;border-radius:7px;background:#276747;color:#fff;text-decoration:none;font-weight:bold">Open report</a></p>
<p style="color:#6a7b70;font-size:13px">This operational alert contains no reporter details or private images. The link requires administrator sign-in.</p>
</td></tr></table></body></html>'''
    plain = (f'SisaCare.AI administrator alert\n\n{headline}\n\nReference: {reference}\n'
             f'Status: {transition}\nReport: {title}\nCategory: {category}\nEvent time: {event_at}\n\n'
             f'Open report: {url}\n\nSign in as an administrator to review the latest status.\n')
    message = EmailMessage()
    message['From'] = sender
    message['To'] = event['recipient']
    message['Subject'] = f'{reference}: {headline}'
    domain = parseaddr(sender)[1].rsplit('@', 1)[1]
    message['Message-ID'] = f"<sisacare-admin-{hashlib.sha256(event['event_key'].encode()).hexdigest()[:32]}@{domain}>"
    message.set_content(plain)
    message.add_alternative(body, subtype='html')
    return message


def telegram_payload(event: dict, settings: Settings) -> dict:
    headline, transition = _labels(event)
    lines = [f'<b>{html.escape(headline)}</b>',
             f"Reference: <code>{html.escape(str(event['reference']))}</code>",
             f"Status: {html.escape(transition)}",
             f"Report: {html.escape(str(event['title'])[:160])}",
             f"Category: {html.escape(str(event['category']))}",
             f"Event time: {html.escape(str(event['event_at']))}"]
    payload = {'chat_id': event['recipient'], 'text': '\n'.join(lines), 'parse_mode': 'HTML',
               'link_preview_options': {'is_disabled': True}, 'protect_content': True}
    # Telegram rejects localhost inline buttons. A deployed HTTPS origin is also
    # required for the administrator to open the report from another device.
    url = report_url(event, settings)
    parsed = urlparse(url)
    if parsed.scheme == 'https' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
        payload['reply_markup'] = {'inline_keyboard': [[{'text': 'Open report', 'url': url}]]}
    else:
        payload['text'] += '\nReview this report in the SisaCare.AI administrator dashboard.'
    return payload


def _send_telegram(event: dict, settings: Settings) -> str:
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        raise TelegramDeliveryError()
    try:
        # http.client does not emit request URLs to the application log; the URL path contains the bot token.
        connection = http.client.HTTPSConnection('api.telegram.org', timeout=10)
        try:
            connection.request('POST', f'/bot{token}/sendMessage',
                body=json.dumps(telegram_payload(event, settings)).encode('utf-8'),
                headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            raw = response.read(65536)
            status = response.status
        finally:
            connection.close()
        data = json.loads(raw)
        if status == 429:
            delay = data.get('parameters', {}).get('retry_after') if isinstance(data, dict) else None
            raise TelegramDeliveryError(delay if isinstance(delay, int) else None)
        if status >= 400 or not isinstance(data, dict) or data.get('ok') is not True:
            raise TelegramDeliveryError()
        result = data.get('result')
        if not isinstance(result, dict) or not isinstance(result.get('message_id'), int):
            raise TelegramDeliveryError()
        return str(result['message_id'])
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise TelegramDeliveryError() from exc


def dispatch_pending_admin_notifications(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    email_ready = channel_ready(settings, 'admin')
    telegram_ready = bool(settings.telegram_admin_chat_id and settings.telegram_bot_token.get_secret_value())
    if not email_ready and not telegram_ready:
        return 0
    sent = 0
    for event in claim_pending(email_ready=email_ready, telegram_ready=telegram_ready):
        try:
            provider_id = None
            if event['channel'] == 'email':
                _send(build_admin_email(event, settings), settings, 'admin')
            else:
                provider_id = _send_telegram(event, settings)
        except (OSError, ValueError, smtplib.SMTPException, TelegramDeliveryError) as exc:
            finish(event['event_key'], event['claim_token'], error_type=type(exc).__name__,
                   retry_after=exc.retry_after if isinstance(exc, TelegramDeliveryError) else None)
            logger.warning('admin_notification_failed channel=%s error_type=%s', event['channel'], type(exc).__name__)
        else:
            finish(event['event_key'], event['claim_token'], provider_message_id=provider_id)
            sent += 1
    return sent
