"""利用側のない戦闘例外の定義を再導入しないことを保証する。"""

import pytest

from ai_rpg_world.domain.combat.exception import combat_exceptions


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
    assert not hasattr(combat_exceptions, exception_name)
