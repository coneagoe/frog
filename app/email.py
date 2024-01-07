from threading import Thread
from flask import current_app, render_template
from flask_mail import Message
from . import mail


def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)


def send_email(subject: str, template: str = '',
               attachment: str = '', **kwargs):
    app = current_app._get_current_object()
    with app.app_context():
        msg = Message(subject,
                      sender=app.config['MAIL_DEFAULT_SENDER'],
                      recipients=app.config['MAIL_RECIPIENTS'])
        if template:
            msg.body = render_template(template + '.txt', **kwargs)
            msg.html = render_template(template + '.html', **kwargs)

        if attachment:
            with app.open_resource(attachment) as f:
                msg.attach(attachment, 'text/csv', f.read())

        thr = Thread(target=send_async_email, args=[app, msg])
        thr.start()
        return thr
