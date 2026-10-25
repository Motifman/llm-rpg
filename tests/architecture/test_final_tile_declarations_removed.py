"""退役したタイル処理だけが使っていた型と対処文を再導入しない。"""

from importlib import import_module

import pytest

from ai_rpg_world.application.llm.remediation_mapping import (
    DEFAULT_REMEDIATION_BY_ERROR_CODE,
    get_remediation,
)


@pytest.mark.parametrize(
    ("module_name", "type_name"),
    [
        ("domain.monster.exception.monster_exceptions", "MonsterPursuitException"),
        ("domain.world.enum.world_enum", "EnvironmentTypeEnum"),
        ("application.world.exceptions.base_exception", "WorldSystemErrorException"),
    ],
)
def test_retired_tile_type_is_absent(module_name: str, type_name: str) -> None:
    """発生元が退役したタイル専用の例外と環境区分は、定義を持たない。"""
    module = import_module(f"ai_rpg_world.{module_name}")
    assert not hasattr(module, type_name)


@pytest.mark.parametrize(
    "error_code",
    [
        "MOVEMENT_FAILED",
        "MOVEMENT_INVALID",
        "GATEWAY_OBJECT_NOT_FOUND",
        "GATEWAY_MONSTER_NOT_FOUND",
        "INTERACTION_TARGET_NOT_FOUND",
        "PLACEMENT_SPOT_NOT_FOUND",
        "INVALID_DIRECTION",
        "PURSUIT_FAILED",
        "PURSUIT_START_FAILED",
        "PURSUIT_CANCEL_FAILED",
    ],
)
def test_retired_tile_error_has_no_specific_remediation(error_code: str) -> None:
    """発生元のない旧タイル失敗コードには専用の対処文を持たず、汎用の案内を返す。"""
    assert error_code not in DEFAULT_REMEDIATION_BY_ERROR_CODE
    assert get_remediation(error_code) == "エラー内容を確認し、別の行動を選んでください。"
