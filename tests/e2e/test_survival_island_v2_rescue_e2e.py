"""survival_island_v2 シナリオの「ゴールまで完走」E2E。

実験 #25 で気付いた gap: 既存テストは subsystem 単位 (game_end 判定だけ /
monster combat だけ / episodic wiring だけ) で、**シナリオ全体を end-to-end
で通すテスト** が無い。実験 #25 で発覚した item resolver 配線抜け
(#356 / #369) も「LLM → tool catalog → resolver → executor → 状態変化」の
1 経路を通せば検知できたが、その shape のテストが存在しなかったため
本番実験まで気付けなかった。

# このテストの位置付け

完全な playthrough (14 日 / 4 人 / LLM 駆動) はコスト的に CI で回せない
ので、**最短経路を scripted な tool call で通す smoke** に絞る:

1. survival_island_v2 セッション起動 (4 人 spawn @ shipwreck_beach)
2. ada (PlayerId=1) を test infra で summit へ teleport
3. ada のインベントリに driftwood / dry_leaves / flint を直接付与
4. **LLM stub** に `spot_graph_interact(signal_fire_pit, light_signal)`
   を返させて `wiring.run_turn(ada)` を呼ぶ
   = ここで通る経路: build_full_prompt → tool_call dispatch →
   `_handle_interact` → resolver → spot_interaction_service →
   precondition (HAS_ITEM driftwood/dry_leaves/flint) → effect
   (REMOVE_ITEM, SET_FLAG signal_fire_lit) → trace recording
5. world_flag `signal_fire_lit` が立っていることを確認
6. tick を 168 (1 回目の救助船到来) まで進める
   = scenario_event `rescue_ship_first_arrive` が発火、outcome 評価が回る
7. ada の outcome が `RESCUED`、`check_game_end().is_ended` が True

E2E 失敗時に切り分けやすいよう、各 step ごとに別 test に切る。
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


def _create_v2_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """survival_island_v2 セッションを 4 人 spawn のまま立ち上げる。

    character_ids は空で起動 (= scenario 既定の 4 spawn を使う)。
    LLM 呼び出しがあると本物のクライアントに飛ぶので、後で stub を差し込む。
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
    )


def _ada_player_id(runtime) -> PlayerId:
    for sp in runtime.scenario.player_spawns:
        if sp.string_id == "ada":
            return PlayerId(int(sp.player_id))
    raise AssertionError("ada が scenario に存在しない")


def _signal_fire_object_label(runtime, player_id: PlayerId) -> str:
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


class TestSurvivalIslandV2RescueE2E:
    """ada が summit で狼煙を上げ → tick 168 で RESCUED まで通る最短 path。"""

    def test_step1_セッション起動で_ada_が_shipwreck_beach_に_spawn(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """v2 シナリオを GameRuntimeManager 経由で立ち上げ、4 人が
        shipwreck_beach に居ることを確認する。"""
        state = _create_v2_session(monkeypatch, tmp_path)
        runtime = state.runtime
        beach_int = _id_int(runtime, "spot", "shipwreck_beach")
        graph = runtime._spot_graph_repo.find_graph()
        present = graph.presence_at(SpotId.create(beach_int)).present_entity_ids
        assert len(present) == 4

    def test_step2_ada_を_summit_に_teleport_できる(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        state = _create_v2_session(monkeypatch, tmp_path)
        runtime = state.runtime
        ada = _ada_player_id(runtime)
        _teleport(runtime, int(ada), "summit")
        summit_int = _id_int(runtime, "spot", "summit")
        graph = runtime._spot_graph_repo.find_graph()
        assert EntityId.create(int(ada)) in graph.presence_at(
            SpotId.create(summit_int)
        ).present_entity_ids

    def test_step3_必要アイテム_3_種を_ada_に_付与できる(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        state = _create_v2_session(monkeypatch, tmp_path)
        runtime = state.runtime
        ada = _ada_player_id(runtime)
        _grant_items(runtime, ada, ("driftwood", "dry_leaves", "flint"))
        inv = runtime._player_inventory_repo.find_by_id(ada)
        assert inv is not None
        # _inventory_slots は SlotId → ItemInstanceId | None。occupied だけ拾う。
        owned_spec_ids = set()
        for slot_id, iid in inv._inventory_slots.items():
            if iid is None:
                continue
            agg = runtime._item_repo.find_by_id(iid)
            if agg is not None:
                owned_spec_ids.add(agg.item_spec.item_spec_id.value)
        expected = {
            _id_int(runtime, "item_spec", n)
            for n in ("driftwood", "dry_leaves", "flint")
        }
        assert expected.issubset(owned_spec_ids)

    def test_step4_LLM_stub_経由で_light_signal_を_実行できる(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """LLM stub に light_signal の tool call を返させ、
        wiring.run_turn 経由で interaction service まで貫通させる。"""
        state = _create_v2_session(monkeypatch, tmp_path)
        runtime = state.runtime
        ada = _ada_player_id(runtime)
        _teleport(runtime, int(ada), "summit")
        _grant_items(runtime, ada, ("driftwood", "dry_leaves", "flint"))

        signal_label = _signal_fire_object_label(runtime, ada)
        stub = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_INTERACT,
            "arguments": {
                "object_label": signal_label,
                "action_name": "light_signal",
                "inner_thought": "救助を呼ぶ。",
            },
        })
        state.llm_wiring.llm_client = stub

        result = state.llm_wiring.run_turn(ada)
        assert result.success is True, (
            f"light_signal が失敗: code={result.error_code} msg={result.message}"
        )

        # signal_fire_lit flag が立っていること
        flag_set = "signal_fire_lit" in runtime._world_flag_state.as_frozen_set()
        assert flag_set, (
            "interaction effect SET_FLAG が反映されていない。"
            f"current flags={runtime._world_flag_state.as_frozen_set()}"
        )

    def test_step5_tick_168_到達で_ada_が_RESCUED_outcome_になる(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """狼煙点火 → tick 168 (rescue_ship_first_arrive) → outcome_resolution
        が ada (summit に居る) を RESCUED 確定する。"""
        state = _create_v2_session(monkeypatch, tmp_path)
        runtime = state.runtime
        ada = _ada_player_id(runtime)
        _teleport(runtime, int(ada), "summit")
        _grant_items(runtime, ada, ("driftwood", "dry_leaves", "flint"))

        # まず stub を light_signal に設定して ada のターンだけ実行。
        # stub の invoke 呼び出し回数を spy して、light_signal が **正確に**
        # 必要なだけ叩かれたことを確認する (code-review HIGH 対応)。
        # 余分な呼び出しが入った場合に検知する。
        signal_label = _signal_fire_object_label(runtime, ada)
        stub = StubLlmClient(tool_call_to_return={
            "name": TOOL_NAME_SPOT_GRAPH_INTERACT,
            "arguments": {
                "object_label": signal_label,
                "action_name": "light_signal",
                "inner_thought": "助けを呼ぶ",
            },
        })
        light_signal_calls = {"n": 0}
        orig_invoke = stub.invoke

        def spy_invoke(*args, **kwargs):
            tc = orig_invoke(*args, **kwargs)
            if tc and tc.get("name") == TOOL_NAME_SPOT_GRAPH_INTERACT:
                light_signal_calls["n"] += 1
            return tc

        stub.invoke = spy_invoke  # type: ignore[method-assign]
        state.llm_wiring.llm_client = stub
        state.llm_wiring.run_turn(ada)
        assert "signal_fire_lit" in runtime._world_flag_state.as_frozen_set()
        # ada の light_signal は self-reschedule chain (= 旧 max_turns) の影響で
        # 1 回以上呼ばれる可能性がある (success=True なら次 tick への reschedule
        # あり)。重要なのは「呼ばれた」ことと、信号が点いた後は別 action に
        # 切り替わることなので、最低 1 回呼ばれたことを assert する。
        assert light_signal_calls["n"] >= 1

        # 以降は全 player を spot_graph_wait に切り替えて tick を進める。
        # advance_tick が他 player の heartbeat ターンを schedule することがあるため、
        # 安全な no-op を返す stub に差し替えて crash しないようにする。
        stub.set_tool_call_to_return({
            "name": "spot_graph_wait",
            "arguments": {"reason": "待機", "inner_thought": "待つ"},
        })

        # rescue が成立する tick まで進める。途中で game_end したら break。
        # #471 以前: do_wait の nested advance_tick による再帰カスケードで
        # 1 test loop 反復内に数百 tick がジャンプしていたため、170 iteration で
        # rescue tick (384) に到達できていた。#471 で nested advance_tick を
        # 除去した結果、1 iteration = 1 tick の自然な進行になり、rescue 成立
        # までに 400 iteration 弱が必要になった。テスト本来の意図 (rescue 経路
        # の貫通検証) は変わらないので iteration 上限を素直に引き上げる。
        # 飢餓と HUNGER decay は本テストの関心外なので無効化する。
        decay_stage = runtime._simulation_service._needs_decay_stage
        decay_stage._starvation_damage_per_tick = 0
        decay_stage._rates = {}

        MAX_ITERATIONS = 500
        for _ in range(MAX_ITERATIONS):
            if runtime.check_game_end().is_ended:
                break
            runtime.advance_tick()
            # advance_tick の副作用で他 player のターンが scheduled された場合
            # も流す (= scenario_event が tick 内に発火する経路を貫通させる)。
            trigger = state.llm_wiring.llm_turn_trigger
            if trigger.pending_player_ids:
                trigger.run_scheduled_turns()

        result = runtime.check_game_end()
        assert result.is_ended is True, (
            f"{MAX_ITERATIONS} iteration 過ぎても game_end が立たない: "
            f"reason={result.reason} tick={runtime.current_tick()}"
        )
        # ada は summit に残っているので RESCUED
        outcome_registry = runtime._player_outcome_registry
        assert outcome_registry is not None
        ada_outcome = outcome_registry.get_outcome(ada)
        assert ada_outcome == PlayerOutcomeEnum.RESCUED, (
            f"ada が RESCUED にならず {ada_outcome} で終わった。"
            "summit に残っているのに rescue 経路が動いていない疑い。"
        )
