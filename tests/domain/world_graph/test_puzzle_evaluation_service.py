"""PuzzleEvaluationService と PuzzleState のユニットテスト。

組み合わせ錠・順序パズルの入力評価、状態遷移、試行回数制限を検証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.service.puzzle_evaluation_service import (
    PuzzleEvaluationService,
)
from ai_rpg_world.domain.world_graph.value_object.puzzle_state import PuzzleState


def _combination_lock(code: str = "1234", max_attempts: int | None = None) -> PuzzleState:
    return PuzzleState(
        puzzle_type="combination_lock",
        solution=tuple(code),
        max_attempts=max_attempts,
    )


def _sequence_puzzle(steps: tuple = ("a", "b", "c")) -> PuzzleState:
    return PuzzleState(
        puzzle_type="sequence",
        solution=steps,
    )


class TestPuzzleStateValidation:
    """PuzzleState のバリデーションテスト"""

    def test_empty_puzzle_type_raises(self) -> None:
        """空のpuzzle_typeでValueErrorが発生すること"""
        with pytest.raises(ValueError, match="puzzle_type cannot be empty"):
            PuzzleState(puzzle_type="", solution=("1",))

    def test_empty_solution_raises(self) -> None:
        """空のsolutionでValueErrorが発生すること"""
        with pytest.raises(ValueError, match="solution cannot be empty"):
            PuzzleState(puzzle_type="combination_lock", solution=())

    def test_puzzle_state_is_frozen(self) -> None:
        """PuzzleStateがfrozenであること"""
        ps = _combination_lock()
        with pytest.raises(AttributeError):
            ps.is_solved = True  # type: ignore[misc]


class TestCombinationLock:
    """組み合わせ錠パズルのテスト"""

    def test_correct_code_solves(self) -> None:
        """正しいコードで解除されること"""
        svc = PuzzleEvaluationService()
        puzzle = _combination_lock("1234")
        result = svc.evaluate(puzzle, "1234")
        assert result.is_just_solved is True
        assert result.new_puzzle.is_solved is True
        assert result.new_puzzle.attempts == 1

    def test_wrong_code_does_not_solve(self) -> None:
        """間違ったコードで解除されないこと"""
        svc = PuzzleEvaluationService()
        puzzle = _combination_lock("1234")
        result = svc.evaluate(puzzle, "0000")
        assert result.is_just_solved is False
        assert result.new_puzzle.is_solved is False
        assert result.new_puzzle.attempts == 1

    def test_already_solved_returns_immediately(self) -> None:
        """既に解けたパズルは再評価しないこと"""
        svc = PuzzleEvaluationService()
        puzzle = _combination_lock().with_input("1234").with_solved()
        result = svc.evaluate(puzzle, "anything")
        assert result.is_just_solved is False
        assert "既に解かれている" in result.message

    def test_max_attempts_blocks(self) -> None:
        """試行回数上限に達したら操作不能になること"""
        svc = PuzzleEvaluationService()
        puzzle = _combination_lock("1234", max_attempts=2)
        # 1回目
        r1 = svc.evaluate(puzzle, "0000")
        assert r1.is_just_solved is False
        # 2回目 → 上限到達メッセージ
        r2 = svc.evaluate(r1.new_puzzle, "0000")
        assert "上限" in r2.message
        # 3回目 → ブロック
        r3 = svc.evaluate(r2.new_puzzle, "1234")
        assert r3.is_just_solved is False
        assert "上限" in r3.message

    def test_correct_on_last_attempt(self) -> None:
        """最後の1回で正解すれば解除されること"""
        svc = PuzzleEvaluationService()
        puzzle = _combination_lock("1234", max_attempts=2)
        r1 = svc.evaluate(puzzle, "0000")  # 1回目: 失敗
        r2 = svc.evaluate(r1.new_puzzle, "1234")  # 2回目: 正解
        assert r2.is_just_solved is True


class TestSequencePuzzle:
    """順序パズルのテスト"""

    def test_correct_sequence_solves(self) -> None:
        """正しい順番で全入力すると解除されること"""
        svc = PuzzleEvaluationService()
        puzzle = _sequence_puzzle(("a", "b", "c"))
        r1 = svc.evaluate(puzzle, "a")
        assert r1.is_just_solved is False
        assert "あと2" in r1.message
        r2 = svc.evaluate(r1.new_puzzle, "b")
        assert r2.is_just_solved is False
        r3 = svc.evaluate(r2.new_puzzle, "c")
        assert r3.is_just_solved is True
        assert r3.new_puzzle.is_solved is True

    def test_wrong_order_resets(self) -> None:
        """間違った順番で入力すると最初からリセットされること"""
        svc = PuzzleEvaluationService()
        puzzle = _sequence_puzzle(("a", "b", "c"))
        r1 = svc.evaluate(puzzle, "a")  # 正しい
        r2 = svc.evaluate(r1.new_puzzle, "c")  # 間違い
        assert r2.is_just_solved is False
        assert "最初からやり直し" in r2.message
        assert r2.new_puzzle.current_input == ()

    def test_retry_after_reset(self) -> None:
        """リセット後にやり直せること"""
        svc = PuzzleEvaluationService()
        puzzle = _sequence_puzzle(("x", "y"))
        r1 = svc.evaluate(puzzle, "y")  # 間違い→リセット
        r2 = svc.evaluate(r1.new_puzzle, "x")  # 正しい
        r3 = svc.evaluate(r2.new_puzzle, "y")  # 正しい→解除
        assert r3.is_just_solved is True

    def test_correct_steps_do_not_consume_attempts(self) -> None:
        """正解ステップは試行回数を消費しないこと（失敗リセットのみカウント）"""
        svc = PuzzleEvaluationService()
        puzzle = _sequence_puzzle(("a", "b", "c"))
        r1 = svc.evaluate(puzzle, "a")
        assert r1.new_puzzle.attempts == 0  # 正解ステップはカウントしない
        r2 = svc.evaluate(r1.new_puzzle, "b")
        assert r2.new_puzzle.attempts == 0
        r3 = svc.evaluate(r2.new_puzzle, "c")  # 解除
        assert r3.is_just_solved is True
        assert r3.new_puzzle.attempts == 0  # 正解ステップはカウントしない

    def test_sequence_max_attempts_counts_failed_sequences(self) -> None:
        """max_attemptsは失敗シーケンス回数でカウントされること"""
        svc = PuzzleEvaluationService()
        puzzle = PuzzleState(
            puzzle_type="sequence",
            solution=("a", "b"),
            max_attempts=2,
        )
        # 1回目失敗
        r1 = svc.evaluate(puzzle, "b")  # 間違い→リセット (attempts=1)
        assert r1.new_puzzle.attempts == 1
        # 2回目失敗 (attempts=2 → 上限到達)
        r2 = svc.evaluate(r1.new_puzzle, "b")  # 間違い→リセット (attempts=2)
        assert r2.new_puzzle.attempts == 2
        # 3回目→ブロック（上限到達後はevaluate冒頭で弾かれる）
        r3 = svc.evaluate(r2.new_puzzle, "a")
        assert r3.is_just_solved is False
        assert "上限" in r3.message


class TestUnknownPuzzleType:
    """未知のパズルタイプのテスト"""

    def test_unknown_type_returns_message(self) -> None:
        """未知のpuzzle_typeではエラーメッセージを返すこと"""
        svc = PuzzleEvaluationService()
        puzzle = PuzzleState(puzzle_type="custom_type", solution=("x",))
        result = svc.evaluate(puzzle, "x")
        assert result.is_just_solved is False
        assert "未知" in result.message
