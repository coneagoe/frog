# -*- coding: utf-8 -*-
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Float, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from datetime import date

db_name = 'sqlite:///tmp.db'

engine = create_engine(db_name, echo=True)
session = Session(bind=engine)
Base = declarative_base()


account_table_name = 'account'


class Account(Base):
    __tablename__ = account_table_name
    name = Column(u'账户', String, primary_key=True)
    assets = Column(u'资产', Float)

    def __repr__(self):
        return f"name: {self.name}, assets: {self.assets}"


def table_exist(table_name):
    return engine.dialect.has_table(engine, table_name)


def create_account_table():
    if not table_exist(account_table_name):
        meta = MetaData()
        account_table = Table(
            account_table_name, meta,
            Column(u'账户', String, primary_key=True),
            Column(u'资产', Float)
        )
        meta.create_all(engine)


def create_sub_account_table(sub_table_name):
    if not table_exist(sub_table_name):
        meta = MetaData()
        account_table = Table(
            sub_table_name, meta,
            Column(u'日期', Date, default=date.today, primary_key=True),
            Column(u'资产', Float)
        )
        meta.create_all(engine)
        sub_account = Account(name=sub_table_name, assets=0)
        session.add(sub_account)
        session.commit()


def init():
    create_account_table()