"""eventing は、ai_rpg_world 内のほかのパッケージに依存しない。"""

from pathlib import Path

import pytest
from tests.architecture.test_being_package_import_boundary import _violations

_EVENTING_ROOT = Path(__file__).resolve().parents[2] / "src/ai_rpg_world/eventing"


def _eventing_violations(root: Path) -> list[str]:
    return _violations(
        root,
        allowed=("ai_rpg_world.eventing",),
        forbidden=("ai_rpg_world",),
        root_package="ai_rpg_world.eventing",
    )


def test_eventing_imports_only_itself() -> None:
    """eventing の全モジュールで、自分以外の ai_rpg_world の import が無い。"""
    assert _eventing_violations(_EVENTING_ROOT) == []


@pytest.mark.parametrize(
    "source",
    [
        "from ai_rpg_world.domain.common.value_object import WorldTick\n",
        "import ai_rpg_world.being.contract\n",
        "from ai_rpg_world import application\n",
        "from ..infrastructure import events\n",
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from ai_rpg_world.domain.common import DomainEvent\n",
        "def f():\n    from ai_rpg_world.presentation import app\n",
        "from ai_rpg_world.eventings import x\n",
    ],
)
def test_external_package_import_is_reported(tmp_path: Path, source: str) -> None:
    """ほかのパッケージへの依存は、相対・型検査用・関数内の import も違反として報告する。"""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")
    assert _eventing_violations(tmp_path)


@pytest.mark.parametrize(
    "source",
    [
        "from ai_rpg_world.eventing import DomainEvent\n",
        "from ai_rpg_world import eventing\n",
        "from .domain_event import DomainEvent\n",
        "from datetime import datetime\n",
    ],
)
def test_own_package_and_standard_library_pass(tmp_path: Path, source: str) -> None:
    """eventing 自身と標準ライブラリの import は違反として報告しない。"""
    (tmp_path / "module.py").write_text(source, encoding="utf-8")
    assert _eventing_violations(tmp_path) == []
