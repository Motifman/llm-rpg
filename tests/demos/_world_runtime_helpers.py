"""tests/demos/test_world_runtime_*.py 用の共有ヘルパー。

旧コードは PR 1〜6 の各テストファイルで ``_create_session`` /
``_name_to_spot_id`` / ``_teleport`` を独立コピーで持っていた。chore
(#240 後続) でここに集約し、各テストは import するだけで使えるようにする。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
)
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"
FORBIDDEN_LIBRARY_PATH = SCENARIO_DIR / "forbidden_library_demo.json"


def create_world_runtime_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stub: Optional[StubLlmClient] = None,
    *,
    world_id: str = "forbidden_library_demo",
    character_name: str = "カイト",
):
    """world_runtime セッションを立ち上げて ``_SessionState`` を返す。

    Args:
        monkeypatch: pytest fixture。``SPOT_GRAPH_TICK_LOOP_ENABLED=false`` を設定する。
        tmp_path: pytest fixture。``characters.json`` の保存先に使う。
        stub: ``llm_wiring.llm_client`` に差し込む LLM stub。``None`` なら
            既定 client (環境変数依存) のまま。
        world_id: 読み込むシナリオの id (既定 ``forbidden_library_demo``)。
        character_name: 作成するキャラクター名。

    Returns:
        ``mgr._sessions[summary.session_id]`` (内部 ``_SessionState``)。
    """
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
    mgr = GameRuntimeManager(
        scenarios_dir=SCENARIO_DIR,
        characters_path=tmp_path / "characters.json",
    )
    char = mgr.create_character(CharacterCreateRequest(name=character_name))
    summary = mgr.create_session(
        SessionCreateRequest(world_id=world_id, character_ids=[char.id])
    )
    state = mgr._sessions[summary.session_id]
    if stub is not None:
        state.llm_wiring.llm_client = stub
    return state


def name_to_spot_id(runtime, name: str) -> int:
    """シナリオ上のスポット名から spot_id (int) を引く。

    Args:
        runtime: ``WorldRuntime`` または ``runtime._spot_graph_repo``
            を持つオブジェクト。
        name: スポット名 (例: ``"閲覧室"``)。
    """
    graph = runtime._spot_graph_repo.find_graph()
    for node in graph.iter_spot_nodes():
        if node.name == name:
            return node.spot_id.value
    raise KeyError(f"spot {name!r} not in scenario")


def teleport(runtime, player_id_value: int, spot_id_value: int) -> None:
    """テスト用に entity をスポットへ強制配置する。

    既に置かれている場合は冪等 (no-op)。
    """
    graph = runtime._spot_graph_repo.find_graph()
    eid = EntityId.create(player_id_value)
    if graph.presence_at(SpotId.create(spot_id_value)).is_present(eid):
        return
    try:
        graph.unplace_entity(eid)
    except Exception:
        # まだ未配置の場合は無視
        pass
    graph.place_entity(eid, SpotId.create(spot_id_value))
    runtime._spot_graph_repo.save(graph)
