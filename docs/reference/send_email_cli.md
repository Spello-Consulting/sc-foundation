# sc-send-email command

Installing the library adds an `sc-send-email` command to the project's virtual environment
(`.venv/bin/sc-send-email`). It sends one email using the same settings rules as
`SCConfigManager.get_email_settings()`, so shell scripts — for example a workflow script that emails you
when a step fails — don't need their own inline Python.

```
sc-send-email --subject TEXT (--body TEXT | --body-file PATH | --body -)
              [--config PATH] [--section NAME] [--to EMAIL] [--test]
```

| Argument | Description |
|:--|:--|
| `--subject` | Required. The email subject. `SubjectPrefix` / `SMTP_SUBJECT_PREFIX`, if set, is added to the start. |
| `--body TEXT` | The email body. Text starting with `<html` or `<!DOCTYPE html` is sent as HTML, otherwise as plain text. |
| `--body -` | Read the body from stdin. The easiest way to pass multi-line text from a shell script. |
| `--body-file PATH` | Read the body from a file. |
| `--config PATH` | Optional YAML config file to read the email section from. Defaults to `$APP_CONFIG`. |
| `--section NAME` | Config section holding the email settings. Defaults to `Email`. |
| `--to EMAIL` | Send to this address instead of `SMTP_SEND_TO_EMAIL` / `SendEmailsTo`. |
| `--test` | Connect and log in to the SMTP server, but don't send the email. |

## Settings

Settings come from the `SMTP_*` environment variables listed under
[Section: Email](../index.md#section-email), falling back to the config file's email section. Environment
variables always win. With no config file, every setting comes from the environment.

The config file is read directly, not validated against your app's schema, so a config that your app rejects
can't stop an alert email from being sent. If the file is missing or unreadable, `sc-send-email` prints a
warning and carries on using the environment variables only.

## Exit status

| Status | Meaning |
|:--|:--|
| 0 | Email sent, or skipped because email is disabled (`SMTP_ENABLE=false` / `EnableEmail: False`) or not fully configured. The reason for a skip is printed to stderr. |
| 1 | Sending was attempted and failed (connection, TLS or authentication error). |
| 2 | Usage error: bad arguments, an unreadable `--body-file`, or an invalid `SMTP_SECURITY`. |

## Using it from a shell script

```bash
send_email() {
  local mailer="$ROOT_DIR/.venv/bin/sc-send-email"
  [ -x "$mailer" ] || { echo "sc-send-email not available, skipping: $1" >&2; return 0; }
  printf '%s' "$2" | "$mailer" --subject "$1" --body - || true
}

send_email "Workflow Failed" "$(printf 'Step 3 failed.\nSee log: %s' "$LOG_FILE")"
```

The `|| true` stops a failed email from tripping `set -e` or an `ERR` trap. `examples/sc-send-email.sh` in the
repo is a runnable version you can use to test your SMTP settings:

```bash
op run --env-file=tests/.env.test.template -- examples/sc-send-email.sh --test
```

## Python API

The command uses `SCConfigManager.build_email_settings()`, which you can also call directly to get email
settings without a config file:

```python
settings = SCConfigManager.build_email_settings()                            # environment variables only
settings = SCConfigManager.build_email_settings({"SubjectPrefix": "[App] "}) # env vars, falling back to this dict
```

::: sc_foundation.cli_send_email.main
