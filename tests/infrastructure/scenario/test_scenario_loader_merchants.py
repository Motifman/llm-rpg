"""merchants block のパースと fail-fast 検証 (経済統合 Phase 0)。

シナリオ JSON トップレベルの ``merchants`` は「この世界に NPC 商人が居る」と
いう正の宣言で、宣言の無い世界では既定の空 tuple になる (既存 run が変わらない)。
売買ツールの露出は PR-3 の管轄なので、ここでは宣言の読み込みと、
シナリオ作家の誤記を実行前に落とすことだけを保証する。
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)
from tests.infrastructure.scenario.test_scenario_loader import _minimal_scenario


def _scenario_with_merchants(merchants: Any) -> Dict[str, Any]:
    """最小シナリオへ merchants を差し込んだ raw dict を返す。"""
    scenario = copy.deepcopy(_minimal_scenario())
    scenario["merchants"] = merchants
    return scenario


def _scenario_with_two_item_specs() -> Dict[str, Any]:
    """item_spec が 2 つある最小シナリオ (売値と買値を別 item で書くため)。"""
    scenario = copy.deepcopy(_minimal_scenario())
    scenario["item_specs"].append(
        {"id": "bread", "name": "パン", "description": "焼きたて", "category": "CONSUMABLE"},
    )
    return scenario


def _merchant(**overrides: Any) -> Dict[str, Any]:
    """検証を通る商人宣言 1 件。テスト側は壊したいキーだけ上書きする。"""
    merchant: Dict[str, Any] = {
        "id": "gustav",
        "name": "商人グスタフ",
        "spot": "room_a",
        "sells": [{"item_spec": "key", "price": 10}],
        "buys": [],
    }
    merchant.update(overrides)
    return merchant


class TestMerchantDeclaration:
    """merchants が宣言された世界と、宣言の無い世界の読み込み結果を保証する。"""

    def test_unspecified_merchants_default_to_empty_tuple(self) -> None:
        """merchants を書かないシナリオでは merchants が空 tuple になり、宣言なしの世界として読める。"""
        result = ScenarioLoader().load_from_dict(_minimal_scenario())

        assert result.merchants == ()

    def test_explicit_empty_list_is_same_as_unspecified(self) -> None:
        """merchants に空配列を明示しても空 tuple になり、未宣言と同じ扱いになる。"""
        result = ScenarioLoader().load_from_dict(_scenario_with_merchants([]))

        assert result.merchants == ()

    def test_single_merchant_keeps_declared_name_and_resolved_references(self) -> None:
        """商人 1 件を宣言すると、表示名と、解決済みの spot / item_spec 参照と価格を保持する。"""
        scenario = _scenario_with_merchants([_merchant()])

        result = ScenarioLoader().load_from_dict(scenario)

        assert len(result.merchants) == 1
        merchant = result.merchants[0]
        assert merchant.string_id == "gustav"
        assert merchant.name == "商人グスタフ"
        assert merchant.spot_id.value == result.id_mapper.get_int("spot", "room_a")
        assert len(merchant.sells) == 1
        assert merchant.sells[0].item_spec_id == result.id_mapper.get_int("item_spec", "key")
        assert merchant.sells[0].price == 10
        assert merchant.buys == ()

    def test_merchant_id_is_registered_into_the_merchant_namespace(self) -> None:
        """商人 id は mapper の merchant 名前空間へ登録され、宣言と同じ int id が保持される。"""
        result = ScenarioLoader().load_from_dict(_scenario_with_merchants([_merchant()]))

        assert result.id_mapper.contains("merchant", "gustav")
        assert result.merchants[0].merchant_id == result.id_mapper.get_int("merchant", "gustav")

    def test_buy_only_merchant_is_accepted(self) -> None:
        """買い取りだけを行う商人 (sells 省略) は、売値を持たない商人として読み込める。"""
        scenario = _scenario_with_merchants([
            _merchant(sells=[], buys=[{"item_spec": "key", "price": 6}]),
        ])

        result = ScenarioLoader().load_from_dict(scenario)

        assert result.merchants[0].sells == ()
        assert result.merchants[0].buys[0].price == 6

    def test_same_item_spec_may_appear_in_both_sells_and_buys(self) -> None:
        """同じ item_spec を sells と buys の両方に書けて、売値と買値の差 (スプレッド) を表せる。"""
        scenario = _scenario_with_two_item_specs()
        scenario["merchants"] = [
            _merchant(
                sells=[{"item_spec": "bread", "price": 10}],
                buys=[{"item_spec": "bread", "price": 6}],
            ),
        ]

        result = ScenarioLoader().load_from_dict(scenario)

        merchant = result.merchants[0]
        assert merchant.sells[0].item_spec_id == merchant.buys[0].item_spec_id
        assert (merchant.sells[0].price, merchant.buys[0].price) == (10, 6)

    def test_two_merchants_may_share_one_spot(self) -> None:
        """同じ spot に商人を 2 人並べられる (spot 単位の一意制約を課さない)。"""
        scenario = _scenario_with_merchants([
            _merchant(),
            _merchant(id="hilda", name="商人ヒルダ"),
        ])

        result = ScenarioLoader().load_from_dict(scenario)

        assert [m.string_id for m in result.merchants] == ["gustav", "hilda"]
        assert result.merchants[0].spot_id == result.merchants[1].spot_id


class TestMerchantIdentityValidation:
    """商人の識別子と表示名の誤記を読み込み時に落とす。"""

    @pytest.mark.parametrize("broken_id", [None, "", 1])
    def test_missing_or_non_string_id_is_rejected(self, broken_id: Any) -> None:
        """id が欠落・空文字・文字列以外のとき ScenarioLoadError を投げる。"""
        merchant = _merchant()
        if broken_id is None:
            del merchant["id"]
        else:
            merchant["id"] = broken_id

        with pytest.raises(ScenarioLoadError, match="merchants.*id"):
            ScenarioLoader().load_from_dict(_scenario_with_merchants([merchant]))

    def test_duplicated_id_is_rejected(self) -> None:
        """同じ id の商人を 2 件宣言すると ScenarioLoadError を投げる。"""
        scenario = _scenario_with_merchants([
            _merchant(),
            _merchant(name="商人ヒルダ"),
        ])

        with pytest.raises(ScenarioLoadError, match="gustav"):
            ScenarioLoader().load_from_dict(scenario)

    @pytest.mark.parametrize("broken_name", [None, "", "   ", 1])
    def test_missing_or_blank_name_is_rejected(self, broken_name: Any) -> None:
        """name が欠落・空・空白のみ・文字列以外のとき ScenarioLoadError を投げる。"""
        merchant = _merchant()
        if broken_name is None:
            del merchant["name"]
        else:
            merchant["name"] = broken_name

        with pytest.raises(ScenarioLoadError, match="merchants.*name"):
            ScenarioLoader().load_from_dict(_scenario_with_merchants([merchant]))

    def test_duplicated_name_is_rejected_across_the_whole_scenario(self) -> None:
        """id が違っても表示名が重複する商人はシナリオ全域で拒否する (名前で指す将来の参照が曖昧になるため)。"""
        scenario = _scenario_with_merchants([
            _merchant(),
            _merchant(id="hilda"),
        ])

        with pytest.raises(ScenarioLoadError, match="商人グスタフ"):
            ScenarioLoader().load_from_dict(scenario)


class TestMerchantReferenceValidation:
    """実在しない spot / item_spec への参照を読み込み時に落とす。"""

    def test_unknown_spot_reference_is_rejected(self) -> None:
        """実在しない spot を参照する商人は ScenarioLoadError で落ちる。"""
        scenario = _scenario_with_merchants([_merchant(spot="market_square")])

        with pytest.raises(ScenarioLoadError, match="market_square"):
            ScenarioLoader().load_from_dict(scenario)

    @pytest.mark.parametrize("broken_spot", [None, "", 1])
    def test_missing_or_non_string_spot_is_rejected(self, broken_spot: Any) -> None:
        """spot が欠落・空文字・文字列以外のとき ScenarioLoadError を投げる。"""
        merchant = _merchant()
        if broken_spot is None:
            del merchant["spot"]
        else:
            merchant["spot"] = broken_spot

        with pytest.raises(ScenarioLoadError, match="merchants.*spot"):
            ScenarioLoader().load_from_dict(_scenario_with_merchants([merchant]))

    def test_unknown_item_spec_in_sells_is_rejected(self) -> None:
        """sells が実在しない item_spec を参照すると ScenarioLoadError で落ちる。"""
        scenario = _scenario_with_merchants([
            _merchant(sells=[{"item_spec": "bread", "price": 10}]),
        ])

        with pytest.raises(ScenarioLoadError, match="bread"):
            ScenarioLoader().load_from_dict(scenario)

    def test_unknown_item_spec_in_buys_is_rejected(self) -> None:
        """buys が実在しない item_spec を参照すると ScenarioLoadError で落ちる。"""
        scenario = _scenario_with_merchants([
            _merchant(sells=[], buys=[{"item_spec": "herb", "price": 6}]),
        ])

        with pytest.raises(ScenarioLoadError, match="herb"):
            ScenarioLoader().load_from_dict(scenario)


class TestMerchantPriceListValidation:
    """品揃えと価格の誤記を読み込み時に落とす。"""

    def test_merchant_without_sells_and_buys_is_rejected(self) -> None:
        """sells と buys が両方空の商人は、売りも買いもできない宣言として ScenarioLoadError で落ちる。"""
        scenario = _scenario_with_merchants([_merchant(sells=[], buys=[])])

        with pytest.raises(ScenarioLoadError, match="sells.*buys"):
            ScenarioLoader().load_from_dict(scenario)

    def test_merchant_omitting_both_price_lists_is_rejected(self) -> None:
        """sells と buys をどちらも省略した商人も、両方空と同じく ScenarioLoadError で落ちる。"""
        merchant = _merchant()
        del merchant["sells"]
        del merchant["buys"]

        with pytest.raises(ScenarioLoadError, match="sells.*buys"):
            ScenarioLoader().load_from_dict(_scenario_with_merchants([merchant]))

    @pytest.mark.parametrize("price", [0, -1])
    def test_non_positive_price_is_rejected(self, price: int) -> None:
        """price が 0 以下のとき ScenarioLoadError を投げる (無料・マイナス価格は宣言できない)。"""
        scenario = _scenario_with_merchants([
            _merchant(sells=[{"item_spec": "key", "price": price}]),
        ])

        with pytest.raises(ScenarioLoadError, match="price"):
            ScenarioLoader().load_from_dict(scenario)

    @pytest.mark.parametrize("price", ["10", 10.5, None, True])
    def test_non_integer_price_is_rejected(self, price: Any) -> None:
        """price が整数でないとき (文字列・小数・null・真偽値) ScenarioLoadError を投げる。"""
        scenario = _scenario_with_merchants([
            _merchant(sells=[{"item_spec": "key", "price": price}]),
        ])

        with pytest.raises(ScenarioLoadError, match="price"):
            ScenarioLoader().load_from_dict(scenario)

    def test_duplicated_item_spec_within_sells_is_rejected(self) -> None:
        """同じ商人の sells に同一 item_spec を 2 度書くと、どちらの価格が効くか決まらないので拒否する。"""
        scenario = _scenario_with_merchants([
            _merchant(sells=[
                {"item_spec": "key", "price": 10},
                {"item_spec": "key", "price": 12},
            ]),
        ])

        with pytest.raises(ScenarioLoadError, match="key"):
            ScenarioLoader().load_from_dict(scenario)

    def test_duplicated_item_spec_within_buys_is_rejected(self) -> None:
        """同じ商人の buys に同一 item_spec を 2 度書くと ScenarioLoadError を投げる。"""
        scenario = _scenario_with_merchants([
            _merchant(sells=[], buys=[
                {"item_spec": "key", "price": 6},
                {"item_spec": "key", "price": 7},
            ]),
        ])

        with pytest.raises(ScenarioLoadError, match="key"):
            ScenarioLoader().load_from_dict(scenario)

    def test_missing_item_spec_key_in_price_entry_is_rejected(self) -> None:
        """価格エントリに item_spec が無いとき ScenarioLoadError を投げる。"""
        scenario = _scenario_with_merchants([_merchant(sells=[{"price": 10}])])

        with pytest.raises(ScenarioLoadError, match="item_spec"):
            ScenarioLoader().load_from_dict(scenario)


class TestMerchantsBlockShapeValidation:
    """merchants ブロック自体の形の誤りを読み込み時に落とす。"""

    def test_non_list_merchants_block_is_rejected(self) -> None:
        """merchants が配列でないとき ScenarioLoadError を投げる。"""
        with pytest.raises(ScenarioLoadError, match="merchants"):
            ScenarioLoader().load_from_dict(_scenario_with_merchants({"id": "gustav"}))

    def test_non_object_merchant_entry_is_rejected(self) -> None:
        """merchants の要素がオブジェクトでないとき ScenarioLoadError を投げる。"""
        with pytest.raises(ScenarioLoadError, match="merchants"):
            ScenarioLoader().load_from_dict(_scenario_with_merchants(["gustav"]))

    @pytest.mark.parametrize("broken_list", ["key", {"item_spec": "key"}])
    def test_non_list_price_list_is_rejected(self, broken_list: Any) -> None:
        """sells が配列でないとき ScenarioLoadError を投げる。"""
        scenario = _scenario_with_merchants([_merchant(sells=broken_list)])

        with pytest.raises(ScenarioLoadError, match="sells"):
            ScenarioLoader().load_from_dict(scenario)

    def test_non_object_price_entry_is_rejected(self) -> None:
        """sells の要素がオブジェクトでないとき ScenarioLoadError を投げる。"""
        scenario = _scenario_with_merchants([_merchant(sells=["key"])])

        with pytest.raises(ScenarioLoadError, match="sells"):
            ScenarioLoader().load_from_dict(scenario)
