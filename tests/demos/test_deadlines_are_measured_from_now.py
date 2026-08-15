"""期限が「いまから N 手番後」になり、過ぎたら実際に片付くことを保証する。

## なぜこの試験が要るか

v3.1 の実 run で、**提案が 1 手番で流れた**。t42 に持ちかけた提案が t43 に
「返事がないまま流れた」になり、3 回連続で同じことが起きた。エージェント側は
正しく動いていて (「こっちが返事をする前に流れちまった」)、**機構が壊れていた**。

原因は、期限を計算するときに渡す**現在時刻が常に 0** だったこと。時刻の
提供者を呼ぶ側がメソッド名を間違えていて、その例外を握り潰して 0 を返していた。
集約の計算式 (`created_tick + expires_in_ticks`) は正しかったので、**集約の
単体試験は全部通っていた**。

もう 1 つ、**板の注文は期限を過ぎても消えていなかった**。片付ける処理は書いて
あったが、どこからも呼ばれていなかった。

どちらも「部分は正しいが、繋いだ全体は違う」形なので、ここでは**実際に手番を
進めて、期限の前後で世界がどうなるか**を見る。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "market_town_v3_board.json"
)

_EXPIRES_IN = 6
_ELAPSED_BEFORE_LISTING = 4


@pytest.fixture
def town(tmp_path: Path) -> Any:
    raw: Dict[str, Any] = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    raw["market"]["order_expires_in_ticks"] = _EXPIRES_IN
    raw["market"]["initial_orders"] = []
    path = tmp_path / "town.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(str(path))


def _advance(runtime: Any, ticks: int) -> None:
    for _ in range(ticks):
        runtime.advance_tick()


def _list_bread(runtime: Any, *, baker: int = 3) -> Any:
    """焼き手にパンを持たせて、板へ出す。"""
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        grant_item_specs_to_inventory,
    )
    from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
    from tests.support.overflow_sinks import IGNORE_OVERFLOW

    spec = runtime._item_spec_repo.find_by_name("焼きたてのパン").item_spec_id.value
    grant_item_specs_to_inventory(
        PlayerId(baker), (ItemSpecId.create(spec),), runtime._item_repo,
        runtime._item_spec_repo, runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )
    return runtime._market_service.place_sell_order(
        PlayerId(baker), item_label="焼きたてのパン", quantity=1, unit_price=12,
        current_tick=runtime.current_tick(),
    )


def _executor_for(runtime: Any, clock: Any, *, runtime_for_fallback: Any = None) -> Any:
    """時刻の読み取りだけを見るための、最小配線の executor。"""
    from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (  # noqa: E501
        SpotGraphToolExecutor,
    )
    from ai_rpg_world.application.world_graph.spot_graph_world_services import (
        SpotGraphWorldServices,
    )
    from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
        GameEndConditionEvaluator,
    )

    return SpotGraphToolExecutor(
        spot_graph_world_services=SpotGraphWorldServices(
            interaction=runtime._interaction_service,
            exploration=runtime._exploration_service,
            world_flags=runtime._world_flag_state,
            game_end_evaluator=GameEndConditionEvaluator(),
            exploration_progress=runtime._exploration_progress,
            movement=runtime._movement_service,
        ),
        player_inventory_repository=runtime._player_inventory_repo,
        item_repository=runtime._item_repo,
        time_provider=clock,
        runtime=runtime_for_fallback,
    )


def _held_items(runtime: Any, player_id: int) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(PlayerId(player_id))
    return sum(1 for _ in inventory.iter_occupied_slots())


def _board_order_ids(runtime: Any) -> set:
    return {o.order_id.value for o in runtime._market_service.board().orders}


class TestTheDeadlineStartsFromNow:
    """期限は「いまから N 手番後」であって、「世界の開始から N 手番後」ではない。"""

    def test_an_order_placed_later_expires_later(self, town) -> None:
        """4 手番進んでから出した注文の期限は、4 + N になる。

        ここが 0 + N だと、**出した瞬間にもう期限切れ**になる。実 run では
        t42 の提案が t43 で流れた。
        """
        _advance(town, _ELAPSED_BEFORE_LISTING)

        order = _list_bread(town)

        assert order.expires_at_tick == _ELAPSED_BEFORE_LISTING + _EXPIRES_IN


class TestTheToolPathSeesTheRealClock:
    """ツール経由で渡る現在時刻が、世界の時計と一致する。"""

    def test_the_executor_reports_the_current_tick(self, town) -> None:
        """4 手番進めたら、ツール側が読む現在時刻も 4 になる。

        壊れていたのはここ。時刻の提供者を呼ぶメソッド名が違っていて、
        例外を握り潰して 0 を返していた。**呼ぶ側だけを見ても、渡された
        値が正しいかは分からない。**
        """
        _advance(town, _ELAPSED_BEFORE_LISTING)
        executor = _executor_for(town, town._time_provider)

        assert executor._current_tick_value() == _ELAPSED_BEFORE_LISTING

    def test_a_broken_clock_is_not_silently_read_as_zero(self, town, caplog) -> None:
        """時刻が読めないときは、0 を返す前に警告を残す。

        **黙って 0 を返すと、期限がすべて「世界の開始から」になる。**
        run が終わるまで誰も気づけない形だった。
        """
        class _BrokenClock:
            def get_current_tick(self):
                raise RuntimeError("時計が読めない")

        executor = _executor_for(town, _BrokenClock())

        with caplog.at_level("WARNING"):
            assert executor._current_tick_value() == 0

        assert caplog.records, "時刻が読めないのに警告が 1 件も出ていない"

    def test_a_broken_clock_falls_back_to_the_world(self, town, caplog) -> None:
        """時刻の提供者が壊れていても、世界そのものに時刻を訊く。

        提供者だけを見て諦めると、**壊れた瞬間に全部の期限が開始起点に
        戻る**。落とし所は 0 ではなく、同じ世界の別の読み方。
        """
        class _BrokenClock:
            def get_current_tick(self):
                raise RuntimeError("時計が読めない")

        _advance(town, _ELAPSED_BEFORE_LISTING)
        executor = _executor_for(town, _BrokenClock(), runtime_for_fallback=town)

        assert executor._current_tick_value() == _ELAPSED_BEFORE_LISTING

    def test_no_clock_at_all_still_warns(self, town, caplog) -> None:
        """時計がどこにも無い構成でも、0 を返す前に警告を残す。

        提供者が例外を投げる場合は提供者側で警告が出るので、**最後の
        砦の警告はこの経路でしか確かめられない**。変異試験で、この経路に
        検査が無いことが分かった。
        """
        executor = _executor_for(town, None)

        with caplog.at_level("WARNING"):
            assert executor._current_tick_value() == 0

        assert caplog.records, "時計が無いのに警告が 1 件も出ていない"


class TestExpiredOrdersActuallyLeaveTheBoard:
    """期限を過ぎた注文が、手番の進行で実際に板から消える。"""

    def test_the_order_is_still_there_before_the_deadline(self, town) -> None:
        """期限前は板に残っている (**正の対照**)。

        これが無いと、下の「消える」試験は「そもそも一度も載らなかった」
        でも緑になる。
        """
        order = _list_bread(town)

        _advance(town, _EXPIRES_IN - 1)

        assert order.order_id.value in _board_order_ids(town)

    def test_the_order_is_gone_after_the_deadline(self, town) -> None:
        """期限を過ぎると板から消える。

        片付ける処理は書いてあったが、**どこからも呼ばれていなかった**。
        v3 run では t33 に出した注文が t80 まで生きていた。
        """
        order = _list_bread(town)

        _advance(town, _EXPIRES_IN + 1)

        assert order.order_id.value not in _board_order_ids(town)

    def test_the_deposited_item_comes_back(self, town) -> None:
        """期限切れで下げた注文の品は、持ち主の手元へ戻る。

        戻らないと、**預けた品が黙って世界から消える**。
        """
        _list_bread(town)
        before = _held_items(town, 3)

        _advance(town, _EXPIRES_IN + 1)

        assert _held_items(town, 3) == before + 1
