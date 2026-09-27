"""openrouter_ping が provider 選定に使える形で結果を返すことを保証する。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "openrouter_ping.py"


@pytest.fixture(scope="module")
def ping():
    spec = importlib.util.spec_from_file_location("openrouter_ping", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _response(*, tool_calls, finish_reason):
    message = SimpleNamespace(content="", tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=None, model="m")


class TestTheSummarySaysWhetherAToolCameBack:
    """要約に、ツールが返ったかと打ち切り理由が載る。"""

    def test_reports_a_returned_tool_call(self, ping) -> None:
        """ツール呼び出しが返った応答は tool_called が真で、打ち切り理由も載る。"""
        summary = ping._summarize(
            _response(tool_calls=[object()], finish_reason="tool_calls"), 10
        )

        assert summary["tool_called"] is True
        assert summary["finish_reason"] == "tool_calls"

    def test_reports_a_response_cut_off_before_the_tool(self, ping) -> None:
        """上限で打ち切られツールが無い応答は tool_called が偽で、打ち切り理由が length になる。"""
        summary = ping._summarize(_response(tool_calls=None, finish_reason="length"), 10)

        assert summary["tool_called"] is False
        assert summary["finish_reason"] == "length"


class TestRepeatIsBounded:
    """直列の繰り返し回数に上限がある。"""

    @pytest.mark.parametrize("repeat", [0, 31])
    def test_out_of_range_repeat_is_refused_before_any_call(
        self, ping, monkeypatch, repeat: int
    ) -> None:
        """--repeat が 1〜30 の外なら、クライアントを作る前に終了コード 2 で止まる。"""
        def fail(*_args, **_kwargs):
            raise AssertionError("呼び出してはいけない")

        monkeypatch.setattr(ping, "LiteLLMClient", fail)

        assert ping.main(["--repeat", str(repeat)]) == 2
