"""勝敗が、条件の型ではなくシナリオの書き場所で決まることを保証する。

## 何が起きていたか

評価器が条件の**型ごとに勝敗を固定**していた。陣営全滅なら LOSE、フラグ
成立なら WIN、という具合に。

station_drill の勝利条件はこう書いてある。

    win:  SURVIVING_PLAYERS_WITH_STATE_AT_MOST {role: keeper} max_surviving: 0

「インポスターの生存者が 0 になったらクルーの勝ち」という宣言だが、型が
陣営全滅なので **LOSE として返っていた**。つまり **インポスターを追放した
クルーが敗北扱い**になる。会議・投票・追放という、この世界で一番見たい
勝ち筋がまるごと壊れていた。

裏返しも成り立つ。lose に FLAGS_SET_AT_LEAST を書けば WIN が返る。

## なぜ型で決められないか

型は「何が起きたか」しか表さない。**それが勝ちか負けかは、シナリオが
どちらのリストに書いたかで決まる。** 同じ「陣営が全滅した」でも、消えたのが
インポスターなら勝ち、クルーなら負け。

呼び出し側は自分がどちらのリストを回しているか知っているので、そちらに
決めさせる。既定値は置かない。置くと、新しい呼び出し側が黙ってどちらかに
倒れる。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.demos.station_drill_lighting_helpers import darken_spot

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI, _SENA, _KUZE, _AOI, _HAGI, _YURA, _JIN, _SAKI = (
    PlayerId(i) for i in range(1, 9)
)


class TestEjectingTheImpostorIsAWin:
    """インポスターを追放したらクルーの勝ち。"""

    def test_the_result_is_a_win(self) -> None:
        """追放の結果が WIN として返る。

        **これが壊れていた。** 会議で正しく追放できても敗北として記録され、
        run の分析がまるごと誤る。
        """
        runtime = create_world_runtime(_DRILL)

        runtime.eject_player(_KUZE)
        runtime.eject_player(_JIN)
        result = runtime.check_game_end()

        assert result.is_ended is True
        assert result.result is GameResultEnum.WIN

    def test_ejecting_a_crew_member_is_not_a_win(self) -> None:
        """クルーを 1 人追放しても勝ちにならない。

        「追放したら勝ち」ではなく「インポスターが居なくなったら勝ち」。
        """
        runtime = create_world_runtime(_DRILL)

        runtime.eject_player(_SENA)

        assert runtime.check_game_end().is_ended is False


class TestTheCountIsHeadcountNotKills:
    """数えているのは生存人数であって、殺害回数ではない。"""

    def test_ejections_move_the_lose_line(self) -> None:
        """殺害が 0 回でも、追放でクルーが減れば敗北に届く。

        殺害を数えていたら、追放で減った human は勘定に入らない。
        **キルは過程であって、判定の対象ではない。**
        """
        runtime = create_world_runtime(_DRILL)

        runtime.eject_player(_SENA)
        runtime.eject_player(_AOI)
        assert runtime.check_game_end().is_ended is False

        runtime.eject_player(_HAGI)
        assert runtime.check_game_end().is_ended is False

        runtime.eject_player(_YURA)
        result = runtime.check_game_end()

        assert result.is_ended is True
        assert result.result is GameResultEnum.LOSE

    def test_kills_and_ejections_count_together(self) -> None:
        """殺害と追放が混ざっても、合計の生存者で判定する。"""
        runtime = create_world_runtime(_DRILL)

        def move(player_id: PlayerId, spot: str) -> None:
            graph = runtime._spot_graph_repo.find_graph()
            graph.unplace_entity(EntityId.create(int(player_id)))
            graph.place_entity(
                EntityId.create(int(player_id)),
                SpotId.create(runtime.id_mapper.get_int("spot", spot)),
            )
            runtime._spot_graph_repo.save(graph)

        move(_KUZE, "storage")
        runtime.do_interact(_KUZE, "supply_shelf", "find_cutter")
        for player_id in (_SENA, _KUZE):
            move(player_id, "corridor")
        darken_spot(runtime)
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
        runtime.advance_tick()

        runtime.eject_player(_AOI)
        assert runtime.check_game_end().is_ended is False

        runtime.eject_player(_HAGI)
        assert runtime.check_game_end().is_ended is False

        runtime.eject_player(_YURA)

        assert runtime.check_game_end().result is GameResultEnum.LOSE


class TestTheCallerMustDecide:
    """呼び出し側が勝敗を渡さないと動かない。"""

    def test_omitting_the_side_is_an_error(self) -> None:
        """`result_on_match` を渡さないと落ちる。

        既定値を置くと、新しい呼び出し側が**黙ってどちらかに倒れる**。
        型ごとに固定していた元の実装が、まさにその形だった。
        """
        from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (  # noqa: E501
            GameEndConditionEvaluator,
        )

        runtime = create_world_runtime(_DRILL)
        graph = runtime._spot_graph_repo.find_graph()

        with pytest.raises(TypeError):
            GameEndConditionEvaluator().evaluate(
                graph,
                runtime.scenario.win_conditions[0],
                frozenset(),
                list(runtime.get_player_ids()),
            )


class TestTheScenarioSaysWhichSide:
    """シナリオは陣営ごとに適切な条件型を選べる。"""

    def test_opposite_sides_may_use_different_condition_types(self) -> None:
        """複数インポスターでは勝利と敗北が別の条件型でも宣言できる。

        勝利はインポスター全滅、敗北は現在の両陣営が同数という別の問いで
        ある。条件型が勝敗を決める旧実装へ戻さず、書かれた側を評価する。
        """
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        win_types = {c["type"] for c in raw["game_end_conditions"]["win"]}
        lose_types = {c["type"] for c in raw["game_end_conditions"]["lose"]}

        assert win_types == {"FLAGS_SET_AT_LEAST", "SURVIVING_PLAYERS_WITH_STATE_AT_MOST"}
        assert lose_types == {"SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE"}
