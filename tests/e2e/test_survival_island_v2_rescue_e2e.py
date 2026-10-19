"""実シナリオのセッション起動から点火、救助、漂流確定までを連続して通す。

実験 #25 / PR #370 で必要になった、LLM → 対象解決 → 相互作用 →
世界状態の接続を守る。準備の4検査も同じ起動内に置き、失敗した段階を示す。
救助192・漂流384はPR #435の改定値。時計や救助条件を試験用に短縮しない。
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
from tests.support.overflow_sinks import IGNORE_OVERFLOW

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def _create_v2_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """survival_island_v2 セッションを 4 人 spawn のまま立ち上げる。

    APIに必要なキャラクタを1件渡し、世界の登場人物はシナリオの4人を使う。
    時間を進める前にLLMクライアントをスタブへ差し替える。
    """
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
    mgr = GameRuntimeManager(
        scenarios_dir=SCENARIOS_DIR,
        characters_path=tmp_path / "characters.json",
    )
    # SessionCreateRequest は character_ids が non-empty を要求する。v2 シナリオの
    # spawn は内部的に scenario 側で定義されるが、API 上は 1 件以上の character_id
    # が要る。world_character として 1 件渡す (内容は session 内では使われない)。
    char = mgr.create_character(CharacterCreateRequest(name="テスト探索者"))
    summary = mgr.create_session(
        SessionCreateRequest(world_id="survival_island_v2", character_ids=[char.id])
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
        overflow_sink=IGNORE_OVERFLOW,
    )


def _ada_player_id(runtime) -> PlayerId:
    for sp in runtime.scenario.player_spawns:
        if sp.string_id == "ada":
            return PlayerId(int(sp.player_id))
    raise AssertionError("ada が scenario に存在しない")


def _signal_fire_target_label(runtime, player_id: PlayerId) -> str:
    """summit に居る player の runtime_context から signal_fire_pit のラベルを引く。

    OBJ ラベル (例: OBJ1) は build_full_prompt 時に各 player ごとに割り当て
    られる。object の string_id ("signal_fire_pit") を id_mapper で int に
    変換し、world_object_id 一致で identify する (display_name の表記揺れに
    依存しない、code-review LOW 対応)。
    """
    signal_world_obj_id = _id_int(runtime, "object", "signal_fire_pit")
    prompt = runtime.build_full_prompt(player_id)
    ctx = prompt["tool_runtime_context"]
    for label, target in ctx.targets.items():
        if getattr(target, "kind", None) != "spot_graph_object":
            continue
        if getattr(target, "world_object_id", None) == signal_world_obj_id:
            return label
    raise AssertionError(
        f"signal_fire_pit が ada の runtime_context に出ていない。"
        f"targets={[(l, t.kind, getattr(t, 'world_object_id', None)) for l, t in ctx.targets.items()]}"
    )


def _advance_to_tick(state, target_tick: int) -> None:
    """待機手番も処理し、途中終了や時計の飛越を見逃さず指定時刻まで進める。"""
    runtime = state.runtime
    start = runtime.current_tick()
    assert start <= target_tick
    for expected_tick in range(start + 1, target_tick + 1):
        assert not runtime.check_game_end().is_ended, (
            f"tick {runtime.current_tick()} で目標 {target_tick} より早く終了した"
        )
        runtime.advance_tick()
        trigger = state.llm_wiring.llm_turn_trigger
        if trigger.pending_player_ids:
            trigger.run_scheduled_turns()
        assert runtime.current_tick() == expected_tick, "1反復で1tickだけ進む"
    assert runtime.current_tick() == target_tick


class TestSurvivalIslandV2RescueE2E:
    """山頂のAdaは192で救助され、残る3人は384で漂流が確定する。"""

    def test_signal_rescues_ada_at_192_and_ends_at_384(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """初期配置・実所持・点火の接続を通し、救助と終了の前後を検査する。"""
        state = _create_v2_session(monkeypatch, tmp_path)
        runtime = state.runtime
        ada = _ada_player_id(runtime)
        graph = runtime._spot_graph_repo.find_graph()
        beach = SpotId.create(_id_int(runtime, "spot", "shipwreck_beach"))
        assert len(graph.presence_at(beach).present_entity_ids) == 4
        others = tuple(pid for pid in runtime.get_player_ids() if pid != ada)
        assert len(others) == 3

        _teleport(runtime, int(ada), "summit")
        graph = runtime._spot_graph_repo.find_graph()
        summit = SpotId.create(_id_int(runtime, "spot", "summit"))
        assert EntityId.create(int(ada)) in graph.presence_at(summit).present_entity_ids

        _grant_items(runtime, ada, ("driftwood", "dry_leaves", "flint"))
        inventory = runtime._player_inventory_repo.find_by_id(ada)
        assert inventory is not None
        owned_specs = set()
        for _, item_id in inventory.iter_occupied_slots():
            item = runtime._item_repo.find_by_id(item_id)
            assert item is not None
            owned_specs.add(item.item_spec.item_spec_id)
        assert {
            ItemSpecId.create(_id_int(runtime, "item_spec", name))
            for name in ("driftwood", "dry_leaves", "flint")
        }.issubset(owned_specs)

        signal_label = _signal_fire_target_label(runtime, ada)
        stub = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_INTERACT,
            "arguments": {
                "target_label": signal_label,
                "action_name": "light_signal",
                "inner_thought": "助けを呼ぶ",
            },
        })
        state.llm_wiring.llm_client = stub
        result = state.llm_wiring.run_turn(ada)
        assert result.success is True, (
            f"light_signal が失敗: code={result.error_code} msg={result.message}"
        )
        assert "signal_fire_lit" in runtime._world_flag_state.as_frozen_set()

        # 本番の待機手番も残す。#471の入れ子tick再発も進行中に検知する。
        stub.set_tool_call_to_return({
            "name": "wait",
            "arguments": {"reason": "待機", "inner_thought": "待つ"},
        })
        # 飢餓と欲求減衰は既存試験と同じく関心外とする。
        decay_stage = runtime._simulation_service._needs_decay_stage
        decay_stage._starvation_damage_per_tick = 0
        decay_stage._rates = {}

        registry = runtime._player_outcome_registry
        assert registry is not None
        _advance_to_tick(state, 191)
        assert registry.get_outcome(ada) == PlayerOutcomeEnum.UNRESOLVED
        assert not runtime.check_game_end().is_ended

        _advance_to_tick(state, 192)
        assert registry.get_outcome(ada) == PlayerOutcomeEnum.RESCUED
        assert all(registry.get_outcome(pid) == PlayerOutcomeEnum.UNRESOLVED for pid in others)
        assert not runtime.check_game_end().is_ended

        _advance_to_tick(state, 383)
        assert registry.get_outcome(ada) == PlayerOutcomeEnum.RESCUED
        assert all(registry.get_outcome(pid) == PlayerOutcomeEnum.UNRESOLVED for pid in others)
        assert not runtime.check_game_end().is_ended

        _advance_to_tick(state, 384)
        assert registry.get_outcome(ada) == PlayerOutcomeEnum.RESCUED
        assert all(registry.get_outcome(pid) == PlayerOutcomeEnum.STRANDED for pid in others)
        assert runtime.check_game_end().is_ended is True
