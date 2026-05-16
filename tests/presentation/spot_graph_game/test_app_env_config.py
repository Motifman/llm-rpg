"""``app._read_tick_loop_config`` の env パース挙動 (NaN / inf を含む)。

PR #151 セルフレビュー (MED-SEC: NaN/inf バイパスガード) の回帰防止。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.presentation.spot_graph_game.app import (
    _DEFAULT_TICK_INTERVAL_SEC,
    _read_tick_loop_config,
)


class TestReadTickLoopConfig:
    """``_read_tick_loop_config`` の境界挙動。"""

    def test_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env 未設定なら enabled=True / default interval を返す。"""
        monkeypatch.delenv("SPOT_GRAPH_TICK_LOOP_ENABLED", raising=False)
        monkeypatch.delenv("SPOT_GRAPH_TICK_INTERVAL_SEC", raising=False)
        enabled, interval = _read_tick_loop_config()
        assert enabled is True
        assert interval == _DEFAULT_TICK_INTERVAL_SEC

    def test_disabled_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """false 値で enabled=False を返す。"""
        monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
        enabled, _ = _read_tick_loop_config()
        assert enabled is False

    def test_invalid_float_string_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """float() で raise する文字列は default に fallback。"""
        monkeypatch.setenv("SPOT_GRAPH_TICK_INTERVAL_SEC", "not_a_number")
        _, interval = _read_tick_loop_config()
        assert interval == _DEFAULT_TICK_INTERVAL_SEC

    def test_negative_value_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """負の値は default に fallback (loop 構築で raise させない)。"""
        monkeypatch.setenv("SPOT_GRAPH_TICK_INTERVAL_SEC", "-1.0")
        _, interval = _read_tick_loop_config()
        assert interval == _DEFAULT_TICK_INTERVAL_SEC

    def test_nan_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """NaN は default に fallback (isfinite ガード)。"""
        monkeypatch.setenv("SPOT_GRAPH_TICK_INTERVAL_SEC", "nan")
        _, interval = _read_tick_loop_config()
        assert interval == _DEFAULT_TICK_INTERVAL_SEC

    def test_positive_infinity_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """+inf は default に fallback。"""
        monkeypatch.setenv("SPOT_GRAPH_TICK_INTERVAL_SEC", "inf")
        _, interval = _read_tick_loop_config()
        assert interval == _DEFAULT_TICK_INTERVAL_SEC

    def test_valid_value_passes_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """有効な値はそのまま使われる。"""
        monkeypatch.setenv("SPOT_GRAPH_TICK_INTERVAL_SEC", "2.5")
        _, interval = _read_tick_loop_config()
        assert interval == 2.5
