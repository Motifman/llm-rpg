"""所持金が動いたら、どのツールから動いても同じ形で trace に残ることを保証する。

`gold_after` / `gold_delta` / `gold_change_source` を出していたのは商人ツール
(`buy_item` / `sell_item`) **だけ**だった。板を通した売買は 7G 増えても所持金の
記録が 1 行も出ず、trace から所持金の台帳を組むと**板で稼いだ人を実際より
低く見積もる**。

商人ツールだけが出していたのは、**先に作ったからで設計判断ではない**。ツールを
1 つ足すたびに分析器が壊れる形 (= どのツールが gold を動かすかの知識が分析器の
側へ漏れる) なので、**呼び出しの前後で測る**ようにした。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.world_llm_turn.gold_change_trace import (
    wrap_with_gold_change,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _Purse:
    """呼ばれるたびに決めた額を返す、所持金の読み取り役。"""

    def __init__(self, *amounts: Optional[int]) -> None:
        self._amounts = list(amounts)

    def __call__(self, player_id: PlayerId) -> Optional[int]:
        return self._amounts.pop(0) if self._amounts else None


def _handler(trace_payload: Optional[Dict[str, Any]] = None, *, success: bool = True):
    def _run(player_id: PlayerId, arguments: Dict[str, Any],
             runtime_context: Any) -> LlmCommandResultDto:
        return LlmCommandResultDto(
            success=success, message="やった", trace_payload=trace_payload,
        )
    return _run


def _call(handler) -> Optional[Dict[str, Any]]:
    return handler(PlayerId(1), {}, None).trace_payload


class TestGoldThatMovedIsAlwaysRecorded:
    """所持金が変わったら、3 つの項目が必ず付く。"""

    def test_the_three_fields_appear_when_gold_moved(self) -> None:
        """所持金が 12G から 19G へ増えたら、増分・残高・出どころが残る。"""
        wrapped = wrap_with_gold_change(
            _handler(), _Purse(12, 19), tool_name="market_sell",
        )

        payload = _call(wrapped)

        assert payload["gold_delta"] == 7
        assert payload["gold_after"] == 19
        assert payload["gold_change_source"] == "market_sell"

    def test_spending_is_recorded_as_a_negative_delta(self) -> None:
        """払った場合は増分が負になる (向きを符号で表す)。"""
        wrapped = wrap_with_gold_change(
            _handler(), _Purse(19, 4), tool_name="market_buy",
        )

        assert _call(wrapped)["gold_delta"] == -15

    def test_a_handler_without_a_payload_still_gets_one(self) -> None:
        """trace を 1 つも出していないツールでも、動いたなら残す。

        **記録しているツールにだけ足す形だと、記録していないツールが
        永久に漏れる。**
        """
        wrapped = wrap_with_gold_change(
            _handler(None), _Purse(10, 3), tool_name="market_bid",
        )

        assert _call(wrapped)["gold_delta"] == -7


class TestNothingIsAddedWhenNothingMoved:
    """動いていないのに項目を足さない (**正の対照**)。"""

    def test_an_unchanged_purse_adds_no_fields(self) -> None:
        """所持金が変わらなかったツールには、3 つとも付かない。

        全ツールに付けると trace が太り、「gold が動いた行」を数える側が
        毎回 0 を除く仕事をすることになる。
        """
        wrapped = wrap_with_gold_change(
            _handler({"tool_event": "listed"}), _Purse(12, 12),
            tool_name="market_list_item",
        )

        payload = _call(wrapped)

        assert payload == {"tool_event": "listed"}

    def test_the_original_payload_is_not_mutated(self) -> None:
        """元の payload を書き換えず、新しい dict を返す。"""
        original = {"tool_event": "sold"}
        wrapped = wrap_with_gold_change(
            _handler(original), _Purse(12, 19), tool_name="market_sell",
        )

        _call(wrapped)

        assert original == {"tool_event": "sold"}


class TestTheHandlersOwnLabelSurvivesButItsNumbersDoNot:
    """出どころの名前は handler のものを使い、**数字は測った側を使う**。"""

    def test_an_explicit_source_label_is_kept(self) -> None:
        """handler が出どころを名乗っていたら、その名前を残す。

        `merchant_buy` のような意味のある名前を、ツール名で潰さない。
        """
        wrapped = wrap_with_gold_change(
            _handler({"gold_change_source": "merchant_buy"}), _Purse(19, 4),
            tool_name="buy_item",
        )

        assert _call(wrapped)["gold_change_source"] == "merchant_buy"

    def test_a_stale_declared_amount_is_replaced_by_the_measured_one(self) -> None:
        """handler の申告と実際がずれていたら、**実際の値を残す**。

        申告は書いた時点の想定で、実際は世界で起きたこと。台帳を組むのは
        後者でなければならない。
        """
        wrapped = wrap_with_gold_change(
            _handler({"gold_delta": -99, "gold_after": 0}), _Purse(19, 4),
            tool_name="buy_item",
        )

        payload = _call(wrapped)

        assert (payload["gold_delta"], payload["gold_after"]) == (-15, 4)


class TestAnUnreadablePurseIsNotGuessed:
    """所持金が読めない構成では、何も足さずに素通りする。"""

    @pytest.mark.parametrize("purse", [_Purse(None, 19), _Purse(12, None)])
    def test_missing_readings_add_nothing(self, purse) -> None:
        """前後どちらかが読めなければ、差分を作らない。

        読めないことを 0 と書くと、**動かなかったのと区別がつかなくなる**。
        """
        wrapped = wrap_with_gold_change(
            _handler({"tool_event": "sold"}), purse, tool_name="market_sell",
        )

        assert _call(wrapped) == {"tool_event": "sold"}

    def test_a_purse_that_raises_does_not_break_the_tool(self) -> None:
        """所持金の読み取りが失敗しても、ツール自体は成功のまま返る。

        trace は分析用で、世界の進行には要らない。
        """
        def _broken(player_id):
            raise RuntimeError("読めない")

        wrapped = wrap_with_gold_change(
            _handler({"tool_event": "sold"}), _broken, tool_name="market_sell",
        )

        result = wrapped(PlayerId(1), {}, None)

        assert result.success is True
        assert result.trace_payload == {"tool_event": "sold"}


class TestTheWrapperIsVisibleFromOutside:
    """包まれていることを、外から確かめられる。"""

    def test_a_wrapped_handler_is_marked(self) -> None:
        """包んだ handler には印が付く。

        「全ツールが通っているか」を起動時・テストで総当たりできるように
        する。**印が無いと、新しいツールが素通りしても誰も気づかない。**
        """
        wrapped = wrap_with_gold_change(_handler(), _Purse(), tool_name="wait")

        assert getattr(wrapped, "records_gold_change", False) is True


class _Ledger:
    """複数人の所持金を持つ、読み書きできる財布。"""

    def __init__(self, **amounts: int) -> None:
        self.amounts = {int(k.lstrip("p")): v for k, v in amounts.items()}

    def read(self, player_id: PlayerId):
        return self.amounts.get(int(player_id.value))

    def roster(self):
        return [PlayerId(pid) for pid in sorted(self.amounts)]


def _moving_handler(ledger: _Ledger, moves: Dict[int, int], *, declared=()):
    """実行時に複数人の所持金を動かす handler。"""

    def _run(player_id: PlayerId, arguments: Dict[str, Any],
             runtime_context: Any) -> LlmCommandResultDto:
        for pid, delta in moves.items():
            ledger.amounts[pid] += delta
        return LlmCommandResultDto(
            success=True, message="やった",
            gold_affected_player_ids=tuple(declared),
        )
    return _run


class TestBothSidesOfATradeAreRecorded:
    """二者間で動いた所持金が、両方とも残る。"""

    def test_the_other_party_appears_in_the_changes(self) -> None:
        """相手の増減も `gold_changes` に出る。

        呼んだ人だけを測っていたときは、受け取った側の行が 1 件も出ず、
        台帳を**差額から逆算**するしかなかった。逆算が要る時点で、知識が
        分析器の側へ戻っている。
        """
        ledger = _Ledger(p1=12, p2=12)
        wrapped = wrap_with_gold_change(
            _moving_handler(ledger, {1: -10, 2: +10}, declared=(2,)),
            ledger.read, tool_name="trade_accept", roster_reader=ledger.roster,
        )

        payload = _call(wrapped)

        assert payload["gold_changes"] == [
            {"player_id": 1, "delta": -10, "after": 2},
            {"player_id": 2, "delta": 10, "after": 22},
        ]

    def test_the_actor_keeps_the_original_fields(self) -> None:
        """行動した人の分は、これまでと同じ項目にも出る。

        既に書いた分析器と、過去の run の読み方を壊さないため。
        """
        ledger = _Ledger(p1=12, p2=12)
        wrapped = wrap_with_gold_change(
            _moving_handler(ledger, {1: -10, 2: +10}, declared=(2,)),
            ledger.read, tool_name="trade_accept", roster_reader=ledger.roster,
        )

        payload = _call(wrapped)

        assert (payload["gold_delta"], payload["gold_after"]) == (-10, 2)

    def test_people_who_did_not_move_are_left_out(self) -> None:
        """動かなかった人は並ばない (**正の対照**)。

        全員を毎回並べると、trace から「誰が関わったか」が読めなくなる。
        """
        ledger = _Ledger(p1=12, p2=12, p3=12)
        wrapped = wrap_with_gold_change(
            _moving_handler(ledger, {1: -10, 2: +10}, declared=(2,)),
            ledger.read, tool_name="trade_accept", roster_reader=ledger.roster,
        )

        moved = {row["player_id"] for row in _call(wrapped)["gold_changes"]}

        assert moved == {1, 2}


class TestTheDeclarationIsCheckedAgainstReality:
    """申告は真実ではなく期待で、食い違えば警告になる。"""

    def test_an_undeclared_mover_warns(self, caplog) -> None:
        """申告に無い人の所持金が動いたら警告する。

        **どこかで意図しない移動が起きている**ということなので、まさに
        検出したい事故になる。
        """
        ledger = _Ledger(p1=12, p2=12)
        wrapped = wrap_with_gold_change(
            _moving_handler(ledger, {1: -10, 2: +10}),
            ledger.read, tool_name="trade_accept", roster_reader=ledger.roster,
        )

        with caplog.at_level("WARNING"):
            _call(wrapped)

        assert any("申告に無い" in r.getMessage() for r in caplog.records)

    def test_a_declared_but_still_purse_warns(self, caplog) -> None:
        """動くと申告された人が動かなかったら警告する。"""
        ledger = _Ledger(p1=12, p2=12)
        wrapped = wrap_with_gold_change(
            _moving_handler(ledger, {1: -10}, declared=(2,)),
            ledger.read, tool_name="trade_accept", roster_reader=ledger.roster,
        )

        with caplog.at_level("WARNING"):
            _call(wrapped)

        assert any("動かなかった" in r.getMessage() for r in caplog.records)

    def test_a_correct_declaration_is_quiet(self, caplog) -> None:
        """申告と実測が合っていれば、何も言わない (**正の対照**)。

        これが無いと、上の 2 件は「常に警告が出る」実装でも緑になる。
        """
        ledger = _Ledger(p1=12, p2=12)
        wrapped = wrap_with_gold_change(
            _moving_handler(ledger, {1: -10, 2: +10}, declared=(2,)),
            ledger.read, tool_name="trade_accept", roster_reader=ledger.roster,
        )

        with caplog.at_level("WARNING"):
            _call(wrapped)

        assert caplog.records == []
