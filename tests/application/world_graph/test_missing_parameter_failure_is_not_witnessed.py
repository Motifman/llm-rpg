"""操作に要る引数が渡されずに断られたとき、同じ場所の他の人へ失敗の観測を出さないことを保証する (#1607)。

引数が無いのは道具の呼び方の誤りで、世界では何も起きていない (design_decisions D1591)。
本人にはツールの結果として案内が返るので、目撃者に配る出来事が無い。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from tests.support.command_scope_fakes import (
    install_passthrough_spot_interaction_constructor,
)

from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotObjectInteractionFailedEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
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

_WRITER = 1
_WITNESS = 2
_SPOT = SpotId.create(1)
_SIGN = SpotObjectId.create(20)


@pytest.fixture(autouse=True)
def _bind_command_scope(monkeypatch) -> None:
    install_passthrough_spot_interaction_constructor(
        monkeypatch, SpotInteractionApplicationService
    )


def _write(action_name: str, *, preconditions=(), on_failure_observation=None):
    return InteractionDef(
        action_name=action_name,
        display_label="書き込む",
        preconditions=preconditions,
        effects=(
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
                parameters={},
            ),
        ),
        on_failure_observation=on_failure_observation,
    )


def _service_with_a_sign():
    sign = SpotObject(
        object_id=_SIGN,
        name="古い看板",
        description="d",
        object_type=SpotObjectTypeEnum.SIGN,
        state={},
        interactions=(
            _write("write"),
            _write("write_loudly", on_failure_observation="誰かが看板の前で立ち止まった。"),
            _write(
                "write_by_lamplight",
                preconditions=(
                    InteractionCondition(
                        condition_type=InteractionConditionTypeEnum.FLAG_SET,
                        flag_name="lamp_lit",
                        failure_message="暗くて字が書けない。",
                    ),
                ),
            ),
        ),
    )
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(
        SpotNode(
            spot_id=_SPOT, name="広場", description="d",
            category=SpotCategoryEnum.OTHER, parent_id=None,
        )
    )
    for player in (_WRITER, _WITNESS):
        graph.place_entity(EntityId.create(player), _SPOT)
    graph.clear_events()
    interiors = InMemorySpotInteriorRepository()
    interiors.save(_SPOT, SpotInterior((), (sign,), (), ()))
    data_store = InMemoryDataStore()
    inventories = InMemoryPlayerInventoryRepository(data_store)
    inventories.save(PlayerInventoryAggregate(player_id=PlayerId(_WRITER)))
    publisher = MagicMock()
    service = SpotInteractionApplicationService(
        spot_graph_repository=InMemorySpotGraphRepository(graph),
        spot_interior_repository=interiors,
        player_inventory_repository=inventories,
        item_repository=InMemoryItemRepository(data_store),
        item_spec_repository=InMemoryItemSpecRepository(),
        world_flag_state=MutableWorldFlagState(),
        event_publisher=publisher,
    )
    return service, publisher


def _failed_events(publisher: MagicMock) -> list[SpotObjectInteractionFailedEvent]:
    return [
        event
        for call in publisher.publish_all.call_args_list
        for event in call.args[0]
        if isinstance(event, SpotObjectInteractionFailedEvent)
    ]


def _attempt(service, action_name: str, parameters: dict) -> InteractionNotAllowedException:
    with pytest.raises(InteractionNotAllowedException) as caught:
        service.execute_interaction(
            PlayerId(_WRITER),
            _SIGN,
            action_name,
            interaction_parameters=parameters,
            current_tick=WorldTick(3),
        )
    return caught.value


class TestMissingTextOnASign:
    """看板に書く操作で text が無いときと、前提条件で断られたときの、目撃者への失敗の観測の違いを保証する。"""

    @pytest.mark.parametrize("action_name", ["write", "write_loudly"])
    def test_missing_text_returns_guidance_to_the_writer_and_publishes_no_failure(
        self, action_name: str
    ) -> None:
        """text を渡さずに看板に書こうとすると、本人には text の案内を返し、シナリオが目撃者向けの失敗の文を宣言していても失敗の観測を出さない。"""
        service, publisher = _service_with_a_sign()

        refusal = _attempt(service, action_name, {})

        assert "text" in str(refusal)
        assert _failed_events(publisher) == []

    def test_precondition_refusal_still_publishes_a_failure(self) -> None:
        """text を渡しても前提条件で断られたときは、これまでどおり前提条件の文を載せた失敗の観測を出す。"""
        service, publisher = _service_with_a_sign()

        _attempt(service, "write_by_lamplight", {"text": "水場は北"})

        failures = _failed_events(publisher)
        assert [f.failure_reason for f in failures] == ["暗くて字が書けない。"]
