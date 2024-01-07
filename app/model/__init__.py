from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()
db = SQLAlchemy(model_class=Base)


from .monitor_stock import MonitorStock, table_name_monitor_stock # noqa
