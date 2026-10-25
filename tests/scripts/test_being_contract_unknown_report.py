"""``scripts/being_contract_unknown_report.py`` が trace から観測を組み直し、「不明」の欄を経路ごとに数えることを保証する。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/being_contract_unknown_report.py"


@pytest.fixture(scope="module")
def report() -> ModuleType:
    spec = importlib.util.spec_from_file_location("being_contract_unknown_report", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _event(seq: int, kind: str, tick: int, player_id: int, **payload: Any) -> dict[str, Any]:
    return {"seq": seq, "kind": kind, "tick": tick, "player_id": player_id, "payload": payload}


def _observation(seq: int, tick: int, player_id: int, label: str, **fields: Any) -> dict[str, Any]:
    payload = {
        "prose": "カイが言った: 「水場は北だ」",
        "structured": {"type": "player_spoke", "speaker": "カイ", "channel": "say", "role": "other"},
        "observation_category": "social",
        "schedules_turn": True,
        "game_time_label": label,
    }
    payload.update(fields)
    return _event(seq, "observation", tick, player_id, **payload)


def _write_trace(tmp_path: Path, events: list[dict[str, Any]]) -> Path:
    trace = tmp_path / "trace.jsonl"
    trace.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
    return trace


def _spawn(seq: int, player_id: int, name: str, spot: str) -> dict[str, Any]:
    return _event(seq, "position_change", 0, player_id, player_name=name, spot_name=spot)


def test_counts_unknown_fields_per_route_and_pairs_action_results(report: ModuleType, tmp_path: Path) -> None:
    """発言とツールの結果を組み直し、発言の「自分宛てか」だけが「不明」として数えられる。"""
    trace = _write_trace(
        tmp_path,
        [
            _spawn(1, 2, "ノア", "浜辺"),
            _observation(2, 1, 2, "深夜 0:05"),
            _event(3, "action", 1, 2, tool="travel_to", arguments={}),
            _event(4, "action_result", 1, 2, tool="travel_to", success=False, result_summary="進めない。"),
        ],
    )
    tally = report.Tally()

    report.tally_trace(trace, tally)

    assert tally.converted == {"ToldOrWritten": 1, "OwnActionResult": 1}
    assert dict(tally.unknown) == {("addressed_to_self", "ToldOrWritten"): 1}
    assert tally.seconds_available == 2
    assert not tally.skipped


def test_not_representable_observations_are_counted_by_reason(report: ModuleType, tmp_path: Path) -> None:
    """本文が空の観測は変換されず、理由と種類つきで写せなかった観測に数えられる。"""
    trace = _write_trace(
        tmp_path,
        [
            _spawn(1, 2, "ノア", "浜辺"),
            _observation(2, 1, 2, "深夜 0:05", prose=" ", structured={"type": "player_spoke"}),
        ],
    )
    tally = report.Tally()

    report.tally_trace(trace, tally)

    assert sum(tally.converted.values()) == 0
    assert dict(tally.not_representable) == {"empty_body: player_spoke": 1}


def test_loop_guard_warning_is_counted_as_an_environment_notice(report: ModuleType, tmp_path: Path) -> None:
    """同じ行動の繰り返しへの警告は、環境からの知らせとして変換された件数に数えられる (design_decisions D1824-10)。"""
    trace = _write_trace(
        tmp_path,
        [
            _spawn(1, 2, "ノア", "浜辺"),
            _observation(
                2,
                1,
                2,
                "深夜 0:05",
                prose="同じ行動を繰り返している。",
                structured={"loop_guard": True, "tool_name": "wait"},
                observation_category="self_only",
            ),
        ],
    )
    tally = report.Tally()

    report.tally_trace(trace, tally)

    assert dict(tally.converted) == {"EnvironmentNotice": 1}
    assert dict(tally.not_representable) == {}


def test_memo_tool_result_is_counted_as_not_representable(report: ModuleType, tmp_path: Path) -> None:
    """メモ機能の結果は、止まらずに、Being 自身の記録として写せなかった件数に数え、そのあとの道具の結果は数え続ける。"""
    trace = _write_trace(
        tmp_path,
        [
            _spawn(1, 2, "ノア", "浜辺"),
            _observation(2, 1, 2, "深夜 0:05"),
            _event(3, "action", 1, 2, tool="memo_add", arguments={}),
            _event(4, "action_result", 1, 2, tool="memo_add", success=True, result_summary="メモを追加しました。"),
            _event(5, "action", 1, 2, tool="travel_to", arguments={}),
            _event(6, "action_result", 1, 2, tool="travel_to", success=True, result_summary="着いた。"),
        ],
    )
    tally = report.Tally()

    report.tally_trace(trace, tally)

    assert dict(tally.not_representable) == {"being_inner_record: memo_add": 1}
    assert tally.converted["OwnActionResult"] == 1


def test_action_result_without_matching_action_is_skipped(report: ModuleType, tmp_path: Path) -> None:
    """対応する action が無いツールの結果は、呼び出しの ID を作れないので数えずに理由を残す。"""
    trace = _write_trace(
        tmp_path,
        [
            _spawn(1, 2, "ノア", "浜辺"),
            _event(2, "action_result", 1, 2, tool="travel_to", success=True, result_summary="着いた。"),
        ],
    )
    tally = report.Tally()

    report.tally_trace(trace, tally)

    assert dict(tally.skipped) == {"action_result: 対応する action が無い": 1}


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        ([(1, "深夜 0:05"), (12, "深夜 1:00")], 300),
        ([(1, "深夜 0:05"), (12, "深夜 2:00")], None),
    ],
)
def test_seconds_per_tick_is_inferred_only_when_every_label_agrees(
    report: ModuleType, labels: list[tuple[int, str]], expected: float | None
) -> None:
    """時刻ラベルの時計がすべて 1 つの秒数で説明できるときだけ、その秒数を返す。"""
    events = [_observation(i, tick, 2, label) for i, (tick, label) in enumerate(labels)]

    assert report.infer_seconds_per_tick(events) == expected


def test_action_results_are_paired_with_oldest_action_of_same_tool(
    report: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ツールの結果は、同じツール名の action のうち最も古い未対応のものの seq から呼び出しの ID を作る。"""
    trace = _write_trace(
        tmp_path,
        [
            _spawn(1, 2, "ノア", "浜辺"),
            _observation(2, 1, 2, "深夜 0:05"),
            _event(3, "action", 1, 2, tool="travel_to", arguments={}),
            _event(4, "action", 1, 2, tool="wait", arguments={}),
            _event(5, "action", 1, 2, tool="travel_to", arguments={}),
            _event(6, "action_result", 1, 2, tool="wait", success=True, result_summary="待った。"),
            _event(7, "action_result", 1, 2, tool="travel_to", success=True, result_summary="着いた。"),
        ],
    )
    call_ids: list[str] = []
    original = report.observation_from_action_result

    def spy(entry: Any, *, call_id: str, observer: Any) -> Any:
        call_ids.append(call_id)
        return original(entry, call_id=call_id, observer=observer)

    monkeypatch.setattr(report, "observation_from_action_result", spy)

    report.tally_trace(trace, report.Tally())

    assert call_ids == ["call-4", "call-3"]


def test_action_result_without_same_tick_observation_uses_placeholder_label(report: ModuleType, tmp_path: Path) -> None:
    """同じ tick の観測が無いツールの結果は、時刻の文を仮置きして数え、仮置きの件数に入る。"""
    trace = _write_trace(
        tmp_path,
        [
            _spawn(1, 2, "ノア", "浜辺"),
            _event(2, "action", 3, 2, tool="wait", arguments={}),
            _event(3, "action_result", 3, 2, tool="wait", success=True, result_summary="待った。"),
        ],
    )
    tally = report.Tally()

    report.tally_trace(trace, tally)

    assert tally.converted["OwnActionResult"] == 1
    assert tally.placeholder_labels == 1


def test_render_markdown_reports_unknown_percentage_per_field_and_route(report: ModuleType, tmp_path: Path) -> None:
    """発言 1 件とツールの結果 1 件なら、自分宛てかの「不明」は全体 50%、言われた 100%、行動の結果 0% と出る。"""
    trace = _write_trace(
        tmp_path,
        [
            _spawn(1, 2, "ノア", "浜辺"),
            _observation(2, 1, 2, "深夜 0:05"),
            _event(3, "action", 1, 2, tool="wait", arguments={}),
            _event(4, "action_result", 1, 2, tool="wait", success=True, result_summary="待った。"),
        ],
    )
    tally = report.Tally()
    report.tally_trace(trace, tally)

    markdown = report.render_markdown(tally)

    assert "| addressed_to_self | 50.0% | 100.0% | 0.0% |" in markdown
    assert "| subject_name | 0.0% | 0.0% | 0.0% |" in markdown


def test_main_returns_1_when_no_trace_is_found(report: ModuleType, tmp_path: Path) -> None:
    """trace.jsonl が見つからない引数だけを渡すと、終了コード 1 を返す。"""
    assert report.main([str(tmp_path / "missing")]) == 1
