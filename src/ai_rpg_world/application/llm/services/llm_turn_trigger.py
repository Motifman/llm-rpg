"""
LLM ターン駆動のデフォルト実装。
スケジュール済みプレイヤーを保持し、run_scheduled_turns で LlmAgentTurnRunner.run_turn を 1 プレイヤーあたり 1 回ずつ実行する。
プレイヤー単位で例外を隔離し、1 人の失敗で他プレイヤーの予定ターンが失われない。
"""

import logging

from ai_rpg_world.application.llm.contracts.interfaces import ILlmTurnTrigger
from ai_rpg_world.application.llm.services.llm_agent_turn_runner import LlmAgentTurnRunner
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class DefaultLlmTurnTrigger(ILlmTurnTrigger):
    """
    観測到着時に schedule_turn でキューに追加し、
    ゲームループ等から run_scheduled_turns で一括実行する。
    同一プレイヤーは 1 回の run_scheduled_turns で 1 回だけ run_turn される。
    プレイヤー単位で例外を隔離するため、1 人の run_turn 失敗でも他プレイヤーは実行される。
    """

    def __init__(self, turn_runner: LlmAgentTurnRunner) -> None:
        if not isinstance(turn_runner, LlmAgentTurnRunner):
            raise TypeError("turn_runner must be LlmAgentTurnRunner")
        self._turn_runner = turn_runner
        self._pending: set[int] = set()
        self._logger = logging.getLogger(self.__class__.__name__)

    def schedule_turn(self, player_id: PlayerId) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        self._pending.add(player_id.value)

    def run_scheduled_turns(self) -> None:
        """
        スケジュール済みの全プレイヤーについて run_turn を 1 回ずつ実行し、キューをクリアする。
        1起動1ツール前提: 実行結果の should_reschedule が True の場合のみ、次 tick 用に _pending へ戻す。
        同一 run_scheduled_turns 内の自己ループは作らず、次 tick 送りに固定する。
        プレイヤー単位で例外を隔離し、失敗したプレイヤーはログに記録するが他プレイヤーの実行は継続する。
        """
        to_run = list(self._pending)
        self._pending.clear()
        for pid in to_run:
            try:
                result = self._turn_runner.run_turn(PlayerId(pid))
                if result.should_reschedule:
                    self._pending.add(pid)
            except Exception as e:
                self._logger.warning(
                    "LLM turn failed for player %s: %s",
                    pid,
                    str(e),
                    exc_info=True,
                )
