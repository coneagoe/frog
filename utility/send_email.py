import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication


def send_email(subject: str, attachment_file_name: str):
    message = MIMEMultipart()
    message['From'] = os.environ['email_sender']
    message['To'] = os.environ['email_receiver']
    message['Subject'] = subject

    body = 'Please find the attachment.'
    message.attach(MIMEText(body, 'plain'))

    with open(attachment_file_name, 'rb') as attachment:
        part = MIMEApplication(attachment.read(), Name=attachment_file_name)
        part['Content-Disposition'] = f'attachment; filename="{attachment_file_name}"'
        message.attach(part)

    with smtplib.SMTP_SSL(os.environ['email_server'], os.environ['email_server_port']) as smtp:
        smtp.login(os.environ['email_user'], os.environ['email_password'])
        smtp.send_message(message)
