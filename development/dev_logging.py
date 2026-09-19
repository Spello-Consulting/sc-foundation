"""Manual testing code for the sc_foundation libraries. Should not be included in the distrbution."""

import datetime as dt  # noqa: F401
import pathlib
import platform
import sys
from time import sleep

from dev_config_schemas import ConfigSchema

from sc_foundation import (
    DateHelper,  # noqa: F401
    SCConfigManager,
    SCLogger,
)

CONFIG_FILE = "development/dev_config.yaml"
MESSAGE_TEXT = "development/long_message.txt"


def test_reportable_issue(logger: SCLogger):
    # Log a reportable issue
    entity = "Output 1"
    issue = "Test issue"
    send_delay = 4  # seconds
    message = f"This is a test reportable issue for {entity} - {issue}"
    loop_target = 15

    logger.report_notifiable_issue(entity, issue, send_delay, message)

    # Now loop for 10 seconds, logging a message every 1 seconds
    for i in range(loop_target):
        print(f"Loop iteration {i + 1}/{loop_target}")
        sleep(1)
        if logger.report_notifiable_issue(entity, issue, send_delay, message):
            print("Email sent for reportable issue.")
            logger.clear_notifiable_issue(entity, issue)


def log_fatal_error(logger: SCLogger):
    # Log a fatal issue
    message = pathlib.Path(MESSAGE_TEXT).read_text(encoding="utf-8")

    logger.log_fatal_error(message, exit_app=False)
    print("Logged fatal error without exiting the app.")


def test_sms(logger: SCLogger):
    # Test sending an SMS
    message = "This is a test SMS from sc_foundation."

    if logger.send_sms(message):
        print("Test SMS sent successfully.")
    else:
        print("Test SMS failed to send.")


def main():
    """Main function to run the example code."""
    print(f"Hello from sc-foundation running on {platform.system()}")

    # Get our default schema, validation schema, and placeholders
    schemas = ConfigSchema()

    # Initialize the SC_ConfigManager class
    try:
        config = SCConfigManager(
            config_file=CONFIG_FILE,
            default_config=schemas.default,
            validation_schema=schemas.validation,
            placeholders=schemas.placeholders
        )
    except RuntimeError as e:
        print(f"Configuration file error: {e}", file=sys.stderr)
        return

    # Initialize the SC_Logger class
    try:
        logger_settings = config.get_logger_settings()
        heartbeat_config = config.get("HeartbeatMonitor")
        logger = SCLogger(logger_settings, heartbeat_config=heartbeat_config)
    except RuntimeError as e:
        print(f"Logger initialisation error: {e}", file=sys.stderr)
        return
    logger.log_message("This is a test message at the summary level.", "summary")

    # Send a test SMS if Twilio is configured
    # test_sms(logger)

    # Setup email
    email_settings = config.get_email_settings()
    if email_settings is not None:
        logger.register_email_settings(email_settings)
        if logger.send_email("sc_foundation test - main()", "This is a test email."):
            print("Test email sent successfully.")
        else:
            print("Test email failed to send.")

    # Ping the heartbeat monitor    if heartbeat_config is not None:
    if logger.ping_heartbeat():
        print("Heartbeat ping successful.")
    else:
        print("Heartbeat ping failed.")

    # Wait 2 seconds and ping again to test the frequency setting
    sleep(2)
    if logger.ping_heartbeat():
        print("Second heartbeat ping successful.")
    else:
        print("Second heartbeat ping failed due to frequency limit.")

    # See if we have a fatal error from a previous run
    if logger.get_fatal_error():
        print("Prior fatal error detected.")
        logger.clear_fatal_error()

    # test_reportable_issue(logger)
    # log_fatal_error(logger)


if __name__ == "__main__":
    main()
