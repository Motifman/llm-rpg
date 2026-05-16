"""``SimulationTickLoop`` の自走挙動の単体テスト。

自走 tick 駆動アーキテクチャの第一歩。FastAPI に依存しない形で
loop 単体の start/stop/間隔変更/エラー耐性を確認する。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

# Import this first to break a pre-existing circular import in the
# observation contracts package (see chat_intervention test for the same
# workaround).
from ai_rpg_world.application.observation.services.observation_context_buffer import (  # noqa: F401
    DefaultObservationContextBuffer,
)
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
    _SessionState,
)
from ai_rpg_world.presentation.spot_graph_game.tick_loop import (
    SimulationTickLoop,
)


@dataclass
class _FakeRuntime:
    """``advance_tick()`` の呼び出し回数を記録するだけのスタブランタイム。

    ループは単一の asyncio スレッドで動くのでロックは不要。
    """

    name: str = "fake"
    advance_calls: int = 0
    fail_on_next: bool = False

    def advance_tick(self) -> int:
        if self.fail_on_next:
            self.fail_on_next = False
            raise RuntimeError("forced failure")
        self.advance_calls += 1
        return self.advance_calls


def _add_session(
    manager: GameRuntimeManager,
    session_id: str,
    runtime: _FakeRuntime,
    status: str = "running",
) -> None:
    manager._sessions[session_id] = _SessionState(
        session_id=session_id,
        world_id="w",
        world_title="W",
        character_ids=[],
        status=status,
        created_at="now",
        runtime=runtime,
    )


async def _wait_until(
    predicate, timeout: float = 1.0, poll: float = 0.01
) -> bool:
    """指定 predicate が True になるまで polling し、bool で結果を返す。

    時間ベースの sleep + assert より CI 負荷に強い。
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(poll)
    return predicate()


class TestSimulationTickLoop:
    """``SimulationTickLoop`` の自走挙動。"""

    def test_running_sessions_advance_on_interval(self) -> None:
        """interval ごとに running セッションの advance_tick が呼ばれる。"""
        manager = GameRuntimeManager()
        runtime = _FakeRuntime()
        _add_session(manager, "s1", runtime)

        async def scenario() -> bool:
            loop = SimulationTickLoop(manager=manager, interval_seconds=0.02)
            loop.start()
            try:
                return await _wait_until(
                    lambda: runtime.advance_calls >= 2, timeout=2.0
                )
            finally:
                await loop.stop()

        reached = asyncio.run(scenario())
        assert reached, (
            f"ループが 2 tick 進むことを期待 (実際: {runtime.advance_calls})"
        )

    def test_paused_and_ended_sessions_are_skipped(self) -> None:
        """paused / ended のセッションは tick が進まない。"""
        manager = GameRuntimeManager()
        running = _FakeRuntime("running")
        paused = _FakeRuntime("paused")
        ended = _FakeRuntime("ended")
        _add_session(manager, "r", running, status="running")
        _add_session(manager, "p", paused, status="paused")
        _add_session(manager, "e", ended, status="ended")

        async def scenario() -> None:
            loop = SimulationTickLoop(manager=manager, interval_seconds=0.02)
            loop.start()
            try:
                await _wait_until(
                    lambda: running.advance_calls >= 1, timeout=2.0
                )
            finally:
                await loop.stop()

        asyncio.run(scenario())

        assert running.advance_calls >= 1
        assert paused.advance_calls == 0
        assert ended.advance_calls == 0

    def test_exception_in_one_session_does_not_stop_loop(self) -> None:
        """1 セッションの例外が他セッションの tick を止めない。"""
        manager = GameRuntimeManager()
        bad = _FakeRuntime("bad", fail_on_next=True)
        good = _FakeRuntime("good")
        _add_session(manager, "bad", bad)
        _add_session(manager, "good", good)

        async def scenario() -> None:
            loop = SimulationTickLoop(manager=manager, interval_seconds=0.02)
            loop.start()
            try:
                await _wait_until(
                    lambda: good.advance_calls >= 2, timeout=2.0
                )
            finally:
                await loop.stop()

        asyncio.run(scenario())

        # good は影響を受けず複数回 tick されるはず
        assert good.advance_calls >= 2

    def test_stop_is_idempotent_and_fast(self) -> None:
        """stop() を二度呼んでも安全で、ループ終了は速やかに完了する。"""
        manager = GameRuntimeManager()
        _add_session(manager, "s", _FakeRuntime())

        async def scenario() -> SimulationTickLoop:
            loop = SimulationTickLoop(manager=manager, interval_seconds=0.05)
            loop.start()
            await asyncio.sleep(0.06)
            await loop.stop()
            await loop.stop()  # 二度目の stop でエラーにならない
            return loop

        loop = asyncio.run(scenario())
        assert not loop.is_running

    def test_start_is_idempotent(self) -> None:
        """既に running の loop に対して start() しても多重起動しない。"""
        manager = GameRuntimeManager()
        _add_session(manager, "s", _FakeRuntime())

        async def scenario() -> None:
            loop = SimulationTickLoop(manager=manager, interval_seconds=0.05)
            loop.start()
            first_task = loop._task
            loop.start()  # 二度目は no-op
            assert loop._task is first_task
            await loop.stop()

        asyncio.run(scenario())

    def test_invalid_interval_rejected_at_construction(self) -> None:
        """interval が極端に小さい場合は構築時に弾かれる。"""
        with pytest.raises(ValueError):
            SimulationTickLoop(
                manager=GameRuntimeManager(),
                interval_seconds=0.0,
            )

    def test_invalid_interval_rejected_in_setter(self) -> None:
        """set_interval も同様に validate される。"""
        loop = SimulationTickLoop(
            manager=GameRuntimeManager(),
            interval_seconds=1.0,
        )
        with pytest.raises(ValueError):
            loop.set_interval(0.0)

    def test_set_interval_takes_effect_at_next_iteration(self) -> None:
        """set_interval で短くした後は新しい cadence で tick が進む。"""
        manager = GameRuntimeManager()
        runtime = _FakeRuntime()
        _add_session(manager, "s", runtime)

        async def scenario() -> int:
            # 最初は粗いインターバルで開始 → tick がなかなか進まない
            loop = SimulationTickLoop(manager=manager, interval_seconds=1.0)
            loop.start()
            try:
                # tick 1 回目を待ってから interval を短くする
                await _wait_until(
                    lambda: runtime.advance_calls >= 1, timeout=2.0
                )
                baseline = runtime.advance_calls
                loop.set_interval(0.02)
                # interval 変更が次の sleep から効くため、現在進行中の sleep が
                # 終わるまで最大 1 秒待ち、その後 cadence で複数回 tick する
                # ことを確認
                await _wait_until(
                    lambda: runtime.advance_calls >= baseline + 3,
                    timeout=3.0,
                )
                return runtime.advance_calls
            finally:
                await loop.stop()

        final_calls = asyncio.run(scenario())
        assert final_calls >= 4
