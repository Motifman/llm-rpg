"""実 ``WorldRuntime`` をまたいだ実験スナップショットの保存→復元を保証する。

既存のサブシステム変換器単体テストだけでは、``create_world_runtime`` が実際に
組み立てる repository / store 配線と ``ExperimentSnapshotSession`` の接続漏れを
検出できない。このテストは、1 つ目の実行環境から ``world.json`` と Being
snapshot file を出力し、別の実行環境に復元したうえで、snapshot 契約上の状態が
一致することを固定する。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_rpg_world.application.being.experiment_snapshot_session import (
    ExperimentSnapshotSession,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPrediction,
)
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import GoalEntry
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_id import DEFAULT_SINGLE_WORLD_ID
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.ground_item import GroundItem
from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime
from tests.runtime_config_helpers import runtime_config


_NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
_SCENARIO_PATH = Path("data/scenarios/forbidden_library_demo.json")
_SCENARIO_NAME = "forbidden_library_demo"


def _snapshot_runtime_config() -> Any:
    """本命観察 run 周辺で使う per-Being store を実体化する設定を返す。"""
    return runtime_config(
        episodic_enabled=True,
        semantic_passive_top_k=3,
        pending_prediction_enabled=True,
        goal_store_enabled=True,
        belief_consolidation_enabled=True,
        belief_evidence_enabled=True,
        goal_reflect_enabled=True,
        stagnation_pressure_enabled=True,
    )


def _create_runtime() -> Any:
    runtime = create_world_runtime(_SCENARIO_PATH, config=_snapshot_runtime_config())
    runtime._wire_auxiliary_tool_stack()
    for player_id in runtime.get_player_ids():
        runtime._aux_being_provisioning.ensure_attached(player_id)
    return runtime


def _session(runtime: Any, snapshot_dir: Path) -> ExperimentSnapshotSession:
    return ExperimentSnapshotSession(
        wiring_result=_wiring_stub_from_world_runtime(runtime),
        snapshot_dir=snapshot_dir,
    )


def _being_id(runtime: Any, player_id: PlayerId) -> BeingId:
    being_id = runtime.aux_being_resolver.resolve_being_id(
        DEFAULT_SINGLE_WORLD_ID, player_id
    )
    assert being_id is not None
    return being_id


def _observation(prose: str) -> ObservationEntry:
    return ObservationEntry(
        occurred_at=_NOW,
        output=ObservationOutput(
            prose=prose,
            structured={"event_kind": "snapshot_roundtrip"},
            observation_category="self_only",
            schedules_turn=True,
        ),
        game_time_label="Day 2 12:00",
    )


def _add_item_fixture(runtime: Any, *, holder: PlayerId) -> None:
    """実 runtime の item / inventory / spot_interior repo に最小 item 状態を作る。"""
    carried_id = ItemInstanceId(9001)
    ground_id = ItemInstanceId(9002)
    carried_spec = runtime._item_spec_repo.find_by_id(ItemSpecId(6)).to_item_spec()
    ground_spec = runtime._item_spec_repo.find_by_id(ItemSpecId(9)).to_item_spec()
    runtime._item_repo.save(
        ItemAggregate.create(
            carried_id,
            carried_spec,
            quantity=3,
            state={"source": "inventory", "fresh": True},
        )
    )
    runtime._item_repo.save(
        ItemAggregate.create(
            ground_id,
            ground_spec,
            quantity=1,
            state={"source": "spot"},
        )
    )

    inventory = runtime._player_inventory_repo.find_by_id(holder)
    assert inventory is not None
    inventory.acquire_item(carried_id, carried_spec.item_spec_id.value)
    inventory.reserve_item(SlotId(0))
    runtime._player_inventory_repo.save(inventory)

    spot_id = SpotId(1)
    interior = runtime._spot_interior_repo.find_by_spot_id(spot_id)
    assert interior is not None
    runtime._spot_interior_repo.save(
        spot_id,
        interior.with_ground_item(
            GroundItem(
                item_instance_id=ground_id,
                item_spec_id=ground_spec.item_spec_id,
            )
        ),
    )


def _populate_runtime_state(runtime: Any) -> None:
    player_id = PlayerId(1)
    being_id = _being_id(runtime, player_id)

    runtime._time_provider.set_current_tick(37)
    graph = runtime._spot_graph_repo.find_graph()
    graph._entity_spot[EntityId.create(player_id.value)] = SpotId(2)
    status = runtime._player_status_repo.find_by_id(player_id)
    assert status is not None
    status._hp = Hp(value=73, max_hp=100)
    status.increase_need(NeedType.HUNGER, 41)
    status.increase_need(NeedType.FATIGUE, 12)
    status._state = {"snapshot_marker": "status"}
    runtime._player_status_repo.save(status)

    _add_item_fixture(runtime, holder=player_id)

    runtime._sliding_window.append(player_id, _observation("窓に残る観測"))
    runtime._obs_buffer.append(player_id, _observation("次行動に渡す未処理観測"))
    runtime._action_result_store.append(
        player_id,
        action_summary="snapshot action",
        result_summary="snapshot result",
        occurred_at=_NOW,
        success=False,
        error_code="INVALID_TARGET_LABEL",
        tool_name="spot_graph_interact",
        expected_result="棚を調べれば鍵が見つかるはず",
        intention="鍵を探す",
        emotion_hint="焦り",
        occurred_tick=37,
        prediction_context_id="predctx-runtime-roundtrip",
        in_context_belief_ids=("sem-runtime-1",),
    )
    runtime._encounter_memory.observe(
        player_id,
        EncounterKey.spot("ancient_archive"),
        current_tick=37,
    )

    runtime._todo_store.add_by_being(
        being_id,
        "再開後も忘れてはいけない作業",
        current_tick=37,
    )
    runtime._episodic_stack.semantic_memory_store.add_by_being(
        being_id,
        SemanticMemoryEntry(
            entry_id="sem-runtime-1",
            player_id=player_id.value,
            text="古い棚には鍵が隠れていることがある",
            evidence_episode_ids=("ep-runtime-1",),
            confidence=0.72,
            created_at=_NOW,
            importance_score=8,
            tags=("library",),
        ),
    )
    runtime._episodic_stack.semantic_memory_store.register_cluster_signature_if_new_by_being(
        being_id,
        "spot:ancient_archive|tool:interact",
    )
    runtime._episodic_stack.pending_prediction_store.add_by_being(
        being_id,
        PendingPrediction(
            pending_id="pending-runtime-1",
            text="次に棚を調べれば鍵の手がかりが出る",
            resolution_cues=("spot:ancient_archive",),
            tick_from=38,
            tick_to=45,
            origin_episode_id="ep-runtime-1",
            created_tick=37,
            kind="plan",
        ),
    )
    runtime._goal_journal_store.add_by_being(
        being_id,
        GoalEntry(
            goal_id="goal-runtime-1",
            player_id=player_id.value,
            text="図書館から脱出する手がかりを見つける",
            status="active",
            locked=False,
            origin="self",
            created_tick=37,
            created_at=_NOW,
        ),
    )
    runtime._stagnation_pressure_store.increment_by_being(being_id)
    runtime._stagnation_pressure_store.increment_by_being(being_id)


def _world_snapshot_payload(runtime: Any, session: ExperimentSnapshotSession) -> dict[str, Any]:
    return session.world_snapshot_service.capture(
        runtime,
        source_scenario=_SCENARIO_NAME,
        world_tick=runtime.current_tick(),
        captured_at="2026-07-20T12:00:00+00:00",
    ).to_dict()


def _memory_payloads_by_being(
    runtime: Any, session: ExperimentSnapshotSession
) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for player_id in runtime.get_player_ids():
        being_id = _being_id(runtime, player_id)
        payloads[being_id.value] = json.loads(session._memory_snapshot.capture(being_id))
    return payloads


def test_experiment_snapshot_session_restores_state_across_real_world_runtimes(
    tmp_path: Path,
) -> None:
    """実 ``WorldRuntime`` A から保存した snapshot を B に戻すと主要状態が一致する。

    world 側は tick / 位置 / HP / needs / inventory / item_instance /
    spot_interior / sliding_window / action_result / encounter を、Being 側は
    semantic / pending_prediction / goal / stagnation を含む snapshot payload
    一式を照合する。
    """
    source_runtime = _create_runtime()
    _populate_runtime_state(source_runtime)
    source_session = _session(source_runtime, tmp_path / "source")

    expected_world = _world_snapshot_payload(source_runtime, source_session)
    expected_memory = _memory_payloads_by_being(source_runtime, source_session)
    source_session.capture_world(
        source_runtime,
        source_scenario=_SCENARIO_NAME,
        world_tick=source_runtime.current_tick(),
    )
    capture_report = source_session.capture_all(
        source_runtime.get_player_ids(),
        source_scenario=_SCENARIO_NAME,
    )
    assert capture_report.is_clean

    restored_runtime = _create_runtime()
    restored_session = _session(restored_runtime, tmp_path / "restored")
    restored_session.restore_world_from_dir(
        restored_runtime,
        tmp_path / "source",
        current_scenario=_SCENARIO_NAME,
    )
    restore_report = restored_session.restore_all_from_dir(
        tmp_path / "source",
        current_scenario=_SCENARIO_NAME,
    )
    assert sorted(b.value for b in restore_report.restored) == sorted(expected_memory)

    restored_world = _world_snapshot_payload(restored_runtime, restored_session)
    restored_memory = _memory_payloads_by_being(restored_runtime, restored_session)
    assert restored_world == expected_world
    assert restored_memory == expected_memory
    assert restored_runtime._item_repo.generate_item_instance_id().value > 9002

    player_world = expected_world["subsystems"]
    assert player_world["world_tick"]["world_tick"] == 37
    assert player_world["player_vitals"]["entries"][0]["hp_value"] == 73
    assert player_world["player_needs"]["entries"][0]["needs"][0]["value"] == 41
    assert player_world["player_inventory"]["entries"][0]["reserved_item_ids"] == [9001]
    assert player_world["item_instance"]["entries"] == [
        {
            "item_instance_id": 9001,
            "item_spec_id": 6,
            "quantity": 3,
            "durability_current": None,
            "state": {"source": "inventory", "fresh": True},
        },
        {
            "item_instance_id": 9002,
            "item_spec_id": 9,
            "quantity": 1,
            "durability_current": None,
            "state": {"source": "spot"},
        },
    ]
    assert player_world["spot_interior"]["entries"][0]["ground_items"] == [
        {"item_instance_id": 9002, "item_spec_id": 9}
    ]
    assert (
        player_world["action_result_store"]["entries"][0]["entries"][0][
            "prediction_context_id"
        ]
        == "predctx-runtime-roundtrip"
    )
    assert (
        player_world["encounter_memory"]["entries"][0]["records"][0]["key"]
        == "spot:ancient_archive"
    )

    being_payload = expected_memory["being_w1_p1"]
    assert being_payload["memo"][0]["content"] == "再開後も忘れてはいけない作業"
    assert being_payload["semantic_entries"][0]["entry_id"] == "sem-runtime-1"
    assert being_payload["pending_predictions"][0]["kind"] == "plan"
    assert being_payload["goal_journal"][0]["goal_id"] == "goal-runtime-1"
    assert being_payload["stagnation_pressure_count"] == [2]
