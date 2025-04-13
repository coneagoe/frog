import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication


def send_email(subject: str, body: str, attachment_file_name: str | None = None):
    mail_server = os.getenv("MAIL_SERVER")
    mail_port = os.getenv("MAIL_PORT")
    mail_sender = os.getenv("MAIL_SENDER")
    mail_password = os.getenv("MAIL_PASSWORD")
    mail_receivers = os.getenv("MAIL_RECEIVERS")

    if not all([mail_server, mail_port, mail_sender,
                mail_password, mail_receivers]):
        logging.error("Email configuration is missing.")
        logging.error(f"mail_server: {mail_server}, mail_port: {mail_port}, "
                      f"mail_sender: {mail_sender}, mail_password: {mail_password}, "
                      f"mail_receivers: {mail_receivers}")
        return

    message = MIMEMultipart()
    message['From'] = mail_sender
    message['To'] = mail_receivers
    message['Subject'] = subject

    message.attach(MIMEText(body, 'plain'))

    if attachment_file_name is not None:
        with open(attachment_file_name, 'rb') as attachment:
            part = MIMEApplication(attachment.read(), Name=attachment_file_name)
            part['Content-Disposition'] = f'attachment; filename="{attachment_file_name}"'
            message.attach(part)

    with smtplib.SMTP_SSL(mail_server, mail_port) as smtp:
        smtp.login(mail_sender, mail_password)
        smtp.send_message(message)
        smtp.quit()
