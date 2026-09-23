"""過去 run の行動の窓を組み直し、意味上の繰り返しの判断 (#1412) を実 Jev で測る。

完全一致の検出が拾えなかった繰り返しと、繰り返しでない窓を人が読んでラベルを付け、
検出器と同じ state と質問で Jev に問う。閾値は、繰り返しでない窓を採らない高さに置く。

- 窓: その player の直近 K 件の `action` と `action_result` の組。要約は本番と同じ
  ``format_action_summary_for_display`` で作り、内心や目的は入れない
- ラベル: 下の ``CASES`` に (run, player, 窓の最後の tick, 繰り返しか, 読んだ理由) で持つ

使い方:
    uv run python scripts/jev_semantic_repeat_demo.py show --run offering_race_v2_second --player 1 --end-tick 53
    uv run python scripts/jev_semantic_repeat_demo.py run --out var/jev_semantic_repeat_demo/results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from ai_rpg_world.application.llm.services.action_summary_format import (  # noqa: E402
    format_action_summary_for_display,
)
from ai_rpg_world.application.llm.services.semantic_repeat_detector import (  # noqa: E402
    QUESTION_NAME,
    RecentAction,
    build_question,
    build_state,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (  # noqa: E402
    ResolvedLlmRuntimeConfig,
)

_DEFAULT_RUNS_DIR = _REPO_ROOT.parent.parent.parent / "var" / "runs"


@dataclass(frozen=True)
class Case:
    run: str
    player_id: int
    end_tick: int
    repeating: bool
    note: str


CASES: tuple[Case, ...] = (
    # 完全一致で拾えなかった繰り返し
    Case("offering_race_v2_second", 1, 53, True, "ユノへの同じ申し出 ×3。1 回目だけ target_label 付き"),
    Case("station_drill_021", 2, 19, True, "無い操作「カッターを取り出す」×3 のあと「カッターを取る」に言い換え"),
    Case("m7_v3coop_003", 3, 81, True, "見つからない対象を 4 回。4 回目だけ呼び名を変えた"),
    Case("m7_v3coop_001", 4, 100, True, "拾い尽くした漂着物に 4 回働きかけて拒否"),
    Case("station_drill_023", 1, 19, True, "担当外の配線箱に操作名を変えて 3 回。間に通気口"),
    Case("station_drill_012", 1, 15, True, "棚卸し帳と資材棚に無い操作を交互に 4 回"),
    Case("station_drill_035", 3, 28, True, "医務室と温室の往復"),
    Case("station_drill_gemma31_jev_thinking_001", 7, 11, True, "何も起きない操作と待機の往復"),
    Case("v4coop_0731_007", 1, 146, True, "真水を使う と 汲んだばかりで拒否 の往復"),
    Case("v4coop_reasonfirst_003", 4, 137, True, "読んだ刻み跡の読み直しと空の箱を開ける、の往復"),
    # 完全一致でも拾える繰り返し (対照)
    Case("offering_race_first", 4, 20, True, "[完全一致] 摘めない茂みへ同じ操作"),
    Case("station_drill_gemma31_jev_001", 1, 23, True, "[完全一致] 引数なしの wait の連続"),
    # 繰り返しでない窓
    Case("offering_race_v2_second", 2, 54, False, "待機 → 麦束を渡す → 刈る → メモ"),
    Case("station_drill_034", 7, 5, False, "同じ相手への囁き ×4。中身が段階的に進む"),
    Case("station_drill_034", 3, 5, False, "同じ相手への囁き ×4。作戦が詰まっていく"),
    Case("market_town_v37_division", 1, 30, False, "移動失敗 → 待機 → 摘む → 摘み尽くし"),
    Case("station_drill_021", 1, 20, False, "拒否 → 待機 → メモ確認 → 報告"),
    Case("v4coop_0731_007", 2, 60, False, "発言 → 移動 → 探索 → 標識を調べる"),
    Case("market_town_v37_division", 3, 45, False, "メモ → 焼けない → 待機 → 相談"),
    Case("r1_003", 1, 94, False, "椰子の実を拾って食べる ×2。空腹が回復していく"),
)


def load_window(runs_dir: Path, run: str, player_id: int, end_tick: int, k: int) -> tuple[str, list[RecentAction], list[int]]:
    trace = runs_dir / run / "trace.jsonl"
    pending: dict[str, Any] | None = None
    pairs: list[tuple[int, RecentAction]] = []
    for line in trace.open():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("player_id") != player_id:
            continue
        tick = e.get("tick")
        if tick is None or tick > end_tick:
            continue
        p = e.get("payload") or {}
        if e.get("kind") == "action":
            pending = {"tick": tick, "tool": p.get("tool"), "arguments": p.get("arguments") or {}}
        elif e.get("kind") == "action_result" and pending is not None:
            pairs.append((pending["tick"], RecentAction(
                action=format_action_summary_for_display(pending["tool"], pending["arguments"]),
                result=str(p.get("result_summary") or ""),
                succeeded=p.get("success"),
            )))
            pending = None
    tail = pairs[-k:]
    return _player_name(runs_dir / run, player_id), [a for _, a in tail], [t for t, _ in tail]


def _player_name(run_dir: Path, player_id: int) -> str:
    config = run_dir / "experiment.config.resolved.json"
    try:
        scenario_path = json.loads(config.read_text()).get("scenario_path") or ""
    except (OSError, json.JSONDecodeError):
        return f"player{player_id}"
    for base in (_REPO_ROOT, _REPO_ROOT.parent.parent.parent):
        p = base / scenario_path
        if p.is_file():
            players = json.loads(p.read_text()).get("players", [])
            if 0 < player_id <= len(players):
                return str(players[player_id - 1].get("name") or f"player{player_id}")
    return f"player{player_id}"


def cmd_show(args: argparse.Namespace) -> int:
    name, actions, ticks = load_window(Path(args.runs_dir), args.run, args.player, args.end_tick, args.k)
    print(f"{args.run} {name}(p{args.player}) t{ticks[0] if ticks else '-'}〜{args.end_tick}")
    for t, a in zip(ticks, actions):
        print(f"  t{t} [{'OK' if a.succeeded else 'NG'}] {a.action}\n        → {a.result[:160]}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv
    load_dotenv(); load_dotenv(_REPO_ROOT.parent.parent.parent / ".env")
    from ai_rpg_world.application.llm.ports.typed_judgment_port import TypedJudgmentUnavailableException
    from ai_rpg_world.application.llm.wiring._typed_judgment_factory import create_typed_judgment_port_from_config
    port = create_typed_judgment_port_from_config(ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="jev"))
    results = []
    for case in CASES:
        name, actions, ticks = load_window(Path(args.runs_dir), case.run, case.player_id, case.end_tick, args.k)
        row: dict[str, Any] = {
            "run": case.run, "player_id": case.player_id, "ticks": ticks, "repeating": case.repeating,
            "note": case.note, "state": build_state(name, actions),
        }
        samples = []
        for _ in range(args.repeat):
            try:
                a = port.judge(row["state"], {QUESTION_NAME: build_question(name)})[QUESTION_NAME]
                samples.append(round(float(a.value), 4))
            except TypedJudgmentUnavailableException as exc:
                row["error"] = str(exc)
        row["probabilities"] = samples
        results.append(row)
        print(f"{'繰り返し' if case.repeating else '非繰返し'} {samples} {case.run} p{case.player_id} t{ticks[0] if ticks else '-'}〜{case.end_tick} {case.note}")
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"k": args.k, "results": results}, ensure_ascii=False, indent=1))
    pos = [min(r["probabilities"]) for r in results if r["repeating"] and r["probabilities"]]
    neg = [max(r["probabilities"]) for r in results if not r["repeating"] and r["probabilities"]]
    print(f"\n繰り返し {len(pos)} 件の最小: {min(pos) if pos else None} / 非繰返し {len(neg)} 件の最大: {max(neg) if neg else None}")
    for threshold in (0.5, 0.7, 0.8, 0.85, 0.9, 0.95):
        tp = sum(1 for p in pos if p >= threshold); fp = sum(1 for p in neg if p >= threshold)
        print(f"  閾値 {threshold}: 繰り返しを採る {tp}/{len(pos)}, 非繰返しを採る {fp}/{len(neg)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", default=str(_DEFAULT_RUNS_DIR))
    parser.add_argument("--k", type=int, default=ResolvedLlmRuntimeConfig.for_tests().typed_judgment_semantic_repeat_window)
    sub = parser.add_subparsers(dest="command", required=True)
    ps = sub.add_parser("show"); ps.add_argument("--run", required=True); ps.add_argument("--player", type=int, required=True); ps.add_argument("--end-tick", type=int, required=True); ps.set_defaults(func=cmd_show)
    pr = sub.add_parser("run"); pr.add_argument("--out", default="var/jev_semantic_repeat_demo/results.json"); pr.add_argument("--repeat", type=int, default=2); pr.set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
