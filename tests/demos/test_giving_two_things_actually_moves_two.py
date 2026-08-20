"""「ふたつとも持ってけ」が、実際に 2 つ動くことを保証する。

## なぜこの試験が要るか

実 run で、トムが `quantity: 2` を指定し「ふたつとも持ってけ」と言ったのに、
**1 個しか動かなかった**。しかも `give_item_partial_failure: false` で、
**失敗としても記録されていない**。合計 2 個のパンが、両者に気づかれないまま
移動しなかった。飢えている世界で 2 個は大きい。

原因は、`gives` の要素に `quantity` が**存在しなかった**こと。engine は知らない
引数を黙って捨て、1 要素 = 1 個の設計どおりに 1 個動かして成功を返した。
**丸めていたのではなく、最初から見ていなかった。**

つまり **schema が「2 個渡す」を表現できないのに、エージェントは自然にそう書いた**。
言葉の側が正しく、世界の側が追いついていなかった。

## 数が足りないときに黙らない

手元にある数より多く頼まれたら、**渡せるだけ渡して、渡した数を返す**。黙って
成功にすると、頼んだ数と動いた数の差が誰にも見えない。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO = (
    Path(__file__).resolve().parents[2]
    / "data" / "scenarios" / "market_town_v3_board.json"
)

_GIVER = 3
_TAKER = 5
_BREAD = "焼きたてのパン"


@pytest.fixture
def town() -> Any:
    return create_world_runtime(str(_SCENARIO))


def _hand(runtime: Any, player_id: int, count: int) -> None:
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        grant_item_specs_to_inventory,
    )
    from tests.support.overflow_sinks import IGNORE_OVERFLOW

    spec = runtime._item_spec_repo.find_by_name(_BREAD).item_spec_id.value
    grant_item_specs_to_inventory(
        PlayerId(player_id),
        tuple(ItemSpecId.create(spec) for _ in range(count)),
        runtime._item_repo, runtime._item_spec_repo,
        runtime._player_inventory_repo, overflow_sink=IGNORE_OVERFLOW,
    )


def _held(runtime: Any, player_id: int) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(PlayerId(player_id))
    return sum(1 for _ in inventory.iter_occupied_slots())


def _give(runtime: Any, *, quantity: Any = None) -> Any:
    """resolver が作る形の引数で `give_item` を実行する。

    resolver は `gives` の各要素を `gives_resolved` へ変換する。ここでは
    その出力の形をそのまま組み立てる (resolver 自身の検査は別クラス)。
    """
    spec = runtime._item_spec_repo.find_by_name(_BREAD).item_spec_id.value
    entry: Dict[str, Any] = {
        "index": 0,
        "item_spec_id": spec,
        "is_spoiled": False,
        "target_player_id": _TAKER,
        "target_display_name": _TAKER_NAME,
        "item_display_name": _BREAD,
        "item_label": _BREAD,
        "target_player_label": _TAKER_NAME,
    }
    if quantity is not None:
        entry["quantity"] = quantity
    return _executor(runtime)._give_item(
        _GIVER, {"gives_resolved": [entry], "inner_thought": "渡す"},
    )


#: 受け取る側の名前 (シナリオ宣言と同じ)。
_TAKER_NAME = "ミナ"


def _executor(runtime: Any) -> Any:
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
        item_transfer_service=runtime._item_transfer_service,
        runtime=runtime,
    )


class TestAskingForTwoMovesTwo:
    """頼んだ数だけ動く。"""

    def test_two_are_handed_over(self, town) -> None:
        """`quantity: 2` を指定すると、2 つ動く。"""
        _hand(town, _GIVER, 2)

        _give(town, quantity=2)

        assert _held(town, _TAKER) == 2

    def test_omitting_the_quantity_still_moves_one(self, town) -> None:
        """省略時は 1 つ (**既定を変えない**)。

        既存のシナリオと過去の run の読み方を変えないため。
        """
        _hand(town, _GIVER, 2)

        _give(town)

        assert _held(town, _TAKER) == 1


class TestRunningOutIsSaidOutLoud:
    """足りないときに黙らない。"""

    def test_only_what_is_held_moves(self, town) -> None:
        """手元に 1 つしか無いのに 2 つ頼んだら、1 つだけ動く。"""
        _hand(town, _GIVER, 1)

        _give(town, quantity=2)

        assert _held(town, _TAKER) == 1

    def test_the_result_says_how_many_moved(self, town) -> None:
        """結果に、頼んだ数と渡した数の**両方**が出る。

        渡した数だけだと、読む側は自分の意図が満たされたか判断できない。
        """
        _hand(town, _GIVER, 1)

        result = _give(town, quantity=2)

        assert "2つ頼んで1つ渡した" in result.message

    def test_the_trace_keeps_both_numbers(self, town) -> None:
        """trace にも、頼んだ数と動いた数の両方が残る。

        **実 run ではここが「成功 1 件」としか残らず、2 個のパンが消えた
        ことを誰も追えなかった。**
        """
        _hand(town, _GIVER, 1)

        payload = _give(town, quantity=2).trace_payload

        assert payload["give_item_requested_quantity"] == 2
        assert payload["give_item_moved_quantity"] == 1
        assert payload["give_item_partial_failure"] is True


class TestAnImpossibleCountIsRefused:
    """数として成立しない指定は、引数解決の時点で弾く。"""

    @pytest.mark.parametrize("bad", [0, -1, "2", True])
    def test_it_is_rejected(self, bad) -> None:
        """0 以下・文字列・真偽値は拒否する。

        `bool` は `int` の派生なので、素直に書くと `True` が 1 として通る。
        「パンを True 個渡す」を作らせない。
        """
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (  # noqa: E501
            _give_quantity_or_raise,
        )
        from ai_rpg_world.application.llm.services._resolver_helpers import (
            ToolArgumentResolutionException,
        )

        with pytest.raises(ToolArgumentResolutionException):
            _give_quantity_or_raise(bad)

    def test_omitting_it_means_one(self) -> None:
        """省略は 1 と読む (**既定を変えない**)。"""
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (  # noqa: E501
            _give_quantity_or_raise,
        )

        assert _give_quantity_or_raise(None) == 1
