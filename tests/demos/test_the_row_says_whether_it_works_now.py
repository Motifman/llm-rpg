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

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.demos.station_drill_lighting_helpers import darken_spot

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


def _take_lantern(runtime, player_id: PlayerId) -> None:
    """物資庫の非常用ケースからランタンを取る。"""
    _move(runtime, player_id, "storage")
    runtime.build_observation(player_id)
    runtime.do_interact(player_id, "emergency_lantern_case", "take_lantern")


def _runtime_with_strike_lighting(tmp_path: Path, *lighting: tuple[str, str]):
    """``strike_down`` の明るさ条件を差し替えた世界を作る。

    同梱シナリオは ``SPOT_LIGHTING_IS`` を 1 つ持つだけだが、``_IS_NOT`` も
    loader と実行評価器の両方が受け付け、複数並べることもできる。**片方だけ
    断りが付く**状態や**片方満たせば通ると読む**状態を見つけるために、極性と
    本数を変えた世界で同じことを確かめる。
    """
    data = json.loads(_DRILL.read_text(encoding="utf-8"))
    for idef in data["player_interactions"]:
        if idef["action_name"] != "strike_down":
            continue
        others = [
            cond
            for cond in idef["preconditions"]
            if not cond["condition_type"].startswith("SPOT_LIGHTING_IS")
        ]
        idef["preconditions"] = others + [
            {
                "condition_type": condition_type,
                "required_lighting": required_lighting,
                "failure_message": "ここの明るさでは無理だ。",
            }
            for condition_type, required_lighting in lighting
        ]
    path = tmp_path / "station_drill_lighting_variant.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return create_world_runtime(path)


def _row(runtime, viewer: PlayerId, target_name: str) -> str:
    """人物の本体行と、直後の「いまできない」行を一続きで返す。"""
    lines = runtime.build_observation(viewer).splitlines()
    index = next(
        index
        for index, line in enumerate(lines)
        if f'"{target_name}"' in line
    )
    selected = [lines[index].strip()]
    if index + 1 < len(lines) and lines[index + 1].strip().startswith(
        "いまできない:"
    ):
        selected.append(lines[index + 1].strip())
    return "\n".join(selected)


def _action_text(row: str, action_name: str) -> str:
    """人物の二段表示から、指定した対人 action の表示だけを取り出す。"""
    actions = row.replace("\n", "、").split("、")
    return next(
        action
        for action in actions
        if f'"{action_name}"' in action
    )


class TestTheRowSaysWhenTheLightIsWrong:
    """明るさの条件を満たしていないとき、行がそう書く。"""

    def test_a_lit_room_says_it_is_lit(self, runtime) -> None:
        """明るい部屋では「いまは明るい」が行に出る。

        **run 011 でここが空白だった。** インポスターは 3 回選んで 3 回
        弾かれている。
        """
        row = _action_text(_row(runtime, _KUZE, "モリ"), "strike_down")

        assert "strike_down" in row
        assert "いまは明るい" in row

    def test_a_dark_room_says_nothing_extra(self, runtime) -> None:
        """暗い部屋では余計な断りが付かない。

        **「常に付く」でもこのテストの片割れは通る**ので、付かない側を
        必ず一緒に見る。付きっぱなしだと、暗い所でも襲えないと読める。
        """
        darken_spot(runtime)
        _move(runtime, _KUZE, "corridor")
        _move(runtime, _SENA, "corridor")

        row = _action_text(_row(runtime, _KUZE, "セナ"), "strike_down")

        assert "strike_down" in row
        assert "いまは" not in row

    def test_a_lantern_changes_the_row(self, runtime) -> None:
        """灯りを持つ人が入ってくると、行の断りが変わる。

        灯りは仕事の道具であると同時に身を守る手段で、**この関係が行から
        読めることに意味がある**。
        """
        darken_spot(runtime)
        _move(runtime, _KUZE, "corridor")
        _move(runtime, _SENA, "corridor")
        assert "いまは" not in _action_text(
            _row(runtime, _KUZE, "セナ"), "strike_down"
        )

        _take_lantern(runtime, _MORI)
        _move(runtime, _MORI, "corridor")  # ランタン持ち

        assert "いまは薄暗い" in _action_text(
            _row(runtime, _KUZE, "セナ"), "strike_down"
        )

    def test_the_declared_condition_is_still_shown(self, runtime) -> None:
        """宣言のほうの「暗い場所のみ」は消さない。

        いまの状況だけ書いて宣言を消すと、**なぜできないのかが分からず**、
        暗い所へ移るという次の手に繋がらない。
        """
        row = _row(runtime, _KUZE, "モリ")

        assert "暗い場所のみ" in row


class TestBothPolaritiesOfTheLightingConditionAreRead:
    """「この明るさで」と「この明るさ以外で」の両方に断りが付く。

    宣言の集合を「要求される明るさ」として集めると、``_IS_NOT`` は意味が
    裏返るので**同じ集合には入れられない**。実行時と同じ形で 1 つずつ
    評価する。
    """

    def test_a_forbidden_lighting_says_the_room_is_that_way_now(
        self, tmp_path
    ) -> None:
        """「暗い所では不可」の条件で暗い部屋に居ると、行が「いまは暗い」と書く。

        極性を読まずに要求値の集合として扱うと、``DARK`` が集合に入って
        いるため暗い部屋では成立と誤読され、**断りが消える**。実行時は弾く
        ので「選べるのに必ず失敗する手」に戻る。
        """
        runtime = _runtime_with_strike_lighting(
            tmp_path, ("SPOT_LIGHTING_IS_NOT", "DARK")
        )
        darken_spot(runtime)
        _move(runtime, _KUZE, "corridor")
        _move(runtime, _SENA, "corridor")

        row = _action_text(_row(runtime, _KUZE, "セナ"), "strike_down")

        assert "strike_down" in row
        assert "いまは暗い" in row

    def test_a_forbidden_lighting_stays_silent_where_it_is_allowed(
        self, tmp_path
    ) -> None:
        """「暗い所では不可」の条件で明るい部屋に居ると、断りが付かない。

        **「常に付く」でも上のテストは通る**ので、付かない側を一緒に見る。
        """
        runtime = _runtime_with_strike_lighting(
            tmp_path, ("SPOT_LIGHTING_IS_NOT", "DARK")
        )

        row = _action_text(_row(runtime, _KUZE, "モリ"), "strike_down")

        assert "strike_down" in row
        assert "いまは" not in row


class TestEveryLightingConditionMustHold:
    """明るさ条件が複数あるとき、**すべて**満たさないと断りが付く。

    実行時は AND で畳む。行の側だけ「どれか 1 つ満たせば成立」に緩むと、
    条件が 1 本のうちは同じに見えるのに、2 本目を足した途端に食い違う。
    """

    def _two_exclusions(self, tmp_path):
        """「明るくもなく薄暗くもない所で」の宣言。暗い所でだけ通る。"""
        return _runtime_with_strike_lighting(
            tmp_path,
            ("SPOT_LIGHTING_IS_NOT", "BRIGHT"),
            ("SPOT_LIGHTING_IS_NOT", "DIM"),
        )

    def test_one_satisfied_condition_does_not_excuse_the_other(
        self, tmp_path
    ) -> None:
        """薄暗い部屋では、「明るくない」を満たしていても断りが付く。

        灯りを持つ人が居る通路は薄暗い。「明るくない」は満たすが「薄暗くない」
        は満たさない。**片方の成立で全体を成立と読む**と断りが消え、実行時は
        弾くので食い違う。
        """
        runtime = self._two_exclusions(tmp_path)
        darken_spot(runtime)
        _take_lantern(runtime, _MORI)
        for player_id in (_KUZE, _SENA, _MORI):
            _move(runtime, player_id, "corridor")

        row = _action_text(_row(runtime, _KUZE, "セナ"), "strike_down")

        assert "strike_down" in row
        assert "いまは薄暗い" in row

    def test_all_satisfied_conditions_add_nothing(self, tmp_path) -> None:
        """暗い部屋では、両方満たすので断りが付かない。

        **「常に付く」でも上のテストは通る**ので、付かない側を一緒に見る。
        """
        runtime = self._two_exclusions(tmp_path)
        darken_spot(runtime)
        _move(runtime, _KUZE, "corridor")
        _move(runtime, _SENA, "corridor")

        row = _action_text(_row(runtime, _KUZE, "セナ"), "strike_down")

        assert "strike_down" in row
        assert "いまは" not in row


class TestABrokenLightingLookupDoesNotBecomeASilentPass:
    """明るさを引けないとき、断りだけ黙って消えることがない。"""

    def test_a_failing_resolver_drops_the_row_instead_of_the_hint(
        self, runtime, caplog
    ) -> None:
        """明るさ解決が例外で落ちると、同席者行の action 候補ごと消えて警告が残る。

        断りだけ消して行を出すと、**明るい部屋で「いつでも襲える」と読める**
        行に戻る。それは #860 で消したかった「選べるのに必ず失敗する手」
        そのもので、しかも今度は静かに戻る。

        prompt 全体は失わない。対人 action が出ないぶん手段は見つからなく
        なるが、現在状態そのものを落とすより軽い。
        """

        def _broken(_spot):
            raise RuntimeError("照明 resolver の配線が壊れている")

        runtime._player_interaction_service._effective_lighting_resolver.resolve = (
            _broken
        )

        with caplog.at_level("WARNING"):
            row = _row(runtime, _KUZE, "モリ")

        assert "strike_down" not in row
        assert any("対人 action" in record.message for record in caplog.records)


class TestTheWaitIsShownInWorldTerms:
    """待ち時間が、世界の時計と同じ単位で行に出る。"""

    def _after_one_strike(self, runtime):
        _move(runtime, _KUZE, "storage")
        runtime.do_interact(_KUZE, "supply_shelf", "find_cutter")
        for player_id in (_SENA, _KUZE, _AOI):
            _move(runtime, player_id, "corridor")
        darken_spot(runtime)
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

        比較対象を全員 crew のままにすると、全員へ同じ秘密を漏らす実装でも
        一致してしまう。セナだけを keeper に変え、異なる秘匿値を持つ対象でも
        表示が同じことを確かめる。インポスターを複数にしたとき、表示だけで
        相方が判明する回帰をここで止める。
        """
        sena_status = runtime._player_status_repo.find_by_id(_SENA)
        sena_status.merge_state({"role": "keeper"})
        runtime._player_status_repo.save(sena_status)

        hints = {
            name: _action_text(
                _row(runtime, _KUZE, name), "strike_down"
            )
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
