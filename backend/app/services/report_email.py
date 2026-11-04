"""Transactional report email delivery through configured SMTP accounts."""

from __future__ import annotations

import html
import hashlib
import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.parse import quote

from app.core.config import Settings, get_settings
from app.repositories.reports import claim_pending_report_emails, finish_report_email

logger = logging.getLogger(__name__)


def _valid_address(value: str) -> bool:
    parsed = parseaddr(value)
    return bool(parsed[1] and value.count("@") == 1 and
                not any(c in value for c in "\r\n,;") and
                not any(c.isspace() for c in parsed[1]))


def channel_ready(settings: Settings, channel: str) -> bool:
    host = getattr(settings, f"{channel}_smtp_host").strip()
    sender = getattr(settings, f"{channel}_smtp_from").strip()
    username = getattr(settings, f"{channel}_smtp_username").strip()
    password = getattr(settings, f"{channel}_smtp_password").get_secret_value()
    recipient_ok = channel != "admin" or _valid_address(settings.admin_notification_email.strip())
    return bool(host and _valid_address(sender) and recipient_ok and (bool(username) == bool(password)))


def build_report_message(event: dict[str, str], settings: Settings) -> EmailMessage:
    """Build a restrained, escaped HTML email with an equivalent text part."""
    kind = event["event_type"]
    recipient = event["recipient_email"]
    if kind not in {"submitted", "assigned", "in_progress", "pending_verification", "resolved"} or not _valid_address(recipient):
        raise ValueError("Invalid report email event.")
    channel = "admin" if kind == "submitted" else "user"
    sender = getattr(settings, f"{channel}_smtp_from").strip()
    if not _valid_address(sender):
        raise ValueError("Invalid SMTP sender.")

    reference = re.sub(r"[\r\n]+", " ", event["reference"]).strip()
    title = event["title"]
    location = event["location"]
    status_label = kind.replace("_", " ").title()
    if kind == "submitted":
        subject = f"New waste report {reference}"
        heading = "A new report is ready for review"
        lead = "A community member has submitted a waste report. Review the report in the administrator dashboard."
        url = f"{settings.email_public_base_url.rstrip('/')}/admin/reports/{quote(event['report_id'], safe='')}"
        button = "Review report"
        extra = ""
    elif kind in {"assigned", "in_progress", "pending_verification"}:
        subject = f"Report {reference}: {status_label}"
        heading = f"Your report is {status_label.lower()}"
        lead = {"assigned": "A collection team has been assigned to your report.",
                "in_progress": "The collection team has started work on your report.",
                "pending_verification": "The collection team submitted cleanup proof for administrator review."}[kind]
        url = f"{settings.email_public_base_url.rstrip('/')}/account/reports/{quote(event['report_id'], safe='')}"
        button = "View report"
        extra = ""
    else:
        subject = f"Report {reference} has been resolved"
        heading = "Your report has been resolved"
        lead = "An administrator has marked this report as resolved and recorded the follow-up details."
        url = f"{settings.email_public_base_url.rstrip('/')}/account/reports/{quote(event['report_id'], safe='')}"
        button = "View resolution"
        extra = f"Resolution details: {event['resolution_details']}" if event.get("resolution_details") else ""

    safe = {key: html.escape(str(value), quote=True) for key, value in {
        "heading": heading, "lead": lead, "reference": reference, "title": title,
        "location": location, "extra": extra, "url": url, "button": button,
        "status": status_label,
    }.items()}
    extra_html = f'<tr><td style="padding:8px 0;color:#46564d">{safe["extra"]}</td></tr>' if extra else ""
    location_html = f'<tr><td style="padding:8px 0;color:#46564d">Location: {safe["location"]}</td></tr>' if kind == "submitted" else ""
    body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:28px 12px;background:#f2f6f3;font-family:Arial,sans-serif;color:#173327">
<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px;margin:auto;background:#ffffff;border:1px solid #d9e5db;border-radius:12px">
<tr><td style="padding:26px 30px;background:#123b29;color:#ffffff;border-radius:12px 12px 0 0;font-size:20px;font-weight:bold">SisaCare.AI</td></tr>
<tr><td style="padding:30px"><h1 style="margin:0 0 12px;font-size:24px;line-height:1.3">{safe['heading']}</h1>
<p style="margin:0 0 22px;color:#46564d;line-height:1.6">{safe['lead']}</p>
<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;border-top:1px solid #e3eae4;border-bottom:1px solid #e3eae4;padding:10px 0">
<tr><td style="padding:8px 0;color:#46564d">Reference: <strong style="color:#173327">{safe['reference']}</strong></td></tr>
<tr><td style="padding:8px 0;color:#46564d">Current status: <strong style="color:#173327">{safe['status']}</strong></td></tr>
<tr><td style="padding:8px 0;color:#46564d">Report: <strong style="color:#173327">{safe['title']}</strong></td></tr>
{location_html}{extra_html}</table>
<p style="margin:28px 0"><a href="{safe['url']}" style="display:inline-block;padding:13px 20px;border-radius:7px;background:#276747;color:#ffffff;text-decoration:none;font-weight:bold">{safe['button']}</a></p>
<p style="margin:0;color:#6a7b70;font-size:13px;line-height:1.5">This is an update about a report submitted through SisaCare.AI. Sign in to view the latest status.</p>
</td></tr></table></body></html>"""
    text = f"SisaCare.AI\n\n{heading}\n\n{lead}\n\nReference: {reference}\nCurrent status: {status_label}\nReport: {title}"
    if kind == "submitted": text += f"\nLocation: {location}"
    if extra:
        text += f"\n{extra}"
    text += f"\n\n{button}: {url}\n"
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    stable_key = event.get("event_key") or f"{event['report_id']}:{kind}"
    sender_domain = parseaddr(sender)[1].rsplit("@", 1)[1]
    message["Message-ID"] = f"<sisacare-{hashlib.sha256(stable_key.encode()).hexdigest()[:32]}@{sender_domain}>"
    message.set_content(text)
    message.add_alternative(body, subtype="html")
    return message


def _send(message: EmailMessage, settings: Settings, channel: str) -> None:
    host = getattr(settings, f"{channel}_smtp_host")
    port = getattr(settings, f"{channel}_smtp_port")
    security = getattr(settings, f"{channel}_smtp_security")
    username = getattr(settings, f"{channel}_smtp_username")
    password = getattr(settings, f"{channel}_smtp_password").get_secret_value()
    context = ssl.create_default_context()
    if security == "ssl":
        connection = smtplib.SMTP_SSL(host, port, timeout=10, context=context)
    else:
        connection = smtplib.SMTP(host, port, timeout=10)
    with connection as smtp:
        if security == "starttls":
            smtp.starttls(context=context)
        if username:
            smtp.login(username, password)
        smtp.send_message(message)


def dispatch_pending_report_emails(settings: Settings | None = None) -> int:
    """Send a small batch; failures remain queued for bounded retry."""
    settings = settings or get_settings()
    admin_ready = channel_ready(settings, "admin")
    user_ready = channel_ready(settings, "user")
    if not admin_ready and not user_ready:
        return 0
    sent = 0
    for event in claim_pending_report_emails(include_admin=admin_ready, include_user=user_ready):
        try:
            channel = "admin" if event["event_type"] == "submitted" else "user"
            _send(build_report_message(event, settings), settings, channel)
        except (OSError, smtplib.SMTPException, ValueError) as exc:
            finish_report_email(event["event_key"], event["claim_token"], error_type=type(exc).__name__)
            logger.warning("report_email_delivery_failed event=%s error_type=%s", event["event_type"], type(exc).__name__)
        else:
            finish_report_email(event["event_key"], event["claim_token"])
            sent += 1
    return sent
