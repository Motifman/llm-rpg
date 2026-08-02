"""行に「いま条件を満たしているか」まで書き、engine の単位を出さない。

## 宣言だけでは足りなかった

実 run 011 で、インポスターが明るい集会室から 3 回続けて襲おうとして、
3 回とも弾かれた。行はこう出ていた。

    雰囲気: 明るさ: 明るい / 音: 換気扇の低い唸り / 気温: 暖かい
      ...
      - "モリ" [背後から襲う (strike_down・暗い場所のみ・解体用カッターが要る)]

**2 行上に「明るい」と書いてあるのに、選べる手として並んでいる。**
「暗い場所のみ」という宣言は付いていたが、**いまそれを満たしているかは
書いていない**。注記だけでは足りなかった。

部屋の明るさはその人の画面に出ている事実なので、これで絞っても新しい情報は
漏れない (#860 の不変条件)。

## 行ごと落とす案は採らない

明るい部屋に居るインポスターから襲う手が消えると、**自分の手段そのものを
見失う**。「いまはできない」と書けば、暗い所へ移るという次の手に繋がる。
``ConditionVisibility.PUBLIC`` の既存の分け方と同じ判断。

## 4 つ目の tick の漏れ

同じ行に待ち時間が ``あと 13 tick`` と出ていた。#956 で直したのは拒否
メッセージだけで、**行のラベルが残っていた**。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
#: モリ(灯り) / セナ / クゼ(インポスター) / アオイ / ハギ(灯り)
_MORI, _SENA, _KUZE, _AOI, _HAGI = (PlayerId(i) for i in range(1, 6))


@pytest.fixture()
def runtime():
    return create_world_runtime(_DRILL)


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _row(runtime, viewer: PlayerId, target_name: str) -> str:
    return next(
        line.strip()
        for line in runtime.build_observation(viewer).splitlines()
        if f'"{target_name}"' in line
    )


class TestTheRowSaysWhenTheLightIsWrong:
    """明るさの条件を満たしていないとき、行がそう書く。"""

    def test_a_lit_room_says_it_is_lit(self, runtime) -> None:
        """明るい部屋では「いまは明るい」が行に出る。

        **run 011 でここが空白だった。** インポスターは 3 回選んで 3 回
        弾かれている。
        """
        row = _row(runtime, _KUZE, "モリ")  # 集会室は明るい

        assert "strike_down" in row
        assert "いまは明るい" in row

    def test_a_dark_room_says_nothing_extra(self, runtime) -> None:
        """暗い部屋では余計な断りが付かない。

        **「常に付く」でもこのテストの片割れは通る**ので、付かない側を
        必ず一緒に見る。付きっぱなしだと、暗い所でも襲えないと読める。
        """
        _move(runtime, _KUZE, "corridor")
        _move(runtime, _SENA, "corridor")

        row = _row(runtime, _KUZE, "セナ")

        assert "strike_down" in row
        assert "いまは" not in row

    def test_a_lantern_changes_the_row(self, runtime) -> None:
        """灯りを持つ人が入ってくると、行の断りが変わる。

        灯りは仕事の道具であると同時に身を守る手段で、**この関係が行から
        読めることに意味がある**。
        """
        _move(runtime, _KUZE, "corridor")
        _move(runtime, _SENA, "corridor")
        assert "いまは" not in _row(runtime, _KUZE, "セナ")

        _move(runtime, _MORI, "corridor")  # ランタン持ち

        assert "いまは薄暗い" in _row(runtime, _KUZE, "セナ")

    def test_the_declared_condition_is_still_shown(self, runtime) -> None:
        """宣言のほうの「暗い場所のみ」は消さない。

        いまの状況だけ書いて宣言を消すと、**なぜできないのかが分からず**、
        暗い所へ移るという次の手に繋がらない。
        """
        row = _row(runtime, _KUZE, "モリ")

        assert "暗い場所のみ" in row


class TestTheWaitIsShownInWorldTerms:
    """待ち時間が、世界の時計と同じ単位で行に出る。"""

    def _after_one_strike(self, runtime):
        _move(runtime, _KUZE, "storage")
        runtime.do_interact(_KUZE, "supply_shelf", "find_cutter")
        for player_id in (_SENA, _KUZE, _AOI):
            _move(runtime, player_id, "corridor")
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
        return runtime

    def test_the_row_counts_in_minutes(self, runtime) -> None:
        """一度使ったあと、行に残り時間が分で出る。

        ``あと 13 tick`` と出ていた。**tick は世界の中に無い語** (#892)。
        #956 で直したのは拒否メッセージだけで、行が残っていた。
        宣言は 15 手番、1 手番 5 分の世界なので 75 分。
        """
        self._after_one_strike(runtime)

        row = _row(runtime, _KUZE, "アオイ")

        assert "あと 75 分" in row
        assert "tick" not in row

    def test_no_wait_is_shown_before_the_first_use(self, runtime) -> None:
        """一度も使っていないうちは、待ち時間が出ない。

        **「常に出る」でも上のテストは通る**ので、出ない側を一緒に見る。
        """
        _move(runtime, _KUZE, "corridor")
        _move(runtime, _SENA, "corridor")

        assert "あと" not in _row(runtime, _KUZE, "セナ")


class TestNothingLeaksThroughTheNewHint:
    """新しい断りが、相手の秘密を映さない。"""

    def test_the_hint_is_the_same_whoever_is_targeted(self, runtime) -> None:
        """相手が誰でも、断りの中身が変わらない。

        明るさは**行為者が居る場所**の性質で、相手とは関係が無い。相手ごとに
        変わるなら、それは相手の何かを見てしまっている。
        """
        hints = {
            name: _row(runtime, _KUZE, name).split("strike_down")[1]
            for name in ("モリ", "セナ", "アオイ", "ハギ")
        }

        assert len(set(hints.values())) == 1, hints
        assert "いまは明るい" in next(iter(hints.values()))

    def test_a_crew_member_still_sees_no_such_row(self, runtime) -> None:
        """クルーの行には襲う手そのものが出ない。

        断りを足したせいで、伏せていた行が出るようになっていないかを見る。
        """
        row = _row(runtime, _MORI, "セナ")

        assert "strike_down" not in row
