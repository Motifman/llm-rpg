"""survival_island_v3_coop の協力ゲートと救助経路の E2E (P12)。

smoke テスト (tests/infrastructure/scenario/test_survival_island_v3_coop_smoke.py)
は JSON 構造の静的検証であり、「点火の 2 人ゲートがランタイムで実際に効くか」
「新しい救助 tick (144) で RESCUED まで貫通するか」は保証しない (独立レビュー
MEDIUM 指摘への対応)。v2 の E2E (test_survival_island_v2_rescue_e2e.py) と
同じ scripted tool call 方式で、協力シナリオの核心 3 点を実行して確認する:

1. 材料が全部揃っていても、山頂に 1 人しかいなければ点火できない
   (PLAYERS_AT_SPOT ゲートがランタイムで拒否する)
2. 2 人いれば点火でき、材料 (流木 3 / 枯れ葉 2) が数どおり消費される
3. 点火後 tick 144 で、山頂に居る 2 人だけが RESCUED になり、
   麓に残った者は救助されない (「狼煙が見えても麓に居れば置いていかれる」)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_INTERACT
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_item_specs_to_inventory,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
)
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"

# 狼煙の必要材料 (v3_coop で増量した数)。
_MATERIALS = ("driftwood",) * 3 + ("dry_leaves",) * 2 + ("flint",)


def _create_coop_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
    mgr = GameRuntimeManager(
        scenarios_dir=SCENARIOS_DIR,
        characters_path=tmp_path / "characters.json",
    )
    char = mgr.create_character(CharacterCreateRequest(name="テスト探索者"))
    summary = mgr.create_session(
        SessionCreateRequest(
            world_id="survival_island_v3_coop", character_ids=[char.id]
        )
    )
    return mgr._sessions[summary.session_id]


def _id_int(runtime, kind: str, str_id: str) -> int:
    return runtime.id_mapper.get_int(kind, str_id)


def _teleport(runtime, player_id_int: int, spot_str_id: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    eid = EntityId.create(player_id_int)
    spot_int = _id_int(runtime, "spot", spot_str_id)
    try:
        graph.unplace_entity(eid)
    except Exception:
        pass
    graph.place_entity(eid, SpotId.create(spot_int))
    runtime._spot_graph_repo.save(graph)


def _grant_items(runtime, player_id: PlayerId, item_str_ids: tuple) -> None:
    spec_ids = tuple(
        ItemSpecId.create(_id_int(runtime, "item_spec", sid)) for sid in item_str_ids
    )
    grant_item_specs_to_inventory(
        player_id=player_id,
        item_spec_ids=spec_ids,
        item_repository=runtime._item_repo,
        item_spec_repository=runtime._item_spec_repo,
        player_inventory_repository=runtime._player_inventory_repo,
    )


def _player_id(runtime, string_id: str) -> PlayerId:
    for sp in runtime.scenario.player_spawns:
        if sp.string_id == string_id:
            return PlayerId(int(sp.player_id))
    raise AssertionError(f"{string_id} が scenario に存在しない")


def _signal_fire_object_label(runtime, player_id: PlayerId) -> str:
    signal_world_obj_id = _id_int(runtime, "object", "signal_fire_pit")
    prompt = runtime.build_full_prompt(player_id)
    ctx = prompt["tool_runtime_context"]
    for label, target in ctx.targets.items():
        if getattr(target, "kind", None) != "spot_graph_object":
            continue
        if getattr(target, "world_object_id", None) == signal_world_obj_id:
            return label
    raise AssertionError("signal_fire_pit が runtime_context に出ていない")


def _run_light_signal_turn(state, runtime, actor: PlayerId):
    """actor に light_signal の tool call を 1 ターン実行させる。"""
    label = _signal_fire_object_label(runtime, actor)
    stub = StubLlmClient(
        tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_INTERACT,
            "arguments": {
                "object_label": label,
                "action_name": "light_signal",
                "inner_thought": "狼煙を上げる。",
            },
        }
    )
    state.llm_wiring.llm_client = stub
    return state.llm_wiring.run_turn(actor)


def _flag_lit(runtime) -> bool:
    return "signal_fire_lit" in runtime._world_flag_state.as_frozen_set()


class TestSoloCannotLight:
    """材料が全部揃っていても、山頂に 1 人では点火できない (協力の必要条件)。"""

    def test_solo_light_signal_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """ada が単独で summit に居て材料 3/2/1 を持っていても、
        PLAYERS_AT_SPOT (2 人) ゲートに拒否され signal_fire_lit は立たない。"""
        state = _create_coop_session(monkeypatch, tmp_path)
        runtime = state.runtime
        ada = _player_id(runtime, "ada")
        _teleport(runtime, int(ada), "summit")
        _grant_items(runtime, ada, _MATERIALS)

        result = _run_light_signal_turn(state, runtime, ada)

        assert not _flag_lit(runtime), (
            "1 人でも点火できてしまった。PLAYERS_AT_SPOT ゲートが"
            "ランタイムで効いていない。"
        )
        assert result.success is False


class TestInsufficientMaterials:
    """2 人いても材料が足りなければ点火できない (増量の検証)。"""

    def test_single_driftwood_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """流木 1 本 (v2 なら足りた量) では required_quantity=3 に拒否される。"""
        state = _create_coop_session(monkeypatch, tmp_path)
        runtime = state.runtime
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        _teleport(runtime, int(ada), "summit")
        _teleport(runtime, int(noah), "summit")
        _grant_items(runtime, ada, ("driftwood", "dry_leaves", "dry_leaves", "flint"))

        result = _run_light_signal_turn(state, runtime, ada)

        assert not _flag_lit(runtime), (
            "流木 1 本で点火できてしまった。required_quantity が"
            "ランタイムで数えられていない。"
        )
        assert result.success is False


class TestDuoLightsAndSummitOnlyRescue:
    """2 人なら点火でき、tick 144 で山頂の 2 人だけが救助される。"""

    def test_duo_light_succeeds_and_rescue_resolves_at_144(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """ada + noah が summit で点火 → tick 144 の救助で 2 人は RESCUED、
        麓に残った rio は救助されない (STRANDED)。狼煙が見えても山頂に
        居ない者は置いていかれる、という v3 の協調要求の核を実行で確認する。"""
        state = _create_coop_session(monkeypatch, tmp_path)
        runtime = state.runtime
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        rio = _player_id(runtime, "rio")
        _teleport(runtime, int(ada), "summit")
        _teleport(runtime, int(noah), "summit")
        _grant_items(runtime, ada, _MATERIALS)

        result = _run_light_signal_turn(state, runtime, ada)
        assert result.success is True, (
            f"2 人揃って材料 3/2/1 でも点火に失敗: "
            f"code={result.error_code} msg={result.message}"
        )
        assert _flag_lit(runtime)

        # 以降は全 player を wait に切り替えて tick を進める。
        stub = state.llm_wiring.llm_client
        stub.set_tool_call_to_return(
            {"name": "wait", "arguments": {"reason": "待機", "inner_thought": "待つ"}}
        )

        # 飢餓は本テストの関心外なので無効化 (v2 E2E と同じ扱い)。
        decay_stage = runtime._simulation_service._needs_decay_stage
        decay_stage._starvation_damage_per_tick = 0
        decay_stage._rates = {}

        # stranded_at_tick=240 で全員の outcome が確定して game_end する。
        MAX_ITERATIONS = 300
        for _ in range(MAX_ITERATIONS):
            if runtime.check_game_end().is_ended:
                break
            runtime.advance_tick()
            trigger = state.llm_wiring.llm_turn_trigger
            if trigger.pending_player_ids:
                trigger.run_scheduled_turns()

        assert runtime.check_game_end().is_ended is True

        registry = runtime._player_outcome_registry
        assert registry is not None
        assert registry.get_outcome(ada) == PlayerOutcomeEnum.RESCUED
        assert registry.get_outcome(noah) == PlayerOutcomeEnum.RESCUED
        # 麓に残った rio は狼煙が上がっていても救助されない。
        assert registry.get_outcome(rio) == PlayerOutcomeEnum.STRANDED
