"""``#404`` 修正の回帰テスト: ``do_move`` がネスト ``advance_tick`` を回さない。

旧実装: ``EscapeGameRuntime.do_move`` は ``start_travel_to_spot`` 後に
``for _ in range(200): advance_tick()`` を回し、travel が完了するまでツール
内で同期的に world tick を進めていた。これが 1 driver tick = 656 秒の
wall time スパイクと「travel 1 回で 134 LLM call」の silent failure (#404)
の主因だった。

新実装: ``do_move`` は travel state を立てて即 return する。

本テストはその振る舞いを最小構成で固める:

- ``do_move`` 呼び出し前後で world tick が **進まない** こと
- 呼び出し直後に ``is_traveling=True`` が立つこと
- ``advance_until_player_idle`` を回せば最終的に到着すること
"""

from __future__ import annotations

from pathlib import Path

import pytest

from demos.escape_game.escape_game_runtime import create_escape_game_runtime


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCENARIO_PATH = _REPO_ROOT / "data" / "scenarios" / "forbidden_library_demo.json"


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LLM_EPISODIC_ENABLED", raising=False)
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
    return create_escape_game_runtime(_SCENARIO_PATH)


class TestDoMoveNoNestedAdvanceTick:
    """``do_move`` は travel 開始だけで返り、world tick を進めない。"""

    def test_do_move_は_world_tick_を進めない(self, runtime) -> None:
        """旧実装は 200 回まで advance_tick を回していた。新実装は 0 回。"""
        player_id = runtime.get_player_ids()[0]
        tick_before = runtime.current_tick()

        runtime.do_move(player_id, "reading_room")

        tick_after = runtime.current_tick()
        assert tick_after == tick_before, (
            f"do_move でネスト advance_tick が走った: "
            f"{tick_before} → {tick_after}"
        )

    def test_do_move_直後は_is_traveling_True(self, runtime) -> None:
        """travel state が立ち、後続 tick で advance される下準備ができる。"""
        player_id = runtime.get_player_ids()[0]
        runtime.do_move(player_id, "reading_room")

        status = runtime._player_status_repo.find_by_id(player_id)
        assert status is not None
        nav = status.spot_navigation_state
        assert nav is not None
        assert nav.is_traveling, "do_move で is_traveling が立たない"

    def test_advance_until_player_idle_で到着まで進む(self, runtime) -> None:
        """外側ループ相当の advance_tick を回せば最終的に at_rest になる。"""
        player_id = runtime.get_player_ids()[0]
        runtime.do_move(player_id, "reading_room")
        runtime.advance_until_player_idle(player_id)

        assert runtime.get_player_spot_name(player_id) == "閲覧室"
        status = runtime._player_status_repo.find_by_id(player_id)
        assert status is not None
        nav = status.spot_navigation_state
        assert nav is not None
        assert not nav.is_traveling

    def test_同一_spot_指定は_no_op_で_world_tick_も進めない(self, runtime) -> None:
        """既に居る spot を指定した場合も world tick は進まない。"""
        player_id = runtime.get_player_ids()[0]
        current_spot_name = runtime.get_player_spot_name(player_id)
        # current spot の str_id を得る (id_mapper 経由)
        tick_before = runtime.current_tick()
        # forbidden_library_demo の player_a 初期位置は entrance_hall
        runtime.do_move(player_id, "entrance_hall")

        # spot 名 / tick 不変、is_traveling は立たない
        assert runtime.get_player_spot_name(player_id) == current_spot_name
        assert runtime.current_tick() == tick_before
        status = runtime._player_status_repo.find_by_id(player_id)
        assert status is not None
        nav = status.spot_navigation_state
        # nav が None (= 初期化前) ではないか、is_traveling=False のどちらか
        assert nav is None or not nav.is_traveling
