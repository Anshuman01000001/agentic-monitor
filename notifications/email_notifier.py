import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from config.settings import settings

logger = logging.getLogger(__name__)


def send_email(subject: str, html_body: str, to: str = None):
    to = to or settings.ALERT_EMAIL_TO
    if not to:
        logger.warning("No recipient configured for send_email")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = to
    part = MIMEText(html_body, "html")
    msg.attach(part)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
            s.starttls()
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.sendmail(settings.SMTP_USER, [to], msg.as_string())
        logger.info("Email sent to %s", to)
        return True
    except Exception as e:
        logger.exception("Failed to send email: %s", e)
        return False
