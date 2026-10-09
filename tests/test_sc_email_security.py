"""pytest for the SMTP connection security (STARTTLS / implicit TLS, certificate verification) of SCLogger.send_email()."""
# ruff: noqa: PLR6301
import shutil
import socket
import ssl
import subprocess  # noqa: S404
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from sc_foundation import SCConfigManager, SCLogger

SMTP_ENV_VARS = [
    "SMTP_ENABLE", "SMTP_SERVER", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME",
    "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "SMTP_SEND_TO_EMAIL", "SMTP_SUBJECT_PREFIX",
]


def make_logger(port: int | None = 587, security: str | None = None) -> SCLogger:
    """Create a console-only logger with email settings registered.

    Args:
        port (int | None): The SMTPPort value. If None, the key is omitted.
        security (str | None): The SMTPSecurity value. If None, the key is omitted.

    Returns:
        logger (SCLogger): The configured logger.
    """
    logger = SCLogger({"logfile_name": None, "console_verbosity": "error"})
    settings: dict = {
        "SMTPServer": "smtp.example.com",
        "SMTPUsername": "user",
        "SMTPPassword": "secret",
        "FromEmail": "from@example.com",
        "SendEmailsTo": "to@example.com",
    }
    if port is not None:
        settings["SMTPPort"] = port
    if security is not None:
        settings["SMTPSecurity"] = security
    logger.register_email_settings(settings)
    return logger


@pytest.fixture
def smtp_mocks():
    """Patch smtplib.SMTP and smtplib.SMTP_SSL as used by SCLogger.

    Yields:
        mocks (tuple): The (smtp_cls, smtp_ssl_cls) mock classes.
    """
    with patch("sc_foundation.sc_logging.smtplib.SMTP") as smtp_cls, \
         patch("sc_foundation.sc_logging.smtplib.SMTP_SSL") as smtp_ssl_cls:
        yield smtp_cls, smtp_ssl_cls


def assert_verifying_context(context: ssl.SSLContext) -> None:
    """Assert that an SSL context verifies the server certificate and hostname."""
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


class TestSecurityModeSelection:
    """Which smtplib class is used, and whether starttls is called."""

    def test_port_465_defaults_to_implicit_tls(self, smtp_mocks):
        smtp_cls, smtp_ssl_cls = smtp_mocks
        assert make_logger(port=465).send_email("Subject", "Body") is True

        smtp_ssl_cls.assert_called_once()
        smtp_cls.assert_not_called()
        server = smtp_ssl_cls.return_value.__enter__.return_value
        server.starttls.assert_not_called()
        server.login.assert_called_once_with("user", "secret")
        server.sendmail.assert_called_once()

    def test_port_587_defaults_to_starttls(self, smtp_mocks):
        smtp_cls, smtp_ssl_cls = smtp_mocks
        assert make_logger(port=587).send_email("Subject", "Body") is True

        smtp_cls.assert_called_once()
        smtp_ssl_cls.assert_not_called()
        server = smtp_cls.return_value.__enter__.return_value
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("user", "secret")
        server.sendmail.assert_called_once()

    def test_no_port_defaults_to_starttls(self, smtp_mocks):
        smtp_cls, smtp_ssl_cls = smtp_mocks
        assert make_logger(port=None).send_email("Subject", "Body") is True

        smtp_cls.assert_called_once()
        smtp_ssl_cls.assert_not_called()

    def test_ssl_on_non_465_port(self, smtp_mocks):
        smtp_cls, smtp_ssl_cls = smtp_mocks
        assert make_logger(port=2465, security="ssl").send_email("Subject", "Body") is True

        smtp_ssl_cls.assert_called_once()
        smtp_cls.assert_not_called()
        smtp_ssl_cls.return_value.__enter__.return_value.starttls.assert_not_called()

    def test_starttls_on_port_465(self, smtp_mocks):
        smtp_cls, smtp_ssl_cls = smtp_mocks
        assert make_logger(port=465, security="starttls").send_email("Subject", "Body") is True

        smtp_cls.assert_called_once()
        smtp_ssl_cls.assert_not_called()
        smtp_cls.return_value.__enter__.return_value.starttls.assert_called_once()

    def test_security_value_is_case_insensitive(self, smtp_mocks):
        _, smtp_ssl_cls = smtp_mocks
        assert make_logger(port=587, security="SSL").send_email("Subject", "Body") is True
        smtp_ssl_cls.assert_called_once()

    def test_invalid_security_value_returns_false(self, smtp_mocks):
        smtp_cls, smtp_ssl_cls = smtp_mocks
        assert make_logger(port=587, security="plaintext").send_email("Subject", "Body") is False

        smtp_cls.assert_not_called()
        smtp_ssl_cls.assert_not_called()


class TestCertificateVerification:
    """Both connection types must be given a verifying SSL context."""

    def test_starttls_path_verifies_certificate(self, smtp_mocks):
        smtp_cls, _ = smtp_mocks
        assert make_logger(port=587).send_email("Subject", "Body") is True

        server = smtp_cls.return_value.__enter__.return_value
        context = server.starttls.call_args.kwargs["context"]
        assert_verifying_context(context)

    def test_implicit_tls_path_verifies_certificate(self, smtp_mocks):
        _, smtp_ssl_cls = smtp_mocks
        assert make_logger(port=465).send_email("Subject", "Body") is True

        context = smtp_ssl_cls.call_args.kwargs["context"]
        assert_verifying_context(context)


class TestFailureLogging:
    """Errors are logged with the connection mode so that a mismatch is recognisable."""

    def test_ssl_error_returns_false_and_logs_mode(self, smtp_mocks):
        smtp_cls, _ = smtp_mocks
        smtp_cls.return_value.__enter__.return_value.starttls.side_effect = ssl.SSLError("certificate verify failed")
        logger = make_logger(port=587)

        with patch.object(logger, "log_message") as log_message:
            assert logger.send_email("Subject", "Body") is False

        logged = " ".join(str(call.args[0]) for call in log_message.call_args_list)
        assert "SMTP/SSL error" in logged
        assert "security=starttls" in logged
        assert "smtp.example.com:587" in logged

    def test_timeout_logs_mode(self, smtp_mocks):
        _, smtp_ssl_cls = smtp_mocks
        smtp_ssl_cls.side_effect = TimeoutError("timed out")
        logger = make_logger(port=465)

        with patch.object(logger, "log_message") as log_message:
            assert logger.send_email("Subject", "Body") is False

        logged = " ".join(str(call.args[0]) for call in log_message.call_args_list)
        assert "security=ssl" in logged


class TestConfigSettings:
    """SMTPSecurity handling in SCConfigManager.get_email_settings() and config validation."""

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        for var in SMTP_ENV_VARS:
            monkeypatch.delenv(var, raising=False)

    @staticmethod
    def write_config(tmp_path: Path, email_lines: str) -> SCConfigManager:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "Files:\n"
            "  LogfileVerbosity: summary\n"
            "  ConsoleVerbosity: summary\n"
            "Email:\n"
            "  EnableEmail: true\n"
            "  SMTPServer: smtp.example.com\n"
            "  SMTPUsername: user\n"
            "  SMTPPassword: secret\n"
            "  SendEmailsTo: to@example.com\n"
            f"{email_lines}",
            encoding="utf-8",
        )
        return SCConfigManager(config_file=str(config_file))

    def test_default_from_port_587(self, tmp_path):
        settings = self.write_config(tmp_path, "  SMTPPort: 587\n").get_email_settings()
        assert settings is not None
        assert settings["SMTPSecurity"] == "starttls"

    def test_default_from_port_465(self, tmp_path):
        settings = self.write_config(tmp_path, "  SMTPPort: 465\n").get_email_settings()
        assert settings is not None
        assert settings["SMTPSecurity"] == "ssl"

    def test_default_when_no_port_specified(self, tmp_path):
        settings = self.write_config(tmp_path, "").get_email_settings()
        assert settings is not None
        assert settings["SMTPPort"] == 587
        assert settings["SMTPSecurity"] == "starttls"

    def test_config_file_value(self, tmp_path):
        settings = self.write_config(tmp_path, "  SMTPPort: 2465\n  SMTPSecurity: ssl\n").get_email_settings()
        assert settings is not None
        assert settings["SMTPSecurity"] == "ssl"

    def test_environment_variable_overrides_config_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SMTP_SECURITY", "SSL")
        settings = self.write_config(tmp_path, "  SMTPPort: 587\n  SMTPSecurity: starttls\n").get_email_settings()
        assert settings is not None
        assert settings["SMTPSecurity"] == "ssl"

    def test_environment_port_drives_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SMTP_PORT", "465")
        settings = self.write_config(tmp_path, "  SMTPPort: 587\n").get_email_settings()
        assert settings is not None
        assert settings["SMTPSecurity"] == "ssl"

    def test_invalid_config_file_value_fails_validation(self, tmp_path):
        with pytest.raises(RuntimeError, match="SMTPSecurity"):
            self.write_config(tmp_path, "  SMTPSecurity: tls13\n")

    def test_invalid_environment_value_fails(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SMTP_SECURITY", "tls13")
        config = self.write_config(tmp_path, "")
        with pytest.raises(RuntimeError, match="SMTP security mode"):
            config.get_email_settings()


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl CLI not available")
def test_self_signed_certificate_is_refused(tmp_path):
    """A server presenting a self-signed certificate must be refused, and send_email() must return False."""
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    openssl = shutil.which("openssl")
    assert openssl is not None
    subprocess.run(  # noqa: S603
        [
            openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=localhost", "-keyout", str(key), "-out", str(cert),
        ],
        check=True,
        capture_output=True,
    )

    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certfile=str(cert), keyfile=str(key))

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(10)
    port = listener.getsockname()[1]

    def serve() -> None:
        try:
            conn, _ = listener.accept()
        except OSError:
            return
        try:
            with server_context.wrap_socket(conn, server_side=True) as tls:
                tls.sendall(b"220 localhost ESMTP\r\n")
        except (ssl.SSLError, OSError):
            pass  # The client is expected to abort the handshake
        finally:
            conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    logger = SCLogger({"logfile_name": None, "console_verbosity": "error"})
    logger.register_email_settings({
        "SMTPServer": "localhost",
        "SMTPPort": port,
        "SMTPSecurity": "ssl",
        "SMTPUsername": "user",
        "SMTPPassword": "secret",
        "FromEmail": "from@example.com",
        "SendEmailsTo": "to@example.com",
    })

    try:
        assert logger.send_email("Subject", "Body") is False
    finally:
        listener.close()
        thread.join(timeout=5)
