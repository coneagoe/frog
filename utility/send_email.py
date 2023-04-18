import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import conf


def send_email(subject: str, attachment_file_name: str):
    sender_email = conf.get_sender_email()
    sender_user = conf.get_sender_user()
    sender_password = conf.get_sender_password()
    receiver_email = conf.get_receiver_email()

    message = MIMEMultipart()
    message['From'] = sender_email
    message['To'] = receiver_email
    message['Subject'] = subject

    body = 'Please find the attachment.'
    message.attach(MIMEText(body, 'plain'))

    with open(attachment_file_name, 'rb') as attachment:
        part = MIMEApplication(attachment.read(), Name=attachment_file_name)
        part['Content-Disposition'] = f'attachment; filename="{attachment_file_name}"'
        message.attach(part)

    with smtplib.SMTP_SSL(conf.get_smtp_server(), conf.get_smtp_port()) as smtp:
        smtp.login(sender_user, sender_password)
        smtp.send_message(message)
