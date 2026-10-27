"""Sending email (the "Email / SMS Gateway" in the architecture).

One function, send_email(), for every feature that emails someone: 2FA login codes (NFR-10),
password reset (SEC-5) and alerts. With SMTP_HOST set it sends through that SMTP server
(Gmail, Mailtrap, a college server ...). Without it, nothing leaves the machine: the email is
written to the backend log and kept in OUTBOX, so development, demos and tests need no mail
account.
"""

import logging
import smtplib
from collections import deque
from dataclasses import dataclass
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger("pms.email")


@dataclass
class SentEmail:
    to: str
    subject: str
    body: str


# Last emails "sent" while SMTP is not set up (newest last). Tests read the code from here.
OUTBOX: deque[SentEmail] = deque(maxlen=50)


def send_email(to: str, subject: str, body: str) -> None:
    s = get_settings()
    if not s.smtp_host:
        OUTBOX.append(SentEmail(to, subject, body))
        log.info("EMAIL (not sent, SMTP_HOST is empty) to=%s subject=%s\n%s", to, subject, body)
        return

    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
        if s.smtp_tls:
            smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)
    log.info("EMAIL sent to=%s subject=%s", to, subject)  # never log the body: it holds codes
