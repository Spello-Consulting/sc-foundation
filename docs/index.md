# Spello Consulting Foundation Library

## Available Classes

The Spello Consulting Foundation library provides some foundational classes for:

- [SCCommon](reference/common.md): Some common functions used by other classes.
- [SCConfigManager](reference/configmanager.md): Reading from and validating YAML style config files
- [SCLogging](reference/logging.md): Logging messages to the console and a log file and sending email in plain text or HTML format
- [CSVReader](reference/csvreader.md): Reading data from and and writing to CSV files
- [DateHelper](reference/datehelper.md): Date and datetime helper functions
- [JSONEncoder](reference/jsonencoder.md): Helps convert dicts and lists to json and back, preserving datetime and enum data types.

## Installing the library

The library is available from PyPi, so to add it to your Python project use pip:

    pip install sc-foundation-services

Or better yet, use UV:

    uv add sc-foundation-services

## Configuration File 
The library uses a YAML file for configuration. An example config file (*config.yaml.example*) is [available on Github](https://github.com/Spello-Consulting/sc-foundation). Copy this to *[your_app_name].yaml* before using the library. 

Here's the example file - the library expects to find the Files and Email sections in the file:

```yaml
# This is an example configuration file for the Spello Consulting foundation library
AmberAPI:
  APIKey: This is not the real API key
  BaseUrl: https://api.amber.com.au/v1
  Timeout: 15


Files:
  # Name of the log file. Set to blak of None to disable logging
  LogfileName: logfile.log
  # How many lines of log file to keep. Set to 0 to disable log file truncation. Defaults to 10,000 if not specified 
  LogfileMaxLines: 500
  # How much information do we write to the log file. One of: none; error; warning; summary; detailed; debug, all. Defaults to detailed if not specified.
  LogfileVerbosity: all
  # How much information do we write to the console. One of: error; warning; summary; detailed; debug, all. Defaults to summary if not specified.
  ConsoleVerbosity: detailed


# Enter your settings here if you want to be emailed when there's a critical error 
# We recommend using environment variables for sensitive information like SMTP credentials, rather than storing them in the config file:
Email:
  EnableEmail: True
  SMTPServer: smtp.gmail.com
  SMTPPort: 587
  # Optional. One of: starttls; ssl. If not set, ssl is used for port 465, otherwise starttls.
  SMTPSecurity: starttls
  SubjectPrefix: 
```

### Configuration Parameters

#### Section: Files

| Parameter | Description | 
|:--|:--|
| LogfileName | The name of the log file, can be a relative or absolute path. | 
| LogfileMaxLines | Maximum number of lines to keep in the log file. If zero, file will never be truncated. | 
| LogfileVerbosity | The level of detail captured in the log file. One of: none; error; warning; summary; detailed; debug; all | 
| ConsoleVerbosity | Controls the amount of information written to the console. One of: error; warning; summary; detailed; debug; all. Errors are written to stderr all other messages are written to stdout | 

#### Section: Email

| Config Parameter | Environment Variable Equivilent | Description | 
|:--|:--|:--|
| EnableEmail | SMTP_ENABLE | Set to *True* if you want to allow the app to send emails. If True, the remaining settings in this section must be configured correctly. | 
| SMTPServer | SMTP_SERVER | The SMTP host name that supports TLS encryption. If using a Google account, set to smtp.gmail.com |
| SMTPPort | SMTP_PORT | The port number to use to connect to the SMTP server. Defaults to 587. If using a Google account, set to 587 (STARTTLS) or 465 (implicit TLS) |
| SMTPSecurity | SMTP_SECURITY | Optional. How the connection to the SMTP server is secured. One of: *starttls* (connect then upgrade to TLS, typically port 587 or 2525) or *ssl* (implicit TLS, typically port 465). If not set, *ssl* is used when SMTPPort is 465, otherwise *starttls*. The server's TLS certificate and hostname are always verified, so a server with a self-signed, expired or mismatched certificate will be refused. |
| SMTPUsername | SMTP_USERNAME | Your username used to login to the SMTP server. If using a Google account, set to your Google email address. Alternatively, set the SMTP_USERNAME environment variable.  |
| SMTPPassword | SMTP_PASSWORD | The password used to login to the SMTP server. If using a Google account, create an app password for the app at https://myaccount.google.com/apppasswords. Alternatively, set the SMTP_PASSWORD environment variable.  |
| SendEmailsTo | SMTP_SEND_TO_EMAIL | Email address to send emails to |
| SubjectPrefix | SMTP_SUBJECT_PREFIX | Optional. If set, the app will add this text to the start of any email subject line for emails it sends. |

## Example code

Here's an example module that shows how to use the library classes. Use the **API Reference** navigation to view the API methods for each class. The code example and the companion config and Excel files is available in the examples/ folder in the Github repo.

```python

  {%
    include "../examples/example.py"
  %}
```