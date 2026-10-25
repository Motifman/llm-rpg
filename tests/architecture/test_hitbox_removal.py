"""タイル上の当たり判定だけが退役し、共有の値と保存先が残ることを保証する。"""

from pathlib import Path


def test_hitbox_implementation_is_absent() -> None:
    """当たり判定専用の集約・保存先・サービス・値・出来事の実装は存在しない。"""
    root = Path(__file__).resolve().parents[2] / "src" / "ai_rpg_world"
    combat = root / "domain" / "combat"
    assert not list((combat / "aggregate").glob("*.py"))
    assert not list((combat / "repository").glob("*.py"))
    assert not list((combat / "service").glob("*.py"))
    assert not list((combat / "event").glob("*.py"))
    assert {p.stem for p in (combat / "value_object").glob("*.py")} == {
        "hit_box_shape",
        "hit_box_velocity",
        "hit_effect",
        "status_effect",
        "status_modifier",
    }
    assert not list((root / "infrastructure" / "repository").glob("*hit_box*.py"))


def test_shared_memory_store_has_no_hitboxes() -> None:
    """共有のメモリ保存先は当たり判定の状態と採番を持たず、全消去しても復活させない。"""
    from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore

    store = InMemoryDataStore()
    assert "hit_boxes" not in vars(store)
    assert "next_hit_box_id" not in vars(store)
    store.clear_all()
    assert "hit_boxes" not in vars(store)
    assert "next_hit_box_id" not in vars(store)
