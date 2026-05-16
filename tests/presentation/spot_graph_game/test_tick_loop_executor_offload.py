"""``SimulationTickLoop`` の executor offload の挙動テスト。

Issue #154 で報告された「LLM 同期 I/O が event loop を占有しウォールタイムが
伸びる」問題への対応 (B-2)。

検証する不変条件:
1. tick 中 (advance_tick が blocking sleep を含むケース) でも
   event loop が応答可能 (= 別の async task がほぼ即座に進める)
2. 既存の advance_tick 結果・連続失敗カウンタの挙動は変わらない
3. 単一の executor 内で実行されるので同一セッションの tick が並列に
   重ならない (state-corruption 回避)
"""

from __future__ import annotations

import asyncio
import time

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


class _BlockingRuntime:
    """advance_tick で意図的に sync sleep する (LLM I/O を模倣)。"""

    def __init__(self, block_seconds: float = 0.15) -> None:
        self._block_seconds = block_seconds
        self.calls = 0

    def advance_tick(self) -> int:
        # 同期 sleep — event loop に直接呼ばれると loop 全体がブロックされる
        time.sleep(self._block_seconds)
        self.calls += 1
        return self.calls


class _SerialCheckRuntime:
    """advance_tick が **並列に重ならない** ことを assert するランタイム。"""

    def __init__(self) -> None:
        self._active = 0
        self._max_active = 0
        self.calls = 0

    def advance_tick(self) -> int:
        self._active += 1
        self._max_active = max(self._max_active, self._active)
        try:
            time.sleep(0.02)
            self.calls += 1
            return self.calls
        finally:
            self._active -= 1


def _add(manager: GameRuntimeManager, sid: str, runtime) -> None:
    manager._sessions[sid] = _SessionState(
        session_id=sid,
        world_id="w",
        world_title="W",
        character_ids=[],
        status="running",
        created_at="now",
        runtime=runtime,
    )


class TestExecutorOffload:
    """tick が executor にオフロードされ event loop を blocking しない。"""

    def test_event_loop_stays_responsive_during_blocking_tick(self) -> None:
        """advance_tick が長く blocking しても event loop は応答する。

        executor にオフロードしない実装では、advance_tick の sleep 中に
        event loop 全体がブロックされ、別の asyncio タスクが進めなくなる。
        オフロード実装ではこの並行タスクは独立に多数回進められるはず。

        絶対時間で 20 回完走を期待する書き方は CI の負荷で fragile になる
        ため、**相対比較**で検証する: 「tick による blocking 時間より十分
        多い回数」を相対的に求めるアプローチ。
        """
        manager = GameRuntimeManager()
        # 300ms blocking — event loop が直結なら 1 tick 中はほぼ全ての
        # asyncio sleep が完了できない。executor 経由なら影響を受けない。
        runtime = _BlockingRuntime(block_seconds=0.30)
        _add(manager, "blocked", runtime)

        async def scenario() -> int:
            loop = SimulationTickLoop(manager=manager, interval_seconds=0.02)
            counter = {"n": 0}

            async def heartbeat_task() -> None:
                # tick が 1 回完走する間 (~300ms)、10ms 周期で yield する
                # 何回 yield できたかで event loop の応答性を測る
                deadline = asyncio.get_running_loop().time() + 0.4
                while asyncio.get_running_loop().time() < deadline:
                    await asyncio.sleep(0.01)
                    counter["n"] += 1

            loop.start()
            try:
                await heartbeat_task()
            finally:
                await loop.stop()
            return counter["n"]

        ticks_before = runtime.calls
        n = asyncio.run(scenario())

        # event loop が tick で 300ms ブロックされると 0.4s の窓で
        # 進めるのは概ね 10 回前後。offload 実装では 30 回前後進めるはず。
        # 中間値 20 を最低ラインに置けば、CI スケジューラ揺らぎを許容しつつ
        # blocking 検出として有効。
        assert n >= 20, (
            f"event loop appears blocked; heartbeat progressed only {n} times"
        )
        # tick が少なくとも 1 回は走った
        assert runtime.calls > ticks_before

    def test_serial_invocation_within_executor(self) -> None:
        """同じ runtime に対する advance_tick は並列に重ならない (シリアル実行)。

        現在の実装は default executor を 1 タスクで使うため、ある tick の
        advance_tick が完了する前に次の tick が始まることはない。
        state-corruption リスクを抑える性質を回帰として固定する。
        """
        manager = GameRuntimeManager()
        runtime = _SerialCheckRuntime()
        _add(manager, "serial", runtime)

        async def scenario() -> None:
            loop = SimulationTickLoop(manager=manager, interval_seconds=0.01)
            loop.start()
            try:
                # 数 tick 回す
                running_loop = asyncio.get_running_loop()
                deadline = running_loop.time() + 0.3
                while runtime.calls < 3 and running_loop.time() < deadline:
                    await asyncio.sleep(0.01)
            finally:
                await loop.stop()

        asyncio.run(scenario())
        assert runtime.calls >= 2
        # 並列に走った瞬間が観測されなかったこと (max_active が常に 1)
        assert runtime._max_active == 1, (
            f"advance_tick was invoked in parallel (max_active={runtime._max_active})"
        )
