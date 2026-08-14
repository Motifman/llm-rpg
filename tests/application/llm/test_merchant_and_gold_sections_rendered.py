"""商人と所持金が「現在の状況」に出るか (経済統合 Phase 1)。

商人を宣言した世界では、同席している商人の品揃えと価格、および自分の所持金が
状況確認に出る。宣言していない世界では、どちらの節も 1 行も出ない
(過去 run との比較可能性を保つため)。
"""

from __future__ import annotations

from typing import Any, Dict, List

from ai_rpg_world.application.llm.services.prompt_section_layout import (
    FREE_ROAM_SECTIONS,
    MEETING_SECTIONS,
    PromptSection,
)
from ai_rpg_world.application.llm.services._label_allocator import LabelAllocator
from ai_rpg_world.application.llm.services._runtime_target_collector import (
    RuntimeTargetCollector,
)
from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphMerchantEntry,
    SpotGraphMerchantPriceEntry,
    SpotGraphPlayerSnapshotDto,
)


def _gustav() -> SpotGraphMerchantEntry:
    return SpotGraphMerchantEntry(
        merchant_id=1,
        name="商人グスタフ",
        sells=(SpotGraphMerchantPriceEntry(item_name="パン", price=10),),
        buys=(SpotGraphMerchantPriceEntry(item_name="薬草", price=6),),
    )


def _make_snapshot(**overrides: Any) -> SpotGraphPlayerSnapshotDto:
    defaults: Dict[str, Any] = {
        "current_spot_id": 0,
        "current_spot_name": "",
        "current_spot_description": "",
        "travel_status_line": "",
    }
    defaults.update(overrides)
    return SpotGraphPlayerSnapshotDto(**defaults)


def _render_merchants(snap: SpotGraphPlayerSnapshotDto) -> List[str]:
    lines: List[str] = []
    SpotGraphUiContextBuilder()._build_merchant_section(
        snap, LabelAllocator(), RuntimeTargetCollector(), lines,
    )
    return lines


def _render_gold(snap: SpotGraphPlayerSnapshotDto) -> List[str]:
    lines: List[str] = []
    SpotGraphUiContextBuilder()._build_gold_section(snap, lines)
    return lines


class TestMerchantSection:
    """商人節が、同席している商人の品揃えと価格を出す挙動を保証する。"""

    def test_merchant_at_spot_is_listed_with_prices(self) -> None:
        """同席している商人の名前・売値・買値が、名前を引用符で囲んだ形で出る。"""
        lines = _render_merchants(
            _make_snapshot(economy_declared=True, merchants_at_spot=(_gustav(),)),
        )

        joined = "\n".join(lines)
        assert "商人:" in joined
        assert '"商人グスタフ"' in joined
        assert '売: "パン" 10G' in joined
        assert '買: "薬草" 6G' in joined

    def test_sell_only_merchant_omits_the_buy_line(self) -> None:
        """買い取りをしない商人には買値の行を出さない (空の行で場所を取らない)。"""
        merchant = SpotGraphMerchantEntry(
            merchant_id=1,
            name="商人グスタフ",
            sells=(SpotGraphMerchantPriceEntry(item_name="パン", price=10),),
            buys=(),
        )

        joined = "\n".join(
            _render_merchants(
                _make_snapshot(economy_declared=True, merchants_at_spot=(merchant,)),
            )
        )

        assert '売: "パン" 10G' in joined
        assert "買:" not in joined

    def test_buy_only_merchant_omits_the_sell_line(self) -> None:
        """売り物を持たない商人には売値の行を出さない。"""
        merchant = SpotGraphMerchantEntry(
            merchant_id=1,
            name="商人グスタフ",
            sells=(),
            buys=(SpotGraphMerchantPriceEntry(item_name="薬草", price=6),),
        )

        joined = "\n".join(
            _render_merchants(
                _make_snapshot(economy_declared=True, merchants_at_spot=(merchant,)),
            )
        )

        assert '買: "薬草" 6G' in joined
        assert "売:" not in joined

    def test_multiple_price_entries_are_joined_on_one_line(self) -> None:
        """同じ商人が複数の品を売るとき、売値は 1 行にスラッシュ区切りで並ぶ。"""
        merchant = SpotGraphMerchantEntry(
            merchant_id=1,
            name="商人グスタフ",
            sells=(
                SpotGraphMerchantPriceEntry(item_name="パン", price=10),
                SpotGraphMerchantPriceEntry(item_name="薬草の束", price=25),
            ),
        )

        joined = "\n".join(
            _render_merchants(
                _make_snapshot(economy_declared=True, merchants_at_spot=(merchant,)),
            )
        )

        assert '売: "パン" 10G / "薬草の束" 25G' in joined

    def test_two_merchants_at_one_spot_are_both_listed(self) -> None:
        """同じ spot に商人が 2 人居れば、2 人とも一覧に出る。"""
        hilda = SpotGraphMerchantEntry(
            merchant_id=2,
            name="商人ヒルダ",
            sells=(SpotGraphMerchantPriceEntry(item_name="ランタン", price=40),),
        )

        joined = "\n".join(
            _render_merchants(
                _make_snapshot(
                    economy_declared=True, merchants_at_spot=(_gustav(), hilda),
                ),
            )
        )

        assert '"商人グスタフ"' in joined
        assert '"商人ヒルダ"' in joined

    def test_absence_is_stated_when_the_world_declares_merchants(self) -> None:
        """商人を宣言した世界で商人の居ない場所に立つと、居ないことを明示する。

        黙って節を消すと「商人が居ない」と「まだ見つけていない」が区別できず、
        探し回って手番を溶かす。
        """
        joined = "\n".join(
            _render_merchants(_make_snapshot(economy_declared=True, merchants_at_spot=())),
        )

        assert "商人: (この場所には居ない)" in joined

    def test_nothing_is_rendered_when_the_world_declares_no_merchants(self) -> None:
        """商人を宣言していない世界では、商人節を 1 行も出さない。

        その世界には商人という概念が無いので、不在を明示すると宣言なしの
        既存シナリオの prompt が変わり、過去 run との比較可能性が切れる。
        """
        assert _render_merchants(_make_snapshot(economy_declared=False)) == []


class TestGoldSection:
    """所持金の行が、経済を宣言した世界にだけ出る挙動を保証する。"""

    def test_gold_is_rendered_when_the_world_declares_merchants(self) -> None:
        """商人を宣言した世界では所持金の行が出る。"""
        lines = _render_gold(_make_snapshot(economy_declared=True, own_gold=30))

        assert lines == ["所持金: 30G"]

    def test_zero_gold_is_still_rendered(self) -> None:
        """所持金が 0 でも行を出す (「無一文」と「経済の無い世界」を区別するため)。"""
        lines = _render_gold(_make_snapshot(economy_declared=True, own_gold=0))

        assert lines == ["所持金: 0G"]

    def test_nothing_is_rendered_when_the_world_declares_no_merchants(self) -> None:
        """商人を宣言していない世界では所持金の行を出さない。"""
        assert _render_gold(_make_snapshot(economy_declared=False, own_gold=0)) == []


class TestEconomySectionLayout:
    """経済の節が、どのフェーズのどの位置に出るかを保証する。"""

    def test_merchants_precede_inventory_in_free_roam(self) -> None:
        """自由時間では、商人節はオブジェクト節の後・所持アイテム節の前に出る。"""
        order = list(FREE_ROAM_SECTIONS)

        assert order.index(PromptSection.OBJECTS) < order.index(PromptSection.MERCHANTS)
        assert order.index(PromptSection.MERCHANTS) < order.index(PromptSection.GOLD)
        assert order.index(PromptSection.GOLD) < order.index(PromptSection.INVENTORY)

    def test_merchants_are_dropped_during_a_meeting(self) -> None:
        """会議中は商人節を出さない (その場で選べない対象は並べない規約に従う)。"""
        assert PromptSection.MERCHANTS not in MEETING_SECTIONS

    def test_gold_is_kept_during_a_meeting(self) -> None:
        """会議中も所持金は出す (所持アイテムと同じく主張の材料になるため)。"""
        assert PromptSection.GOLD in MEETING_SECTIONS
