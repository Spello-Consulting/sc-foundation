"""Command-line email sender: the `sc-send-email` console script.

Sends a single email using the same settings rules as SCConfigManager.get_email_settings(): the SMTP_*
environment variables take precedence, falling back to the Email section of an optional YAML config file.
Intended for shell scripts (e.g. workflow failure alerts) that already have the SMTP_* variables in their
environment.

Usage:
    sc-send-email --subject TEXT (--body TEXT | --body-file PATH | --body -)
                  [--config PATH] [--section NAME] [--to EMAIL] [--test]

Exit status:
    0  Email sent, or deliberately skipped because email is disabled or not configured.
    1  Sending was attempted and failed.
    2  Usage error: bad arguments, unreadable body file or invalid SMTP settings.
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Any

import yaml

from sc_foundation.sc_config_mgr import SCConfigManager
from sc_foundation.sc_logging import SCLogger

EXIT_OK = 0
EXIT_SEND_FAILED = 1
EXIT_USAGE = 2

PROG = "sc-send-email"


def _warn(message: str) -> None:
    """Print a message prefixed with the program name to stderr.

    Args:
        message: The message to print.
    """
    print(f"[{PROG}] {message}", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        The configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Send an email using the SMTP_* environment variables, falling back to the Email section of an "
            "optional YAML config file."
        ),
    )
    parser.add_argument("--subject", required=True, help="Email subject. SubjectPrefix, if configured, is prepended.")
    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="Email body text, or '-' to read the body from stdin.")
    body_group.add_argument("--body-file", type=Path, help="Read the email body from this file.")
    parser.add_argument("--config", help="YAML config file to read email settings from. Defaults to $APP_CONFIG.")
    parser.add_argument("--section", default="Email", help="Config file section holding the email settings (default: Email).")
    parser.add_argument("--to", dest="send_to", help="Send to this address instead of the configured recipient.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Connect and log in to the SMTP server, but don't send the email.",
    )
    return parser


def _read_body(args: argparse.Namespace) -> str:
    """Return the email body from --body, --body - (stdin) or --body-file.

    Args:
        args: The parsed command-line arguments.

    Returns:
        The email body text. Raises OSError if the body file can't be read.
    """
    if args.body_file is not None:
        return Path(args.body_file).read_text(encoding="utf-8")
    if args.body == "-":
        return sys.stdin.read()
    return str(args.body)


def _load_config_section(config_path: str | None, section: str) -> dict[str, Any] | None:
    """Return the email section of the YAML config file, or None if there's no usable config.

    The file is read directly rather than through SCConfigManager so that a config file that fails the calling
    app's validation (often the very failure being reported) can't stop the email from being sent.

    Args:
        config_path: Path to the YAML config file, or None.
        section: The name of the section holding the email settings.

    Returns:
        The section as a dict, or None if there's no config file, it can't be read or the section is missing.
    """
    if not config_path:
        return None
    path = Path(config_path)
    if not path.is_file():
        _warn(f"Config file {config_path} not found, using environment variables only.")
        return None
    try:
        with path.open(encoding="utf-8") as file:
            config = yaml.safe_load(file)
    except (OSError, yaml.YAMLError) as e:
        _warn(f"Could not read config file {config_path} ({e}), using environment variables only.")
        return None
    if not isinstance(config, dict):
        return None
    section_settings = config.get(section)
    return section_settings if isinstance(section_settings, dict) else None


def main(argv: list[str] | None = None) -> int:
    """Run the sc-send-email command.

    Args:
        argv: Command-line arguments, excluding the program name. Defaults to sys.argv[1:].

    Returns:
        The process exit status (see the module docstring).
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # argparse exits 0 for --help and 2 for usage errors
        return e.code if isinstance(e.code, int) else EXIT_USAGE

    try:
        body = _read_body(args)
    except OSError as e:
        _warn(f"Could not read the email body: {e}")
        return EXIT_USAGE

    config_path = args.config or os.environ.get("APP_CONFIG")
    section_settings = _load_config_section(config_path, args.section)
    try:
        email_settings = SCConfigManager.build_email_settings(section_settings, args.section)
    except RuntimeError as e:
        _warn(str(e))
        return EXIT_USAGE

    if email_settings is None:
        _warn("Email is disabled or not fully configured (check the SMTP_* environment variables), skipping.")
        return EXIT_OK

    logger = SCLogger({"logfile_name": None, "console_verbosity": "summary"})
    logger.register_email_settings(email_settings)
    if not logger.send_email(args.subject, body, test_mode=args.test, send_to_email=args.send_to):
        return EXIT_SEND_FAILED

    recipient = args.send_to or email_settings.get("SendEmailsTo")
    if not args.test:
        print(f"[{PROG}] Email sent to {recipient}: {args.subject}")
    return EXIT_OK


def cli() -> None:
    """Console-script entry point: run main() and exit with its status."""
    sys.exit(main())


if __name__ == "__main__":
    cli()
