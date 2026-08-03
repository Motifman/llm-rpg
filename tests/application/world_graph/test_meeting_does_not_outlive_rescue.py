"""会議が救命の猶予を食い潰さないことを保証する。

#864 のマージ後レビューで見つかった穴。倒れている相手を報告すると、
**その相手がちょうど死ぬ**状態だった。

    grace_ticks        = 30   (倒れてから 30 tick で DEAD 確定)
    MEETING_TICK_LIMIT = 30   (会議は最大 30 tick)

report_body は「倒れているが蘇生できる相手」を見つけたときの手段で、
全員が死体の場所に集まる。ところが会議中は tend_to_player が露出しない
ので、隣に居るのに手当てできない。会議が上限まで走ると猶予と一致して、
**報告した行為そのものが相手を死体に変える**。

これは #848 で置いた判断と衝突する。

> 倒れている (is_down) だけの相手は蘇生できるので生存として数えます。
> ここで終わらせると、駆けつけて助け起こす行為の意味が消えます。

2 つの数字が一致していたのは偶然で、突き合わせた形跡が無かった。会議中に
tend_to_player を出すのは症状の緩和にすぎない (誰も手当てを選ばなければ
同じことが起きる)。**本体は 2 つの時間の関係を構造で固定すること**。
"""

from __future__ import annotations

from ai_rpg_world.application.player.services.player_death_grace_tick_stage import (
    PlayerDeathGraceTickStage,
)
from ai_rpg_world.application.world_graph.game_phase_store import GamePhaseStore
from ai_rpg_world.application.llm.tool_exposure import PHASE_COMMON_TOOLS
from ai_rpg_world.application.world_runtime.world_runtime import WorldRuntime


class TestMeetingEndsBeforeTheGraceExpires:
    """会議の上限は、倒れた人が死ぬまでの猶予より必ず短い。"""

    def test_the_meeting_limit_is_shorter_than_the_death_grace(self) -> None:
        """会議は救命猶予より先に終わる。

        ここが逆転すると、会議に巻き込まれている間に倒れている人が死ぬ。
        どちらの定数を後から動かしても、この関係が壊れた時点で落ちる。
        """
        assert (
            GamePhaseStore.DEFAULT_MEETING_TICK_LIMIT
            < PlayerDeathGraceTickStage.DEFAULT_GRACE_TICKS
        )

    def test_there_is_room_to_reach_the_fallen_afterwards(self) -> None:
        """会議が終わってから駆けつける余地が残る。

        1 tick でも短ければ上の条件は満たすが、閉じた瞬間に死ぬのでは
        「助けに行く」が選べない。移動と手当てに要る分を残す。
        """
        remaining = (
            PlayerDeathGraceTickStage.DEFAULT_GRACE_TICKS
            - GamePhaseStore.DEFAULT_MEETING_TICK_LIMIT
        )

        assert remaining >= 5

    def test_the_production_stage_uses_the_named_constant(self) -> None:
        """本番の配線が、その定数をそのまま使っている。

        べた書きに戻ると、上の 2 つが通ったまま本番だけ穴が開く。
        """
        import inspect
        import ai_rpg_world.application.world_runtime.world_runtime as module

        source = inspect.getsource(module)

        assert "grace_ticks=30" not in source
        assert "PlayerDeathGraceTickStage.DEFAULT_GRACE_TICKS" in source


class TestTendingIsAvailableDuringMeetings:
    """会議中も倒れている人に手当てできる。"""

    def test_tend_to_player_is_a_phase_common_tool(self) -> None:
        """tend_to_player はフェーズを問わず出る。

        全員が死体の場所に集まっているのに手当てだけできない、という
        状態を作らない。露出が無闇に広がる心配は無い。#860 の行ゲートが
        「同席かつ行動不能な相手が居るときだけ」に絞っている。

        蘇生の無い世界は、engine ではなくシナリオが `disabled_tools` で
        落とす。ここから外すと、蘇生のある世界を壊す。
        """
        assert "tend_to_player" in PHASE_COMMON_TOOLS


class TestReportingDoesNotKillTheReported:
    """報告した相手が、会議のあいだに死なない。

    レビューで指摘された失敗そのものを再現する。定数の関係 (上の class)
    だけだと、会議の終了処理が変わって上限どおりに閉じなくなったときに
    見逃す。実際に走らせて確かめる。
    """

    def test_the_fallen_survives_the_full_meeting(self) -> None:
        """会議を上限まで走らせても、報告された相手はまだ生きている。

        ここが落ちるなら、**倒れている人を見つけたと知らせる行為が、その
        相手を死体に変えている**。#848 の「倒れているだけの相手は蘇生できる」
        が成立しなくなる。

        **毎 tick 発言させるのが要点。** 黙らせると沈黙上限 (6) で会議が
        すぐ閉じてしまい、tick 上限を一度も通らない。最初この形で書いて
        しまい、穴が開いたままでもテストが通った。議論が続いている状況を
        作らないと、上限と猶予の一致を踏めない。
        """
        from pathlib import Path

        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )
        from ai_rpg_world.domain.player.enum.player_outcome_enum import (
            PlayerOutcomeEnum,
        )
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase

        scenario = (
            Path(__file__).resolve().parents[3]
            / "tests" / "fixtures" / "scenarios" / "darkened_station.json"
        )
        runtime = create_world_runtime(scenario)
        reporter, fallen = PlayerId(3), PlayerId(4)

        # アオイを倒す。まだ蘇生できる状態。
        #
        # 猶予タイマーへの登録まで自分で行う。repo に直接ダメージを入れる
        # だけでは aggregate に積まれた PlayerDownedEvent が publish されず、
        # **タイマーが動き出さないので永遠に死なない**。それに気付かずに
        # 「死ななかった」を assert すると、穴が開いたままでも通る空振りの
        # テストになる (実際に一度そう書いた)。
        status = runtime._player_status_repo.find_by_id(fallen)
        status.apply_damage(status.hp.value)
        runtime._player_status_repo.save(status)
        runtime._death_grace_timer.register(fallen, int(runtime.current_tick()))

        assert runtime.report_body(reporter, fallen).success

        # 誰も投票しないまま、議論だけが続く。発言し続けるので沈黙上限では
        # 終わらず、tick 上限まで走る。
        for _ in range(GamePhaseStore.DEFAULT_MEETING_TICK_LIMIT + 1):
            runtime.do_say(reporter, "まだ結論は出ない")
            runtime.advance_tick()

        assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM
        assert (
            runtime._player_outcome_registry.get_outcome(fallen)
            is not PlayerOutcomeEnum.DEAD
        )

    def test_tending_is_offered_while_the_meeting_runs(self) -> None:
        """会議中、倒れている相手への手当てが選択肢に出ている。

        全員が死体の場所に集まっているのに手当てだけできない、が
        起きていないことを実際の tool 一覧で確かめる。
        """
        from pathlib import Path

        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        scenario = (
            Path(__file__).resolve().parents[3]
            / "tests" / "fixtures" / "scenarios" / "darkened_station.json"
        )
        runtime = create_world_runtime(scenario)
        reporter, fallen = PlayerId(3), PlayerId(4)

        status = runtime._player_status_repo.find_by_id(fallen)
        status.apply_damage(status.hp.value)
        runtime._player_status_repo.save(status)
        runtime.report_body(reporter, fallen)

        names = [d.name for d in runtime.get_tool_definitions(for_every_player=True)]
        assert "tend_to_player" in names
