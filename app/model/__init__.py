from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)

from .monitor_stock import TABLE_NAME_MONITOR_STOCK, MonitorStock  # noqa
