"""採取とスキルの退役した実行経路を再導入せず、装備と保存を残す。"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / "src/ai_rpg_world"


def test_tile_harvest_application_is_removed() -> None:
    """タイル専用の採取アプリケーションはディレクトリごと存在しない。"""
    assert not (_ROOT / "application" / "harvest").exists()


def test_skill_application_keeps_storage_and_awakened_defaults() -> None:
    """スキルのサービスには覚醒の既定値だけが残り、保存先の配線は存在する。"""
    services = _ROOT / "application/skill/services"
    assert {path.name for path in services.glob("*.py")} == {
        "__init__.py",
        "awakened_mode_defaults.py",
    }
    assert (_ROOT / "application/skill/skill_sqlite_wiring.py").is_file()


def test_skill_domain_keeps_proposals_and_equipment_values() -> None:
    """スキルのドメインサービスには進化提案だけが残り、装備と命中の値は存在する。"""
    services = _ROOT / "domain/skill/service"
    assert {path.name for path in services.glob("*.py")} == {
        "__init__.py",
        "skill_proposal_domain_service.py",
    }
    for name in ("skill_spec", "skill_hit_pattern", "skill_deck"):
        assert (_ROOT / "domain/skill/value_object" / f"{name}.py").is_file()
