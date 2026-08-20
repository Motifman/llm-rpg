"""配信先解決の表が、レジストリの割り当てと一致していることを保証する。

## なぜこの網が要るか

観測の配信先は 2 段構えになっている。

1. ``ObservedEventRegistry`` が「このイベントはどの strategy が担当するか」を持つ
2. その strategy が「誰に届けるか」を決める

1 に登録したのに 2 に規則を書き忘れると、``supports()`` は True を返し、
``resolve()`` は空リストを返す。例外は出ず、テストも緑のまま、**そのイベントは
誰にも観測されない**。倒れている者の除外が strategy ごとに書かれていて実 run
008 で漏れた (死んだ者が生者の声を拾った) のと同じ、「1 つ足した人が忘れる」形。

イベント型は 124 個ある。取引・売買・依頼のような要素を組み込むほど増えるので、
増やすたびに人間が突き合わせる形では続かない。ここでレジストリを回して強制する。

## 表を採用した strategy を足すとき

``_TABLE_DRIVEN`` に 1 行足すだけで、下の全テストが自動で対象にする。
期待表 (``expected_rules``) には **production とは独立に**、どのイベントにどの
規則を当てるかを書く。網羅テストはキーの有無しか見ないので、規則の取り違えは
期待表でしか捕まらない (実測: `spot_graph` で規則を 1 つ差し替えても全
13,307 件が緑だった)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies._dispatch import (
    RecipientRuleWiringError,
    blank_reasons,
)
from ai_rpg_world.application.observation.services.recipient_strategies.default_recipient_strategy import (
    _RECIPIENT_RULES as _DEFAULT_RULES,
    DefaultRecipientStrategy,
)
from ai_rpg_world.domain.monster.event.monster_events import (
    MonsterDiedEvent,
    MonsterEvadedEvent,
    MonsterFedEvent,
    MonsterHealedEvent,
    MonsterSpawnedEvent,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.application.observation.services.recipient_strategies.monster_recipient_strategy import (
    _DELIVERS_TO_NOBODY as _MONSTER_NOBODY,
    _RECIPIENT_RULES as _MONSTER_RULES,
    MonsterRecipientStrategy,
)
from ai_rpg_world.application.observation.services.recipient_strategies.spot_graph_recipient_strategy import (
    _RECIPIENT_RULES as _SPOT_GRAPH_RULES,
    SpotGraphRecipientStrategy,
)


@dataclass(frozen=True)
class _TableDrivenStrategy:
    """表引きを採用した strategy 1 つ分の検査対象。"""

    key: str
    strategy_class: type
    rules: Mapping[type, object]
    expected_rules: Mapping[str, str]
    delivers_to_nobody: Mapping[type, str] = field(default_factory=dict)
    #: ``__init__`` の第 2 引数以降を埋める代役を作る関数。
    extra_dependencies: tuple = ()

    def __str__(self) -> str:  # pytest の id に使う
        return self.key

    def nobody_types(self) -> tuple:
        """「誰にも配らない」型を公開アクセサ経由で取る (無い strategy は空)。"""
        accessor = getattr(
            self.strategy_class, "event_types_delivered_to_nobody", None
        )
        return tuple(accessor()) if accessor is not None else ()

    def build(self, registry: ObservedEventRegistry):
        """この strategy を、必要な依存を代役で埋めて構築する。"""
        return self.strategy_class(registry, *(f() for f in self.extra_dependencies))


_SPOT_GRAPH_EXPECTED = {
    "EntityEnteredSpotEvent": "_deliver_to_others_at_the_event_spot",
    "EntityLeftSpotEvent": "_deliver_to_others_at_the_event_spot",
    "SpotObjectInteractionFailedEvent": "_deliver_to_others_at_the_event_spot",
    "PlayerGaveItemEvent": "_deliver_to_others_at_the_event_spot",
    "PlayerTradedWithMerchantEvent": "_deliver_to_others_at_the_event_spot",
    "PlayerTradeOfferEvent": "_deliver_to_everyone_at_the_event_spot",
    # 板の動きは板の前の人へ。加えて、その場に居なくても知るべき当事者
    # (売れた売り手 / 流れた注文の持ち主) にだけ個別に届ける。
    "MarketBoardActivityEvent": "_deliver_market_activity",
    # 取り落としは本人にも届ける。置いた側と違い、本人が知らないと拾い直せない。
    "PlayerOverflowedItemEvent": "_deliver_to_everyone_at_the_event_spot",
    # 届かなかった品の行き先は買い手にだけ。板の前の人には「地面に品が
    # 増えた」以上の意味が無く、買い手には払ったのに品が無い理由になる。
    "MarketDeliveryLeftAtBoardEvent": "_deliver_only_to_the_subject",
    "SpotPlayerPreparedActionEvent": "_deliver_to_others_at_the_event_spot",
    "SpotExploredEvent": "_deliver_to_others_at_the_event_spot",
    "SpotPlayerStateChangedInSpotEvent": "_deliver_to_others_at_the_event_spot",
    "SpotObjectInteractedEvent": "_deliver_to_others_only_when_witnessed",
    "PlayerDroppedItemEvent": "_deliver_to_others_only_when_witnessed",
    "PlayerPickedUpItemEvent": "_deliver_to_others_only_when_witnessed",
    "PlayerInteractedWithPlayerEvent": "_deliver_interpersonal_action",
    "SpotObjectStateChangedEvent": "_deliver_excluding_the_actor_if_known",
    "SpotPublicEffectObservedEvent": "_deliver_excluding_the_actor_if_known",
    "ConnectionStateChangedEvent": "_resolve_connection_changed",
    "ConnectionCreatedEvent": "_deliver_to_both_ends_of_the_connection",
    "ConnectionDestroyedEvent": "_deliver_to_both_ends_of_the_connection",
    "MeetingVoteResolvedEvent": "_deliver_to_everyone_in_the_world",
    "GamePhaseChangedEvent": "_deliver_to_everyone_in_the_world",
    "TimeOfDayChangedEvent": "_deliver_to_everyone_in_the_world",
    "MeetingVoteCastEvent": "_deliver_vote_progress_to_the_other_voters",
    "MonsterAppearedAtSpotEvent": "_deliver_to_everyone_at_the_event_spot",
    "MonsterLeftSpotEvent": "_deliver_to_everyone_at_the_event_spot",
    "MonsterAttackedPlayerInSpotEvent": "_deliver_to_everyone_at_the_event_spot",
    "MonsterAteGroundItemEvent": "_deliver_to_everyone_at_the_event_spot",
    "MonsterPredatedMonsterInSpotEvent": "_deliver_to_everyone_at_the_event_spot",
    "MonsterStartedFleeingInSpotEvent": "_deliver_to_everyone_at_the_event_spot",
    "MonsterStartedChasingInSpotEvent": "_deliver_to_everyone_at_the_event_spot",
    "MonsterAbandonedChaseInSpotEvent": "_deliver_to_everyone_at_the_event_spot",
    "MonsterFeltTemperatureDiscomfortInSpotEvent": "_deliver_to_everyone_at_the_event_spot",
    "MonsterRespondedToPackHelpInSpotEvent": "_deliver_to_everyone_at_the_event_spot",
    "MonsterFollowedPackFleeInSpotEvent": "_deliver_to_everyone_at_the_event_spot",
    "MonsterAlertedByPackInSpotEvent": "_deliver_to_everyone_at_the_event_spot",
    "PlayerAttackedMonsterInSpotEvent": "_deliver_to_others_excluding_the_attacker",
    "SpotSoundHeardEvent": "_deliver_only_to_the_listener",
    "SpotPresenceListenedEvent": "_deliver_only_to_the_listener",
}

_DEFAULT_EXPECTED = {
    "LocationEnteredEvent": "_resolve_location_entered",
    "LocationExitedEvent": "_resolve_location_exited",
    "PlayerLocationChangedEvent": "_resolve_player_location_changed",
    "PlayerDownedEvent": "_deliver_to_everyone_known",
    "PlayerRevivedEvent": "_deliver_to_everyone_known",
    "PlayerLevelUpEvent": "_deliver_only_to_the_subject",
    "PlayerGoldEarnedEvent": "_deliver_only_to_the_subject",
    "PlayerGoldPaidEvent": "_deliver_only_to_the_subject",
    "ItemAddedToInventoryEvent": "_deliver_only_to_the_subject",
    "ItemDroppedFromInventoryEvent": "_deliver_only_to_the_subject",
    "ItemEquippedEvent": "_deliver_only_to_the_subject",
    "ItemUnequippedEvent": "_deliver_only_to_the_subject",
    "InventorySlotOverflowEvent": "_deliver_only_to_the_subject",
    "ItemTakenFromChestEvent": "_deliver_only_to_the_acting_player",
    "ItemStoredInChestEvent": "_resolve_item_stored_in_chest",
    "ResourceHarvestedEvent": "_deliver_only_to_the_player_behind_the_actor",
    "WorldObjectInteractedEvent": "_deliver_only_to_the_player_behind_the_actor",
    "SpotWeatherChangedEvent": "_resolve_spot_weather_changed",
}

_MONSTER_EXPECTED = {
    "MonsterSpawnedEvent": "_deliver_to_everyone_at_the_declared_spot",
    "MonsterRespawnedEvent": "_deliver_to_everyone_at_the_declared_spot",
    "MonsterDiedEvent": "_deliver_death_to_the_spot_and_the_killer",
    "MonsterDamagedEvent": "_deliver_damage_to_the_spot_and_the_attacker",
    "MonsterEvadedEvent": "_deliver_to_everyone_at_the_monsters_spot",
    "MonsterHealedEvent": "_deliver_to_everyone_at_the_monsters_spot",
    "MonsterFedEvent": "_deliver_to_everyone_at_the_actors_spot",
    "ActorStateChangedEvent": "_deliver_to_everyone_at_the_actors_spot",
}

#: 表引きを採用した strategy。移植したら 1 行足す。
_TABLE_DRIVEN = [
    _TableDrivenStrategy(
        key="spot_graph",
        strategy_class=SpotGraphRecipientStrategy,
        rules=_SPOT_GRAPH_RULES,
        expected_rules=_SPOT_GRAPH_EXPECTED,
        # spot_graph_repository, player_status_repository
        extra_dependencies=(MagicMock, MagicMock),
    ),
    _TableDrivenStrategy(
        key="default",
        strategy_class=DefaultRecipientStrategy,
        rules=_DEFAULT_RULES,
        expected_rules=_DEFAULT_EXPECTED,
        # player_audience_query, world_object_to_player_resolver
        extra_dependencies=(MagicMock, MagicMock),
    ),
    _TableDrivenStrategy(
        key="monster",
        strategy_class=MonsterRecipientStrategy,
        rules=_MONSTER_RULES,
        expected_rules=_MONSTER_EXPECTED,
        delivers_to_nobody=_MONSTER_NOBODY,
        # player_audience_query, physical_map_repository,
        # world_object_to_player_resolver
        extra_dependencies=(MagicMock, MagicMock, MagicMock),
    ),
]


@pytest.fixture(params=_TABLE_DRIVEN, ids=str)
def target(request: pytest.FixtureRequest) -> _TableDrivenStrategy:
    return request.param


class TestDispatchCoversTheRegistry:
    """レジストリが割り当てた全イベント型に、規則か「配らない」宣言がある。"""

    def test_every_registered_event_type_is_accounted_for(
        self, target: _TableDrivenStrategy
    ) -> None:
        """担当と登録された全イベント型が、規則の表か例外表に載っている。

        どちらにも無い型は ``supports()`` が True を返すのに配信先が空になり、
        観測が誰にも届かないまま気づけない。
        """
        registered = ObservedEventRegistry().get_event_types_for_strategy(target.key)
        declared = set(target.strategy_class.handled_event_types()) | set(
            target.nobody_types()
        )
        missing = sorted(t.__name__ for t in registered if t not in declared)

        assert not missing, (
            f"[{target.key}] レジストリが割り当てているのに配信先が決まらない"
            "イベント型があります: " + ", ".join(missing)
        )

    def test_no_rule_points_at_an_unregistered_event_type(
        self, target: _TableDrivenStrategy
    ) -> None:
        """表に、レジストリが割り当てていない型が残っていない。

        余った規則は決して呼ばれない。担当が別 strategy へ移ったのに規則だけ
        残っていると、読んだ人はここで配信されていると誤解する。
        """
        registered = set(ObservedEventRegistry().get_event_types_for_strategy(target.key))
        declared = set(target.strategy_class.handled_event_types()) | set(
            target.nobody_types()
        )
        stale = sorted(t.__name__ for t in declared if t not in registered)

        assert not stale, (
            f"[{target.key}] レジストリが割り当てていないイベント型の宣言が"
            "残っています: " + ", ".join(stale)
        )

    def test_reasons_for_delivering_to_nobody_are_written(
        self, target: _TableDrivenStrategy
    ) -> None:
        """「誰にも配らない」理由が空文字列でない。

        理由欄があっても空で登録できるなら「登録すれば無検査で通る」抜け道が
        残る。中身の妥当さはレビューが見るしかないが、空は機械で落とせる。
        """
        blank = blank_reasons(target.delivers_to_nobody)

        assert not blank, f"[{target.key}] 配らない理由が書かれていません: {blank}"


class TestEachEventKeepsItsRule:
    """どのイベントにどの規則を当てるかが、意図した対応から変わっていない。"""

    def test_expected_table_matches_production(
        self, target: _TableDrivenStrategy
    ) -> None:
        """production の規則表と期待表のキーが一致している。

        片方だけ増えると、増えた側の対応が誰にも確認されないまま通る。
        """
        actual = {t.__name__ for t in target.rules}
        expected = set(target.expected_rules)

        assert actual == expected, (
            f"[{target.key}] production のみ: {sorted(actual - expected)} / "
            f"期待表のみ: {sorted(expected - actual)}"
        )

    def test_every_event_is_delivered_by_the_expected_rule(
        self, target: _TableDrivenStrategy
    ) -> None:
        """各イベント型が、意図した配信規則に紐付いている。

        規則を取り違えると配信先が別物になる (例: 同席者全員 → 本人だけ)。
        取り違えは表の 1 行の差し替えで起きるので、ここで固定する。網羅テストは
        キーの有無しか見ないため、これが無いと取り違えを検出できない。
        """
        by_name = {t.__name__: rule for t, rule in target.rules.items()}
        wrong = sorted(
            f"{name}: 期待 {expected} / 実際 {by_name[name].__name__}"
            for name, expected in target.expected_rules.items()
            if by_name[name].__name__ != expected
        )

        assert not wrong, f"[{target.key}] 規則が取り違えられています: " + " / ".join(wrong)


class TestWiringGapIsRefusedBeforeTheRunStarts:
    """規則の無いイベント型が担当と登録されていたら、構築時に落ちる。

    表引きを採用した **全 strategy** について確かめる。以前は spot_graph だけを
    直接構築していて、default / monster から検査呼び出しを消しても全 6,181 件が
    緑のままだとレビューで実証された。「壊れた状態で始めない」がこの仕組みの
    存在理由なのに、3 つのうち 2 つで固定されていなかった。
    """

    def test_constructing_with_an_unruled_event_type_raises(
        self, target: _TableDrivenStrategy
    ) -> None:
        """規則の無い型を担当と宣言したレジストリでは strategy を構築できない。

        run 中に落とすのでは遅い。LLM ツール経路は ``_execute_tool`` を広い
        ``except Exception`` で囲んでおり、そこを通った例外は
        ``LLM_TOOL_EXECUTION_FAILED`` という汎用のツール失敗に化けて、配線漏れが
        エージェントの操作ミスと同じ見え方になる。さらに
        ``_process_graph_events`` は ``clear_events()`` を先に呼ぶので、バッチ
        途中で落ちると残りのイベントが復元不能になる。
        """

        class _UnruledEvent:
            """どの配信規則にも載っていないイベントの代役。"""

        with pytest.raises(RecipientRuleWiringError) as exc:
            target.build(
                ObservedEventRegistry(event_to_strategy={_UnruledEvent: target.key})
            )

        assert "_UnruledEvent" in str(exc.value)

    def test_the_default_registry_constructs_cleanly(
        self, target: _TableDrivenStrategy
    ) -> None:
        """既定のレジストリでは構築が通る (検査が常に落ちる形になっていない)。

        正の対照。上の検査が何でも落とすだけなら、配線が正しいことを主張
        できていない。
        """
        strategy = target.build(ObservedEventRegistry())

        assert strategy is not None


class TestEventsDeliveredToNobodyReturnNoRecipients:
    """「誰にも配らない」と宣言した型が、実際に空リストを返す。"""

    @pytest.mark.parametrize(
        "event_type", sorted(_MONSTER_NOBODY, key=lambda t: t.__name__),
        ids=lambda t: t.__name__,
    )
    def test_resolving_returns_no_recipients(self, event_type: type) -> None:
        """宣言した 8 型すべてで ``resolve()`` が空リストを返す。

        宣言は表にあるだけでは効かない。実行時の分岐
        (``if type(event) in _DELIVERS_TO_NOBODY``) を通ることを、型ごとに確かめる。
        以前は 8 型のうち 3 型しか実挙動が確認されておらず、残り 5 型は表を
        規則側へ移しても気づけなかった。
        """
        audience = MagicMock()
        audience.players_at_spot.return_value = [PlayerId(1), PlayerId(2)]
        strategy = MonsterRecipientStrategy(
            ObservedEventRegistry(), audience, MagicMock(), MagicMock()
        )

        recipients = strategy.resolve(event_type.__new__(event_type))

        assert recipients == []


class TestMonsterRulesComputeRealRecipients:
    """monster の各配信規則が、実際に誰を選ぶか。"""

    def _strategy(self, audience, monster_spot=None, actor_spot=None):
        monster_repo = MagicMock()
        monster_repo.find_by_id.return_value = (
            MagicMock(spot_id=monster_spot) if monster_spot is not None else None
        )
        physical_map = MagicMock()
        physical_map.find_spot_id_by_object_id.return_value = actor_spot
        return MonsterRecipientStrategy(
            ObservedEventRegistry(), audience, physical_map, MagicMock(), monster_repo
        )

    def test_spawn_uses_the_spot_on_the_event(self) -> None:
        """出現はイベントの ``spot_id`` に居る全員へ届く (monster を引き直さない)。"""
        audience = MagicMock()
        audience.players_at_spot.return_value = [PlayerId(1), PlayerId(2)]
        strategy = self._strategy(audience)
        event = MonsterSpawnedEvent.__new__(MonsterSpawnedEvent)
        object.__setattr__(event, "spot_id", SpotId(7))

        recipients = strategy.resolve(event)

        assert [p.value for p in recipients] == [1, 2]
        audience.players_at_spot.assert_called_once_with(SpotId(7))

    def test_evade_looks_the_spot_up_from_the_monster(self) -> None:
        """回避はイベントに spot が無いので monster を引いて場所を決める。"""
        audience = MagicMock()
        audience.players_at_spot.return_value = [PlayerId(3)]
        strategy = self._strategy(audience, monster_spot=SpotId(9))
        event = MonsterEvadedEvent.__new__(MonsterEvadedEvent)
        object.__setattr__(event, "aggregate_id", MagicMock())

        recipients = strategy.resolve(event)

        assert [p.value for p in recipients] == [3]
        audience.players_at_spot.assert_called_once_with(SpotId(9))

    def test_death_adds_the_killer_on_top_of_the_spot(self) -> None:
        """死は場所の全員に加えて、離れている倒した本人にも届く。"""
        audience = MagicMock()
        audience.players_at_spot.return_value = [PlayerId(1)]
        strategy = self._strategy(audience)
        event = MonsterDiedEvent.__new__(MonsterDiedEvent)
        object.__setattr__(event, "spot_id", SpotId(4))
        object.__setattr__(event, "aggregate_id", MagicMock())
        object.__setattr__(event, "killer_player_id", PlayerId(5))

        recipients = strategy.resolve(event)

        assert [p.value for p in recipients] == [1, 5]

    def test_death_does_not_duplicate_a_killer_who_is_present(self) -> None:
        """倒した本人が同席していても 1 回しか入らない。

        以前は重複を残して返し、外側の resolver が除いていた。見えない差は
        検証できないので、内側で除く契約に揃えた。
        """
        audience = MagicMock()
        audience.players_at_spot.return_value = [PlayerId(1), PlayerId(5)]
        strategy = self._strategy(audience)
        event = MonsterDiedEvent.__new__(MonsterDiedEvent)
        object.__setattr__(event, "spot_id", SpotId(4))
        object.__setattr__(event, "aggregate_id", MagicMock())
        object.__setattr__(event, "killer_player_id", PlayerId(5))

        recipients = strategy.resolve(event)

        assert [p.value for p in recipients] == [1, 5]

    def test_fed_looks_the_spot_up_from_the_actor(self) -> None:
        """採食は ``actor_id`` の world object から場所を引く。"""
        audience = MagicMock()
        audience.players_at_spot.return_value = [PlayerId(8)]
        strategy = self._strategy(audience, actor_spot=SpotId(2))
        event = MonsterFedEvent.__new__(MonsterFedEvent)
        object.__setattr__(event, "actor_id", MagicMock())

        recipients = strategy.resolve(event)

        assert [p.value for p in recipients] == [8]
        audience.players_at_spot.assert_called_once_with(SpotId(2))

    def test_nobody_is_reached_when_the_spot_cannot_be_resolved(self) -> None:
        """場所が判らないときは誰にも届けない (リポジトリ未注入の経路)。"""
        audience = MagicMock()
        strategy = self._strategy(audience, monster_spot=None)
        event = MonsterHealedEvent.__new__(MonsterHealedEvent)
        object.__setattr__(event, "aggregate_id", MagicMock())

        recipients = strategy.resolve(event)

        assert recipients == []
        audience.players_at_spot.assert_not_called()
