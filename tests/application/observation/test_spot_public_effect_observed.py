"""Phase 4-E PR 3: SpotPublicEffectObservedEvent の配信先解決と formatter 出力。

汎用 public observable event は AppliedEffectKind ごとに人向けプロセを切り替え、
actor は二重観測防止のため除外される。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.spot_graph_formatter import (
    SpotGraphObservationFormatter,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.spot_graph_recipient_strategy import (
    SpotGraphRecipientStrategy,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionCreatedEvent,
    ConnectionDestroyedEvent,
    SpotPublicEffectObservedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectKind,
    StateDeltaEntry,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(999)
SPOT_A = SpotId(1)
SPOT_B = SpotId(2)
PLAYER_1 = PlayerId(1)
PLAYER_2 = PlayerId(2)
PLAYER_3 = PlayerId(3)
ENTITY_1 = EntityId.create(1)


def _make_strategy(entity_spot_mapping: dict) -> SpotGraphRecipientStrategy:
    registry_map = {
        SpotPublicEffectObservedEvent: "spot_graph",
        ConnectionCreatedEvent: "spot_graph",
        ConnectionDestroyedEvent: "spot_graph",
    }
    registry = ObservedEventRegistry(event_to_strategy=registry_map)

    graph = MagicMock()
    graph.entity_spot_mapping.return_value = {
        EntityId.create(eid): SpotId(sid)
        for eid, sid in entity_spot_mapping.items()
    }
    repo = MagicMock()
    repo.find_graph.return_value = graph

    statuses = []
    for pid in entity_spot_mapping:
        s = MagicMock()
        s.player_id = PlayerId(pid)
        statuses.append(s)
    player_status_repo = MagicMock()
    player_status_repo.find_all.return_value = statuses

    return SpotGraphRecipientStrategy(
        observed_event_registry=registry,
        spot_graph_repository=repo,
        player_status_repository=player_status_repo,
    )


def _make_formatter() -> SpotGraphObservationFormatter:
    name_resolver = MagicMock()
    name_resolver.player_name = lambda pid: f"player{pid.value}"

    graph = MagicMock()
    spot_a = MagicMock()
    spot_a.name = "酒場"
    spot_b = MagicMock()
    spot_b.name = "倉庫"
    graph.get_spot = lambda sid: spot_a if sid == SPOT_A else spot_b
    repo = MagicMock()
    repo.find_graph.return_value = graph

    ctx = ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
        spot_graph_repository=repo,
    )
    return SpotGraphObservationFormatter(ctx)


class TestPublicEffectRecipient:
    """SpotPublicEffectObservedEvent の配信先解決。"""

    def test_excludes_actor(self) -> None:
        """actor は同 spot に居ても配信先から除外される。"""
        strategy = _make_strategy({1: 1, 2: 1, 3: 2})
        event = SpotPublicEffectObservedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            actor_entity_id=ENTITY_1,
            kind=AppliedEffectKind.DAMAGE,
            description="5のダメージを受けた",
            target_ref="",
            state_delta=(),
        )
        ids = {r.value for r in strategy.resolve(event)}
        assert 1 not in ids  # actor 除外
        assert 2 in ids
        assert 3 not in ids

    def test_includes_all_when_actor_unknown(self) -> None:
        """actor 不明 (None) なら同 spot 全員配信。"""
        strategy = _make_strategy({1: 1, 2: 1})
        event = SpotPublicEffectObservedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            actor_entity_id=None,
            kind=AppliedEffectKind.ATMOSPHERE_UPDATE,
            description="部屋が暗くなった",
            target_ref="1",
            state_delta=(),
        )
        ids = {r.value for r in strategy.resolve(event)}
        assert 1 in ids
        assert 2 in ids


class TestPublicEffectFormatter:
    """kind ごとに観測プロセが組み立てられる。"""

    def test_damage_renders_with_actor_name(self) -> None:
        """DAMAGE は「<actor>が<description>」プロセになる。"""
        formatter = _make_formatter()
        event = SpotPublicEffectObservedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            actor_entity_id=ENTITY_1,
            kind=AppliedEffectKind.DAMAGE,
            description="炎で焼けた",
            target_ref="",
            state_delta=(),
        )
        out = formatter.format(event, PLAYER_2)
        assert out is not None
        assert "player1" in out.prose
        assert "炎で焼けた" in out.prose
        assert out.observation_category == "social"

    def test_atmosphere_update_uses_spot_name_and_delta(self) -> None:
        """ATMOSPHERE_UPDATE は spot 名 + state_delta から具体プロセを組み立てる。

        summary.description は「スポット {int_id} の雰囲気が変化した」という
        汎用文字列で読みづらいため、formatter 側で spot 名を解決して使う。
        """
        formatter = _make_formatter()
        event = SpotPublicEffectObservedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            actor_entity_id=ENTITY_1,
            kind=AppliedEffectKind.ATMOSPHERE_UPDATE,
            description="スポット 1 の雰囲気が変化した",
            target_ref="1",
            state_delta=(StateDeltaEntry(key="lighting", before="DIM", after="DARK"),),
        )
        out = formatter.format(event, PLAYER_2)
        assert out is not None
        # spot 名 (酒場) が出る
        assert "酒場" in out.prose
        # state_delta が反映されている
        assert "lighting" in out.prose
        assert "DARK" in out.prose
        # 整数 spot_id が漏れない
        assert "スポット 1" not in out.prose
        assert out.observation_category == "environment"

    def test_target_item_state_change_renders_delta(self) -> None:
        """TARGET_ITEM_STATE_CHANGE は state_delta を載せる。"""
        formatter = _make_formatter()
        event = SpotPublicEffectObservedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            actor_entity_id=ENTITY_1,
            kind=AppliedEffectKind.TARGET_ITEM_STATE_CHANGE,
            description="作用したアイテムの状態が変化した",
            target_ref="チェスト",
            state_delta=(StateDeltaEntry(key="locked", before=True, after=False),),
        )
        out = formatter.format(event, PLAYER_2)
        assert out is not None
        assert "チェスト" in out.prose
        assert "locked" in out.prose

    def test_actor_self_returns_none(self) -> None:
        """actor 本人には観測を生成しない (二重ガード)。"""
        formatter = _make_formatter()
        event = SpotPublicEffectObservedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            spot_id=SPOT_A,
            actor_entity_id=ENTITY_1,
            kind=AppliedEffectKind.DAMAGE,
            description="痛い",
            target_ref="",
            state_delta=(),
        )
        assert formatter.format(event, PLAYER_1) is None


class TestConnectionEventsObservation:
    """既に graph aggregate が emit している ConnectionCreated/Destroyed が
    観測経路に乗ることを確認する (PR 2 までは未登録だった)。"""

    def test_connection_created_recipient_includes_both_ends(self) -> None:
        strategy = _make_strategy({1: 1, 2: 2, 3: 3})  # 1 in spot1, 2 in spot2
        event = ConnectionCreatedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=ConnectionId.create(99),
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
        )
        ids = {r.value for r in strategy.resolve(event)}
        assert 1 in ids
        assert 2 in ids
        assert 3 not in ids

    def test_connection_created_formatter_renders_spot_names(self) -> None:
        formatter = _make_formatter()
        event = ConnectionCreatedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=ConnectionId.create(99),
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
        )
        out = formatter.format(event, PLAYER_1)
        assert out is not None
        assert "酒場" in out.prose
        assert "倉庫" in out.prose
        assert "通路" in out.prose or "現れた" in out.prose
        assert out.observation_category == "environment"

    def test_connection_destroyed_formatter(self) -> None:
        formatter = _make_formatter()
        event = ConnectionDestroyedEvent.create(
            aggregate_id=GRAPH_ID,
            aggregate_type="SpotGraphAggregate",
            connection_id=ConnectionId.create(99),
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
        )
        out = formatter.format(event, PLAYER_1)
        assert out is not None
        assert "酒場" in out.prose
        assert "崩れた" in out.prose or "消えた" in out.prose
