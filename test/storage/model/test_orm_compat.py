import importlib
import sys
from types import ModuleType

from sqlalchemy import Column
from sqlalchemy.orm import Mapped


def test_mapped_column_falls_back_to_column_without_sqlalchemy_2_api(monkeypatch):
    import sqlalchemy

    import storage.model.orm_compat as orm_compat

    legacy_orm = ModuleType("sqlalchemy.orm")
    setattr(legacy_orm, "Mapped", Mapped)
    monkeypatch.setitem(sys.modules, "sqlalchemy.orm", legacy_orm)
    monkeypatch.setattr(sqlalchemy, "orm", legacy_orm)

    legacy_compat = importlib.reload(orm_compat)

    assert legacy_compat.mapped_column is Column
    assert isinstance(legacy_compat.mapped_column("stock_code"), Column)

    monkeypatch.undo()
    importlib.reload(orm_compat)
