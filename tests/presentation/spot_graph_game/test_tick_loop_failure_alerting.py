"""``SimulationTickLoop`` の連続失敗アラーティング挙動の回帰テスト。

PR #151 セルフレビュー (MED: 連続失敗の見落とし防止) を反映。
"""

from __future__ import annotations

import asyncio
import logging

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


class _AlwaysFailRuntime:
    """``advance_tick`` 呼び出しのたびに例外を投げるランタイム。"""

    def advance_tick(self) -> int:
        raise RuntimeError("boom")


class _OkRuntime:
    def __init__(self) -> None:
        self.count = 0

    def advance_tick(self) -> int:
        self.count += 1
        return self.count


def _add(manager: GameRuntimeManager, sid: str, runtime, status: str = "running") -> None:
    manager._sessions[sid] = _SessionState(
        session_id=sid,
        world_id="w",
        world_title="W",
        character_ids=[],
        status=status,
        created_at="now",
        runtime=runtime,
    )


class TestConsecutiveFailureAlerting:
    """連続失敗が閾値に達したら ERROR ログを出す挙動。"""

    def test_alert_logged_after_consecutive_failures(self, caplog) -> None:
        """同一セッションが連続失敗すると閾値で ERROR を 1 回出す。"""
        manager = GameRuntimeManager()
        _add(manager, "bad", _AlwaysFailRuntime())
        loop = SimulationTickLoop(manager=manager, interval_seconds=0.02)

        async def scenario() -> None:
            with caplog.at_level(
                logging.ERROR,
                logger="ai_rpg_world.presentation.spot_graph_game.tick_loop",
            ):
                loop.start()
                try:
                    # 6 回程度回す (閾値 = 5)
                    await asyncio.sleep(0.20)
                finally:
                    await loop.stop()

        asyncio.run(scenario())

        # ERROR ログに 'manual intervention may be required' が含まれる
        assert any(
            "manual intervention may be required" in record.message
            for record in caplog.records
            if record.levelno == logging.ERROR
        )

    def test_counter_resets_on_success(self) -> None:
        """1 度成功するとカウンタがリセットされる (途中で復旧したセッション)。"""
        runtime = _OkRuntime()
        manager = GameRuntimeManager()
        _add(manager, "ok", runtime)
        loop = SimulationTickLoop(manager=manager, interval_seconds=0.02)

        async def scenario() -> None:
            loop.start()
            await asyncio.sleep(0.1)
            await loop.stop()

        asyncio.run(scenario())
        # 連続失敗カウンタは空 (内部 dict)
        assert loop._consecutive_failures == {}
        assert runtime.count >= 1
