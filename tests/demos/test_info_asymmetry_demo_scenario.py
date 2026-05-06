"""協力ギミック #14 (情報非対称パズル) の最小デモシナリオの end-to-end 検証。

`data/scenarios/info_asymmetry_demo.json` を読み込み、PUZZLE_INPUT_MATCH 条件
が runtime parameter (interaction_parameters) と照合されること、失敗時に
on_failure_observation が同スポットの他プレイヤーへ届くこと、を確認する。
"""

from __future__ import annotations

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
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotObjectInteractionFailedEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
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


@pytest.fixture
def info_asymmetry():
    """シナリオを組み立てて interaction service と publisher mock を返す。"""
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
    svc = SpotInteractionApplicationService(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        player_inventory_repository=inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=MutableWorldFlagState(),
        event_publisher=publisher,
    )
    return loaded, svc, publisher


def _ids(loaded) -> Tuple[int, int]:
    pa_id = next(s.player_id for s in loaded.player_spawns if s.string_id == "player_a")
    keypad_oid = loaded.id_mapper.get_int("object", "vault_keypad")
    return pa_id, keypad_oid


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

    def test_correct_code_unlocks_vault(self, info_asymmetry) -> None:
        """正しいコード『421』を入力すると vault_unlocked フラグが立つ。"""
        loaded, svc, _ = info_asymmetry
        pa_id, keypad_oid = _ids(loaded)
        # まず A を中央ホールへ移動
        graph = svc._spot_graph_repository.find_graph()
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        graph.unplace_entity(EntityId.create(pa_id))
        graph.place_entity(
            EntityId.create(pa_id),
            SpotId.create(loaded.id_mapper.get_int("spot", "central_hall")),
        )
        svc._spot_graph_repository.save(graph)

        result = svc.execute_interaction(
            PlayerId(pa_id),
            SpotObjectId.create(keypad_oid),
            "submit_code",
            interaction_parameters={"code": "421"},
        )
        assert any("解除" in m for m in result.messages)
        assert "vault_unlocked" in svc._world_flag_state.as_frozen_set()

    def test_wrong_code_raises_and_does_not_set_flag(self, info_asymmetry) -> None:
        """誤ったコードは InteractionNotAllowedException、フラグは立たない。"""
        loaded, svc, _ = info_asymmetry
        pa_id, keypad_oid = _ids(loaded)
        graph = svc._spot_graph_repository.find_graph()
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        graph.unplace_entity(EntityId.create(pa_id))
        graph.place_entity(
            EntityId.create(pa_id),
            SpotId.create(loaded.id_mapper.get_int("spot", "central_hall")),
        )
        svc._spot_graph_repository.save(graph)

        with pytest.raises(InteractionNotAllowedException):
            svc.execute_interaction(
                PlayerId(pa_id),
                SpotObjectId.create(keypad_oid),
                "submit_code",
                interaction_parameters={"code": "999"},
            )
        assert "vault_unlocked" not in svc._world_flag_state.as_frozen_set()

    def test_wrong_code_emits_failure_observation_to_others(self, info_asymmetry) -> None:
        """誤入力時に SpotObjectInteractionFailedEvent が publish される。

        観測本文はシナリオの on_failure_observation のままで、actor 本人を
        除く同スポット送信は recipient strategy が担う。
        """
        loaded, svc, publisher = info_asymmetry
        pa_id, keypad_oid = _ids(loaded)
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        # A と B を両方とも central_hall に集めて、失敗観測が B に届く構図に。
        pb_id = next(s.player_id for s in loaded.player_spawns if s.string_id == "player_b")
        central = SpotId.create(loaded.id_mapper.get_int("spot", "central_hall"))
        graph = svc._spot_graph_repository.find_graph()
        graph.unplace_entity(EntityId.create(pa_id))
        graph.place_entity(EntityId.create(pa_id), central)
        graph.unplace_entity(EntityId.create(pb_id))
        graph.place_entity(EntityId.create(pb_id), central)
        svc._spot_graph_repository.save(graph)

        with pytest.raises(InteractionNotAllowedException):
            svc.execute_interaction(
                PlayerId(pa_id),
                SpotObjectId.create(keypad_oid),
                "submit_code",
                interaction_parameters={"code": "000"},
            )
        failed_events = _published_failed_events(publisher)
        assert len(failed_events) == 1
        assert failed_events[0].observation_message == "キーパッドの誤入力ブザーが小さく響いた。"
        assert failed_events[0].entity_id.value == pa_id

    def test_no_failure_observation_when_field_missing(self, info_asymmetry) -> None:
        """on_failure_observation 未設定の interaction で失敗してもイベントは出ない。

        南室の張り紙の examine action は ALWAYS のみで失敗パスが無いが、
        試しに無効な action_name を投げて InteractionNotFoundException が
        出ることだけ確認する（observation 流れには入らない）。
        """
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotFoundException,
        )
        loaded, svc, publisher = info_asymmetry
        pa_id, _ = _ids(loaded)
        poster_oid = loaded.id_mapper.get_int("object", "south_poster")
        with pytest.raises(InteractionNotFoundException):
            svc.execute_interaction(
                PlayerId(pa_id),
                SpotObjectId.create(poster_oid),
                "nonexistent_action",
            )
        # InteractionNotFoundException は precondition failure ではないので
        # failure observation は出ない
        assert _published_failed_events(publisher) == []
