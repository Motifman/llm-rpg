"""パズル判定のドメインサービス（stateless）。

組み合わせ錠・順序パズル・アイテム合成のパズル入力を評価し、
更新された PuzzleState を返す。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ai_rpg_world.domain.world_graph.value_object.puzzle_state import PuzzleState


@dataclass(frozen=True)
class PuzzleEvaluationResult:
    """パズル評価結果。"""

    new_puzzle: PuzzleState
    is_just_solved: bool  # 今回の入力で解けたか
    message: str


class PuzzleEvaluationService:
    """パズル入力を評価し、状態を遷移させる。"""

    def evaluate(self, puzzle: PuzzleState, input_value: str) -> PuzzleEvaluationResult:
        if puzzle.is_solved:
            return PuzzleEvaluationResult(
                new_puzzle=puzzle,
                is_just_solved=False,
                message="このパズルは既に解かれている。",
            )

        if puzzle.is_max_attempts_reached:
            return PuzzleEvaluationResult(
                new_puzzle=puzzle,
                is_just_solved=False,
                message="試行回数の上限に達した。もう操作できない。",
            )

        if puzzle.puzzle_type == "combination_lock":
            return self._evaluate_combination_lock(puzzle, input_value)
        if puzzle.puzzle_type == "sequence":
            return self._evaluate_sequence(puzzle, input_value)

        return PuzzleEvaluationResult(
            new_puzzle=puzzle,
            is_just_solved=False,
            message=f"未知のパズルタイプ: {puzzle.puzzle_type}",
        )

    def _evaluate_combination_lock(
        self, puzzle: PuzzleState, input_value: str
    ) -> PuzzleEvaluationResult:
        """組み合わせ錠: 正解コードと一致すれば解除。"""
        expected = "".join(puzzle.solution)
        if input_value == expected:
            solved = puzzle.with_input(input_value).with_solved()
            return PuzzleEvaluationResult(
                new_puzzle=solved,
                is_just_solved=True,
                message="正しいコードだ。ロックが解除された。",
            )
        new_puzzle = puzzle.with_input(input_value)
        if new_puzzle.is_max_attempts_reached:
            return PuzzleEvaluationResult(
                new_puzzle=new_puzzle,
                is_just_solved=False,
                message="コードが違う。試行回数の上限に達した。",
            )
        return PuzzleEvaluationResult(
            new_puzzle=new_puzzle,
            is_just_solved=False,
            message="コードが違う。",
        )

    def _evaluate_sequence(
        self, puzzle: PuzzleState, input_value: str
    ) -> PuzzleEvaluationResult:
        """順序パズル: 正しい順番で入力すれば解除。間違えたらリセット。"""
        next_index = len(puzzle.current_input)
        if next_index >= len(puzzle.solution):
            return PuzzleEvaluationResult(
                new_puzzle=puzzle,
                is_just_solved=False,
                message="入力が解の長さを超えている。",
            )

        expected = puzzle.solution[next_index]
        if input_value == expected:
            new_puzzle = puzzle.with_step(input_value)
            if len(new_puzzle.current_input) == len(puzzle.solution):
                solved = new_puzzle.with_solved()
                return PuzzleEvaluationResult(
                    new_puzzle=solved,
                    is_just_solved=True,
                    message="正しい順序だ。パズルが解除された。",
                )
            return PuzzleEvaluationResult(
                new_puzzle=new_puzzle,
                is_just_solved=False,
                message=f"正しい。あと{len(puzzle.solution) - len(new_puzzle.current_input)}ステップ。",
            )

        # 順序間違い → リセット
        reset = puzzle.with_reset_input()
        return PuzzleEvaluationResult(
            new_puzzle=reset,
            is_just_solved=False,
            message="順序が違う。最初からやり直しだ。",
        )
