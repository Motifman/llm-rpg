"""旧タイル移動・追跡の型と集約の専用操作を再導入しない。"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REMOVED = (
    "domain/pursuit",
    "domain/player/value_object/player_navigation_state.py",
    "domain/player/value_object/player_pursuit_state.py",
    "domain/monster/value_object/monster_pursuit_state.py",
)


def test_legacy_modules_are_absent():
    """旧移動・追跡の実装ファイルと、そのモジュールを読むimportが存在しない。"""
    source = ROOT / "src/ai_rpg_world"
    assert not [
        str(p) for name in REMOVED for p in (source / name,) if p.is_file() or (p.is_dir() and list(p.rglob("*.py")))
    ]
    modules = tuple("ai_rpg_world." + n.removesuffix(".py").replace("/", ".") for n in REMOVED)
    for path in source.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(modules), path
            elif isinstance(node, ast.Import):
                assert not any(n.name.startswith(modules) for n in node.names), path


def test_tile_location_event_is_absent():
    """旧タイルの位置更新イベントは発行元の削除とともに退役する。"""
    tree = ast.parse((ROOT / "src/ai_rpg_world/domain/player/event/status_events.py").read_text())
    assert "PlayerLocationChangedEvent" not in {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
