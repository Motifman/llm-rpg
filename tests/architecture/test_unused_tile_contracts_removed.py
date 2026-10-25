"""旧タイル用の未使用契約を退役させ、本番の取得口を残す。"""

import ast
from pathlib import Path

import pytest

WORLD = Path(__file__).resolve().parents[2] / "src/ai_rpg_world/application/world"


@pytest.mark.parametrize(
    ("module", "remaining"),
    [
        ("commands.py", {"CancelMovementCommand"}),
        ("queries.py", {"GetPlayerCurrentStateQuery"}),
    ],
)
def test_only_consumed_command_and_query_contracts_remain(module, remaining):
    """命令・問い合わせには利用側が存在する契約だけが定義される。"""
    tree = ast.parse((WORLD / "contracts" / module).read_text())
    assert {node.name for node in tree.body if isinstance(node, ast.ClassDef)} == remaining


def test_unused_movement_exception_module_is_absent():
    """実行するサービスを失った移動専用例外のモジュールは存在しない。"""
    assert not (WORLD / "exceptions/command/movement_command_exception.py").exists()


@pytest.mark.parametrize(
    "name",
    [
        "PlayerLocationDto",
        "SpotInfoDto",
        "VisibleContextDto",
        "MoveResultDto",
        "PursuitCommandResultDto",
        "PlayerMovementOptionsDto",
    ],
)
def test_unused_standalone_dto_is_absent(name):
    """利用側のない独立DTOは定義されず、現在状態に含まれる型だけを残す。"""
    tree = ast.parse((WORLD / "contracts/dtos.py").read_text())
    assert name not in {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
