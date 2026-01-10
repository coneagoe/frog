from flask import Flask

from config import config

from .email import mail
from .model import db
from .strategy import bp_monitor_stock, scheduler


def create_app(config_name):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    mail.init_app(app)
    db.init_app(app)
    scheduler.init_app(app)

    app.register_blueprint(bp_monitor_stock)

    return app
