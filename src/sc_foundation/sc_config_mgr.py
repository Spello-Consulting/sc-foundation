"""Spello Consulting Configuration Manager Module.

Management of a YAML log file.
"""
import datetime as dt
import os
from collections.abc import Callable
from pathlib import Path

import yaml
from cerberus import Validator
from mergedeep import merge

from sc_foundation.sc_common import SCCommon
from sc_foundation.sc_date_helper import DateHelper
from sc_foundation.validation_schema import yaml_config_validation


class SCConfigManager:
    """Loads the configuration from a YAML file, validates it, and provides access to the configuration values."""

    def __init__(self, config_file: str, default_config: dict | None = None, validation_schema: dict | None = None, placeholders: dict | None = None):
        """Initializes the configuration manager.

        Args:
            config_file (str): The relative or absolute path to the configuration file.
            default_config (Optional[dict], optional): A default configuration dict to use if the config file does not exist.
            validation_schema (Optional[dict], optional): A cerberus style validation schema dict to validate the config file against.
            placeholders (Optional[dict], optional): A dictionary of placeholders to check in the config. If any of these are found, a exception will be raised.

        Raises:
            RuntimeError: If the config file does not exist and no default config is provided, or if there are YAML errors in the config file.

        """
        self._config = {}    # Intialise the actual config object
        self.config_file = config_file
        self.logger_function = None  # Placeholder for a logger function
        self.placeholders = placeholders

        # Build the full validation schema
        if validation_schema is None:
            self.validation_schema = yaml_config_validation
        else:
            self.validation_schema = merge({}, yaml_config_validation, validation_schema)

        # Determine the file path for the log file
        self.config_path = SCCommon.select_file_location(self.config_file)
        if self.config_path is None:
            msg = f"Cannot find config file {self.config_file}. Please check the path."
            raise RuntimeError(msg)

        # If the config file doesn't exist and we have a default config, write that to file
        if not self.config_path.exists():
            if default_config is None:
                msg = f"Cannot find config file {self.config_file} and no default config provided."
                raise RuntimeError(msg)

            with Path(self.config_path).open("w", encoding="utf-8") as file:
                yaml.dump(default_config, file)

        # Now load the config file
        self.load_config()

    def load_config(self) -> bool:
        """Load the configuration from the config file specified to the __init__ method.

        Raises:
            RuntimeError: If there are YAML errors in the config file, if placeholders are found, or if validation fails.

        Returns:
            result (bool): True if the configuration was loaded successfully, otherwise False.
        """
        if not self.config_path:
            return False

        with Path(self.config_path).open(encoding="utf-8") as file:
            try:
                self._config = yaml.safe_load(file)

            except yaml.YAMLError as e:
                msg = f"YAML error in config file {self.config_file}: {e}"
                raise RuntimeError(msg) from e

            else:
                # Make sure there are no placeholders in the config file, exit if there are
                self.check_for_placeholders(self.placeholders)

                # If we have a validation schema, validate the config
                if self.validation_schema is not None:
                    v = Validator()

                    if not v.validate(self._config, self.validation_schema):  # type: ignore[call-arg]
                        # Format cerberus errors into human readable lines like "path.to.field: error message"

                        error_lines = self._format_validator_errors(v.errors)  # type: ignore[call-arg]
                        nice = "\n".join(error_lines)
                        msg = f"Validation error for config file {self.config_path}: \n{nice}"
                        raise RuntimeError(msg)

        return True

    @staticmethod
    def _format_validator_errors(err, path=""):
        msgs = []
        # dict: descend into keys
        if isinstance(err, dict):
            for k, vv in err.items():
                new_path = f"{path}: {k}" if path else str(k)
                msgs.extend(SCConfigManager._format_validator_errors(vv, new_path))
            return msgs
        # list: may contain strings or nested dicts (e.g. list of item errors)
        if isinstance(err, list):
            for idx, item in enumerate(err):
                if isinstance(item, (dict, list)):
                    # for list-items that are dicts, include index in path
                    if isinstance(item, dict):
                        new_path = f"{path}" if path else f"[{idx}]"
                        msgs.extend(SCConfigManager._format_validator_errors(item, new_path))
                    else:
                        msgs.extend(SCConfigManager._format_validator_errors(item, path))
                # item is an error string
                elif path:
                    msgs.append(f"{path} - {item}")
                else:
                    msgs.append(str(item))
            return msgs
        # fallback
        if path:
            msgs.append(f"{path}: {err}")
        else:
            msgs.append(str(err))
        return msgs

    def get_config_file_last_modified(self) -> dt.datetime | None:
        """Get the last modified time of the config file.

        Returns:
            dt.datetime | None: The last modified time if the config file exists, None otherwise.
        """
        if not self.config_path:
            return None

        return DateHelper.get_file_datetime(self.config_path)

    def check_for_config_changes(self, last_check: dt.datetime) -> dt.datetime | None:
        """Check if the configuration file has changed. If it has, reload the configuration.

        Args:
            last_check (dt.datetime): The last time the config was checked.

        Returns:
            result (dt.datetime | None): The new last modified time if the config has changed and was reloaded, None otherwise.
        """
        last_modified_dt = self.get_config_file_last_modified()
        if last_modified_dt is None:
            return None

        if last_check is None or last_modified_dt > last_check:
            # The config file has changed, reload it
            self.load_config()
            return last_modified_dt

        return None

    def register_logger(self, logger_function: Callable) -> None:
        """Registers a logger function to be used for logging messages.

        Args:
            logger_function (Callable): The function to use for logging messages.
        """
        self.logger_function = logger_function

    def check_for_placeholders(self, placeholders: dict | None) -> bool:
        """Recursively scan self._config for any instances of a key found in placeholders.

        If the keys and values match (including nested), return True.

        Args:
            placeholders (dict): A dictionary of placeholders to check in the config.

        Raises:
            RuntimeError: If any placeholder is found in the config file, an exception will be raised with a message indicating the placeholder and its value.

        Returns:
            result (bool): True if any placeholders are found in the config, otherwise False.
        """  # noqa: DOC502
        def recursive_check(config_section, placeholder_section):
            for key, placeholder_value in placeholder_section.items():
                if key and key in config_section:
                    config_value = config_section[key]
                    if isinstance(placeholder_value, dict) and isinstance(config_value, dict):
                        if recursive_check(config_value, placeholder_value):
                            return True
                    elif config_value == placeholder_value:
                        msg = f"Placeholder value '{key}: {placeholder_value}' found in config file {self.config_path}. Please fix this."
                        raise RuntimeError(msg)
            return False

        if placeholders is None:
            return False

        return recursive_check(self._config, placeholders)

    def get(self, *keys, default=None):
        """Retrieve a value from the config dictionary using a sequence of nested keys.

        Example:
            value = config_mgr.get("DeviceType", "WebsiteAccessKey")

        Args:
            keys (*keys): Sequence of keys to traverse the config dictionary.
            default (Optional[variable], optional): Value to return if the key path does not exist.

        Returns:
            value (variable): The value if found, otherwise the default.

        """
        value = self._config
        try:
            for key in keys:
                value = value[key]
        except (KeyError, TypeError):
            return default
        else:
            return value

    def get_logger_settings(self, config_section: str | None = "Files") -> dict:
        """Returns the logger settings from the config file.

        Args:
            config_section (Optional[str], optional): The section in the config file where logger settings are stored.

        Returns:
            settings (dict): A dictionary of logger settings that can be passed to the SCLogger() class initialization.
        """
        logger_settings = {
            "logfile_name": self.get(config_section, "LogfileName"),
            "file_verbosity": self.get(config_section, "LogfileVerbosity", default="summary"),
            "console_verbosity": self.get(config_section, "ConsoleVerbosity", default="summary"),
            "max_lines": self.get(config_section, "LogfileMaxLines", default=10000),
            "timestamp_format": self.get(config_section, "TimestampFormat", default="%Y-%m-%d %H:%M:%S"),
            "log_process_id": self.get(config_section, "LogProcessID", default=False),
            "log_thread_id": self.get(config_section, "LogThreadID", default=False),
        }
        return logger_settings

    def get_email_settings(self, config_section: str | None = "Email") -> dict | None:
        """Returns the email settings from environment variables and/or the config file.

        Environment variables take precedence over config file settings. If email is disabled or not configured correctly, this method will return None.
        Warnings will be logged and included in the email body if the SMTPUsername, SMTPPassword, or SendEmailsTo settings are present in the config file.

        The SMTPSecurity setting (SMTP_SECURITY environment variable) selects how the connection to the SMTP server is secured: "starttls"
        (connect in plain text then upgrade, typically port 587) or "ssl" (implicit TLS, typically port 465). If not set, "ssl" is used when
        the port is 465, otherwise "starttls".

        Args:
            config_section (Optional[str], optional): The section in the config file where email settings are stored.

        Returns:
            settings (dict): A dictionary of email settings or None if email is disabled or not configured correctly.

        Raises:
            RuntimeError: If the SMTP_SECURITY environment variable or the SMTPSecurity config setting is not one of "starttls" or "ssl".
        """
        # fir check to see if we have an EnableEmail setting
        enable_email = os.environ.get("SMTP_ENABLE")
        if enable_email in {"0", "false", "False"}:
            return None

        if enable_email is None:    # Nothing in environment variables, check the config file
            enable_email = self.get(config_section, "EnableEmail", default=True)
            if not enable_email:
                return None

        # Work out the security mode, which defaults from the port number if not specified
        smtp_port = int(os.environ.get("SMTP_PORT") or self.get(config_section, "SMTPPort", default=587))  # pyright: ignore[reportArgumentType]
        default_security = "ssl" if smtp_port == 465 else "starttls"
        smtp_security = str(os.environ.get("SMTP_SECURITY") or self.get(config_section, "SMTPSecurity") or default_security).strip().lower()
        if smtp_security not in {"starttls", "ssl"}:
            msg = f"Invalid SMTP security mode '{smtp_security}'. SMTP_SECURITY / {config_section}.SMTPSecurity must be one of: starttls, ssl."
            raise RuntimeError(msg)

        email_settings = {
            "SMTPServer": os.environ.get("SMTP_SERVER") or self.get(config_section, "SMTPServer"),
            "SMTPPort": smtp_port,
            "SMTPSecurity": smtp_security,
            "SMTPUsername": os.environ.get("SMTP_USERNAME") or self.get(config_section, "SMTPUsername"),
            "SMTPPassword": os.environ.get("SMTP_PASSWORD") or self.get(config_section, "SMTPPassword"),
            "FromEmail": os.environ.get("SMTP_FROM_EMAIL") or self.get(config_section, "FromEmail") or
                         os.environ.get("SMTP_USERNAME") or self.get(config_section, "SMTPUsername"),
            "SendEmailsTo": os.environ.get("SMTP_SEND_TO_EMAIL") or self.get(config_section, "SendEmailsTo"),
            "SubjectPrefix": os.environ.get("SMTP_SUBJECT_PREFIX") or self.get(config_section, "SubjectPrefix"),
            "SecurityWarning": False
        }

        # If the Username, password or SendEmailTo settings are set in the config file, include a security warning
        if self.get(config_section, "SMTPUsername") or self.get(config_section, "SMTPPassword") or self.get(config_section, "SendEmailsTo"):
            email_settings["SecurityWarning"] = True

        # Only return true if all the required email settings have been specified (excluding SubjectPrefix and SecurityWarning)
        required_fields = {k: v for k, v in email_settings.items() if k not in {"SubjectPrefix", "SecurityWarning"}}
        if all(required_fields.values()):
            return email_settings

        return None
