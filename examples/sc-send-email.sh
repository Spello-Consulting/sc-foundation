#!/bin/bash
: '=======================================================
Example / manual test for the sc-send-email command.

Sends a short multi-line test email using the SMTP_* environment variables.
Any extra arguments are passed straight through to sc-send-email.

Run it with the SMTP settings injected from 1Password, e.g. using the test-suite template:

    op run --env-file=tests/.env.test.template -- examples/sc-send-email.sh
    op run --env-file=tests/.env.test.template -- examples/sc-send-email.sh --test
    op run --env-file=tests/.env.test.template -- examples/sc-send-email.sh --to someone@example.com

--test connects and logs in to the SMTP server but does not send the email.
Exit status is that of sc-send-email: 0 sent or skipped, 1 send failed, 2 usage error.
=========================================================='

set -uo pipefail

RepoDir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
Mailer="$RepoDir/.venv/bin/sc-send-email"

if [ ! -x "$Mailer" ]; then
  echo "sc-send-email not found at $Mailer — run 'uv sync' in $RepoDir first." >&2
  exit 2
fi

for var in SMTP_SERVER SMTP_USERNAME SMTP_PASSWORD SMTP_SEND_TO_EMAIL; do
  if [ -z "${!var:-}" ]; then
    echo "Warning: $var is not set — sc-send-email will skip sending." >&2
  fi
done

body="$(printf 'This is a test email from %s.\n\nHost: %s\nTime: %s\n' \
  "$(basename "${BASH_SOURCE[0]}")" "$(hostname)" "$(date '+%Y-%m-%d %H:%M:%S')")"

# Pipe the body via stdin (--body -), the recommended way to pass multi-line text from a shell script.
printf '%s' "$body" | "$Mailer" --subject "sc-send-email test" --body - "$@"
status=$?
echo "sc-send-email exited with status $status"
exit $status
