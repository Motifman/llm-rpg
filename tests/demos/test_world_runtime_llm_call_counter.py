"""``#404`` P2 回帰テスト: WorldRuntime の LLM call counter / travel_active 集計。

progress.jsonl の可観測性フィールド (``llm_calls`` / ``travel_active``) は、
runtime の counter / aggregator を experiment progress reporter が
sample することで実現する。本テストは:

- ``bump_llm_call_count`` × N → ``pop_llm_call_count`` で N が返り、再度
  pop すると 0 (= read-and-reset セマンティクス) になる
- ``count_traveling_players`` が is_traveling な player 数を正しく数える
- 並列 bump (ThreadPoolExecutor 経由) でも値が落ちない

を保証する。silent failure (= 1 driver iteration の内訳が抜ける) が出ると、
656 秒スパイクのような原因不明事象の調査がまた振り出しに戻るため。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCENARIO_PATH = _REPO_ROOT / "data" / "scenarios" / "forbidden_library_demo.json"


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LLM_EPISODIC_ENABLED", raising=False)
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
    return create_world_runtime(_SCENARIO_PATH)


class TestLlmCallCounter:
    """LLM 呼び出しカウンタ (#404 P2)。"""

    def test_initial_value_zero(self, runtime) -> None:
        """初期値は 0。"""
        assert runtime.pop_llm_call_count() == 0

    def test_bump_three_pop_three_pop_zero(self, runtime) -> None:
        """bump 3回 pop で 3が返り 次の pop は 0。"""
        runtime.bump_llm_call_count()
        runtime.bump_llm_call_count()
        runtime.bump_llm_call_count()
        assert runtime.pop_llm_call_count() == 3
        assert runtime.pop_llm_call_count() == 0

    def test_column_bump_value_does_not_crash(self, runtime) -> None:
        """ThreadPoolExecutor で 4 worker × 250 bump = 1000 件。Lock 不在で
        ++int が race するパスを検知する。"""
        N = 1000
        WORKERS = 4
        per_worker = N // WORKERS
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futures = [
                ex.submit(lambda: [runtime.bump_llm_call_count() for _ in range(per_worker)])
                for _ in range(WORKERS)
            ]
            for f in futures:
                f.result()
        assert runtime.pop_llm_call_count() == per_worker * WORKERS


class TestCountTravelingPlayers:
    """travel_active 集計 (#404 P2)。"""

    def test_zero(self, runtime) -> None:
        """誰も移動していない時は 0。"""
        assert runtime.count_traveling_players() == 0

    def test_returns_one_1(self, runtime) -> None:
        """1人移動を開始すると 1が返る。"""
        player_id = runtime.get_player_ids()[0]
        runtime.do_move(player_id, "reading_room")
        assert runtime.count_traveling_players() == 1

    def test_returns_zero(self, runtime) -> None:
        """到着すると 0に戻る。"""
        player_id = runtime.get_player_ids()[0]
        runtime.do_move(player_id, "reading_room")
        runtime.advance_until_player_idle(player_id)
        assert runtime.count_traveling_players() == 0
