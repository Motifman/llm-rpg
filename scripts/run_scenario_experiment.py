#!/usr/bin/env python3
"""任意シナリオ JSON で LLM 実験を走らせる汎用ランナー (Issue #188 Phase 1d)。

特徴:
    - シナリオ非依存: ``data/scenarios/*.json`` を ``--scenario`` で指定
    - trace 自動記録: ``JsonlTraceRecorder`` を内部で生成して runtime に inject
    - HTML 自動生成: 実行後 ``scripts/trace_to_html.py`` を呼んで HTML を出力
    - 汎用レポート: WIN/LOSE/tick/action 数/memo 数の最小集計を Markdown で

scenario 固有の集計 (relay_puzzle の latch tick / kaito-rin marker など) は
``scripts/issue154_full_tables_experiment.py`` に残し、本スクリプトとは独立。

使い方::

    python scripts/run_scenario_experiment.py \\
        --scenario data/scenarios/relay_puzzle_demo.json \\
        --max-ticks 30 \\
        --out var/runs/relay-foo

    # 出力:
    #   var/runs/relay-foo/trace.jsonl
    #   var/runs/relay-foo/report.md
    #   var/runs/relay-foo/trace.html
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

_REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (_REPO_ROOT, _REPO_ROOT / "src"):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from ai_rpg_world.application.trace import (  # noqa: E402
    JsonlTraceRecorder,
    TraceEventKind,
)
from ai_rpg_world.application.trace.recorder import load_trace_events  # noqa: E402

logger = logging.getLogger("run_scenario_experiment")


def _format_duration(seconds: float) -> str:
    """秒を MM:SS / HH:MM:SS 表記に整形する。"""
    seconds = max(0, int(seconds))
    if seconds < 3600:
        return f"{seconds // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


class _ExperimentProgressReporter:
    """実験スクリプト実行中の進捗を可視化する reporter。

    - **stdout** には旧来通り 1 行ずつ tick メッセージを print (パイプログ用)
    - **stderr** には `\\r` で同じ行を上書きしながら inline 進捗を出す
      (パイプで stdout を捨てても terminal で見える)
    - **progress.jsonl** には 1 tick 1 行で JSON を append (`tail -f` 用)

    実装メモ:
        - stderr が tty でない (= 別ファイルへリダイレクト) 場合は `\\r` を使わず
          通常の改行で出す (CI ログでも読める)
        - LLM call の wall time が大きい (5-10s) と 1 tick 5-10s 程度なので、
          毎 tick 更新で十分な滑らかさ
    """

    def __init__(
        self,
        *,
        max_ticks: int,
        stdout: TextIO,
        stderr: Optional[TextIO],
        progress_jsonl: Optional[Path],
    ) -> None:
        self._max_ticks = max(1, int(max_ticks))
        self._stdout = stdout
        self._stderr = stderr
        self._stderr_is_tty = bool(stderr is not None and getattr(stderr, "isatty", lambda: False)())
        self._t0 = time.monotonic()
        self._t_last_tick = self._t0
        self._tick_durations: list[float] = []
        self._progress_fh: Optional[TextIO] = None
        if progress_jsonl is not None:
            progress_jsonl.parent.mkdir(parents=True, exist_ok=True)
            self._progress_fh = open(progress_jsonl, "w", encoding="utf-8")

    def tick_end(
        self,
        i: int,
        world_tick: int,
        *,
        world_tick_start: Optional[int] = None,
        llm_calls: Optional[int] = None,
        travel_active: Optional[int] = None,
    ) -> None:
        """1 driver iteration 完了時に呼ぶ。stdout / stderr / jsonl 全部更新する。

        #404 P2 で追加した可観測性パラメータ (全部 optional、未指定なら従来挙動):

        - ``world_tick_start``: iteration 開始時の world_tick。``world_tick - start``
          で 1 iteration あたりに進んだ world tick 数 (= ``nested_world_ticks``)
          が出る。1 を超えていれば「`do_move` 等が世界を多く進めた」サイン。
        - ``llm_calls``: iteration 中に発火した LLM 呼び出し数。スパイク原因
          特定の最重要指標。
        - ``travel_active``: iteration 終了時点で is_traveling=True の player 数。
        """
        now = time.monotonic()
        last_tick_duration = now - self._t_last_tick
        self._t_last_tick = now
        self._tick_durations.append(last_tick_duration)
        elapsed = now - self._t0
        avg = sum(self._tick_durations) / max(1, len(self._tick_durations))
        remaining_ticks = max(0, self._max_ticks - (i + 1))
        eta = avg * remaining_ticks
        pct = (i + 1) / self._max_ticks * 100.0
        nested_world_ticks: Optional[int] = None
        if world_tick_start is not None:
            nested_world_ticks = max(0, int(world_tick) - int(world_tick_start))

        # stdout: 1 行 print (旧来互換)。
        self._stdout.write(
            f"  駆動 {i + 1}/{self._max_ticks} world_tick={world_tick} "
            f"last_tick={last_tick_duration:.1f}s elapsed={_format_duration(elapsed)} "
            f"eta={_format_duration(eta)}\n"
        )
        self._stdout.flush()

        # stderr: inline 進捗 (tty なら \r で上書き、それ以外は改行)。
        if self._stderr is not None:
            terminator = "\r" if self._stderr_is_tty else "\n"
            line = (
                f"[{i + 1:>3}/{self._max_ticks}] ({pct:5.1f}%) "
                f"tick={world_tick} last={last_tick_duration:5.1f}s "
                f"avg={avg:4.1f}s elapsed={_format_duration(elapsed)} "
                f"eta={_format_duration(eta)}"
            )
            # tty なら行末をクリアするため空白で padding (前行の残り)。
            if self._stderr_is_tty:
                line = line.ljust(110)
            self._stderr.write(line + terminator)
            self._stderr.flush()

        # progress.jsonl: 1 tick 1 行 (tail -f / 集計用)。
        if self._progress_fh is not None:
            entry: Dict[str, Any] = {
                "tick_index": i + 1,
                "max_ticks": self._max_ticks,
                "world_tick": int(world_tick),
                "last_tick_seconds": round(last_tick_duration, 3),
                "elapsed_seconds": round(elapsed, 1),
                "avg_tick_seconds": round(avg, 2),
                "eta_seconds": round(eta, 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            # #404 P2: スパイク原因特定のための内訳。値が None (= reporter
            # 呼び出し側が指定しなかった) なら従来通り省略。
            if world_tick_start is not None:
                entry["world_tick_start"] = int(world_tick_start)
            if nested_world_ticks is not None:
                entry["nested_world_ticks"] = nested_world_ticks
            if llm_calls is not None:
                entry["llm_calls"] = int(llm_calls)
            if travel_active is not None:
                entry["travel_active"] = int(travel_active)
            self._progress_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._progress_fh.flush()

    def message(self, msg: str) -> None:
        """ad-hoc メッセージ (ゲーム終了検出など)。stdout のみに出す。"""
        # stderr の \r 進捗行を一度 改行で確定してからメッセージを出す
        if self._stderr is not None and self._stderr_is_tty:
            self._stderr.write("\n")
            self._stderr.flush()
        self._stdout.write(f"  {msg}\n")
        self._stdout.flush()

    def finalize(self) -> None:
        """完了時の改行・progress.jsonl のクローズ。"""
        if self._stderr is not None and self._stderr_is_tty:
            self._stderr.write("\n")
            self._stderr.flush()
        if self._progress_fh is not None:
            self._progress_fh.close()
            self._progress_fh = None


def _load_dotenv_safe() -> None:
    """.env を best-effort で読み込む (失敗しても黙って続行)。"""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()
    except Exception:
        pass


def _drive_scenario(
    *,
    scenario_path: Path,
    max_ticks: int,
    recorder: JsonlTraceRecorder,
    progress: Any,
    reporter: Optional[_ExperimentProgressReporter] = None,
) -> Dict[str, Any]:
    """シナリオを 1 セッション分回し、最終ステートを dict で返す。

    GameRuntimeManager を内部で使う。:class:`EscapeGameRuntime` 経由なので
    既存の escape_game / relay_puzzle 路線と互換。
    """
    from tempfile import TemporaryDirectory

    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
        GameRuntimeManager,
    )
    from ai_rpg_world.presentation.spot_graph_game.schemas import (
        CharacterCreateRequest,
        SessionCreateRequest,
    )

    os.environ.setdefault("LLM_CLIENT", "litellm")
    os.environ["SPOT_GRAPH_TICK_LOOP_ENABLED"] = "false"

    world_id = scenario_path.stem
    scenarios_dir = scenario_path.parent

    with TemporaryDirectory() as d:
        chars = Path(d) / "characters.json"
        mgr = GameRuntimeManager(scenarios_dir=scenarios_dir, characters_path=chars)
        char = mgr.create_character(
            CharacterCreateRequest(name=f"exp-{scenario_path.stem}")
        )
        summary = mgr.create_session(
            SessionCreateRequest(world_id=world_id, character_ids=[char.id])
        )
        state = mgr._sessions[summary.session_id]
        runtime = state.runtime
        # Phase 1d: trace recorder を runtime に注入 (memo executor + LLM wiring 経路)
        runtime.set_trace_recorder(recorder)

        # Phase 1d viewer: 各プレイヤーの初期位置を position_change として
        # 記録 (from_spot_id=None で「ここから始まった」を表す)。これにより
        # viewer 側は trace.jsonl だけで初期配置を再現できる。
        for pid in runtime.get_player_ids():
            spot_id = runtime.get_player_spot_id(pid)
            if spot_id is None:
                continue
            try:
                spot_name = runtime.get_player_spot_name(pid)
            except Exception:
                spot_name = spot_id
            try:
                player_name = runtime.get_player_name(pid)
            except Exception:
                player_name = None
            recorder.record(
                TraceEventKind.POSITION_CHANGE,
                tick=runtime.current_tick(),
                player_id=int(pid.value),
                from_spot_id=None,
                to_spot_id=spot_id,
                spot_name=spot_name,
                player_name=player_name,
            )

        for pid in runtime.get_player_ids():
            state.llm_wiring.llm_turn_trigger.schedule_turn(pid)

        outcome = "TIMEOUT"
        last_tick = 0
        t0 = time.monotonic()
        # 各 player の前 tick の spot を保持して差分検出に使う
        prev_spots: Dict[int, Optional[str]] = {
            int(pid.value): runtime.get_player_spot_id(pid)
            for pid in runtime.get_player_ids()
        }
        for i in range(max_ticks):
            w0 = runtime.current_tick()
            # 旧 progress callable は legacy (start 通知)。新 reporter は
            # tick 完了時に ETA / per-tick wall time を出す。
            progress(f"駆動 {i + 1}/{max_ticks} world_tick={w0}")
            recorder.record(TraceEventKind.TICK_START, tick=w0)
            # #404 P2: iteration 内 LLM 呼び出し数を計測するため、advance_tick
            # の前に counter をリセットしておく (前 iteration の余り = 0 のはず
            # だが防御的に)。
            _pop = getattr(runtime, "pop_llm_call_count", None)
            if callable(_pop):
                _pop()
            runtime.advance_tick()
            last_tick = runtime.current_tick()
            # tick 終了直後に position 差分を emit (移動が起きた player のみ)
            for pid in runtime.get_player_ids():
                pid_int = int(pid.value)
                new_spot = runtime.get_player_spot_id(pid)
                old_spot = prev_spots.get(pid_int)
                if new_spot is not None and new_spot != old_spot:
                    try:
                        spot_name = runtime.get_player_spot_name(pid)
                    except Exception:
                        spot_name = new_spot
                    try:
                        player_name = runtime.get_player_name(pid)
                    except Exception:
                        player_name = None
                    recorder.record(
                        TraceEventKind.POSITION_CHANGE,
                        tick=last_tick,
                        player_id=pid_int,
                        from_spot_id=old_spot,
                        to_spot_id=new_spot,
                        spot_name=spot_name,
                        player_name=player_name,
                    )
                    prev_spots[pid_int] = new_spot
            recorder.record(TraceEventKind.TICK_END, tick=last_tick)
            # 進捗 reporter: tick 完了時の wall time / ETA を stderr + progress.jsonl に出す
            # #404 P2: スパイク原因の内訳 (nested world tick / LLM 呼出 / 移動中数) を渡す。
            llm_calls: Optional[int] = None
            travel_active: Optional[int] = None
            pop_llm = getattr(runtime, "pop_llm_call_count", None)
            if callable(pop_llm):
                try:
                    llm_calls = int(pop_llm())
                except Exception:
                    llm_calls = None
            count_traveling = getattr(runtime, "count_traveling_players", None)
            if callable(count_traveling):
                try:
                    travel_active = int(count_traveling())
                except Exception:
                    travel_active = None
            if reporter is not None:
                reporter.tick_end(
                    i,
                    last_tick,
                    world_tick_start=int(w0),
                    llm_calls=llm_calls,
                    travel_active=travel_active,
                )
            end_check = runtime.check_game_end()
            if end_check.is_ended:
                outcome = (
                    str(getattr(end_check, "result", None) or "ENDED").upper()
                )
                if reporter is not None:
                    reporter.message(
                        f"ゲーム終了検出 outcome={outcome} world_tick={last_tick}"
                    )
                else:
                    progress(
                        f"ゲーム終了検出 outcome={outcome} world_tick={last_tick}"
                    )
                break
        elapsed = time.monotonic() - t0
        # Issue #311/#325 後続: 非同期 LLM 主観文付与 scheduler (#310) の in-flight
        # ジョブを drain してから return する。これをしないと、scenario 終了
        # 直後に `with JsonlTraceRecorder` が close され、後追いで完了した worker
        # が "recorder is already closed" RuntimeError に当たる (第21回/第22回
        # 実験で各 2 件観測)。30s timeout は max latency (~14s) の余裕分。
        shutdown = getattr(runtime, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown(timeout=30.0)
            except Exception:
                # shutdown 自体の失敗で trace 書き出しを止めない
                logger.warning(
                    "runtime.shutdown(timeout=30) raised; "
                    "async LLM completions may not be fully drained",
                    exc_info=True,
                )
        return {
            "outcome": outcome,
            "last_tick": last_tick,
            "elapsed_sec": elapsed,
            "max_ticks": max_ticks,
        }


def _build_report(
    *,
    scenario_path: Path,
    trace_path: Path,
    summary: Dict[str, Any],
) -> str:
    """trace.jsonl を読み戻して汎用集計レポートを Markdown で返す。"""
    events = list(load_trace_events(trace_path))
    actions: List[Any] = []
    action_results: List[Any] = []
    memo_adds: List[Any] = []
    memo_dones: List[Any] = []
    memo_hints: List[Any] = []
    position_changes: List[Any] = []
    by_player: Dict[int, Dict[str, int]] = {}
    for e in events:
        if e.kind == TraceEventKind.ACTION:
            actions.append(e)
        elif e.kind == TraceEventKind.ACTION_RESULT:
            action_results.append(e)
        elif e.kind == TraceEventKind.MEMO_ADD:
            memo_adds.append(e)
        elif e.kind == TraceEventKind.MEMO_DONE:
            memo_dones.append(e)
        elif e.kind == TraceEventKind.MEMO_HINT:
            memo_hints.append(e)
        elif e.kind == TraceEventKind.POSITION_CHANGE:
            position_changes.append(e)
        pid = e.player_id
        if pid is None:
            continue
        bucket = by_player.setdefault(
            pid,
            {
                "actions": 0,
                "successes": 0,
                "failures": 0,
                "memo_adds": 0,
                "memo_dones": 0,
                "moves": 0,
            },
        )
        if e.kind == TraceEventKind.ACTION:
            bucket["actions"] += 1
        elif e.kind == TraceEventKind.ACTION_RESULT:
            if e.payload.get("success"):
                bucket["successes"] += 1
            else:
                bucket["failures"] += 1
        elif e.kind == TraceEventKind.MEMO_ADD:
            bucket["memo_adds"] += 1
        elif e.kind == TraceEventKind.MEMO_DONE:
            bucket["memo_dones"] += 1
        elif e.kind == TraceEventKind.POSITION_CHANGE:
            # 初期配置 (from_spot_id=None) は move カウントに含めない
            from_spot = e.payload.get("from_spot_id") if isinstance(e.payload, dict) else None
            if from_spot is not None:
                bucket["moves"] += 1

    lines: List[str] = []
    lines.append(f"# Scenario experiment report — {scenario_path.stem}")
    lines.append("")
    lines.append(f"- scenario: `{scenario_path}`")
    lines.append(f"- outcome: **{summary['outcome']}**")
    lines.append(
        f"- last tick: {summary['last_tick']} / max ticks: {summary['max_ticks']}"
    )
    lines.append(f"- elapsed: {summary['elapsed_sec']:.1f}s")
    lines.append(f"- total events: {len(events)}")
    lines.append("")
    lines.append("## イベント種別ごとの件数")
    lines.append("")
    lines.append(f"- action: {len(actions)}")
    lines.append(f"- action_result: {len(action_results)}")
    lines.append(f"- memo_add: {len(memo_adds)}")
    lines.append(f"- memo_done: {len(memo_dones)}")
    lines.append(f"- memo_hint: {len(memo_hints)}")
    lines.append(f"- position_change: {len(position_changes)}")
    lines.append("")
    if by_player:
        lines.append("## プレイヤー別集計")
        lines.append("")
        lines.append("| player_id | actions | successes | failures | memo_adds | memo_dones | moves |")
        lines.append("|-----------|---------|-----------|----------|-----------|------------|-------|")
        for pid in sorted(by_player):
            b = by_player[pid]
            lines.append(
                f"| {pid} | {b['actions']} | {b['successes']} | {b['failures']} | "
                f"{b['memo_adds']} | {b['memo_dones']} | {b.get('moves', 0)} |"
            )
        lines.append("")
    lines.append("## 成果物")
    lines.append("")
    lines.append(f"- trace: `{trace_path}`")
    lines.append(f"- HTML viewer: `{trace_path.with_suffix('.html')}`")
    lines.append("")
    return "\n".join(lines)


def _emit_html(trace_path: Path, html_path: Path, *, title: str) -> None:
    """trace_to_html.py を呼んで HTML を出力。"""
    from scripts.trace_to_html import render_html  # noqa: WPS433

    events = list(load_trace_events(trace_path))
    html_path.write_text(render_html(events, title=title), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    _load_dotenv_safe()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        description="Drive a single LLM-driven scenario session and emit trace + report + HTML"
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        required=True,
        help="Path to scenario JSON (e.g. data/scenarios/relay_puzzle_demo.json)",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=int(os.environ.get("EXPERIMENT_MAX_TICKS", "30")),
        help="Outer tick driving loop count (default 30, env EXPERIMENT_MAX_TICKS)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (defaults to var/runs/<scenario>-<timestamp>)",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Skip HTML generation (still emits trace.jsonl + report.md)",
    )
    parser.add_argument(
        "--publish-gist",
        action="store_true",
        help=(
            "After the run finishes, upload trace.jsonl + report.md + trace.html "
            "(and the scenario JSON) to a secret gist via gh CLI. "
            "Requires `gh auth status` to be authenticated."
        ),
    )
    parser.add_argument(
        "--publish-gist-public",
        action="store_true",
        help="Make the published gist public instead of secret (default secret)",
    )
    parser.add_argument(
        "--publish-gist-desc",
        type=str,
        default=None,
        help="Optional description override for the published gist",
    )
    parser.add_argument(
        "--no-stderr-progress",
        action="store_true",
        help=(
            "Disable inline progress on stderr "
            "(default: print ETA/elapsed/per-tick wall time on stderr in addition to stdout). "
            "Useful in CI / non-tty environments where the inline updater becomes noisy."
        ),
    )
    parser.add_argument(
        "--no-progress-jsonl",
        action="store_true",
        help=(
            "Disable writing progress.jsonl alongside trace.jsonl "
            "(default: emit progress.jsonl for `tail -f` consumers and post-hoc analysis)."
        ),
    )
    args = parser.parse_args(argv)

    if not args.scenario.exists():
        parser.error(f"scenario not found: {args.scenario}")

    out_dir = args.out
    if out_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out_dir = _REPO_ROOT / "var" / "runs" / f"{args.scenario.stem}-{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "trace.jsonl"
    report_path = out_dir / "report.md"
    html_path = out_dir / "trace.html"

    print(f"[run] scenario={args.scenario.name} max_ticks={args.max_ticks}", flush=True)
    print(f"[out] {out_dir}", flush=True)

    with JsonlTraceRecorder(trace_path) as rec:
        rec.record(
            TraceEventKind.RUN_START,
            scenario=args.scenario.name,
            max_ticks=args.max_ticks,
            model=os.environ.get("LLM_MODEL"),
            api_base=os.environ.get("OPENAI_API_BASE"),
        )

        def progress(msg: str) -> None:
            print(f"  {msg}", flush=True)

        # 進捗 reporter: stdout (旧来互換) + stderr inline ETA + progress.jsonl
        reporter = _ExperimentProgressReporter(
            max_ticks=args.max_ticks,
            stdout=sys.stdout,
            stderr=None if args.no_stderr_progress else sys.stderr,
            progress_jsonl=(
                None if args.no_progress_jsonl else (out_dir / "progress.jsonl")
            ),
        )

        try:
            summary = _drive_scenario(
                scenario_path=args.scenario,
                max_ticks=args.max_ticks,
                recorder=rec,
                progress=progress,
                reporter=reporter,
            )
        finally:
            # 例外で抜けても progress.jsonl は閉じる + stderr の改行を出す
            reporter.finalize()
        rec.record(TraceEventKind.RUN_END, **summary)

    report = _build_report(
        scenario_path=args.scenario,
        trace_path=trace_path,
        summary=summary,
    )
    report_path.write_text(report, encoding="utf-8")

    if not args.no_html:
        _emit_html(trace_path, html_path, title=f"{args.scenario.stem} run")
        print(f"[html] {html_path}", flush=True)

    print(f"[report] {report_path}", flush=True)
    print(f"[trace] {trace_path}", flush=True)
    print(
        f"[done] outcome={summary['outcome']} last_tick={summary['last_tick']} "
        f"elapsed={summary['elapsed_sec']:.1f}s",
        flush=True,
    )

    if args.publish_gist:
        # シナリオ JSON も gist に同梱して再現性を担保 (差分が見えるように)
        scenario_copy = out_dir / "scenario.json"
        try:
            scenario_copy.write_bytes(args.scenario.read_bytes())
        except OSError as e:
            logger.warning("failed to copy scenario JSON into run dir: %s", e)

        from scripts.publish_experiment_gist import (  # noqa: WPS433
            GistPublishError,
            publish,
        )

        desc = args.publish_gist_desc or (
            f"llm-rpg experiment: {args.scenario.stem} "
            f"outcome={summary['outcome']} tick={summary['last_tick']}"
        )
        try:
            result = publish(
                out_dir,
                description=desc,
                secret=not args.publish_gist_public,
            )
        except GistPublishError as e:
            print(f"[gist-error] {e}", flush=True)
            return 1
        print(f"[gist] {result['gist_url']}", flush=True)
        if result.get("html_preview_url"):
            print(f"[html-preview] {result['html_preview_url']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
