import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(subject: str, body: str, attachment_file_name: str | None = None):
    mail_server = os.getenv("MAIL_SERVER")
    mail_port = os.getenv("MAIL_PORT")
    mail_sender = os.getenv("MAIL_SENDER")
    mail_password = os.getenv("MAIL_PASSWORD")
    mail_receivers = os.getenv("MAIL_RECEIVERS")

    assert mail_server is not None, "Mail server is not configured."
    assert mail_port is not None, "Mail port is not configured."
    assert mail_sender is not None, "Mail sender is not configured."
    assert mail_password is not None, "Mail password is not configured."
    assert mail_receivers is not None, "Mail receivers are not configured."

    message = MIMEMultipart()
    message["From"] = mail_sender
    message["To"] = mail_receivers
    message["Subject"] = subject

    message.attach(MIMEText(body, "plain"))

    if attachment_file_name is not None:
        with open(attachment_file_name, "rb") as attachment:
            part = MIMEApplication(attachment.read(), Name=attachment_file_name)
            part["Content-Disposition"] = (
                f'attachment; filename="{attachment_file_name}"'
            )
            message.attach(part)

    with smtplib.SMTP_SSL(mail_server, int(mail_port)) as smtp:
        smtp.login(mail_sender, mail_password)
        smtp.send_message(message)
        smtp.quit()
