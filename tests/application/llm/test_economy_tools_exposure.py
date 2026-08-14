"""売買ツールを、商人を宣言した世界にだけ出す (経済統合 Phase 1)。

宣言の無い世界に buy_item が並ぶと、対象候補が永久に空なのに毎ターン選択肢に
載る。会議を宣言しない世界から投票を落とすのと同じ判断で、露出の可否は
``ToolExposure`` だけが決める。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ai_rpg_world.application.llm.tool_exposure import (
    ALWAYS_PRESENT_TOOL_ORDER,
    ToolExposure,
)


@dataclass(frozen=True)
class _Scenario:
    """ToolExposure.from_scenario が読む最小限の形。"""

    disabled_tools: Tuple[str, ...] = ()
    synchronized_action_groups: Tuple[str, ...] = ()
    merchants: Tuple[object, ...] = ()


def _exposure(**kwargs) -> ToolExposure:
    return ToolExposure.from_scenario(_Scenario(**kwargs), meeting_declared=False)


class TestEconomyToolsFollowTheMerchantDeclaration:
    """buy_item / sell_item の露出が merchants 宣言に従う。"""

    def test_economy_tools_are_exposed_when_merchants_are_declared(self) -> None:
        """商人を宣言した世界では buy_item と sell_item が露出する。"""
        exposure = _exposure(merchants=(object(),))

        assert exposure.is_exposed("buy_item")
        assert exposure.is_exposed("sell_item")

    def test_economy_tools_are_hidden_without_merchants(self) -> None:
        """商人を宣言していない世界では、どちらも露出しない。"""
        exposure = _exposure()

        assert not exposure.is_exposed("buy_item")
        assert not exposure.is_exposed("sell_item")

    def test_a_scenario_can_disable_only_buying(self) -> None:
        """disabled_tools で buy_item だけ落とすと、sell_item は残る。"""
        exposure = _exposure(merchants=(object(),), disabled_tools=("buy_item",))

        assert not exposure.is_exposed("buy_item")
        assert exposure.is_exposed("sell_item")

    def test_economy_tools_are_dropped_during_a_meeting(self) -> None:
        """会議中は売買ツールをフェーズ固有ブロックに出さない。"""
        exposure = _exposure(merchants=(object(),))

        assert not exposure.is_available_in_phase("buy_item", in_meeting=True)
        assert exposure.is_available_in_phase("buy_item", in_meeting=False)

    def test_economy_tools_are_not_phase_common(self) -> None:
        """売買ツールは常在ブロックに入らない (会議中に残らない)。"""
        assert not ToolExposure.is_phase_common("buy_item")
        assert not ToolExposure.is_phase_common("sell_item")


class TestPrefixCacheIsNotDisturbed:
    """売買ツールの追加が、常在ブロックの並びを動かさない。"""

    def test_always_present_block_does_not_contain_economy_tools(self) -> None:
        """常在ブロックの並びは従来のままで、売買ツールを含まない。"""
        assert ALWAYS_PRESENT_TOOL_ORDER == (
            "wait",
            "speak",
            "memo_add",
            "memo_list",
            "memo_done",
        )

    def test_economy_tools_are_ordered_after_the_existing_conditional_tools(self) -> None:
        """売買ツールは条件付きブロックの既存ツールより後ろに並ぶ。

        既存ツールの相対順が動くと、payload 先頭からの一致が切れて過去 run と
        比較できなくなる。
        """
        ordered = ToolExposure.order_for_payload(
            ("sell_item", "give_item", "buy_item", "travel_to"),
        )

        assert ordered.index("travel_to") < ordered.index("give_item")
        assert ordered.index("give_item") < ordered.index("buy_item")
        assert ordered.index("buy_item") < ordered.index("sell_item")
