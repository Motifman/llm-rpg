"""作業が数手かかること、その途中経過が痕跡として残ることを保証する。

## なぜ多段にするか

実 run 3 本すべてで、クルーが tick 14〜18 で勝って終わった。作業が 1 手で
終わるので、**暗い部屋に居る時間が短すぎて襲撃の機会が生まれない**。
tick 数を 20 → 30 に増やしても効かなかった (勝つのが早まっただけ)。
延ばすべきは run の長さではなく、危険な場所に留まる時間のほう。

## 副産物: 検証可能な主張が生まれる

進捗は object の状態なので、あとから来た人にも見える。**偽装はフラグも
カウンタも進めない**ので、

    クゼ「配線は俺が全部見ておいた」
    モリ (配線箱を見る) → 「手つかず」

という食い違いが残る。今まで「誰が作業したか」は誰にも確かめられなかった。
engine を足さずに、疑いの材料が 1 つ増える。

## 制約: 偽装も同じ回数だけ動けないと数えられる

本物が 3 手なのに偽装が 1 度きりだと、隣で見ている人は回数を数えるだけで
見分けがつく。多段にして初めて出てくる制約で、1 手構成では存在しなかった。

**ただし偽装に段は要らない。** 目撃者に届く文は全段で同一なので、外から
段は区別できない。必要なのは繰り返せることだけで、段を作ると偽装側にも
進捗カウンタが要り、隠す対象が増える。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI = PlayerId(1)   # crew
_SENA = PlayerId(2)   # crew
_KUZE = PlayerId(3)   # keeper

#: 配線箱の作業を 1 手進める action を、進捗の順に並べたもの。
_WIRING_STEPS = ("tighten_wiring", "tighten_wiring_2", "tighten_wiring_3")
#: 偽装は 1 つを繰り返す。**段を作る必要が無い。** 目撃者に届く文は全段で
#: 同一なので外から段は区別できず、必要なのは「同じ回数だけ動ける」ことだけ。
#: 段を作ると偽装側にも進捗カウンタが要り、隠す対象が増える。
_WIRING_FAKE = "tighten_wiring_pretend"


@pytest.fixture()
def runtime():
    rt = create_world_runtime(_SCENARIO)
    graph = rt._spot_graph_repo.find_graph()
    for pid in (_MORI, _SENA, _KUZE):
        graph.unplace_entity(EntityId.create(int(pid)))
        graph.place_entity(
            EntityId.create(int(pid)),
            SpotId.create(rt.id_mapper.get_int("spot", "corridor")),
        )
    rt._spot_graph_repo.save(graph)
    return rt


def _flags(runtime) -> set[str]:
    return set(runtime._world_flag_state.as_frozen_set())


def _offered(runtime, player_id: PlayerId) -> str:
    for line in runtime.build_observation(player_id).splitlines():
        if "配線箱" in line:
            return line
    return ""


class TestOneActionIsNotEnough:
    """1 手では終わらない。"""

    def test_the_first_step_does_not_complete_it(self, runtime) -> None:
        """1 手目でフラグは立たない。

        ここが立つと多段になっていない。
        """
        runtime.do_interact(_MORI, "junction_box", _WIRING_STEPS[0])

        assert "task_wiring" not in _flags(runtime)

    def test_the_second_step_does_not_complete_it_either(self, runtime) -> None:
        """2 手目でもまだ立たない。"""
        runtime.do_interact(_MORI, "junction_box", _WIRING_STEPS[0])
        runtime.do_interact(_MORI, "junction_box", _WIRING_STEPS[1])

        assert "task_wiring" not in _flags(runtime)

    def test_the_third_step_completes_it(self, runtime) -> None:
        """3 手目で完了する。"""
        for step in _WIRING_STEPS:
            runtime.do_interact(_MORI, "junction_box", step)

        assert "task_wiring" in _flags(runtime)


class TestOnlyOneStepIsOfferedAtATime:
    """その時点で選べる手は 1 つだけ。"""

    def test_the_first_step_is_offered_before_starting(self, runtime) -> None:
        """手つかずのときは 1 手目だけが出る。

        3 つ並ぶと「どれを選べばいいか」で迷い、順番を飛ばそうとする。
        """
        line = _offered(runtime, _MORI)

        assert _WIRING_STEPS[0] in line
        assert _WIRING_STEPS[1] not in line
        assert _WIRING_STEPS[2] not in line

    def test_the_next_step_replaces_it(self, runtime) -> None:
        """1 手進めると、次の手に入れ替わる。"""
        runtime.do_interact(_MORI, "junction_box", _WIRING_STEPS[0])
        line = _offered(runtime, _MORI)

        assert _WIRING_STEPS[1] in line
        assert f"{_WIRING_STEPS[0]})" not in line
        assert f"{_WIRING_STEPS[0]}," not in line

    def test_nothing_is_offered_once_it_is_done(self, runtime) -> None:
        """終わったら候補から消える。

        残ると、終わった作業を何度もやり直す。
        """
        for step in _WIRING_STEPS:
            runtime.do_interact(_MORI, "junction_box", step)

        assert "tighten_wiring" not in _offered(runtime, _MORI)


class TestAnyoneCanTakeOver:
    """途中から他人が引き継げる。"""

    def test_a_different_crew_member_can_continue(self, runtime) -> None:
        """モリが 2 手、セナが 1 手で完了する。

        進捗は object にあるので自然に引き継げる。禁じる理由が無いし、
        手分けの意味も増える。
        """
        runtime.do_interact(_MORI, "junction_box", _WIRING_STEPS[0])
        runtime.do_interact(_MORI, "junction_box", _WIRING_STEPS[1])
        runtime.do_interact(_SENA, "junction_box", _WIRING_STEPS[2])

        assert "task_wiring" in _flags(runtime)


class TestTheFakeLeavesNoTrace:
    """偽装は痕跡を残さない。"""

    def test_pretending_does_not_advance_the_progress(self, runtime) -> None:
        """3 手ぶん偽装しても、作業は手つかずのまま。

        **これが検証可能な主張の土台。** 口では「見ておいた」と言えるが、
        配線箱を見れば進んでいないと分かる。
        """
        for _ in range(len(_WIRING_STEPS)):
            runtime.do_interact(_KUZE, "junction_box", _WIRING_FAKE)

        assert "task_wiring" not in _flags(runtime)
        assert _WIRING_STEPS[0] in _offered(runtime, _MORI)

    def test_the_fake_can_be_repeated_as_many_times_as_the_real_one(
        self, runtime
    ) -> None:
        """偽装は本物と同じ回数だけ繰り返せる。

        本物が 3 手なのに偽装が 1 度きりだと、隣で見ている人は**回数を
        数えるだけ**で見分けられる。繰り返せることが偽装の成立条件。
        """
        for _ in range(len(_WIRING_STEPS)):
            result = runtime.do_interact(_KUZE, "junction_box", _WIRING_FAKE)
            assert result is not None

    def test_a_witness_sees_the_same_thing_either_way(self, runtime) -> None:
        """目撃者に届く文が、本物の各手と偽装の各手で同じ。

        手数を揃えても文が違えば見分けられる。
        """
        def _prose(actor, step):
            before = len(runtime._obs_buffer.get_observations(_SENA))
            runtime.do_interact(actor, "junction_box", step)
            after = runtime._obs_buffer.get_observations(_SENA)[before:]
            return [e.output.prose for e in after if "配線箱" in e.output.prose]

        real = _prose(_MORI, _WIRING_STEPS[0])
        fake = _prose(_KUZE, _WIRING_FAKE)

        assert real and fake, (real, fake)
        assert real[-1].replace("モリ", "＿") == fake[-1].replace("クゼ", "＿")


class TestTheProgressIsVisibleToEveryone:
    """進み具合はその場の全員に見える。"""

    def test_a_partially_done_task_says_so(self, runtime) -> None:
        """途中まで進んだ作業は、そう読める。

        見えないと「検証可能な主張」が成立しない。あとから来た人が
        確かめられることが要点。
        """
        runtime.do_interact(_MORI, "junction_box", _WIRING_STEPS[0])

        assert "途中" in _offered(runtime, _SENA)

    def test_it_does_not_say_who_advanced_it(self, runtime) -> None:
        """誰が進めたかは出さない。

        出すと偽装が成立しない (作業のふりをしても即座に割れる)。
        """
        runtime.do_interact(_MORI, "junction_box", _WIRING_STEPS[0])

        line = _offered(runtime, _SENA)
        assert "モリ" not in line


class TestNoEngineVocabularyLeaksIntoTheProse:
    """進捗の生値がプロンプトに出ない。"""

    def test_the_untouched_state_is_declared_too(self, runtime) -> None:
        """手つかずの状態にも表示文がある。

        宣言が無い state は生値のまま出る方針 (#893) なので、`progress=0`
        がそのままプロンプトに載る。**engine の語彙をプロンプトから外す**
        (#892) に反するし、読み手にとって意味も薄い。

        「進んでいる状態だけ宣言すれば十分」と考えて 0 を飛ばしたのが
        最初の形で、実際に `(progress=0)` と出ていた。
        """
        assert "progress=" not in runtime.build_observation(_MORI)

    def test_every_step_of_the_way_reads_as_japanese(self, runtime) -> None:
        """どの段でも日本語で読める。

        途中の段だけ宣言が漏れると、その 1 手のあいだだけ生値が出る。
        気付きにくいので全段を通す。
        """
        for step in _WIRING_STEPS:
            assert "progress=" not in runtime.build_observation(_MORI)
            runtime.do_interact(_MORI, "junction_box", step)

        assert "progress=" not in runtime.build_observation(_MORI)
