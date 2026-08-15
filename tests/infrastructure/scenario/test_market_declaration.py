"""市場をシナリオから宣言する (経済統合 Phase 3)。

板は**世界に物理的に置かれる**ので、どこに置くかはシナリオが決める。期限も
「世界の広さで決まる調整値」なので `player_trade.offer_expires_in_ticks` と
同じ流儀でシナリオが持つ。

初期注文を置けるようにしているのは、**板が空だと相場感がゼロから始まる**ため。
最初の値付けが完全な当てずっぽうになり、価格が動き出すまでに手番を浪費する。
出し手は商人にする。数量が有限で補充されないので「取り下げ手のいない注文」は
売れれば自然に消える。値は屋台の売り買いとわざとずらす — 同じ値だと屋台と板で
同じ取引ができてしまい、板を使う理由が消える。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)

_TOWN = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "market_town_v1.json"


def _raw() -> Dict[str, Any]:
    return json.loads(_TOWN.read_text(encoding="utf-8"))


def _load(raw: Dict[str, Any], tmp_path: Path):
    path = tmp_path / "market_town_v1.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return ScenarioLoader().load_from_file(path)


def _with_market(raw: Dict[str, Any], **overrides: Any) -> Dict[str, Any]:
    block: Dict[str, Any] = {"board_spot": "market_square"}
    block.update(overrides)
    raw["market"] = block
    return raw


class TestAWorldWithoutAMarketHasNoBoard:
    """市場を宣言していない世界には板が無い。"""

    def test_the_board_spot_is_absent(self, tmp_path: Path) -> None:
        """`market` を書いていない世界では、板の置き場所が決まらない。"""
        result = _load(_raw(), tmp_path)

        assert result.market is None


class TestTheBoardIsDeclaredWithAPlace:
    """板の宣言は、置き場所と期限を持つ。"""

    def test_the_board_spot_is_read(self, tmp_path: Path) -> None:
        """宣言した spot が板の置き場所として読み取られる。"""
        result = _load(_with_market(_raw()), tmp_path)

        assert result.market is not None
        assert result.market.board_spot_id is not None

    def test_a_declared_expiry_is_read(self, tmp_path: Path) -> None:
        """宣言した手番数が注文の期限として読み取られる。"""
        result = _load(_with_market(_raw(), order_expires_in_ticks=40), tmp_path)

        assert result.market.order_expires_in_ticks == 40

    def test_the_expiry_defaults_when_not_written(self, tmp_path: Path) -> None:
        """期限を書かなければ、engine の既定に任せる。

        None と「書いた値」を区別して持つ。既定値をシナリオ側とサービス側の
        2 箇所に置かないため。
        """
        result = _load(_with_market(_raw()), tmp_path)

        assert result.market.order_expires_in_ticks is None


class TestAnUnusableMarketIsRefusedAtLoadTime:
    """成立しえない市場の宣言は、読み込みの時点で落とす。"""

    def test_a_non_object_market_block_is_refused(self, tmp_path: Path) -> None:
        """`market` を object 以外で書くと読み込めない。"""
        raw = _raw()
        raw["market"] = ["market_square"]

        with pytest.raises(ScenarioLoadError) as exc:
            _load(raw, tmp_path)

        assert "market" in str(exc.value)

    def test_a_missing_board_spot_is_refused(self, tmp_path: Path) -> None:
        """置き場所を書かない市場は宣言できない。

        板は物理的に置かれる物なので、どこにあるか決まらない板は作れない。
        """
        raw = _raw()
        raw["market"] = {"order_expires_in_ticks": 40}

        with pytest.raises(ScenarioLoadError) as exc:
            _load(raw, tmp_path)

        assert "board_spot" in str(exc.value)

    def test_an_unknown_board_spot_is_refused(self, tmp_path: Path) -> None:
        """実在しない spot 名を書くと読み込めない。"""
        raw = _with_market(_raw(), board_spot="nowhere")

        with pytest.raises(ScenarioLoadError) as exc:
            _load(raw, tmp_path)

        assert "nowhere" in str(exc.value)

    @pytest.mark.parametrize("value", [0, -1])
    def test_a_non_positive_expiry_is_refused(self, tmp_path: Path, value: int) -> None:
        """0 以下の期限は読み込めない (作った瞬間に流れる注文を作らない)。"""
        raw = _with_market(_raw(), order_expires_in_ticks=value)

        with pytest.raises(ScenarioLoadError) as exc:
            _load(raw, tmp_path)

        assert "order_expires_in_ticks" in str(exc.value)

    def test_a_boolean_expiry_is_refused(self, tmp_path: Path) -> None:
        """真偽値は整数として通さない (`True` が 1 手番として通る罠)。"""
        raw = _with_market(_raw(), order_expires_in_ticks=True)

        with pytest.raises(ScenarioLoadError) as exc:
            _load(raw, tmp_path)

        assert "order_expires_in_ticks" in str(exc.value)

    @pytest.mark.parametrize("value", ["40", 40.0, [40]])
    def test_a_non_integer_expiry_is_refused(self, tmp_path: Path, value: Any) -> None:
        """整数でない期限は読み込めない。"""
        raw = _with_market(_raw(), order_expires_in_ticks=value)

        with pytest.raises(ScenarioLoadError):
            _load(raw, tmp_path)


class TestInitialOrdersAreDeclaredWithTheMarket:
    """初期注文は市場の宣言の中に書く。"""

    def test_no_initial_orders_means_an_empty_board(self, tmp_path: Path) -> None:
        """初期注文を書かなければ、板は空で始まる。"""
        result = _load(_with_market(_raw()), tmp_path)

        assert result.market.initial_orders == ()

    def test_a_declared_order_is_read(self, tmp_path: Path) -> None:
        """宣言した初期注文が、向き・品目・数量・単価つきで読み取られる。"""
        raw = _with_market(_raw(), initial_orders=[
            {"merchant": "gustav", "side": "sell", "item_spec": "herb",
             "quantity": 2, "unit_price": 9},
        ])

        result = _load(raw, tmp_path)

        (order,) = result.market.initial_orders
        assert order.side == "sell"
        assert order.quantity == 2
        assert order.unit_price == 9

    def test_an_unknown_merchant_is_refused(self, tmp_path: Path) -> None:
        """実在しない商人名の初期注文は読み込めない。"""
        raw = _with_market(_raw(), initial_orders=[
            {"merchant": "nobody", "side": "sell", "item_spec": "herb",
             "quantity": 1, "unit_price": 9},
        ])

        with pytest.raises(ScenarioLoadError) as exc:
            _load(raw, tmp_path)

        assert "nobody" in str(exc.value)

    def test_an_unknown_item_is_refused(self, tmp_path: Path) -> None:
        """実在しない品名の初期注文は読み込めない。"""
        raw = _with_market(_raw(), initial_orders=[
            {"merchant": "gustav", "side": "sell", "item_spec": "moonstone",
             "quantity": 1, "unit_price": 9},
        ])

        with pytest.raises(ScenarioLoadError) as exc:
            _load(raw, tmp_path)

        assert "moonstone" in str(exc.value)

    def test_an_unknown_side_is_refused(self, tmp_path: Path) -> None:
        """`sell` / `buy` 以外の向きは読み込めない。"""
        raw = _with_market(_raw(), initial_orders=[
            {"merchant": "gustav", "side": "trade", "item_spec": "herb",
             "quantity": 1, "unit_price": 9},
        ])

        with pytest.raises(ScenarioLoadError) as exc:
            _load(raw, tmp_path)

        assert "side" in str(exc.value)

    @pytest.mark.parametrize("field", ["quantity", "unit_price"])
    @pytest.mark.parametrize("value", [0, -1, True, "3"])
    def test_a_non_positive_number_is_refused(
        self, tmp_path: Path, field: str, value: Any
    ) -> None:
        """数量・単価が 1 以上の整数でない初期注文は読み込めない。"""
        entry = {"merchant": "gustav", "side": "sell", "item_spec": "herb",
                 "quantity": 1, "unit_price": 9}
        entry[field] = value
        raw = _with_market(_raw(), initial_orders=[entry])

        with pytest.raises(ScenarioLoadError):
            _load(raw, tmp_path)
