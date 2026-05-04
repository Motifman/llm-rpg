"""パズル状態の値オブジェクト。

SpotObject に付与し、組み合わせ錠・順序パズル・アイテム合成等の
状態を不変に管理する。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Tuple


@dataclass(frozen=True)
class PuzzleState:
    puzzle_type: str  # "combination_lock" | "sequence"
    solution: Tuple[str, ...]
    current_input: Tuple[str, ...] = ()
    is_solved: bool = False
    max_attempts: Optional[int] = None
    attempts: int = 0

    def __post_init__(self) -> None:
        if not self.puzzle_type.strip():
            raise ValueError("puzzle_type cannot be empty")
        if not self.solution:
            raise ValueError("solution cannot be empty")

    def with_input(self, input_value: str) -> PuzzleState:
        """入力を追加し試行回数を増やす（組み合わせ錠の1回の入力等）。"""
        return replace(
            self,
            current_input=self.current_input + (input_value,),
            attempts=self.attempts + 1,
        )

    def with_step(self, input_value: str) -> PuzzleState:
        """正解ステップの記録（試行回数は増やさない。順序パズルの途中入力用）。"""
        return replace(
            self,
            current_input=self.current_input + (input_value,),
        )

    def with_solved(self) -> PuzzleState:
        return replace(self, is_solved=True)

    def with_reset_input(self) -> PuzzleState:
        """入力をリセットして試行回数を増やす（失敗した1シーケンスで1回）。"""
        return replace(self, current_input=(), attempts=self.attempts + 1)

    @property
    def is_max_attempts_reached(self) -> bool:
        return self.max_attempts is not None and self.attempts >= self.max_attempts
