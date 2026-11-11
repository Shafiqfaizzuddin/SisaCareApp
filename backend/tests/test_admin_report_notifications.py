"""Administrator report-event queue and provider behavior with no live delivery."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.auth import require_admin_user, require_authenticated_user
from app.core.config import Settings
from app.main import app
from app.repositories import admin_notifications, reports, staff
from app.services import admin_notification_delivery as delivery, collection_workflow as workflow


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    monkeypatch.setattr(reports, 'DATABASE_PATH', tmp_path / 'reports.db')
    monkeypatch.setattr(reports, 'REPORT_ASSETS_DIR', tmp_path / 'assets')
    settings = Settings(_env_file=None, admin_notification_email='admin@example.com',
        admin_smtp_host='smtp.example.com', admin_smtp_from='alerts@example.com',
        telegram_bot_token='123:test-token', telegram_admin_chat_id='-1001234567890',
        email_public_base_url='https://sisacare.example')
    monkeypatch.setattr(admin_notifications, 'get_settings', lambda: settings)
    monkeypatch.setattr(workflow, 'get_settings', lambda: settings)
    created = reports.create_report({
        'analysis_id': None, 'reporter_role': 'user', 'user_id': str(uuid4()),
        'title': '<script>Park waste</script>', 'summary': 'Waste',
        'category': 'Plastic', 'location': 'Private home address',
        'latitude': 3.1, 'longitude': 101.7, 'location_source': 'map',
        'admin_notification_email': 'admin@example.com',
    })
    return created['id'], settings


def test_creation_and_status_queue_each_channel_once(scenario, monkeypatch):
    report_id, settings = scenario
    with reports._connect() as db:
        # The existing submission email remains in its original outbox.
        assert db.execute("SELECT COUNT(*) FROM report_email_outbox WHERE event_type = 'submitted'").fetchone()[0] == 1
        rows = db.execute('SELECT channel FROM admin_notification_outbox').fetchall()
        assert [row['channel'] for row in rows] == ['telegram']
    reports.validate_report(report_id, 'valid', str(uuid4()))
    with reports._connect() as db:
        rows = db.execute('SELECT event_key,channel FROM admin_notification_outbox ORDER BY rowid').fetchall()
        assert [row['channel'] for row in rows] == ['telegram', 'email', 'telegram']
        assert len({row['event_key'] for row in rows}) == 3
    sent_email, sent_telegram = [], []
    monkeypatch.setattr(delivery, '_send', lambda message, *_: sent_email.append(message))
    monkeypatch.setattr(delivery, '_send_telegram', lambda event, _: sent_telegram.append(event) or '42')
    assert delivery.dispatch_pending_admin_notifications(settings) == 3
    assert delivery.dispatch_pending_admin_notifications(settings) == 0
    assert len(sent_email) == 1 and len(sent_telegram) == 2
    email_html = sent_email[0].get_body(preferencelist=('html',)).get_content()
    assert '&lt;script&gt;Park waste&lt;/script&gt;' in email_html
    assert '<script>' not in email_html
    assert 'https://sisacare.example/admin/reports/' in email_html
    assert 'Private home address' not in email_html
    telegram = delivery.telegram_payload(sent_telegram[0], settings)
    assert telegram['chat_id'] == settings.telegram_admin_chat_id
    assert telegram['reply_markup']['inline_keyboard'][0][0]['url'].endswith(f'/admin/reports/{report_id}')
    assert 'Private home address' not in telegram['text']
    with reports._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM admin_notification_outbox WHERE sent_at IS NOT NULL').fetchone()[0] == 3


def test_workflow_transitions_queue_events_and_conflicts_do_not(scenario):
    report_id, _ = scenario
    admin, worker = str(uuid4()), str(uuid4())
    reports.validate_report(report_id, 'valid', admin)
    staff.set_grant(worker, 'staff', admin)
    workflow.assign(report_id, worker, 'Collection crew', admin)
    with pytest.raises(workflow.TaskConflict):
        workflow.assign(report_id, worker, 'Collection crew', admin)
    workflow.change(report_id, 'start', worker)
    with pytest.raises(workflow.TaskConflict):
        workflow.change(report_id, 'start', worker)
    with reports._connect() as db:
        rows = db.execute('''SELECT e.new_status,o.channel FROM admin_notification_outbox o
            JOIN report_status_events e ON e.id = o.status_event_id ORDER BY o.rowid''').fetchall()
    assert [row['new_status'] for row in rows] == [
        'submitted', 'verified', 'verified', 'assigned', 'assigned', 'in_progress', 'in_progress']


def test_failed_telegram_is_visible_and_can_be_retried(scenario, monkeypatch):
    report_id, settings = scenario
    monkeypatch.setattr(delivery, '_send_telegram', lambda *_: (_ for _ in ()).throw(delivery.TelegramDeliveryError(1)))
    for _ in range(5):
        with reports._connect() as db:
            db.execute('UPDATE admin_notification_outbox SET next_attempt_at = NULL')
        assert delivery.dispatch_pending_admin_notifications(settings) == 0
    listing = admin_notifications.list_deliveries(status='failed')
    assert len(listing) == 1
    assert listing[0]['recipient_hint'] == 'Private admin channel'
    assert settings.telegram_admin_chat_id not in str(listing)
    assert listing[0]['last_error'] == 'TelegramDeliveryError'
    assert admin_notifications.retry_failed(listing[0]['event_key']) is True
    monkeypatch.setattr(delivery, '_send_telegram', lambda *_: '99')
    assert delivery.dispatch_pending_admin_notifications(settings) == 1
    with reports._connect() as db:
        assert db.execute('SELECT status FROM reports WHERE id = ?', (report_id,)).fetchone()[0] == 'submitted'
        assert db.execute('SELECT provider_message_id FROM admin_notification_outbox').fetchone()[0] == '99'


def test_admin_delivery_api_rejects_other_roles(scenario):
    _report_id, _ = scenario
    client = TestClient(app)
    with client:
        assert client.get('/api/admin/notifications/admin').status_code == 401
        for role in ('user', 'staff'):
            app.dependency_overrides[require_authenticated_user] = lambda role=role: {'id': str(uuid4()), 'role': role}
            try:
                assert client.get('/api/admin/notifications/admin').status_code == 403
                assert client.post('/api/admin/notifications/admin/unknown/retry').status_code == 403
            finally:
                app.dependency_overrides.clear()
        app.dependency_overrides[require_admin_user] = lambda: {'id': str(uuid4()), 'role': 'admin'}
        try:
            result = client.get('/api/admin/notifications/admin')
            assert result.status_code == 200
            assert result.json()['events'][0]['reference'].startswith('SCA-')
            assert 'admin@example.com' not in result.text
            assert client.post('/api/admin/notifications/admin/unknown/retry').status_code == 409
        finally:
            app.dependency_overrides.clear()


def test_telegram_transport_handles_rate_limit_without_leaking_credentials(scenario, monkeypatch, caplog):
    _report_id, settings = scenario
    event = admin_notifications.claim_pending(email_ready=False, telegram_ready=True)[0]
    calls = []

    class FakeResponse:
        status = 429
        def read(self, _limit):
            return json.dumps({'ok': False, 'parameters': {'retry_after': 120}}).encode()

    class FakeConnection:
        def __init__(self, host, timeout):
            calls.append((host, timeout))
        def request(self, method, path, body, headers):
            calls.append((method, path, json.loads(body), headers))
        def getresponse(self):
            return FakeResponse()
        def close(self):
            pass

    monkeypatch.setattr(delivery.http.client, 'HTTPSConnection', FakeConnection)
    with pytest.raises(delivery.TelegramDeliveryError) as exc:
        delivery._send_telegram(event, settings)
    assert exc.value.retry_after == 120
    assert calls[0] == ('api.telegram.org', 10)
    assert calls[1][0] == 'POST'
    assert calls[1][2]['reply_markup']['inline_keyboard'][0][0]['text'] == 'Open report'
    assert settings.telegram_bot_token.get_secret_value() not in caplog.text


def test_localhost_report_link_is_not_sent_as_telegram_button():
    event = {'recipient': '-1001234567890', 'report_id': 'report-1', 'reference': 'SCA-1',
             'previous_status': '', 'new_status': 'submitted', 'title': 'Waste',
             'category': 'Plastic', 'event_at': '2026-11-11T00:00:00Z'}
    local = Settings(_env_file=None, email_public_base_url='http://localhost:5173')
    payload = delivery.telegram_payload(event, local)
    assert 'reply_markup' not in payload
    assert 'administrator dashboard' in payload['text']
    public = Settings(_env_file=None, email_public_base_url='https://sisacare.example')
    assert delivery.telegram_payload(event, public)['reply_markup']['inline_keyboard'][0][0]['url'].endswith('/admin/reports/report-1')
