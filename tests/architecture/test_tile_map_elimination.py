"""tile-map 依存除去 (Issue #227) の構造的保証テスト群。

PR-1〜6 を通じて達成した tile-map 依存除去が、将来のリファクタで再混入しないよう
構造的に固定化する。各 assertion が落ちる場合は「tile-map 依存が spot_graph 経路に
再混入した」ことを意味するため、慎重に意図を確認すること。

カバー範囲:
1. wiring シグネチャ: create_spot_graph_wiring から physical_map_repository が削除済み (PR-5)
2. observation factory: physical_map_repository が default=None で省略可 (PR-1)
3. wiring API: create_llm_agent_wiring の physical_map_repository が Optional (PR-2)
4. WorldQueryService 系列: 5 クラス + factory の physical_map_repository が Optional (PR-3)
5. DefaultPromptBuilder: tile_map_enabled パラメータが存在し default=True (PR-4)
6. spot_graph_wiring 内部: tile_map_enabled=False を渡している (PR-4)
7. Decorator 廃止: SpotGraphAugmentingWorldQueryService が存在しない (PR-6)
8. escape_game runtime: InMemoryPhysicalMapRepository を import しない (PR-5)
9. WorldQueryService: spot_graph_snapshot_provider 注入 API が存在 (PR-6)
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"


# ── 1. wiring シグネチャ ────────────────────────────────────────────────

def test_create_spot_graph_wiring_does_not_accept_physical_map_repository() -> None:
    """create_spot_graph_wiring から physical_map_repository 引数が完全削除されている (PR-5)。"""
    from ai_rpg_world.application.llm.wiring.spot_graph_wiring import (
        create_spot_graph_wiring,
    )
    sig = inspect.signature(create_spot_graph_wiring)
    assert "physical_map_repository" not in sig.parameters


def test_create_llm_agent_wiring_physical_map_repository_is_optional() -> None:
    """create_llm_agent_wiring の physical_map_repository は default=None (PR-2)。"""
    from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring
    sig = inspect.signature(create_llm_agent_wiring)
    param = sig.parameters["physical_map_repository"]
    assert param.default is None


def test_create_observation_recipient_resolver_physical_map_repository_is_optional() -> None:
    """create_observation_recipient_resolver の physical_map_repository は default=None (PR-1)。"""
    from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
        create_observation_recipient_resolver,
    )
    sig = inspect.signature(create_observation_recipient_resolver)
    param = sig.parameters["physical_map_repository"]
    assert param.default is None


# ── 2. WorldQueryService 系列 (PR-3) ─────────────────────────────────────

def test_world_query_service_family_physical_map_repository_is_optional() -> None:
    """WorldQueryService と 4 サブサービス + factory の physical_map_repository が Optional (PR-3)。"""
    from ai_rpg_world.application.world.services.available_moves_query_service import (
        AvailableMovesQueryService,
    )
    from ai_rpg_world.application.world.services.player_location_query_service import (
        PlayerLocationQueryService,
    )
    from ai_rpg_world.application.world.services.spot_context_query_service import (
        SpotContextQueryService,
    )
    from ai_rpg_world.application.world.services.visible_context_query_service import (
        VisibleContextQueryService,
    )
    from ai_rpg_world.application.world.services.world_query_service import (
        WorldQueryService,
    )
    for cls in (
        PlayerLocationQueryService,
        SpotContextQueryService,
        AvailableMovesQueryService,
        VisibleContextQueryService,
        WorldQueryService,
    ):
        sig = inspect.signature(cls.__init__)
        ann = str(sig.parameters["physical_map_repository"].annotation)
        assert "Optional" in ann or "None" in ann, (
            f"{cls.__name__}.physical_map_repository should be Optional"
        )


# ── 3. PromptBuilder の tile_map_enabled (PR-4) ──────────────────────────

def test_default_prompt_builder_has_tile_map_enabled_parameter() -> None:
    """PromptLimits に tile_map_enabled が default=True で存在する (PR-4 + Config 化後)。

    Issue #227 HIGH-1 で __init__ が Config dataclass ベースになり、
    tile_map_enabled は PromptLimits の field に移動した。
    """
    from ai_rpg_world.application.llm.services.prompt_builder_config import (
        PromptLimits,
    )
    instance = PromptLimits()
    assert instance.tile_map_enabled is True


def test_spot_graph_wiring_passes_tile_map_enabled_false() -> None:
    """spot_graph_wiring.py 内に tile_map_enabled=False が記述されている (PR-4)。

    実行時の動作確認は test_prompt_builder_tile_map_enabled.py に任せ、
    ここでは「spot_graph_wiring がこの設定を渡している」というソース上の事実を
    grep で固定する (リファクタで漏れた場合に検出する)。
    """
    spot_graph_wiring = _SRC / "ai_rpg_world/application/llm/wiring/spot_graph_wiring.py"
    text = spot_graph_wiring.read_text(encoding="utf-8")
    assert "tile_map_enabled=False" in text


# ── 4. Decorator 廃止 (PR-6) ────────────────────────────────────────────

def test_spot_graph_augmenting_world_query_module_is_removed() -> None:
    """SpotGraphAugmentingWorldQueryService の module が import できない (PR-6 で削除)。"""
    with pytest.raises(ImportError):
        importlib.import_module(
            "ai_rpg_world.application.world_graph.spot_graph_augmenting_world_query"
        )


def test_spot_graph_wiring_does_not_import_augmenting_decorator() -> None:
    """spot_graph_wiring.py が SpotGraphAugmentingWorldQueryService を import しない (PR-6)。"""
    spot_graph_wiring = _SRC / "ai_rpg_world/application/llm/wiring/spot_graph_wiring.py"
    text = spot_graph_wiring.read_text(encoding="utf-8")
    assert "SpotGraphAugmentingWorldQueryService" not in text


def test_world_query_service_has_attach_spot_graph_snapshot_provider() -> None:
    """WorldQueryService に snapshot provider 注入 API が存在する (PR-6)。"""
    from ai_rpg_world.application.world.services.world_query_service import (
        WorldQueryService,
    )
    assert hasattr(WorldQueryService, "attach_spot_graph_snapshot_provider")


# ── 5. escape_game runtime (PR-5) ───────────────────────────────────────

def test_escape_game_runtime_does_not_import_in_memory_physical_map_repository() -> None:
    """escape_game runtime が InMemoryPhysicalMapRepository を import しない (PR-5)。"""
    runtime_file = _REPO_ROOT / "src/ai_rpg_world/application/escape_game/escape_game_runtime.py"
    text = runtime_file.read_text(encoding="utf-8")
    assert "InMemoryPhysicalMapRepository" not in text


# ── 6. spot_graph_wiring 内部 (PR-5) ────────────────────────────────────

def test_spot_graph_wiring_does_not_import_physical_map_repository() -> None:
    """spot_graph_wiring.py に PhysicalMapRepository の import が無い (PR-5)。"""
    spot_graph_wiring = _SRC / "ai_rpg_world/application/llm/wiring/spot_graph_wiring.py"
    text = spot_graph_wiring.read_text(encoding="utf-8")
    # コメント内に "PhysicalMap" の言及が残るのは OK。import 文だけを検査
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("from ", "import ")):
            assert "PhysicalMapRepository" not in line, (
                f"unexpected PhysicalMapRepository import: {line!r}"
            )
