"""ObservationRecipientResolver のテスト（正常・観測対象外・境界・例外）"""

from unittest.mock import MagicMock

import pytest

# observation.contracts.interfaces と prompt_builder_config の循環 import を避けるため、
# observation service を直接 import する単体テストでは prompt_builder を先に初期化する。
from ai_rpg_world.application.llm.services import prompt_builder as _prompt_builder  # noqa: F401
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    ObservationRecipientResolver,
    create_observation_recipient_resolver,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.player_audience_query_service import (
    PlayerAudienceQueryService,
)
from ai_rpg_world.application.observation.services.recipient_strategies import (
    DefaultRecipientStrategy,
)
from ai_rpg_world.application.player.services.player_perception_policy import (
    PlayerPerceptionPolicy,
)
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.event.inventory_events import ItemAddedToInventoryEvent
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerGoldEarnedEvent,
    PlayerLevelUpEvent,
    PlayerLocationChangedEvent,
    PlayerRevivedEvent,
)
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)


def _make_status(player_id: int, spot_id: int = 1) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(1000),
        hp=Hp.create(100, 100),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100),
        navigation_state=PlayerNavigationState.from_parts(
            current_spot_id=SpotId(spot_id),
            current_coordinate=Coordinate(0, 0, 0),
        ),
    )


class TestObservationRecipientResolver:
    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def resolver(self, status_repo):
        return create_observation_recipient_resolver(
            player_status_repository=status_repo,
        )

    def test_resolve_player_location_changed_includes_actor_and_players_at_target_spot(self, resolver, status_repo):
        """PlayerLocationChangedEvent: 本人と new_spot にいるプレイヤーが配信先"""
        status_repo.save(_make_status(1, spot_id=1))
        status_repo.save(_make_status(2, spot_id=2))
        status_repo.save(_make_status(3, spot_id=2))
        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(0, 0, 0),
        )
        ids = resolver.resolve(event)
        assert len(ids) >= 1
        values = [p.value for p in ids]
        assert 1 in values
        assert 2 in values
        assert 3 in values

    def test_resolve_player_location_changed_deduplicates_recipients_when_same_player_in_multiple_sources(
        self, resolver, status_repo
    ):
        """同一プレイヤーが複数ソース（本人＋同一スポット）で含まれる場合、重複せず1回のみ配信先に含まれる"""
        status_repo.save(_make_status(1, spot_id=2))
        status_repo.save(_make_status(2, spot_id=2))
        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(0, 0, 0),
        )
        ids = resolver.resolve(event)
        values = [p.value for p in ids]
        assert 1 in values
        assert 2 in values
        assert values.count(1) == 1
        assert values.count(2) == 1
        assert len(ids) == 2

    def test_resolve_player_level_up_returns_aggregate_player(self, resolver, status_repo):
        """PlayerLevelUpEvent: aggregate_id のプレイヤーが配信先"""
        status_repo.save(_make_status(1))
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        ids = resolver.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 1

    def test_resolve_player_gold_earned_returns_aggregate_player(self, resolver, status_repo):
        """PlayerGoldEarnedEvent: aggregate_id のプレイヤーが配信先"""
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(5),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        ids = resolver.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 5

    def test_resolve_item_added_inventory_returns_aggregate_player(self, resolver):
        """ItemAddedToInventoryEvent: aggregate_id が配信先"""
        event = ItemAddedToInventoryEvent.create(
            aggregate_id=PlayerId(3),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId(1),
        )
        ids = resolver.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 3

    def test_resolve_unknown_event_returns_empty_list(self, resolver):
        """観測対象外・未知のイベントは空リスト"""

        class UnknownEvent:
            pass

        ids = resolver.resolve(UnknownEvent())
        assert ids == []

    def test_resolve_with_empty_strategies_returns_empty_list(self):
        """戦略が空の Resolver はどのイベントでも空リストを返す"""
        resolver = ObservationRecipientResolver(strategies=[])
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        ids = resolver.resolve(event)
        assert ids == []

    def test_resolve_player_location_changed_includes_self_and_players_at_new_spot(self, resolver, status_repo):
        """PlayerLocationChangedEvent: 本人と new_spot_id にいるプレイヤー"""
        status_repo.save(_make_status(1, spot_id=1))
        status_repo.save(_make_status(2, spot_id=2))
        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(0, 0, 0),
        )
        ids = resolver.resolve(event)
        values = [p.value for p in ids]
        assert 1 in values
        assert 2 in values

    # --- WorldObjectId → PlayerId 解決（ResourceHarvested / LocationExited / WorldObjectInteracted）---

    # --- 例外ケース（リポジトリが例外を投げた場合は伝播）---

    def test_resolve_when_player_audience_query_raises_propagates(self, data_store):
        """PlayerAudienceQuery.players_at_spot が例外を投げた場合、その例外が伝播する"""
        audience_query = MagicMock()
        audience_query.players_at_spot.side_effect = RuntimeError("find_all failed")
        registry = ObservedEventRegistry()
        default_strategy = DefaultRecipientStrategy(
            observed_event_registry=registry,
            player_audience_query=audience_query,
        )
        resolver = ObservationRecipientResolver(strategies=[default_strategy])
        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(1, 1, 0),
        )
        with pytest.raises(RuntimeError, match="find_all failed"):
            resolver.resolve(event)


class TestDefaultRecipientStrategy:
    """DefaultRecipientStrategy の単体テスト（supports / resolve）"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def strategy(self, status_repo):
        audience_query = PlayerAudienceQueryService(
            player_status_repository=status_repo,
        )
        registry = ObservedEventRegistry()
        return DefaultRecipientStrategy(
            observed_event_registry=registry,
            player_audience_query=audience_query,
        )

    def test_supports_player_location_changed_event(self, strategy):
        """PlayerLocationChangedEvent を supports する"""
        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(0, 0, 0),
        )
        assert strategy.supports(event) is True

    def test_supports_player_level_up_event(self, strategy):
        """PlayerLevelUpEvent を supports する"""
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        assert strategy.supports(event) is True

    def test_supports_returns_false_for_unknown_event(self, strategy):
        """未知のイベントでは supports が False"""

        class UnknownEvent:
            pass

        assert strategy.supports(UnknownEvent()) is False

    def test_resolve_player_level_up_returns_aggregate_id(self, strategy):
        """PlayerLevelUpEvent の resolve が aggregate_id を返す"""
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(7),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        ids = strategy.resolve(event)
        assert len(ids) == 1
        assert ids[0].value == 7

    def test_player_downed_event_self_spot_other_player_broadcast(self, strategy, status_repo):
        """ダウンは位置に関わらず全 known player に届く。

        同 spot 目撃者だけに限定すると、単独で倒れた player の異常を誰も
        知らず、ハートビート頼みになる。prose の詳細度は formatter 側で
        位置に応じて分ける。
        """
        status_repo.save(_make_status(1, spot_id=10))  # downed
        status_repo.save(_make_status(2, spot_id=10))  # same spot
        status_repo.save(_make_status(3, spot_id=10))  # same spot
        status_repo.save(_make_status(4, spot_id=20))  # different spot

        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=None,
        )
        ids = strategy.resolve(event)
        id_values = {pid.value for pid in ids}
        assert 1 in id_values  # 本人
        assert 2 in id_values  # 目撃者
        assert 3 in id_values  # 目撃者
        assert 4 in id_values  # 遠隔者にも気配として届く

    def test_player_downed_event_unknown_status_still_reaches_known_players(self, strategy, status_repo):
        """downed 本人が status_repo に居なくても、既知 player には異変を共有する。

        P1-E 後半では down を全 being 共有するため、位置不明でも本人だけに
        閉じない。prose 側は遠隔・位置不明として気配文に倒す。
        """
        status_repo.save(_make_status(1, spot_id=10))
        status_repo.save(_make_status(2, spot_id=20))
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(99),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=None,
        )
        ids = strategy.resolve(event)
        id_values = {pid.value for pid in ids}
        assert id_values == {99, 1, 2}

    def test_player_revived_event_reaches_all_known_players(self, strategy, status_repo):
        """復帰も位置に関わらず全 known player に届く。"""
        status_repo.save(_make_status(1, spot_id=10))
        status_repo.save(_make_status(2, spot_id=20))
        status_repo.save(_make_status(3, spot_id=30))
        event = PlayerRevivedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            hp_recovered=30,
            total_hp=100,
        )

        ids = strategy.resolve(event)

        assert {pid.value for pid in ids} == {1, 2, 3}

    def test_create_resolver_delivers_downed_to_all_known_players_with_spot_graph(self, status_repo):
        """spot_graph 注入時も downed は全 known player に共有される。"""
        status_repo.save(_make_status(1, spot_id=1))
        status_repo.save(_make_status(2, spot_id=1))
        status_repo.save(_make_status(3, spot_id=1))
        graph = MagicMock()
        graph.entity_spot_mapping.return_value = {
            EntityId.create(1): SpotId(5),
            EntityId.create(2): SpotId(5),
            EntityId.create(3): SpotId(9),
        }
        graph.get_entity_spot.return_value = SpotId(5)
        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            spot_graph_repository=spot_graph_repo,
        )
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=None,
        )

        ids = resolver.resolve(event)

        assert {pid.value for pid in ids} == {1, 2, 3}


class TestObservationRecipientResolverPerceptionPlane:
    """最終配信先が共通の知覚方針を通ることを固定する。"""

    @staticmethod
    def _resolver(*, dead_player_id: int) -> ObservationRecipientResolver:
        outcomes = PlayerOutcomeRegistry.new_for_players([PlayerId(1), PlayerId(2)])
        outcomes.set_outcome(PlayerId(dead_player_id), PlayerOutcomeEnum.DEAD)
        policy = PlayerPerceptionPolicy(
            outcome_registry=outcomes,
            departed_agents_enabled=True,
        )
        strategy = MagicMock()
        strategy.supports.return_value = True
        strategy.resolve.return_value = [PlayerId(1), PlayerId(2)]
        life_query = MagicMock()
        life_query.can_receive_world_observation.side_effect = lambda player_id: player_id.value != dead_player_id
        return ObservationRecipientResolver(
            strategies=[strategy],
            player_life_query=life_query,
            player_perception_policy=policy,
        )

    def test_living_recipient_does_not_receive_a_departed_players_event(self) -> None:
        """同じ既存配信範囲でも、生者には幽霊を主体とする観測を届けない。"""
        resolver = self._resolver(dead_player_id=2)
        event = MagicMock()
        event.aggregate_type = "PlayerStatusAggregate"
        event.aggregate_id = PlayerId(2)

        recipients = resolver.resolve(event)

        assert recipients == [PlayerId(2)]

    def test_departed_recipient_receives_a_living_players_event(self) -> None:
        """幽霊は従来の倒れた人除外を越え、既存範囲内の生者の観測を受け取る。"""
        resolver = self._resolver(dead_player_id=2)
        event = MagicMock()
        event.aggregate_type = "PlayerStatusAggregate"
        event.aggregate_id = PlayerId(1)

        recipients = resolver.resolve(event)

        assert recipients == [PlayerId(1), PlayerId(2)]
