"""B255 — the outbound transports.

Console is the default and logs the link; SMTP is standard-library only and is
configured entirely from the environment. Both are asserted here without a network:
``smtplib`` is faked, so what is checked is the message we would send and the
handshake we would perform.
"""

import pytest

from transversal.services import mailer


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "MAIL_TRANSPORT",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "SMTP_STARTTLS",
        "SMTP_SSL",
    ):
        monkeypatch.delenv(name, raising=False)


class _FakeSMTP:
    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls: list = []
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        self.sent = message
        self.calls.append("send_message")


@pytest.fixture
def smtp(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", _FakeSMTP)
    return _FakeSMTP


# ── Choosing a transport ──────────────────────────────────────────────


def test_console_is_the_default():
    assert isinstance(mailer.get_mailer(), mailer.ConsoleMailer)


def test_console_logs_instead_of_sending(caplog):
    with caplog.at_level("WARNING"):
        mailer.ConsoleMailer().send("dave@example.com", "Hi", "the link")

    assert "dave@example.com" in caplog.text
    assert "the link" in caplog.text


def test_an_unknown_transport_fails_loudly(monkeypatch):
    monkeypatch.setenv("MAIL_TRANSPORT", "carrier-pigeon")

    with pytest.raises(mailer.MailNotConfiguredError):
        mailer.get_mailer()


def test_smtp_needs_a_host_and_a_sender(monkeypatch):
    monkeypatch.setenv("MAIL_TRANSPORT", "smtp")

    with pytest.raises(mailer.MailNotConfiguredError):
        mailer.get_mailer()

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    with pytest.raises(mailer.MailNotConfiguredError):
        mailer.get_mailer()


def test_a_bad_port_is_refused(monkeypatch):
    monkeypatch.setenv("MAIL_TRANSPORT", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "game@example.com")
    monkeypatch.setenv("SMTP_PORT", "not-a-port")

    with pytest.raises(mailer.MailNotConfiguredError):
        mailer.get_mailer()


# ── Sending over SMTP ─────────────────────────────────────────────────


def _configured(monkeypatch, **env):
    monkeypatch.setenv("MAIL_TRANSPORT", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "game@example.com")
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_the_defaults_are_587_with_starttls(monkeypatch, smtp):
    _configured(monkeypatch)
    configured = mailer.SMTPMailer.from_env()

    assert configured.port == 587
    assert configured.starttls is True
    assert configured.use_ssl is False


def test_ssl_defaults_to_port_465(monkeypatch, smtp):
    _configured(monkeypatch, SMTP_SSL="true")

    assert mailer.SMTPMailer.from_env().port == 465


def test_a_message_carries_from_to_subject_and_body(monkeypatch, smtp):
    _configured(monkeypatch)

    mailer.SMTPMailer.from_env().send("dave@example.com", "Sign in", "the link")

    message = _FakeSMTP.instances[-1].sent
    assert message["From"] == "game@example.com"
    assert message["To"] == "dave@example.com"
    assert message["Subject"] == "Sign in"
    assert "the link" in message.get_content()


def test_it_starttls_then_logs_in_then_sends(monkeypatch, smtp):
    _configured(monkeypatch, SMTP_USERNAME="apikey", SMTP_PASSWORD="secret")

    mailer.SMTPMailer.from_env().send("dave@example.com", "Sign in", "the link")

    assert _FakeSMTP.instances[-1].calls == [
        "starttls",
        ("login", "apikey", "secret"),
        "send_message",
    ]


def test_an_unauthenticated_relay_is_a_configuration_not_an_error(monkeypatch, smtp):
    _configured(monkeypatch)

    mailer.SMTPMailer.from_env().send("dave@example.com", "Sign in", "the link")

    assert _FakeSMTP.instances[-1].calls == ["starttls", "send_message"]


def test_starttls_can_be_turned_off(monkeypatch, smtp):
    _configured(monkeypatch, SMTP_STARTTLS="false")

    mailer.SMTPMailer.from_env().send("dave@example.com", "Sign in", "the link")

    assert _FakeSMTP.instances[-1].calls == ["send_message"]


def test_implicit_tls_does_not_starttls_on_top(monkeypatch, smtp):
    _configured(monkeypatch, SMTP_SSL="true", SMTP_USERNAME="apikey")

    mailer.SMTPMailer.from_env().send("dave@example.com", "Sign in", "the link")

    assert _FakeSMTP.instances[-1].calls == [("login", "apikey", ""), "send_message"]
