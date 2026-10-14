"""
Spello Consulting Logging Module.

Provides general purpose logging functions.
"""
import datetime as dt
import inspect
import os
import smtplib
import ssl
import sys
import threading
import traceback
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from twilio.base.exceptions import TwilioException
from twilio.rest import Client

from sc_foundation.sc_common import SCCommon
from sc_foundation.sc_date_helper import DateHelper


@dataclass
class NotifiableIssue:
    entity: str
    issue_type: str
    first_reported: dt.datetime
    last_reported: dt.datetime
    send_delay: int
    message: str
    email_sent: bool = False


class SCLogger:
    """A class to handle logging messages with different verbosity levels."""

    def __init__(self, logger_settings: dict, heartbeat_config: dict | None = None):
        """
        Initializes the logger with configuration settings.

        The structure of logger_settings is as follows:

            {
                "logfile_name": Optional[str],  # The name of the log file. If None, no file logging will be done.
                "file_verbosity": Optional[str],  # Verbosity level for file logging
                "console_verbosity": Optional[str],  # Verbosity level for console logging
                "max_lines": Optional[int],  # Maximum number of lines to keep in the log file
                "log_process_id": Optional[bool],  # If True, include the process ID in log messages. Defaults to False.
                "log_thread_id": Optional[bool],  # If True, include the thread ID in log messages. Defaults to False.
            }

        Args:
            logger_settings (dict): A dictionary containing logger settings
            heartbeat_config (Optional[dict]): A dictionary containing the heartbeat monitor configuration.
        """
        # Make a note of the app directory
        self.app_dir = self.client_dir = SCCommon.get_project_root()

        # Setup the path to the fatal error tracking file
        self.fatal_error_file_path = self.app_dir / f"{self.app_dir.name}_fatal_error.txt"

        # Use the register_email_settings method to set up email settings
        self.email_settings = None

        self.verbosity_levels = {
            "none": 0,
            "error": 1,
            "warning": 2,
            "summary": 3,
            "detailed": 4,
            "debug": 5,
            "all": 6,
        }
        # Attributes set in the initialise_logger method
        self.logfile_name = None
        self.logfile_path = None
        self.file_verbosity = "summary"
        self.console_verbosity = "summary"
        self.max_lines = 1000
        self.timestamp_format = "%Y-%m-%d %H:%M:%S"
        self.log_process_id = False
        self.log_thread_id = False
        self.file_logging_enabled = False
        self.notifiable_issues: list[NotifiableIssue] = []

        # Serialize logfile I/O across threads (trim/write must not interleave)
        self._logfile_lock = threading.RLock()
        self._fatal_error_file_lock = threading.RLock()

        # Set up the heartbeat monitor attributes
        self.heartbeat_config = {}
        self.heartbeat_last_post = None
        if heartbeat_config is not None:
            self.register_heartbeat_monitor(heartbeat_config)

        self.initialise_settings(logger_settings)

    def get_logfile_path(self) -> str | None:
        """Returns the path to the current log file, if it exists."""
        return str(self.logfile_path) if self.logfile_path is not None else None

    def initialise_settings(self, logger_settings: dict):
        """
        Set / reset the logger configuration settings. See the __init__() method for the structure of logger_settings.

        Args:
            logger_settings (Optional[dict]): A dictionary containing logger settings.
        """
        self.logfile_name = logger_settings.get("logfile_name")
        self.file_verbosity = logger_settings.get("file_verbosity", "summary")
        self.console_verbosity = logger_settings.get("console_verbosity", "summary")
        self.max_lines = logger_settings.get("max_lines", 1000)
        self.timestamp_format = logger_settings.get("timestamp_format", "%Y-%m-%d %H:%M:%S")
        self.log_process_id = logger_settings.get("log_process_id", False)
        self.log_thread_id = logger_settings.get("log_thread_id", False)

        # See if logfile writing is required
        self.file_logging_enabled = self.logfile_name is not None

        if self.file_logging_enabled and self.logfile_name is not None:
            self.logfile_path = SCCommon.select_file_location(self.logfile_name, create_folder=True)

            # Truncate the log file if it exists
            self._initialise_monitoring_logfile()

    def trim_logfile(self) -> None:
        """Trims the log file to the maximum number of lines specified."""
        if not self.file_logging_enabled:
            return

        assert self.logfile_path is not None, "Log file path must be set before trimming the log file."

        with self._logfile_lock:
            if self.logfile_path.exists() and self.max_lines is not None and self.max_lines > 0:
                with self.logfile_path.open(encoding="utf-8") as file:
                    lines = file.readlines()

                if len(lines) > self.max_lines:
                    # Keep the last max_lines rows
                    keep_lines = lines[-self.max_lines:] if len(lines) > self.max_lines else lines

                    # Overwrite the file with only the last 1000 lines
                    with self.logfile_path.open("w", encoding="utf-8") as file2:
                        file2.writelines(keep_lines)

    def log_message(self, message: str, verbosity: str = "summary") -> None:
        """Writes a log message to the console and/or a file based on verbosity settings.

        Args:
            message (str): The message to log.
            verbosity (str): The verbosity level for the message. Must be one of "none", "error", "warning", "summary", "detailed", "debug", or "all".

        Raises:
            ValueError: If an invalid verbosity level is provided.

        """
        if verbosity not in self.verbosity_levels:
            exception_msg = f"log_message(): Invalid verbosity passed, must be one of {list(self.verbosity_levels.keys())}."
            raise ValueError(exception_msg)

        file_verbosity = self.file_verbosity if self.file_verbosity is not None else "none"
        console_verbosity = self.console_verbosity if self.console_verbosity is not None else "none"
        logfile_level = self.verbosity_levels.get(file_verbosity, 0)
        console_level = self.verbosity_levels.get(console_verbosity, 0)
        message_level = self.verbosity_levels.get(verbosity, 0)

        process_str = ""
        if self.log_process_id and self.log_thread_id:
            process_str = f"[Proc {SCCommon.get_process_id()}, Thread {threading.current_thread().name}] "
        elif self.log_process_id:
            process_str = f"[Proc {SCCommon.get_process_id()}] "
        elif self.log_thread_id:
            process_str = f"[Thread {threading.current_thread().name}] "

        # Deal with console message first
        if console_level >= message_level and console_level > 0:
            if verbosity == "error":
                print(f"ERROR: {process_str}{message}", file=sys.stderr)
            elif verbosity == "warning":
                print(f"WARNING: {process_str}{message}")
            else:
                print(f"{process_str}{message}")

        # Now write to the log file if needed
        if self.file_logging_enabled:
            assert self.logfile_path is not None, "Log file path must be set before trimming the log file."
            error_str = " ERROR" if verbosity == "error" else " WARNING" if verbosity == "warning" else ""
            if logfile_level >= message_level and logfile_level > 0:
                with self._logfile_lock, self.logfile_path.open("a", encoding="utf-8") as file:
                    if not message:
                        file.write("\n")
                    else:
                        # Use the local timezone for the log timestamp
                        file.write(
                            f"{DateHelper.now().strftime(self.timestamp_format)}{error_str}: {process_str}{message}\n"
                        )

    def register_email_settings(self, email_settings: dict | None) -> None:
        """
        Registers email settings for sending emails.

        Use the SCConfigManager.get_email_settings() method to get a dictionary containing the email settings. Otherwise, you can pass a
        dictionary directly to this method with these keys:

            SMTPServer: str, the SMTP server address
            SMTPPort: int, the SMTP server port (optional, defaults to 587)
            SMTPSecurity: str, how the connection is secured: "starttls" or "ssl" (implicit TLS). Optional, defaults to "ssl" if
                SMTPPort is 465, otherwise "starttls".
            SMTPUsername: str, the username for the SMTP server
            SMTPPassword: str, the password for the SMTP server (an app password or API token, if your provider requires one)
            FromEmail: str, the emal address that the email comes from. If none, the SMTPUsername will be used.
            SendEmailsTo: str, the email address to send emails to
            SubjectPrefix: str, a prefix for email subjects (optional, default to None)

        Args:
            email_settings (Optional[dict], optional): A dictionary containing email settings. If empty or None, no email settings will be registered.

        Raises:
            TypeError: If email_settings is not a dictionary.
            ValueError: If any required keys are missing from the email_settings dictionary.

        """
        if email_settings == {} or email_settings is None:
            return  # No email settings provided, so skip registration

        if not isinstance(email_settings, dict):
            msg = "register_email_settings(): Email settings must be a dictionary."
            raise TypeError(msg)

        # Check if all required keys are present
        required_keys = ["SendEmailsTo", "SMTPServer", "SMTPUsername", "SMTPPassword"]
        for key in required_keys:
            if key not in email_settings:
                msg = f"register_email_settings(): Missing required email setting: {key}"
                raise ValueError(msg)

        # Store the email settings in the config object
        self.email_settings = email_settings

    def send_email(self, subject: str, body: str | Path, test_mode: bool = False, send_to_email: str | None = None) -> bool:  # noqa: PLR0911, PLR0912, PLR0914, PLR0915
        """
        Sends an email using the SMTP server previously specified in register_email_settings().

        Args:
            subject (str): The subject of the email.
            body (str): The body of the email. This argument can be one of 4 things:

                1. A string containing the HTML body of the email
                2. A string or Path containing the path to an HTML file to read the body from
                3. A string containing the text body of the email
                4. A string or Path containing the path to an text file to read the body from

            test_mode (bool, optional): If True, the email will not be sent, but a message will be logged indicating that the email would have been sent. Defaults to False.
            send_to_email (str | None, optional): The email address to send the email to. If None, the email will be sent to the default recipient specified in the email settings. Defaults to None.

        Returns:
            result (bool): True if the email was sent successfully, False otherwise.
        """
        if self.email_settings is None:
            return False  # No email settings registered, so skip sending the email

        # First confirm that the body argument was passed as a string
        if not isinstance(body, str) and not isinstance(body, Path):
            self.log_fatal_error("body argument must be a string containing the body content or a file path.", report_stack=False, calling_function="send_email")
            return False

        # See if we need to include a security warning in the email body and log files
        security_warning = self.email_settings.get("SecurityWarning", False)
        if security_warning:
            warning_message = (
                "WARNING: The configuration file for this application includes one of the following deprecated settings:\n"
                "Email.SMTPUsername, Email.SMTPPassword, Email.FromEmail, or Email.SendEmailsTo. These settings may contain sensitive information.\n"
                "Consider moving these settings to environment variables for improved security. See the documentation for more information."
            )
            self.log_message(warning_message, "warning")
            body = f"{body}\n\n{warning_message}"

        # See if the body string is something that looks like a file path
        try:
            payload_path = SCCommon.select_file_location(str(body))
            assert isinstance(payload_path, Path), "select_file_location should return a Path object"
            payload_path.exists()
        except (AssertionError, OSError):
            # Nothing to do here
            payload_path = None

        payload = body  # Default to the body as text content
        payload_type = "plain"

        # Default to treating the body a file path and see if we can resolve it
        if payload_path is not None:
            if payload_path.exists():
                # If the body is a file path, read the content
                with payload_path.open("r", encoding="utf-8") as file:
                    payload = file.read()

                # Determine the payload type based on the file extension
                if payload_path.suffix.lower() == ".html":
                    payload_type = "html"
                elif payload_path.suffix.lower() == ".txt":
                    payload_type = "plain"
                else:
                    self.log_fatal_error(f"Unsupported file type for email body: {payload_path.suffix}", report_stack=False, calling_function="send_email")
                    return False
            else:
                payload_path = None

        if payload_path is None:
            # If fall through to here, then the body was not a file path or the file did not exist
            # Assume that the body is a string containing the content
            payload = str(body)  # Default to the body as text content
            if payload.startswith(("<html", "<!DOCTYPE html")):
                payload_type = "html"
            else:
                payload_type = "plain"

        # Load the SMTP server configuration
        smtp_server = self.email_settings.get("SMTPServer")
        smtp_port = self.email_settings.get("SMTPPort", 587)
        smtp_security = str(self.email_settings.get("SMTPSecurity") or ("ssl" if smtp_port == 465 else "starttls")).strip().lower()
        smtp_username = self.email_settings.get("SMTPUsername")
        smtp_password = self.email_settings.get("SMTPPassword")
        send_from = self.email_settings.get("FromEmail")
        send_to = send_to_email if send_to_email is not None else self.email_settings.get("SendEmailsTo")

        email_settings_complete = all((smtp_username, send_from, send_to, smtp_server, smtp_port, smtp_password))
        if not email_settings_complete:
            self.log_fatal_error("send_email(): Email settings are incomplete. 'SMTPUsername', 'FromEmail', 'SendEmailsTo', 'SMTPServer' and 'SMTPPassword' must be provided.", report_stack=False, calling_function="send_email")
            return False
        assert all(value is not None for value in (smtp_username, send_from, send_to, smtp_server, smtp_port, smtp_password))
        assert type(smtp_server) is str
        assert type(smtp_port) is int
        assert type(smtp_username) is str
        assert type(smtp_password) is str
        assert type(send_from) is str
        assert type(send_to) is str

        if smtp_security not in {"starttls", "ssl"}:
            self.log_message(f"send_email(): Invalid SMTPSecurity setting '{smtp_security}'. Must be one of: starttls, ssl.", "error")
            return False
        conn_desc = f"{smtp_server}:{smtp_port}, security={smtp_security}"

        try:
            # Create the email
            msg = MIMEMultipart()
            msg["From"] = send_from
            msg["To"] = send_to
            if self.email_settings.get("SubjectPrefix", None) is not None:
                msg["Subject"] = self.email_settings.get("SubjectPrefix", "") + subject
            else:
                msg["Subject"] = subject

            # Attach the payload as either plain text or HTML
            part = MIMEText(payload, payload_type)  # type: ignore[arg-type]
            msg.attach(part)

            # Connect to the SMTP server, verifying its certificate and hostname.
            context = ssl.create_default_context()
            if smtp_security == "ssl":
                # Implicit TLS: the handshake happens on connect, so starttls() must not be called
                smtp_connection: smtplib.SMTP = smtplib.SMTP_SSL(host=smtp_server, port=smtp_port, timeout=10, context=context)
            else:
                smtp_connection = smtplib.SMTP(host=smtp_server, port=smtp_port, timeout=10)

            with smtp_connection as server:
                if smtp_security != "ssl":
                    server.starttls(context=context)  # Upgrade the connection to secure
                server.login(smtp_username, smtp_password)  # Log in using the SMTP credentials
                if test_mode:
                    self.log_message(f"Test mode: Email with subject '{msg['Subject']}' would be sent to {send_to}.", "summary")
                else:
                    server.sendmail(send_from, send_to, msg.as_string())  # Send the email

        except TimeoutError as e:
            self.log_message(f"send_email(): Timeout sending email ({conn_desc}): {e}", "error")
            return False
        except smtplib.SMTPAuthenticationError as e:
            self.log_message(f"send_email(): Authentication failed ({conn_desc}): {e}", "error")
            return False
        except smtplib.SMTPRecipientsRefused as e:
            self.log_message(f"send_email(): Recipients refused: {e}", "error")
            return False
        except smtplib.SMTPSenderRefused as e:
            self.log_message(f"send_email(): Sender refused: {e}", "error")
            return False
        except (smtplib.SMTPException, ssl.SSLError) as e:
            self.log_message(f"send_email(): SMTP/SSL error ({conn_desc}): {e}", "error")
            return False
        except (OSError, ConnectionRefusedError, smtplib.SMTPServerDisconnected) as e:
            self.log_message(f"send_email(): Network error sending email ({conn_desc}): {e}", "error")
            return False
        except Exception as e:  # noqa: BLE001
            self.log_message(f"send_email(): Unexpected error: {e}", "error")
            return False
        else:
            return True  # Email sent successfully

    def log_fatal_error(self, message: str, report_stack: bool = False, calling_function: str | None = None, exit_app: bool = True) -> None:
        """
        Log a fatal error, send an email if configured to so and then exit the program.

        Args:
            message (str): The error message to log.
            report_stack (Optional[bool], optional): If True, include the stack trace in the log message.
            calling_function (Optional[str], optional): The name of the function that called this method, if known. If None, the calling function will be determined automatically.
            exit_app (Optional[bool], optional): If True, the program will be exited after logging the fatal error. Defaults to True.

        Raises:
            SystemExit: Exits the program with a status code of 1 after logging the fatal error.

        """  # noqa: DOC502
        function_name = None
        if calling_function is None:
            stack = inspect.stack()
            # Get the frame of the calling function
            calling_frame = stack[1]
            # Get the function name
            function_name = calling_frame.function
            if function_name == "<module>":
                function_name = "main"
            # Get the class name (if it exists)
            class_name = None
            if "self" in calling_frame.frame.f_locals:
                class_name = calling_frame.frame.f_locals["self"].__class__.__name__
                full_reference = f"{class_name}.{function_name}()"
            else:
                full_reference = function_name + "()"
        else:
            full_reference = calling_function + "()"

        if report_stack:
            stack_trace = traceback.format_exc()
            message += f"\n\nStack trace:\n{stack_trace}"

        self.log_message(f"Function {full_reference}: FATAL ERROR: {message}", "error")

        # Try to send an email if configured to do so and we haven't already sent one for a fatal error
        # Don't send concurrent error emails
        if function_name != "send_email" and not self.get_fatal_error():
            self.send_email(
                f"{self.app_dir.name} terminated with a fatal error",
                f"{message} \nAdditional emails will not be sent for concurrent errors.",
            )

        # record the error in in a file so that we keep track of this next time round
        self.set_fatal_error(message)

        # Exit the program
        if exit_app:
            sys.exit(1)

    def get_fatal_error(self) -> bool:
        """Returns True if a fatal error was previously reported, false otherwise."""
        return Path(self.fatal_error_file_path).exists()

    def clear_fatal_error(self) -> bool:
        """
        Clear a previously logged fatal error.

        Returns:
            result (bool): True if the file was deleted, False if it did not exist.
        """
        with self._fatal_error_file_lock:
            if Path(self.fatal_error_file_path).exists():
                Path(self.fatal_error_file_path).unlink()
                return True
        return False

    def set_fatal_error(self, message: str) -> None:
        """
        Create a fatal error tracking file and write the message to it.

        Args:
            message (str): The error message to write to the fatal error file.
        """
        with self._fatal_error_file_lock:
            Path(self.fatal_error_file_path).write_text(message, encoding="utf-8")

    def report_notifiable_issue(self, entity: str, issue_type: str, send_delay: int, message: str) -> bool:
        """
        Log a notifiable issue and send an email if configured to do so.

        When a new combination of entity and issue_type is reported, it will be noted including the current timestamp.
        If one or more issues of the same type are reported for the same entity at least send_delay seconds after the last notification,
        an email will be sent including the first time this issue was reported. Subsequent issues of the same type for the same
        entity will be ignored until the issue is cleared.

        Args:
            entity (str): The entity reporting the issue (e.g., "Device 123", "Module", etc.)
            issue_type (str): A brief description of the issue (e.g. "Offline").
            send_delay (int): The delay in seconds before sending the email
            message (str): The issue message to log and email.

        Returns:
            result (bool): True if the email was sent, False otherwise.
        """
        # Search self.notifiable_issues to see if we have a match by entity and issue_type
        now = DateHelper.now()
        issue_found = False
        for issue in self.notifiable_issues:
            if issue.entity == entity and issue.issue_type == issue_type:
                issue_found = True
                # We have a match - see if we need to send an email
                if (now - issue.first_reported).total_seconds() >= issue.send_delay:
                    # Update the last reported time
                    issue.last_reported = now

                    # Send the email if not already sent
                    if not issue.email_sent:
                        email_subject = f"{self.app_dir.name} - {entity} {issue_type} issue"
                        email_body = f"{entity}: {message}\n\nFirst reported: {issue.first_reported.strftime('%Y-%m-%d %H:%M')}"
                        if self.send_email(email_subject, email_body):
                            issue.email_sent = True
                            return True

                break

        if not issue_found:
            # No existing issue found, create a new one
            new_issue = NotifiableIssue(
                entity=entity,
                issue_type=issue_type,
                first_reported=now,
                last_reported=now,
                send_delay=send_delay,
                message=message,
            )
            self.notifiable_issues.append(new_issue)

        return False

    def clear_notifiable_issue(self, entity: str, issue_type: str) -> bool:
        """
        Clear a notifiable issue.

        If an email was previously sent for this issue, this function will send a "cleared" notification email.

        Args:
            entity (str): The entity reporting the issue (e.g., "Device 123", "Module", etc.)
            issue_type (str): A brief description of the issue (e.g. "Offline").

        Returns:
            result (bool): True if the issue was found and cleared, False otherwise.
        """
        # Search self.notifiable_issues to see if we have a match by entity and issue_type
        for issue in self.notifiable_issues:
            if issue.entity == entity and issue.issue_type == issue_type:
                # Send a cleared email if one was previously sent
                if issue.email_sent:
                    email_subject = f"{self.app_dir.name} - {entity} {issue_type} issue resolved"
                    email_body = f"{entity}: The {issue_type} issue reported on {issue.first_reported.strftime('%Y-%m-%d %H:%M')} has been resolved."
                    self.send_email(email_subject, email_body)

                self.notifiable_issues.remove(issue)
                return True

        return False

    def register_heartbeat_monitor(self, config: dict):
        """
        Register the configuration for the heartbeat monitor.

        The config dictionary should have the following structure:

            {
                "Enable": bool,  # Whether to enable the heartbeat monitor
                "WebsiteURL": str,  # The URL to ping for the heartbeat
                "HeartbeatTimeout": int,  # The timeout in seconds for the heartbeat ping (optional, defaults to 10)
                "Frequency": int,  # The minimum frequency in seconds to ping the heartbeat URL (optional, defaults to 30)
            }

        Args:
            config (dict): A dictionary containing the heartbeat monitor configuration.

        Raises:
            TypeError: If any of the required keys are missing from the config dictionary or if any of the values are of the wrong type or invalid.
        """
        # Do some validation of the config dictionary
        is_enabled = config.get("Enable", False)
        heartbeat_url = config.get("WebsiteURL")
        timeout = config.get("HeartbeatTimeout", 10)
        frequency = config.get("Frequency", 30)

        if not isinstance(is_enabled, bool):
            msg = "Heartbeat config 'Enable' key must be a boolean."
            raise TypeError(msg)
        if not is_enabled:
            return  # Heartbeat monitor is disabled, so nothing to do
        if not isinstance(heartbeat_url, str):
            msg = "Heartbeat config 'WebsiteURL' key must be a string."
            raise TypeError(msg)
        if not isinstance(timeout, int) or timeout <= 0:
            msg = "Heartbeat config 'HeartbeatTimeout' key must be a positive integer."
            raise TypeError(msg)
        if not isinstance(frequency, int) or frequency <= 0:
            msg = "Heartbeat config 'Frequency' key must be a positive integer."
            raise TypeError(msg)

        self.heartbeat_config = config
        self.heartbeat_last_post = None

    def ping_heartbeat(self, is_fail: bool | None = None) -> bool:
        """Ping the heartbeat URL if it's time to do so or is_fail is True.

        Args:
            is_fail (bool, optional): If True, the heartbeat will be considered a failure.

        Returns:
            bool: True if the heartbeat URL is reachable or there's nothing to do, False otherwise.
        """
        # Screen the barrier conditions for whether we need to ping the heartbeat URL
        if not self.heartbeat_config:
            return True  # No heartbeat config, so nothing to do

        assert isinstance(self.heartbeat_config, dict), "Heartbeat config must be a dictionary"
        is_enabled = self.heartbeat_config.get("Enable", False)
        heartbeat_url = self.heartbeat_config.get("WebsiteURL")
        timeout = self.heartbeat_config.get("HeartbeatTimeout", 10)
        frequency = self.heartbeat_config.get("Frequency", 30)

        if not is_enabled or heartbeat_url is None:
            return True
        assert isinstance(heartbeat_url, str), "Heartbeat URL must be a string"

        if self.heartbeat_last_post is not None:
            time_since_last_post = (DateHelper.now() - self.heartbeat_last_post).total_seconds()
            if time_since_last_post < frequency:  # pyright: ignore[reportOperatorIssue]
                return True

        if is_fail:
            heartbeat_url += "/fail"

        try:
            response = requests.get(heartbeat_url, timeout=timeout)  # type: ignore[call-arg]
        except requests.exceptions.Timeout as e:
            self.log_message(f"Timeout making Heartbeat ping: {e}", "error")
            return False
        except requests.RequestException as e:
            self.log_message(f"Heartbeat ping failed: {e}", "error")
            return False
        else:
            self.heartbeat_last_post = DateHelper.now()
            if response.status_code == 200:
                # self.log_message(f"Heartbeat ping posted to {heartbeat_url}", "debug")
                return True
            self.log_message(f"Heartbeat ping failed with status code: {response.status_code}", "error")
            return False

    def sms_configured(self) -> bool:
        """True when Twilio credentials and a sender ID are present and consistent.

        Returns:
            bool: True if Twilio credentials and a sender ID are present and consistent, False otherwise.
        """
        client, _ = self._build_twillo_client()
        return client is not None and bool(os.environ.get("TWILIO_FROM_NUMBER"))

    def send_sms(self, body: str, to_numbers: list[str] | None = None) -> bool:
        """Send a SMS to one or more numbers using Twilio.

        Two authentication styles are supported:

        Account SID + Auth Token (simplest):
            TWILIO_ACCOUNT_SID   = AC...           (your account SID)
            TWILIO_AUTH_TOKEN    = <account auth token>

        API Key (recommended by Twilio; revocable without changing the account):
            TWILIO_ACCOUNT_SID   = AC...           (still your account SID)
            TWILIO_API_KEY_SID   = SK...           (the API key SID)
            TWILIO_API_KEY_SECRET= <api key secret>

        In both cases the account SID must be the ``AC...`` value — an API key (``SK...``)
        is not an account SID and cannot be used in its place.

        In both cases, the sender ID must be set in the environment variable TWILIO_FROM_NUMBER.
        This can be either an E.164 number (e.g., +15005550006) or an alphanumeric
        sender ID (<= 11 chars, e.g., "SpelloWater").

        If credentials are missing, sending is skipped with a warning (email alerts
        still function). This keeps the app runnable before Twilio is configured.

        Args:
            body (str): The message body to send.
            to_numbers (list[str] | None): A list of phone numbers in E.164 format to send the SMS to. If None, the list will be extracted from the TWILIO_SEND_SMS_TO environment variable (comma-separated). If no numbers are provided, the function will return False.

        Returns:
            bool: True if at least one message was accepted by Twilio. Returns False
            (and logs a warning) if credentials are missing or every send fails.
        """
        if not to_numbers:
            to_numbers = os.environ.get("TWILIO_SEND_SMS_TO", "").split(",")
            if not to_numbers:
                return False

        from_id = os.environ.get("TWILIO_FROM_NUMBER")
        if not from_id:
            self.log_message("SMS not sent: TWILIO_FROM_NUMBER not configured.", "error")
            return False

        # Reject if the from_id is not a valid E.164 number or alphanumeric sender ID or more than 11 characters
        if not (from_id.startswith("+") and from_id[1:].isdigit()) and not (from_id.isalnum() and len(from_id) <= 11):
            self.log_message(
                f"SMS not sent: TWILIO_FROM_NUMBER '{from_id}' is not a valid E.164 number or alphanumeric sender ID (<= 11 chars).", "error"
            )
            return False

        client, error = self._build_twillo_client()
        if client is None:
            self.log_message(error, "error")  # pyright: ignore[reportArgumentType]
            return False

        any_sent = False
        for number in to_numbers:
            try:
                client.messages.create(to=number, from_=from_id, body=body)
                any_sent = True
                self.log_message(f"SMS alert sent to {number}.", "summary")
            except TwilioException as exc:
                self.log_message(f"Failed to send SMS to {number}: {exc}", "error")
        return any_sent

    # =============== PRIVATE METHODS ============================================================

    def _initialise_monitoring_logfile(self) -> None:
        """Initialise the monitoring log file. If it exists, truncate it to the max number of lines."""
        if not self.file_logging_enabled:
            return

        self.trim_logfile()

    def _build_twillo_client(self) -> tuple[Client | None, str | None]:  # noqa: PLR6301
        """Construct a Twilio client from env vars, or return (None, reason).

        Returns:
            tuple: A tuple containing the Twilio client (or None if not configured) and an error message (or None if the client was created successfully).
        """
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        api_key_sid = os.environ.get("TWILIO_API_KEY_SID")
        api_key_secret = os.environ.get("TWILIO_API_KEY_SECRET")

        # API-key auth: SK sid + secret authenticate, but the AC account SID is still
        # required for the resource path (/Accounts/{AccountSid}/Messages.json).
        if api_key_sid and api_key_secret:
            if not account_sid:
                return None, (
                    "SMS not sent: TWILIO_API_KEY_SID/SECRET are set but "
                    "TWILIO_ACCOUNT_SID (the AC... account SID) is missing — "
                    "API-key auth still needs the account SID."
                )
            return Client(api_key_sid, api_key_secret, account_sid), None

        if account_sid and auth_token:
            # Catch the common mistake of putting an API key (SK...) in the SID slot.
            if account_sid.startswith("SK"):
                return None, (
                    "SMS not sent: TWILIO_ACCOUNT_SID looks like an API key (SK...). "
                    "Set it to your account SID (AC...) and put the API key in "
                    "TWILIO_API_KEY_SID / TWILIO_API_KEY_SECRET."
                )
            return Client(account_sid, auth_token), None

        return None, "SMS not sent: Twilio credentials not configured in environment."
