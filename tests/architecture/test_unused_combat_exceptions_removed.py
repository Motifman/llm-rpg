"""利用側のない戦闘例外の定義を再導入しないことを保証する。"""

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "exception_name",
    [
        "DamageValidationException",
        "HitBoxInactiveException",
        "CombatTargetNotFoundException",
    ],
)
def test_unused_combat_exception_is_absent(exception_name: str) -> None:
    """利用側のない戦闘例外3種は、例外モジュールから取得できない。"""
    path = Path(__file__).resolve().parents[2] / "src/ai_rpg_world/domain/combat/exception/combat_exceptions.py"
    source = path.read_text(encoding="utf-8") if path.exists() else ""
    assert exception_name not in source
