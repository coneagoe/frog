from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class EnumGovernanceAdapter:
    name: str
    preflight: Callable[..., None]
    apply: Callable[..., bool]
    verify: Callable[..., None]
    rollback: Callable[..., bool]
    result: Callable[..., object]
