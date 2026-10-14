"""Manual testing code for the sc_foundation libraries. Should not be included in the distrbution."""

import datetime as dt
import platform
import sys
from time import sleep

from dev_config_schemas import ConfigSchema

from sc_foundation import (
    DateHelper,
    SCCommon,
    SCConfigManager,
    SCLogger,
)

CONFIG_FILE = "development/dev_config.yaml"


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


def test_select_file_location():
    print(f"Project root: {SCCommon.get_project_root()}")
    print(f"Locate file './dev_config.yaml': {SCCommon.select_file_location('dev_config.yaml')}")
    print(f"Locate file 'src/shelly_models.json': {SCCommon.select_file_location('src/shelly_models.json')}")
    print(f"Locate file 'logs/nolog.log': {SCCommon.select_file_location('logs/nolog.log')}")


def test_select_folder_location():
    print("\n\n")
    print(f"Located project folder at: {SCCommon.select_folder_location()}")
    print(f"Located folder 'logs' at: {SCCommon.select_folder_location('logs')}")
    print(f"Located abs folder at: {SCCommon.select_folder_location('/Users/nick/tmp/123', create_folder=True)}")


def test_get_dawn_dusk_times(config: SCConfigManager):
    location_config = config.get("Location", default={})
    as_date = dt.datetime(2026, 8, 1).date()  # noqa: DTZ001
    return_data = DateHelper.dawn_dusk_times(location_config=location_config, as_at=as_date)
    print("\n\ntest_get_dawn_dusk_times():")
    for key, value in return_data.items():
        print(f"  {key}: {value}")


def test_get_geolocation(config: SCConfigManager):
    location_config = config.get("Location", default={})
    geolocation = SCCommon.get_geo_location(location_config)
    print(f"\n\ntest_get_geolocation() geolocation: {geolocation}")


def test_get_external_ip():
    external_ip = SCCommon.get_external_ip()
    print(f"\n\ntest_get_external_ip() external_ip: {external_ip}")


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
        logger = SCLogger(logger_settings)
    except RuntimeError as e:
        print(f"Logger initialisation error: {e}", file=sys.stderr)
        return
    logger.log_message(f"This is a test message at the summary level. Log file path: {logger.get_logfile_path()}", "summary")

    # SCCommon tests
    # test_select_folder_location()
    # test_get_geolocation(config)
    # test_get_external_ip()
    # test_get_dawn_dusk_times(config)

    # Test internet connection
    # if not SCCommon.check_internet_connection():
    #     logger.log_message("No internet connection detected.", "summary")

    # Test get_deployment_info()
    deployment_info = SCCommon.get_deployment_info()
    print(f"\n\ntest_get_deployment_info() deployment_info: {deployment_info}")

    # Setup email
    email_settings = config.get_email_settings()
    if email_settings is not None:
        logger.register_email_settings(email_settings)
        logger.send_email("sc_foundation test - main()", "This is a test email.")

    # See if we have a fatal error from a previous run
    if logger.get_fatal_error():
        print("Prior fatal error detected.")
        logger.clear_fatal_error()

    #  test_reportable_issue(logger)


if __name__ == "__main__":
    main()
