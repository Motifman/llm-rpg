"""到着は出来事として履歴に残り、着いた先への移動は失敗にならない。

## なぜ

多 tick 移動では宣言と到着が別の tick に起き、**移動中は手番が来ない**
(turn_trigger が `is_traveling` を見て飛ばす)。エージェントから見ると、
出発を宣言した次に意識が戻るのは到着した tick になる。

ところが履歴には出発 (「◯◯へ移動中」) しか残らず、**着いた瞬間の行が
無かった**。現在地は静的な 1 行なので、時系列を追う側の目には入りにくい。
その結果、到着済みなのに同じ移動をもう一度宣言する空転が起きる。

供物競争 v2 run の実測: 11 件。ドナは t13 に広場へ着いたのに t15 で同じ
移動を宣言し、その独白は t11 の計画と同じ文だった。さらに失敗の記録が
履歴に残り、t46・t56 では「エラーを見る限り、今はもう広場にいる。移動する
必要はない」と書きながら**また同じ移動を選んでいた**。

対処は 2 つで、片方だけでは足りない。到着を残す (原因) と、着いた先への
宣言を失敗にしない (連鎖を断つ)。
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_RACE = pathlib.Path(__file__).resolve().parents[2] / "data" / "scenarios" / "offering_race_v2.json"
_GAREN = PlayerId(1)


@pytest.fixture()
def race() -> Any:
    from ai_rpg_world.application.world_runtime.world_runtime import (
        create_world_runtime,
    )

    return create_world_runtime(str(_RACE))


def _history(runtime: Any, player_id: PlayerId, limit: int = 5):
    return runtime._action_result_store.get_recent(player_id, limit)


def _travel(runtime: Any, player_id: PlayerId, destination: str):
    return runtime.do_move(player_id, destination)  # 文字列 ID を渡す


class TestArrivalIsRecorded:
    """着いたことが行動履歴に残る。"""

    def test_the_history_shows_the_arrival(self, race: Any) -> None:
        """移動が完了した tick に「着いた」が履歴へ積まれる。

        出発だけが残る状態だと、次の手番でエージェントは「まだ着いて
        いない」と読んで同じ移動を宣言する。
        """
        _travel(race, _GAREN, "wheat_field")
        for _ in range(4):
            race.advance_tick()

        summaries = [e.action_summary for e in _history(race, _GAREN)]

        assert any("着いた" in s for s in summaries), summaries

    def test_the_departure_is_still_recorded(self, race: Any) -> None:
        """出発の記録は消さない (**正の対照**)。

        「向かった」と「着いた」は別の出来事で、片方に畳むと
        どちらの情報も欠ける。
        """
        _travel(race, _GAREN, "wheat_field")

        summaries = [e.action_summary for e in _history(race, _GAREN)]

        assert any("麦畑" in s for s in summaries), summaries


class TestGoingWhereYouAlreadyAreIsNotAFailure:
    """着いた先へもう一度向かう宣言は、失敗にしない。"""

    def test_traveling_to_the_current_spot_succeeds(self, race: Any) -> None:
        """現在地を行き先に指定しても成功し、「既に居る」と返る。

        失敗にすると、その記録が履歴に残って繰り返しを招く (実 run で
        ドナが 5 回)。
        """
        from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
            _WorldLlmWiring,
        )

        class _Client:
            def invoke(self, messages, tools, tool_choice="required", **kwargs):
                return {"name": "wait", "arguments": {}}

        wiring = _WorldLlmWiring(
            runtime=race,
            observation_buffer=race._obs_buffer,
            llm_client=_Client(),
        )
        context = race.build_full_prompt(_GAREN)["tool_runtime_context"]

        result = wiring._tool_handlers["travel_to"](
            _GAREN,
            {"destination_label": "祭りの広場", "inner_thought": "広場へ戻る"},
            context,
        )

        assert result.success is True, result.message

    def test_the_current_spot_resolves_as_a_destination(self, race: Any) -> None:
        """現在地の名前が、移動先として解決できる。

        接続先だけを候補に登録していたので、現在地を指すと
        ``INVALID_DESTINATION_LABEL`` で落ちていた。
        """
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (  # noqa: E501
            resolve_destination_target,
        )

        context = race.build_full_prompt(_GAREN)["tool_runtime_context"]

        target = resolve_destination_target("祭りの広場", context)

        assert target.spot_id == race.id_mapper.get_int("spot", "festival_square")

    def test_the_current_spot_is_not_advertised_as_a_choice(self, race: Any) -> None:
        """現在地は移動先の候補としてプロンプトに出さない (**負の対照**)。

        救済のための別名であって、選択肢を増やす意図ではない。出すと
        「その場に留まる」が移動の一種に見えて手番を浪費させる。
        """
        text = race.build_full_prompt(_GAREN)["messages"][-1]["content"]

        connections = [line for line in text.splitlines() if line.strip().startswith("- ") and "→" in line]

        assert connections, "接続先の行が無い (検査が空振りする)"
        assert not any("祭りの広場" in line for line in connections), connections


class TestEveryArrivalObserverIsCalled:
    """到着の観察者は足し算で持ち、後から配線しても先客を消さない。"""

    def test_adding_an_observer_keeps_the_existing_ones(self, race: Any) -> None:
        """後から足した観察者と、既にいる観察者の両方が呼ばれる。

        単一 callback の上書きだったころは、後から配線する側 (LLM の手番
        再開) が先に置かれた hook を黙って消していた。**実走経路でだけ
        発火しない**形で、テストでは再現しない静かな失敗だった。
        """
        stage = race._travel_stage
        called: list[str] = []
        stage.add_arrival_observer(lambda pid: called.append("first"))
        stage.add_arrival_observer(lambda pid: called.append("second"))

        _travel(race, _GAREN, "wheat_field")
        for _ in range(4):
            race.advance_tick()

        assert called == ["first", "second"], called
