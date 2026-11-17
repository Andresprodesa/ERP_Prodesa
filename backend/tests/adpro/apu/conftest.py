"""Fixtures del submódulo APU."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from tests.adpro.apu.escenario import crear_escenario


@pytest.fixture()
def esc(db: Session) -> dict[str, int]:
    return crear_escenario(db)
