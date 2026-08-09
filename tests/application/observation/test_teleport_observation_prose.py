"""転移の観測が、宣言文があればそれを、無ければ既定文を出すことを保証する。

## なぜ差し替えなのか

`teleport_entity` は Left / Entered を発行し、formatter が既定文
「Xがこのスポットを去った。」「Xが〜にやってきた。」を組み立てる。宣言文を
別イベントで足すと**同じ移動が 2 回観測される**ので、既定文を置き換える。

宣言が無い転移 (隠し通路を黙って通る等) は既定文のまま動かない。
"""

from __future__ import annotations

from unittest.mock import MagicMock

# **この import を先頭に置くこと。** formatter 系を先に読むと
# contracts.interfaces が部分初期化のまま参照されて循環 import になる
# (既存の test_spot_graph_observation_pipeline.py と同じ並び)。
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.observation_formatter import (
    ObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    EntityEnteredSpotEvent,
    EntityLeftSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


_CORRIDOR = SpotId.create(1)
_ENGINE = SpotId.create(2)
_ACTOR = EntityId.create(7)
_WATCHER = PlayerId(9)


def _handler():
    """公開の formatter 経由で組む。

    handler を直接 import すると循環 import になるうえ、**実際に使われる経路と
    別のものを試験することになる。** 既存のパイプライン試験と同じ組み方に揃える。
    """
    name_resolver = MagicMock(spec=ObservationNameResolver)
    name_resolver.player_name.return_value = "クゼ"
    name_resolver.spot_name.side_effect = lambda sid: {
        int(_CORRIDOR): "連絡通路",
        int(_ENGINE): "機関室",
    }.get(int(sid), "不明なスポット")
    formatter = ObservationFormatter(spot_graph_repository=None)
    formatter._name_resolver = name_resolver
    formatter._context = ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
        spot_graph_repository=None,
    )
    from ai_rpg_world.application.observation.services.formatters.spot_graph_formatter import (
        SpotGraphObservationFormatter,
    )

    formatter._formatters = [SpotGraphObservationFormatter(formatter._context)]
    return formatter


def _left(message=None) -> EntityLeftSpotEvent:
    return EntityLeftSpotEvent.create(
        aggregate_id=SpotGraphId.create(1),
        aggregate_type="SpotGraphAggregate",
        entity_id=_ACTOR,
        spot_id=_CORRIDOR,
        to_spot_id=_ENGINE,
        observation_message=message,
    )


def _entered(message=None) -> EntityEnteredSpotEvent:
    return EntityEnteredSpotEvent.create(
        aggregate_id=SpotGraphId.create(1),
        aggregate_type="SpotGraphAggregate",
        entity_id=_ACTOR,
        spot_id=_ENGINE,
        from_spot_id=_CORRIDOR,
        observation_message=message,
    )


class TestDeclaredTeleportProse:
    """宣言文が既定文を置き換え、{actor} が実際の名前に展開される。"""

    def test_declared_departure_message_replaces_the_default(self) -> None:
        """出発の宣言文がある転移では、「去った」ではなく宣言文が出る。"""
        output = _handler().format(
            _left("{actor}がベントを開けて中に入った。"), _WATCHER
        )

        assert output is not None
        assert output.prose == "クゼがベントを開けて中に入った。"

    def test_declared_arrival_message_replaces_the_default(self) -> None:
        """到着の宣言文がある転移では、「やってきた」ではなく宣言文が出る。"""
        output = _handler().format(
            _entered("ベントが開いて{actor}が中から出てきた。"), _WATCHER
        )

        assert output is not None
        assert output.prose == "ベントが開いてクゼが中から出てきた。"

    def test_declared_message_without_actor_placeholder_is_used_verbatim(self) -> None:
        """暗所の文のように行為者を伏せる宣言は、名前を足さずそのまま出る。"""
        output = _handler().format(
            _entered("ベントが開いて誰かが出てきた音がした。"), _WATCHER
        )

        assert output is not None
        assert output.prose == "ベントが開いて誰かが出てきた音がした。"

    def test_movement_without_declaration_keeps_the_default_prose(self) -> None:
        """宣言の無い移動は従来どおりの文面のまま変わらない。"""
        output = _handler().format(_entered(), _WATCHER)

        assert output is not None
        assert "やってきた" in output.prose
