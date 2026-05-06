"""協力ギミック #14 (情報非対称パズル) の最小デモシナリオの end-to-end 検証。

`data/scenarios/info_asymmetry_demo.json` を読み込み、PUZZLE_INPUT_MATCH 条件
が runtime parameter (interaction_parameters) と照合されること、失敗時に
on_failure_observation が同スポットの他プレイヤーへ届くこと、を確認する。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotObjectInteractionFailedEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
    InteractionNotFoundException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import (
    InMemoryItemSpecRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "info_asymmetry_demo.json"
)


@dataclass
class _Harness:
    """テストが必要とする参照をまとめた構造体（private 属性アクセスを排除）。"""

    loaded: object
    svc: SpotInteractionApplicationService
    publisher: MagicMock
    spot_graph_repo: InMemorySpotGraphRepository
    world_flags: MutableWorldFlagState


@pytest.fixture
def info_asymmetry() -> _Harness:
    """シナリオを組み立てて harness を返す。"""
    loaded = ScenarioLoader().load_from_file(SCENARIO_PATH)
    graph = loaded.graph
    for spawn in loaded.player_spawns:
        graph.place_entity(EntityId.create(spawn.player_id), spawn.spawn_spot_id)
    graph.clear_events()

    spot_graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository()
    for sid, interior in loaded.interiors.items():
        interior_repo.save(sid, interior)
    data_store = InMemoryDataStore()
    inventory_repo = InMemoryPlayerInventoryRepository(data_store)
    item_repo = InMemoryItemRepository(data_store)
    item_spec_repo = InMemoryItemSpecRepository()
    for spawn in loaded.player_spawns:
        inventory_repo.save(PlayerInventoryAggregate(player_id=PlayerId(spawn.player_id)))

    publisher = MagicMock()
    flags = MutableWorldFlagState()
    svc = SpotInteractionApplicationService(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        player_inventory_repository=inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=flags,
        event_publisher=publisher,
    )
    return _Harness(
        loaded=loaded,
        svc=svc,
        publisher=publisher,
        spot_graph_repo=spot_graph_repo,
        world_flags=flags,
    )


def _ids(loaded) -> Tuple[int, int]:
    pa_id = next(s.player_id for s in loaded.player_spawns if s.string_id == "player_a")
    keypad_oid = loaded.id_mapper.get_int("object", "vault_keypad")
    return pa_id, keypad_oid


def _spot(loaded, string_id: str) -> SpotId:
    return SpotId.create(loaded.id_mapper.get_int("spot", string_id))


def _move_player(repo, eid: EntityId, target_spot: SpotId) -> None:
    """テスト用テレポート。public API (unplace + place) のみで実現。"""
    graph = repo.find_graph()
    graph.unplace_entity(eid)
    graph.place_entity(eid, target_spot)
    repo.save(graph)


def _published_failed_events(publisher) -> List[SpotObjectInteractionFailedEvent]:
    failed: List[SpotObjectInteractionFailedEvent] = []
    for call in publisher.publish_all.call_args_list:
        events = call.args[0]
        for ev in events:
            if isinstance(ev, SpotObjectInteractionFailedEvent):
                failed.append(ev)
    return failed


class TestInfoAsymmetryDemoScenario:
    """info_asymmetry_demo.json が #14 仕様通りに動く。"""

    def test_correct_code_unlocks_vault(self, info_asymmetry: _Harness) -> None:
        """正しいコード『421』を入力すると vault_unlocked フラグが立つ。"""
        pa_id, keypad_oid = _ids(info_asymmetry.loaded)
        _move_player(
            info_asymmetry.spot_graph_repo,
            EntityId.create(pa_id),
            _spot(info_asymmetry.loaded, "central_hall"),
        )
        result = info_asymmetry.svc.execute_interaction(
            PlayerId(pa_id),
            SpotObjectId.create(keypad_oid),
            "submit_code",
            interaction_parameters={"code": "421"},
        )
        assert any("解除" in m for m in result.messages)
        assert "vault_unlocked" in info_asymmetry.world_flags.as_frozen_set()

    def test_wrong_code_raises_and_does_not_set_flag(self, info_asymmetry: _Harness) -> None:
        """誤ったコードは InteractionNotAllowedException、フラグは立たない。"""
        pa_id, keypad_oid = _ids(info_asymmetry.loaded)
        _move_player(
            info_asymmetry.spot_graph_repo,
            EntityId.create(pa_id),
            _spot(info_asymmetry.loaded, "central_hall"),
        )
        with pytest.raises(InteractionNotAllowedException):
            info_asymmetry.svc.execute_interaction(
                PlayerId(pa_id),
                SpotObjectId.create(keypad_oid),
                "submit_code",
                interaction_parameters={"code": "999"},
            )
        assert "vault_unlocked" not in info_asymmetry.world_flags.as_frozen_set()

    def test_wrong_code_emits_failure_observation_to_others(
        self, info_asymmetry: _Harness
    ) -> None:
        """誤入力時に SpotObjectInteractionFailedEvent が publish される。

        観測本文はシナリオの on_failure_observation のままで、actor 本人を
        除く同スポット送信は recipient strategy が担う。
        """
        loaded = info_asymmetry.loaded
        pa_id, keypad_oid = _ids(loaded)
        # A と B を両方とも central_hall に集めて、失敗観測が B に届く構図に。
        pb_id = next(s.player_id for s in loaded.player_spawns if s.string_id == "player_b")
        central = _spot(loaded, "central_hall")
        _move_player(info_asymmetry.spot_graph_repo, EntityId.create(pa_id), central)
        _move_player(info_asymmetry.spot_graph_repo, EntityId.create(pb_id), central)

        with pytest.raises(InteractionNotAllowedException):
            info_asymmetry.svc.execute_interaction(
                PlayerId(pa_id),
                SpotObjectId.create(keypad_oid),
                "submit_code",
                interaction_parameters={"code": "000"},
            )
        failed_events = _published_failed_events(info_asymmetry.publisher)
        assert len(failed_events) == 1
        assert failed_events[0].observation_message == "キーパッドの誤入力ブザーが小さく響いた。"
        assert failed_events[0].entity_id.value == pa_id

    def test_no_failure_observation_when_action_does_not_exist(
        self, info_asymmetry: _Harness
    ) -> None:
        """InteractionNotFoundException は precondition 失敗ではないので failed event が出ない。

        on_failure_observation は precondition 経由の失敗にだけ反応する仕様
        を固定する。NotFound 例外はそもそも該当 InteractionDef が無いので
        on_failure_observation を引けない。
        """
        loaded = info_asymmetry.loaded
        pa_id, _ = _ids(loaded)
        poster_oid = loaded.id_mapper.get_int("object", "south_poster")
        with pytest.raises(InteractionNotFoundException):
            info_asymmetry.svc.execute_interaction(
                PlayerId(pa_id),
                SpotObjectId.create(poster_oid),
                "nonexistent_action",
            )
        assert _published_failed_events(info_asymmetry.publisher) == []

    def test_silent_when_event_publisher_is_none(self) -> None:
        """event_publisher=None の場合は失敗観測は静かにスキップ（クラッシュしない）。"""
        loaded = ScenarioLoader().load_from_file(SCENARIO_PATH)
        graph = loaded.graph
        for spawn in loaded.player_spawns:
            graph.place_entity(EntityId.create(spawn.player_id), spawn.spawn_spot_id)
        graph.clear_events()
        spot_graph_repo = InMemorySpotGraphRepository(graph)
        interior_repo = InMemorySpotInteriorRepository()
        for sid, interior in loaded.interiors.items():
            interior_repo.save(sid, interior)
        data_store = InMemoryDataStore()
        inventory_repo = InMemoryPlayerInventoryRepository(data_store)
        item_repo = InMemoryItemRepository(data_store)
        item_spec_repo = InMemoryItemSpecRepository()
        for spawn in loaded.player_spawns:
            inventory_repo.save(PlayerInventoryAggregate(player_id=PlayerId(spawn.player_id)))
        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=interior_repo,
            player_inventory_repository=inventory_repo,
            item_repository=item_repo,
            item_spec_repository=item_spec_repo,
            world_flag_state=MutableWorldFlagState(),
            event_publisher=None,  # ← 重要
        )
        pa_id, keypad_oid = _ids(loaded)
        _move_player(spot_graph_repo, EntityId.create(pa_id), _spot(loaded, "central_hall"))
        # 例外は出るが、publisher=None でも静かにスキップしてクラッシュしないこと
        with pytest.raises(InteractionNotAllowedException):
            svc.execute_interaction(
                PlayerId(pa_id),
                SpotObjectId.create(keypad_oid),
                "submit_code",
                interaction_parameters={"code": "000"},
            )
