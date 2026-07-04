"""`spot_graph_listen` ツールの統合テスト (Phase 5 PR-2)。

executor → SpotGraphAggregate.emit_listen_carefully → event_publisher.publish_all
の経路が期待通り動くかを検証する。

検証:
- 自 spot に音がある + 隣接 spot に音がある → 2 件 publish
- どこにも音が無い → 0 件 publish + 「何も聞こえなかった」メッセージ
- spot_graph_repository / event_publisher が未配線なら UNSUPPORTED_TOOL
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.sound_intensity_enum import (
    SoundIntensityEnum,
)
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotSoundHeardEvent,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)
SPOT_B = SpotId.create(2)


def _node(
    spot_id: SpotId, *,
    intensity: SoundIntensityEnum = SoundIntensityEnum.SILENT,
    ambient: str | None = None,
) -> SpotNode:
    return SpotNode(
        spot_id=spot_id, name=f"spot{spot_id.value}", description="",
        category=SpotCategoryEnum.OTHER, parent_id=None,
        atmosphere=SpotAtmosphere(
            lighting=LightingEnum.BRIGHT,
            sound_ambient=ambient,
            temperature=TemperatureEnum.NORMAL,
            smell=None,
            sound_intensity=intensity,
        ),
    )


def _build_executor(graph: SpotGraphAggregate, event_publisher) -> SpotGraphToolExecutor:
    """executor を最小依存で組み立てる。listen 以外のハンドラは触らないので
    他のリポジトリは MagicMock で十分。
    """
    spot_graph_repo = MagicMock()
    spot_graph_repo.find_graph.return_value = graph

    services = MagicMock()
    services.movement = MagicMock()  # コンストラクタで `is None` チェックが入るため

    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
        event_publisher=event_publisher,
        spot_graph_repository=spot_graph_repo,
    )


class TestListenCarefullyHappyPath:
    """自 spot と隣接 spot に音があれば 2 件 publish される。"""

    def test_自_spot_と_隣接_spot_両方_で_event_publish(self) -> None:
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A, intensity=SoundIntensityEnum.MODERATE, ambient="A音"))
        g.add_spot(_node(SPOT_B, intensity=SoundIntensityEnum.LOUD, ambient="B音"))
        g.add_connection(SpotConnection(
            connection_id=ConnectionId.create(10),
            from_spot_id=SPOT_A, to_spot_id=SPOT_B,
            name="path", description="", travel_ticks=1,
            is_bidirectional=False, passage=Passage.open(),
        ))
        eid = EntityId.create(7)
        g.place_entity(eid, SPOT_A)
        g.clear_events()  # 入場 event を捨てる

        publisher = MagicMock()
        executor = _build_executor(g, publisher)

        result = executor._listen(7, {"inner_thought": "聞いてみる"})

        assert result.success is True
        assert "2 箇所" in result.message
        # publish_all が呼ばれ、SpotSoundHeardEvent が 2 件
        publisher.publish_all.assert_called_once()
        published = publisher.publish_all.call_args[0][0]
        sound_events = [e for e in published if isinstance(e, SpotSoundHeardEvent)]
        assert len(sound_events) == 2
        # aggregate の event はクリアされている
        assert g.get_events() == []


class TestListenCarefullySilent:
    """どこにも音が無い場合: publish なし、「何も聞こえなかった」メッセージ。"""

    def test_全_spot_SILENT_では_publish_なし(self) -> None:
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A))  # SILENT
        g.add_spot(_node(SPOT_B))  # SILENT
        g.add_connection(SpotConnection(
            connection_id=ConnectionId.create(10),
            from_spot_id=SPOT_A, to_spot_id=SPOT_B,
            name="path", description="", travel_ticks=1,
            is_bidirectional=False, passage=Passage.open(),
        ))
        eid = EntityId.create(7)
        g.place_entity(eid, SPOT_A)
        g.clear_events()

        publisher = MagicMock()
        executor = _build_executor(g, publisher)

        result = executor._listen(7, {"inner_thought": ""})

        assert result.success is True
        assert "何も聞こえなかった" in result.message
        publisher.publish_all.assert_not_called()


class TestListenCarefullyUnwired:
    """spot_graph_repository / event_publisher が未配線なら UNSUPPORTED_TOOL。"""

    def test_event_publisher_未配線_は_失敗(self) -> None:
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A, intensity=SoundIntensityEnum.MODERATE))
        services = MagicMock()
        services.movement = MagicMock()
        executor = SpotGraphToolExecutor(
            spot_graph_world_services=services,
            player_inventory_repository=MagicMock(),
            item_repository=MagicMock(),
            event_publisher=None,
            spot_graph_repository=MagicMock(),
        )

        result = executor._listen(7, {"inner_thought": ""})

        assert result.success is False
        assert result.error_code == "UNSUPPORTED_TOOL"

    def test_spot_graph_repository_未配線_は_失敗(self) -> None:
        services = MagicMock()
        services.movement = MagicMock()
        executor = SpotGraphToolExecutor(
            spot_graph_world_services=services,
            player_inventory_repository=MagicMock(),
            item_repository=MagicMock(),
            event_publisher=MagicMock(),
            spot_graph_repository=None,
        )

        result = executor._listen(7, {"inner_thought": ""})

        assert result.success is False
        assert result.error_code == "UNSUPPORTED_TOOL"


class TestListenCarefullyHandlerRegistration:
    """get_handlers() に listen ハンドラが登録される。"""

    def test_get_handlers_に_listen_が_登録される(self) -> None:
        services = MagicMock()
        services.movement = MagicMock()
        executor = SpotGraphToolExecutor(
            spot_graph_world_services=services,
            player_inventory_repository=MagicMock(),
            item_repository=MagicMock(),
        )
        handlers = executor.get_handlers()
        assert "listen" in handlers
