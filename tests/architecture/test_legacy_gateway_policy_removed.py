"""旧ゲートウェイ専用の遷移条件と保存先が復活しないことを保証する。"""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_RETIRED_MODULES = (
    "domain/world/value_object/transition_condition",
    "domain/world/repository/transition_policy_repository",
    "infrastructure/repository/in_memory_transition_policy_repository",
    "infrastructure/repository/sqlite_transition_policy_repository",
)


@pytest.mark.parametrize("module", _RETIRED_MODULES)
def test_legacy_gateway_policy_module_is_absent(module: str) -> None:
    """旧ゲートウェイ専用の遷移条件・保存契約・保存実装はソースに存在しない。"""
    assert not (_ROOT / "src/ai_rpg_world" / f"{module}.py").exists()


def test_runtime_sources_do_not_reference_legacy_gateway_policy() -> None:
    """製品コードと起動スクリプトは旧モジュールを型・再公開・動的文字列でも参照しない。"""
    retired_names = tuple(module.rsplit("/", 1)[-1] for module in _RETIRED_MODULES)
    references = [
        str(path.relative_to(_ROOT))
        for directory in ("src", "scripts")
        for path in (_ROOT / directory).rglob("*.py")
        if any(name in path.read_text(encoding="utf-8") for name in retired_names)
    ]
    assert references == []
