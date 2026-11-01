"""Report notification templates, transport, and durable event tests."""

import sqlite3

from app.core.config import Settings
from app.repositories import reports
from app.services import report_email


def smtp_settings() -> Settings:
    return Settings(
        _env_file=None,
        admin_notification_email="admin@example.com",
        admin_smtp_host="sandbox.smtp.mailtrap.io",
        admin_smtp_username="admin-user",
        admin_smtp_password="secret",
        admin_smtp_from="SisaCare <alerts@example.com>",
        user_smtp_host="smtp.example.com",
        user_smtp_username="sender",
        user_smtp_password="secret",
        user_smtp_from="SisaCare <updates@example.com>",
        email_public_base_url="https://sisacare.example",
    )


def test_templates_escape_report_fields_and_include_plain_text() -> None:
    settings = smtp_settings()
    event = {
        "event_type": "submitted", "recipient_email": "admin@example.com",
        "report_id": "abc123", "reference": "SCA-123", "title": "<script>Bad</script>",
        "location": "Community Hall & Park", "assigned_team": "", "resolution_details": "",
    }
    message = report_email.build_report_message(event, settings)
    assert message["Subject"] == "New waste report SCA-123"
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "&lt;script&gt;Bad&lt;/script&gt;" in html
    assert "<script>Bad</script>" not in html
    assert "Community Hall &amp; Park" in html
    assert "https://sisacare.example/admin/reports/abc123" in html
    assert "Reference: SCA-123" in message.get_body(preferencelist=("plain",)).get_content()
    event.update(event_type="resolved", recipient_email="member@gmail.com",
                 resolution_details="Collected by Team A")
    resolved = report_email.build_report_message(event, settings)
    assert resolved["To"] == "member@gmail.com"
    assert "Collected by Team A" in resolved.get_body(preferencelist=("plain",)).get_content()
    assert "/account/reports/abc123" in resolved.get_body(preferencelist=("html",)).get_content()


def test_smtp_transport_uses_tls_and_configured_login(monkeypatch) -> None:
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            calls.append(("close",))

        def starttls(self, *, context):
            assert context is not None
            calls.append(("tls",))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("send", message["To"]))

    monkeypatch.setattr(report_email.smtplib, "SMTP", FakeSMTP)
    event = {"event_type": "in_progress", "recipient_email": "member@gmail.com",
             "report_id": "abc123", "reference": "SCA-123", "title": "Waste",
             "location": "Park", "assigned_team": "Team A"}
    settings = smtp_settings()
    report_email._send(report_email.build_report_message(event, settings), settings, "user")
    assert calls == [
        ("connect", "smtp.example.com", 587, 10), ("tls",),
        ("login", "sender", "secret"), ("send", "member@gmail.com"), ("close",),
    ]


def test_report_events_queue_once_and_send_to_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "reports.db")
    monkeypatch.setattr(reports, "REPORT_ASSETS_DIR", tmp_path / "assets")
    created = reports.create_report({
        "analysis_id": None, "reporter_role": "user", "user_id": "resident-1",
        "title": "Plastic waste", "summary": "Plastic waste found.",
        "category": "Recyclable Waste", "location": "Community Hall",
        "latitude": 6.4, "longitude": 100.2, "location_source": "map",
        "notification_email": "resident@gmail.com",
        "admin_notification_email": "admin@example.com",
    })
    report_id = created["id"]
    reports.validate_report(report_id, "valid", "admin-1")
    reports.transition_report(report_id, "assign", "admin-1", assigned_team="Team A", notify_user=True)
    reports.transition_report(report_id, "assign", "admin-1", assigned_team="Team B", notify_user=True)
    reports.transition_report(report_id, "resolve", "admin-1", resolution_details="Collected", notify_user=True)
    with sqlite3.connect(tmp_path / "reports.db") as database:
        rows = database.execute(
            "SELECT event_type, recipient_email FROM report_email_outbox ORDER BY rowid"
        ).fetchall()
        snapshot = database.execute("SELECT notification_email FROM reports WHERE id = ?", (report_id,)).fetchone()[0]
    assert rows == [
        ("submitted", "admin@example.com"),
        ("in_progress", "resident@gmail.com"),
        ("resolved", "resident@gmail.com"),
    ]
    assert snapshot == "resident@gmail.com"

    sent = []
    monkeypatch.setattr(report_email, "_send", lambda message, _settings, channel: sent.append((channel, message["To"])))
    assert report_email.dispatch_pending_report_emails(smtp_settings()) == 3
    assert sent == [("admin", "admin@example.com"), ("user", "resident@gmail.com"), ("user", "resident@gmail.com")]
    assert report_email.dispatch_pending_report_emails(smtp_settings()) == 0
    with sqlite3.connect(tmp_path / "reports.db") as database:
        assert database.execute("SELECT COUNT(*) FROM report_email_outbox WHERE sent_at IS NOT NULL").fetchone()[0] == 3


def test_smtp_failure_keeps_message_for_later_retry(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(reports, "DATABASE_PATH", tmp_path / "reports.db")
    reports.initialize_database()
    with reports._connect() as database:
        database.execute(
            """INSERT INTO reports (id, reference, reporter_role, user_id, title, summary,
               category, location, status, created_at, updated_at)
               VALUES ('r1', 'SCA-1', 'user', 'u1', 'Waste', 'Waste',
               'Recyclable Waste', 'Park', 'submitted', '2026-10-29', '2026-10-29')"""
        )
        reports._queue_email(database, "r1", "submitted", "admin@example.com", "2026-10-29")

    def fail(*_args):
        raise OSError("Temporary SMTP failure")

    monkeypatch.setattr(report_email, "_send", fail)
    assert report_email.dispatch_pending_report_emails(smtp_settings()) == 0
    with sqlite3.connect(tmp_path / "reports.db") as database:
        sent_at, attempts, error, next_attempt = database.execute(
            "SELECT sent_at, attempts, last_error, next_attempt_at FROM report_email_outbox"
        ).fetchone()
    assert sent_at is None and attempts == 1 and error == "OSError" and next_attempt
    assert report_email.dispatch_pending_report_emails(smtp_settings()) == 0
