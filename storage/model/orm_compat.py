from importlib import import_module
from typing import Any, Callable, cast

from sqlalchemy.orm import Mapped

try:
    _sqlalchemy_mapped_column = getattr(import_module("sqlalchemy.orm"), "mapped_column")
except AttributeError:
    _sqlalchemy_mapped_column = getattr(import_module("sqlalchemy"), "Column")

mapped_column: Callable[..., Any] = cast(Callable[..., Any], _sqlalchemy_mapped_column)

__all__ = ["Mapped", "mapped_column"]
