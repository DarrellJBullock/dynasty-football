"""Sending email (password resets). Through SMTP when `SMTP_HOST` is set (any
transactional email service offers SMTP); otherwise each message is written as a file to
`EMAIL_OUTBOX` (the e2e tests read it there), or else just logged (local development)."""

import logging
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

from app.config import get_settings

log = logging.getLogger("app.email")


def send(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    # Plain ASCII text goes as is, so a link isn't wrapped across lines.
    message.set_content(body, cte="7bit" if body.isascii() else None)
    if settings.smtp_host:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            smtp.send_message(message)
    elif settings.email_outbox:
        outbox = Path(settings.email_outbox)
        outbox.mkdir(parents=True, exist_ok=True)
        (outbox / f"{time.time_ns()}.eml").write_bytes(bytes(message))
    else:
        log.info("email to %s (no SMTP configured): %s\n%s", to, subject, body)
