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


class TestUnknownEventIsRefusedLoudly:
    """規則の無いイベントを渡されたら黙って空を返さない。"""

    def test_resolving_an_event_without_a_rule_raises(self) -> None:
        """規則の無い型を resolve に渡すと例外になる。

        空リストを返すと「配信先が居ない」と区別がつかない。区別がつかないと、
        配線漏れが「たまたま誰も居なかった」に見えて run 分析から消える。
        """

        class _UnruledEvent:
            """どの配信規則にも載っていないイベントの代役。"""

        strategy = SpotGraphRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(
                event_to_strategy={_UnruledEvent: _STRATEGY_KEY}
            ),
            spot_graph_repository=None,  # type: ignore[arg-type]
            player_status_repository=None,  # type: ignore[arg-type]
        )

        with pytest.raises(KeyError):
            strategy.resolve(_UnruledEvent())
