"""Minimal outgoing email over SMTP (stdlib only).

Works with any SMTP provider, including free ones (a Gmail account with an app password,
Brevo's free tier, ...). Without MAIL_SERVER the message is written to the log, which is
enough for local development.
"""
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage

from flask import current_app

from app.utility import config

log = logging.getLogger(__name__)

# Messages "sent" while app.config["TESTING"] is on end up here instead.
outbox = []


def _deliver(msg):
    try:
        context = ssl.create_default_context()
        if config.MAIL_USE_SSL:
            server = smtplib.SMTP_SSL(config.MAIL_SERVER, config.MAIL_PORT, context=context, timeout=15)
        else:
            server = smtplib.SMTP(config.MAIL_SERVER, config.MAIL_PORT, timeout=15)
        with server:
            if config.MAIL_USE_TLS and not config.MAIL_USE_SSL:
                server.starttls(context=context)
            if config.MAIL_USERNAME:
                server.login(config.MAIL_USERNAME, config.MAIL_PASSWORD)
            server.send_message(msg)
    except Exception:  # never crash a request because the mail server is down
        log.exception("Could not send email to %s", msg["To"])


def send_email(to, subject, body):
    msg = EmailMessage()
    msg["From"] = config.MAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    if current_app.config.get("TESTING"):
        outbox.append(msg)
        return
    if not config.MAIL_SERVER:
        log.warning("MAIL_SERVER is not set, so this email was not sent:\nTo: %s\nSubject: %s\n\n%s", to, subject, body)
        return
    # Send in the background: the response time must not reveal whether the address exists.
    threading.Thread(target=_deliver, args=(msg,), daemon=True).start()
