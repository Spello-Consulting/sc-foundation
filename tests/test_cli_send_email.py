"""pytest for the sc-send-email command-line email sender (sc_foundation.cli_send_email)."""
import io
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sc_foundation import SCConfigManager
from sc_foundation.cli_send_email import EXIT_OK, EXIT_SEND_FAILED, EXIT_USAGE, main

SMTP_ENV_VARS = [
    "SMTP_ENABLE", "SMTP_SERVER", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USERNAME",
    "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "SMTP_SEND_TO_EMAIL", "SMTP_SUBJECT_PREFIX", "APP_CONFIG",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove any SMTP_* / APP_CONFIG values (conftest may load real ones) so each test controls its environment."""
    for var in SMTP_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def smtp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set a complete set of SMTP_* environment variables."""
    monkeypatch.setenv("SMTP_SERVER", "smtp.env.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "env-user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "env-secret")
    monkeypatch.setenv("SMTP_SEND_TO_EMAIL", "env-to@example.com")


@pytest.fixture
def smtp_cls() -> Iterator[MagicMock]:
    """Patch smtplib.SMTP as used by SCLogger.send_email().

    Yields:
        The mock SMTP class.
    """
    with patch("sc_foundation.sc_logging.smtplib.SMTP") as mock_cls:
        yield mock_cls


def sent_message(smtp_cls: MagicMock) -> tuple[str, str, str]:
    """Return the (from, to, message) of the single email sent through the mocked SMTP class.

    Args:
        smtp_cls: The mocked SMTP class.

    Returns:
        The arguments passed to sendmail().
    """
    server = smtp_cls.return_value.__enter__.return_value
    server.sendmail.assert_called_once()
    return server.sendmail.call_args.args


def write_config(tmp_path: Path, text: str) -> Path:
    """Write a YAML config file into tmp_path.

    Args:
        tmp_path: The pytest temporary directory.
        text: The YAML content.

    Returns:
        The path to the config file.
    """
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.usefixtures("smtp_env")
def test_env_only_sends(smtp_cls: MagicMock) -> None:
    """With only environment variables set, the email goes to SMTP_SEND_TO_EMAIL via SMTP_SERVER."""
    assert main(["--subject", "Hello", "--body", "Line 1\nLine 2"]) == EXIT_OK
    smtp_cls.assert_called_once_with(host="smtp.env.example.com", port=587, timeout=10)
    send_from, send_to, message = sent_message(smtp_cls)
    assert send_from == "env-user@example.com"
    assert send_to == "env-to@example.com"
    assert "Subject: Hello" in message
    assert "Line 1" in message


@pytest.mark.usefixtures("smtp_env")
def test_env_overrides_config(smtp_cls: MagicMock, tmp_path: Path) -> None:
    """Environment variables win over config file values (regression for the inline-script bug in finance_tools #56)."""
    config = write_config(tmp_path, (
        "Email:\n"
        "  EnableEmail: True\n"
        "  SMTPServer: smtp.config.example.com\n"
        "  SendEmailsTo: config-to@example.com\n"
        "  SubjectPrefix: '[App] '\n"
    ))
    assert main(["--subject", "Hi", "--body", "x", "--config", str(config)]) == EXIT_OK
    smtp_cls.assert_called_once_with(host="smtp.env.example.com", port=587, timeout=10)
    _, send_to, message = sent_message(smtp_cls)
    assert send_to == "env-to@example.com"
    assert "Subject: [App] Hi" in message


@pytest.mark.usefixtures("smtp_env")
def test_app_config_env_used_by_default(smtp_cls: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """$APP_CONFIG is used when --config isn't given."""
    config = write_config(tmp_path, "Email:\n  SubjectPrefix: '[FromAppConfig] '\n")
    monkeypatch.setenv("APP_CONFIG", str(config))
    assert main(["--subject", "Hi", "--body", "x"]) == EXIT_OK
    _, _, message = sent_message(smtp_cls)
    assert "Subject: [FromAppConfig] Hi" in message


@pytest.mark.usefixtures("smtp_env")
def test_config_section_override(smtp_cls: MagicMock, tmp_path: Path) -> None:
    """--section selects a different config section."""
    config = write_config(tmp_path, "Alerts:\n  SubjectPrefix: '[Alerts] '\n")
    assert main(["--subject", "Hi", "--body", "x", "--config", str(config), "--section", "Alerts"]) == EXIT_OK
    _, _, message = sent_message(smtp_cls)
    assert "Subject: [Alerts] Hi" in message


@pytest.mark.usefixtures("smtp_env")
@pytest.mark.parametrize("config_text", ["Email: [not, a, dict\n", "just a string\n", "Files:\n  Other: 1\n"])
def test_bad_or_missing_config_falls_back_to_env(smtp_cls: MagicMock, tmp_path: Path, config_text: str) -> None:
    """An unreadable config, or one without the section, falls back to environment variables."""
    config = write_config(tmp_path, config_text)
    assert main(["--subject", "Hi", "--body", "x", "--config", str(config)]) == EXIT_OK
    _, send_to, _ = sent_message(smtp_cls)
    assert send_to == "env-to@example.com"


@pytest.mark.usefixtures("smtp_env")
def test_missing_config_file_falls_back_to_env(smtp_cls: MagicMock, tmp_path: Path) -> None:
    """A config path that doesn't exist falls back to environment variables."""
    assert main(["--subject", "Hi", "--body", "x", "--config", str(tmp_path / "nope.yaml")]) == EXIT_OK
    sent_message(smtp_cls)


@pytest.mark.usefixtures("smtp_env")
def test_smtp_enable_false_skips(smtp_cls: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """SMTP_ENABLE=false skips sending and exits 0."""
    monkeypatch.setenv("SMTP_ENABLE", "false")
    assert main(["--subject", "Hi", "--body", "x"]) == EXIT_OK
    smtp_cls.assert_not_called()


@pytest.mark.usefixtures("smtp_env")
def test_config_enable_email_false_skips(smtp_cls: MagicMock, tmp_path: Path) -> None:
    """Email.EnableEmail: False in the config skips sending and exits 0."""
    config = write_config(tmp_path, "Email:\n  EnableEmail: False\n")
    assert main(["--subject", "Hi", "--body", "x", "--config", str(config)]) == EXIT_OK
    smtp_cls.assert_not_called()


def test_not_configured_skips(smtp_cls: MagicMock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Missing credentials skip sending, exit 0 and say why on stderr."""
    monkeypatch.setenv("SMTP_SERVER", "smtp.env.example.com")
    monkeypatch.setenv("SMTP_SEND_TO_EMAIL", "env-to@example.com")
    assert main(["--subject", "Hi", "--body", "x"]) == EXIT_OK
    smtp_cls.assert_not_called()
    assert "skipping" in capsys.readouterr().err


@pytest.mark.usefixtures("smtp_env")
def test_body_from_stdin(smtp_cls: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """--body - reads the body from stdin."""
    monkeypatch.setattr("sys.stdin", io.StringIO("Body from stdin\nSecond line"))
    assert main(["--subject", "Hi", "--body", "-"]) == EXIT_OK
    _, _, message = sent_message(smtp_cls)
    assert "Body from stdin" in message


@pytest.mark.usefixtures("smtp_env")
def test_body_from_file(smtp_cls: MagicMock, tmp_path: Path) -> None:
    """--body-file reads the body from a file."""
    body_file = tmp_path / "body.txt"
    body_file.write_text("Body from file", encoding="utf-8")
    assert main(["--subject", "Hi", "--body-file", str(body_file)]) == EXIT_OK
    _, _, message = sent_message(smtp_cls)
    assert "Body from file" in message


@pytest.mark.usefixtures("smtp_env")
def test_body_file_missing_is_usage_error(smtp_cls: MagicMock, tmp_path: Path) -> None:
    """An unreadable --body-file exits 2 without sending."""
    assert main(["--subject", "Hi", "--body-file", str(tmp_path / "missing.txt")]) == EXIT_USAGE
    smtp_cls.assert_not_called()


@pytest.mark.parametrize("argv", [
    ["--body", "x"],                                          # no subject
    ["--subject", "Hi"],                                      # no body
    ["--subject", "Hi", "--body", "x", "--body-file", "f"],   # both body options
])
def test_bad_arguments_are_usage_errors(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    """Missing or conflicting arguments exit 2."""
    assert main(argv) == EXIT_USAGE
    capsys.readouterr()


@pytest.mark.usefixtures("smtp_env")
def test_invalid_smtp_security_is_usage_error(smtp_cls: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """An invalid SMTP_SECURITY exits 2 without sending."""
    monkeypatch.setenv("SMTP_SECURITY", "plaintext")
    assert main(["--subject", "Hi", "--body", "x"]) == EXIT_USAGE
    smtp_cls.assert_not_called()


@pytest.mark.usefixtures("smtp_env")
def test_smtp_failure_exits_1(smtp_cls: MagicMock) -> None:
    """A failure while sending exits 1."""
    smtp_cls.side_effect = OSError("connection refused")
    assert main(["--subject", "Hi", "--body", "x"]) == EXIT_SEND_FAILED


@pytest.mark.usefixtures("smtp_env")
def test_to_override(smtp_cls: MagicMock) -> None:
    """--to overrides the configured recipient."""
    assert main(["--subject", "Hi", "--body", "x", "--to", "other@example.com"]) == EXIT_OK
    _, send_to, _ = sent_message(smtp_cls)
    assert send_to == "other@example.com"


@pytest.mark.usefixtures("smtp_env")
def test_test_mode_logs_in_but_does_not_send(smtp_cls: MagicMock) -> None:
    """--test connects and logs in but doesn't send."""
    assert main(["--subject", "Hi", "--body", "x", "--test"]) == EXIT_OK
    server = smtp_cls.return_value.__enter__.return_value
    server.login.assert_called_once_with("env-user@example.com", "env-secret")
    server.sendmail.assert_not_called()


def test_build_email_settings_matches_get_email_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """build_email_settings(section) gives the same result as get_email_settings() on a config with that section."""
    monkeypatch.setenv("SMTP_USERNAME", "env-user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "env-secret")
    section = {"SMTPServer": "smtp.config.example.com", "SMTPPort": 465, "SendEmailsTo": "config-to@example.com", "SubjectPrefix": "[P] "}
    config_file = write_config(tmp_path, (
        "Files:\n  LogfileVerbosity: summary\n  ConsoleVerbosity: summary\n"
        "Email:\n  SMTPServer: smtp.config.example.com\n  SMTPPort: 465\n"
        "  SendEmailsTo: config-to@example.com\n  SubjectPrefix: '[P] '\n"
    ))
    from_file = SCConfigManager(str(config_file)).get_email_settings()
    from_dict = SCConfigManager.build_email_settings(section)
    assert from_dict == from_file
    assert from_dict is not None
    assert from_dict["SMTPSecurity"] == "ssl"
    assert from_dict["SecurityWarning"] is True
