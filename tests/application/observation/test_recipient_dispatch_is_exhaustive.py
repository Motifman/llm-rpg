"""配信先解決の分岐が、レジストリの割り当てと一致していることを保証する。

## なぜこの網が要るか

観測の配信先は 2 段構えになっている。

1. ``ObservedEventRegistry`` が「このイベントはどの strategy が担当するか」を持つ
2. その strategy が「誰に届けるか」を決める

1 に登録したのに 2 に規則を書き忘れると、``supports()`` は True を返し、
``resolve()`` は空リストを返す。例外は出ず、テストも緑のまま、**そのイベントは
誰にも観測されない**。倒れている者の除外が strategy ごとに書かれていて実 run
008 で漏れた (死んだ者が生者の声を拾った) のと同じ、「1 つ足した人が忘れる」形。

イベント型は 124 個あり、``spot_graph`` だけで 35 個を担当する。#925 系
(非同期 Decision/Intent) や #931 (外見知覚) でさらに増えるので、増やすたびに
人間が突き合わせる形では続かない。ここでレジストリを回して強制する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.spot_graph_recipient_strategy import (
    _RECIPIENT_RULES,
    RecipientRuleWiringError,
    SpotGraphRecipientStrategy,
)

_STRATEGY_KEY = "spot_graph"


def _registered_event_types() -> tuple[type, ...]:
    return ObservedEventRegistry().get_event_types_for_strategy(_STRATEGY_KEY)


class TestSpotGraphDispatchCoversTheRegistry:
    """レジストリが spot_graph に割り当てた全イベント型に配信規則がある。"""

    def test_every_registered_event_type_has_a_rule(self) -> None:
        """spot_graph 担当の全イベント型が配信規則の表に載っている。

        載っていない型は ``supports()`` が True を返すのに配信先が空になり、
        観測が誰にも届かないまま気づけない。
        """
        handled = set(SpotGraphRecipientStrategy.handled_event_types())
        missing = sorted(
            t.__name__ for t in _registered_event_types() if t not in handled
        )

        assert not missing, (
            "レジストリが spot_graph に割り当てているのに、配信規則が無い"
            "イベント型があります。observation が誰にも届きません: " + ", ".join(missing)
        )

    def test_no_rule_points_at_an_unregistered_event_type(self) -> None:
        """配信規則の表に、レジストリが spot_graph に割り当てていない型が無い。

        余った規則は決して呼ばれない。担当が別 strategy へ移ったのに規則だけ
        残っていると、読んだ人はここで配信されていると誤解する。
        """
        registered = set(_registered_event_types())
        stale = sorted(
            t.__name__
            for t in SpotGraphRecipientStrategy.handled_event_types()
            if t not in registered
        )

        assert not stale, (
            "レジストリが spot_graph に割り当てていないイベント型の規則が"
            "残っています: " + ", ".join(stale)
        )


class TestWiringGapIsRefusedBeforeTheRunStarts:
    """規則の無いイベント型が担当と登録されていたら、構築時に落ちる。"""

    def test_constructing_with_an_unruled_event_type_raises(self) -> None:
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
            SpotGraphRecipientStrategy(
                observed_event_registry=ObservedEventRegistry(
                    event_to_strategy={_UnruledEvent: _STRATEGY_KEY}
                ),
                spot_graph_repository=None,  # type: ignore[arg-type]
                player_status_repository=None,  # type: ignore[arg-type]
            )

        assert "_UnruledEvent" in str(exc.value)

    def test_the_default_registry_constructs_cleanly(self) -> None:
        """既定のレジストリでは構築が通る (検査が常に落ちる形になっていない)。

        正の対照。上の検査が何でも落とすだけなら、配線が正しいことを主張
        できていない。
        """
        strategy = SpotGraphRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            spot_graph_repository=None,  # type: ignore[arg-type]
            player_status_repository=None,  # type: ignore[arg-type]
        )

        assert strategy is not None


#: イベント型 → そのイベントを配る規則の名前。**production の表とは独立に、
#: 期待する対応をここへ書く。**
#:
#: 網羅テスト (上) はキーの有無しか見ないので、規則を取り違えても落ちない。
#: 実測: `MonsterFeltTemperatureDiscomfortInSpotEvent` の規則を「同席者全員」
#: から「聞いた本人だけ」へ差し替えても、全 13,307 件が緑のままだった。
#: 「同席者全員が目撃する」観測が「本人しか気づかない」に変わっても誰も
#: 気づけない = このリファクタが潰そうとしている静かな失敗そのもの。
#:
#: 各規則が実際に誰を選ぶかは、規則ごとの振る舞いテストが持つ
#: (`test_spot_graph_recipient_strategy.py` ほか)。ここは「どのイベントに
#: どの規則を当てるか」だけを固定する。
_EXPECTED_RULE_NAMES: dict[str, str] = {
    "EntityEnteredSpotEvent": "_deliver_to_others_at_the_event_spot",
    "EntityLeftSpotEvent": "_deliver_to_others_at_the_event_spot",
    "SpotObjectInteractionFailedEvent": "_deliver_to_others_at_the_event_spot",
    "PlayerGaveItemEvent": "_deliver_to_others_at_the_event_spot",
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


class TestEachEventKeepsItsRule:
    """どのイベントにどの配信規則を当てるかが、意図した対応から変わっていない。"""

    def test_expected_table_covers_every_rule_in_production(self) -> None:
        """production の表と期待表のキーが一致している。

        片方だけ増えると、増えた側の対応が誰にも確認されないまま通る。
        """
        actual = {t.__name__ for t in _RECIPIENT_RULES}
        expected = set(_EXPECTED_RULE_NAMES)

        assert actual == expected, (
            f"production のみ: {sorted(actual - expected)} / "
            f"期待表のみ: {sorted(expected - actual)}"
        )

    @pytest.mark.parametrize(
        ("event_type_name", "expected_rule_name"),
        sorted(_EXPECTED_RULE_NAMES.items()),
        ids=lambda v: v,
    )
    def test_event_is_delivered_by_the_expected_rule(
        self, event_type_name: str, expected_rule_name: str
    ) -> None:
        """各イベント型が、意図した配信規則に紐付いている。

        規則を取り違えると配信先が別物になる (例: 同席者全員 → 本人だけ)。
        取り違えは表の 1 行の差し替えで起きるので、ここで固定する。
        """
        by_name = {t.__name__: rule for t, rule in _RECIPIENT_RULES.items()}

        assert by_name[event_type_name].__name__ == expected_rule_name
