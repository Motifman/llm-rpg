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

    def __init__(self, turn_runner: LlmAgentTurnRunner, max_turns: int = 5) -> None:
        if not isinstance(turn_runner, LlmAgentTurnRunner):
            raise TypeError("turn_runner must be LlmAgentTurnRunner")
        if not isinstance(max_turns, int) or max_turns < 1:
            raise ValueError("max_turns must be a positive int")
        self._turn_runner = turn_runner
        self._max_turns = max_turns
        self._pending: set[int] = set()
        self._turn_counts: dict[int, int] = {}
        self._logger = logging.getLogger(self.__class__.__name__)

    def schedule_turn(self, player_id: PlayerId) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        pid = player_id.value
        self._pending.add(pid)
        self._turn_counts[pid] = 0

    def run_scheduled_turns(self) -> None:
        """
        スケジュール済みの全プレイヤーについて run_turn を 1 回ずつ実行し、キューをクリアする。
        継続条件: world_no_op でなければ max_turns 未達まで次 tick で再実行。
        should_reschedule が True のときは従来どおりエラー再試行として継続。
        プレイヤー単位で例外を隔離し、失敗したプレイヤーはログに記録するが他プレイヤーの実行は継続する。
        """
        to_run = list(self._pending)
        self._pending.clear()
        for pid in to_run:
            try:
                result = self._turn_runner.run_turn(PlayerId(pid))
                current_count = self._turn_counts.get(pid, 0)
                new_count = current_count + 1

                if result.was_no_op:
                    self._turn_counts.pop(pid, None)
                elif result.should_reschedule:
                    self._pending.add(pid)
                elif new_count < self._max_turns:
                    self._pending.add(pid)
                    self._turn_counts[pid] = new_count
                else:
                    self._turn_counts.pop(pid, None)
            except Exception as e:
                self._logger.warning(
                    "LLM turn failed for player %s: %s",
                    pid,
                    str(e),
                    exc_info=True,
                )
