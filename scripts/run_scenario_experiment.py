#!/usr/bin/env python3
"""任意シナリオ JSON で LLM 実験を走らせる汎用ランナー (Issue #188 Phase 1d)。

特徴:
    - シナリオ非依存: ``data/scenarios/*.json`` を ``--scenario`` で指定
    - trace 自動記録: ``JsonlTraceRecorder`` を内部で生成して runtime に inject
    - HTML 自動生成: 実行後に trace.html / viewer.html / timeline.html を出力
    - 汎用レポート: WIN/LOSE/tick/action 数などの最小集計を Markdown で

使い方::

    python scripts/run_scenario_experiment.py \\
        --scenario data/scenarios/forbidden_library_demo.json \\
        --max-world-ticks 30 \\
        --out var/runs/library-foo

    # 出力:
    #   var/runs/library-foo/trace.jsonl
    #   var/runs/library-foo/report.md
    #   var/runs/library-foo/trace.html
    #   var/runs/library-foo/viewer.html
    #   var/runs/library-foo/timeline.html
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
        ResolvedLlmRuntimeConfig,
    )

_REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (_REPO_ROOT, _REPO_ROOT / "src"):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from ai_rpg_world.application.llm.contracts.aux_llm_call import (  # noqa: E402
    AuxLlmComponent,
)
from ai_rpg_world.application.trace import (  # noqa: E402
    JsonlTraceRecorder,
    TraceEventKind,
)
from ai_rpg_world.application.trace.recorder import load_trace_events  # noqa: E402
from ai_rpg_world.domain.world_graph.value_object.game_end_result import (  # noqa: E402
    GameEndResult,
)

logger = logging.getLogger("run_scenario_experiment")

_EXPERIMENT_PROFILE_DIR = _REPO_ROOT / "data" / "experiment_profiles"

#: run として使えない終了。成果物は残すが、呼び出し元には失敗を返す。
#: - ``LLM_FAILURE``: 1 件も成功しなかった (認証ミス等)
#: - ``LLM_ABORTED``: 途中から連続で落ちはじめ、自ら打ち切った
_UNUSABLE_OUTCOMES = frozenset({"LLM_FAILURE", "LLM_ABORTED"})


def _outcome_and_reason(
    end_check: GameEndResult,
) -> tuple[str, str | None]:
    """世界側の終了判定を trace と集計へ渡す値へまとめて変換する。"""
    outcome = end_check.result.value if end_check.result is not None else "ENDED"
    reason = str(end_check.reason or "") or None
    return outcome, reason


def _llm_abort_reason(runtime: Any) -> str | None:
    """runtime が「恒久障害なので止めろ」と言っているなら、その理由を返す。

    判定そのものは `LlmFailureStreakMonitor` が持つ。ここは **hook を持たない
    runtime を巻き込まない**ための薄い入口で、判定の失敗で run を落とさない
    (監視が壊れても実験は続く方が安全)。
    """
    hook = getattr(runtime, "llm_abort_reason", None)
    if not callable(hook):
        return None
    try:
        reason = hook()
    except Exception:
        logger.warning("runtime.llm_abort_reason() raised", exc_info=True)
        return None
    return str(reason) if reason else None


def _classify_llm_run_health(
    recorder: Any,
    *,
    outcome: str,
    end_reason: str | None,
) -> tuple[str, str | None, int, int]:
    """trace 上の LLM 呼び出しが全滅していれば失敗終了へ変える。

    呼び出し0件の世界は対象外。1件以上試みて成功が0件だった場合だけ、通常の
    ``TIMEOUT`` 等へ縮退させず ``LLM_FAILURE`` にする。認証失敗だけでなく、
    ``NO_TOOL_CALL`` を含む全失敗が同じ入口を通る。
    """
    trace_path = getattr(recorder, "path", None)
    if not isinstance(trace_path, Path):
        return outcome, end_reason, 0, 0

    calls = [event for event in load_trace_events(trace_path) if event.kind == TraceEventKind.LLM_CALL]
    total = len(calls)
    succeeded = sum(bool(event.payload.get("success")) for event in calls)
    if total == 0 or succeeded > 0 or outcome == "LLM_ABORTED":
        # 連続失敗で自ら止めた run は、既に理由を持っている。全滅判定で
        # 上書きすると「なぜ止めたか」が「全部失敗した」に丸められる。
        return outcome, end_reason, total, succeeded

    error_counts: dict[str, int] = {}
    for event in calls:
        error_code = str(event.payload.get("error_code") or "UNKNOWN")
        error_counts[error_code] = error_counts.get(error_code, 0) + 1
    breakdown = ", ".join(f"{code}: {count}" for code, count in sorted(error_counts.items()))
    reason = f"LLM 呼び出し {total} 件がすべて失敗したため実験結果を無効とする ({breakdown})"
    return "LLM_FAILURE", reason, total, succeeded


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
        max_world_ticks: int,
        stdout: TextIO,
        stderr: TextIO | None,
        progress_jsonl: Path | None,
    ) -> None:
        # #404 P1: 旧 max_ticks (= 外側 for ループ回数) を max_world_ticks
        # (= world_tick の上限) に意味論変更。`#405` で 1 iteration = 1 world tick
        # に揃ったため両者はほぼ同義だが、概念整理として world tick 基準に統一する。
        self._max_world_ticks = max(1, int(max_world_ticks))
        self._stdout = stdout
        self._stderr = stderr
        self._stderr_is_tty = bool(stderr is not None and getattr(stderr, "isatty", lambda: False)())
        self._t0 = time.monotonic()
        self._t_last_tick = self._t0
        self._tick_durations: list[float] = []
        self._progress_fh: TextIO | None = None
        if progress_jsonl is not None:
            progress_jsonl.parent.mkdir(parents=True, exist_ok=True)
            self._progress_fh = open(progress_jsonl, "w", encoding="utf-8")

    def tick_end(
        self,
        i: int,
        world_tick: int,
        *,
        world_tick_start: int | None = None,
        llm_calls: int | None = None,
        travel_active: int | None = None,
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
        remaining_ticks = max(0, self._max_world_ticks - (i + 1))
        eta = avg * remaining_ticks
        pct = (i + 1) / self._max_world_ticks * 100.0
        nested_world_ticks: int | None = None
        if world_tick_start is not None:
            nested_world_ticks = max(0, int(world_tick) - int(world_tick_start))

        # stdout: 1 行 print (旧来互換)。
        self._stdout.write(
            f"  駆動 {i + 1}/{self._max_world_ticks} world_tick={world_tick} "
            f"last_tick={last_tick_duration:.1f}s elapsed={_format_duration(elapsed)} "
            f"eta={_format_duration(eta)}\n"
        )
        self._stdout.flush()

        # stderr: inline 進捗 (tty なら \r で上書き、それ以外は改行)。
        if self._stderr is not None:
            terminator = "\r" if self._stderr_is_tty else "\n"
            line = (
                f"[{i + 1:>3}/{self._max_world_ticks}] ({pct:5.1f}%) "
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
            entry: dict[str, Any] = {
                "tick_index": i + 1,
                "max_world_ticks": self._max_world_ticks,
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


def _json_config_value(value: Any) -> str:
    """profile の JSON 値を既存 resolver に渡せる文字列へ変換する。"""
    if isinstance(value, bool):
        return "1" if value else "0"
    if value is None:
        return ""
    return str(value)


def _load_experiment_config_source(
    *,
    profile: str | None,
    config_path: Path | None,
) -> tuple[dict[str, Any], Path | None]:
    """実験設定 source JSON を読む。未指定なら空設定。"""
    if profile and config_path is not None:
        raise ValueError("--profile and --experiment-config are mutually exclusive")
    if profile:
        path = _EXPERIMENT_PROFILE_DIR / f"{profile}.json"
    else:
        path = config_path
    if path is None:
        return {}, None
    if not path.exists():
        raise FileNotFoundError(f"experiment config not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"experiment config must be a JSON object: {path}")
    return data, path


def _runtime_config_mapping_from_source(
    config_source: Mapping[str, Any],
) -> dict[str, str]:
    """source config の runtime_config セクションを resolver 用 mapping にする。

    ここでは process env に書き戻さない。profile/config 使用時の実験設定は
    この mapping → ResolvedLlmRuntimeConfig の 1 経路だけにする。
    """
    values = config_source.get("runtime_config", {})
    if values is None:
        values = {}
    if not isinstance(values, dict):
        raise ValueError("experiment config field 'runtime_config' must be an object")
    rendered_values: dict[str, str] = {}
    for key, value in values.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("experiment config runtime_config keys must be non-empty strings")
        rendered_values[key] = _json_config_value(value)
    return rendered_values


# 外した実験設定の欄。書かれていたら、黙って無視せず起動前に止める。
_REMOVED_CONFIG_FIELDS = {
    "snapshot_load_mode": (
        "記憶だけを持ち越して世界を最初からやり直す replay は外しました "
        "(design_decisions D1514 の「その後」)。snapshot からの再開は、いつも世界も記憶も続きから始めます"
    ),
}


def _reject_removed_config_fields(config_source: Mapping[str, Any]) -> None:
    for field, reason in _REMOVED_CONFIG_FIELDS.items():
        if field in config_source:
            raise ValueError(f"experiment config field {field!r} is no longer supported: {reason}")


_SECRET_KEY_FRAGMENTS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD")


def _mask_secret_values(value: Any, *, key_name: str = "") -> Any:
    """manifest に秘密値が残らないよう再帰的に伏せる。"""
    normalized_key = key_name.upper()
    if any(fragment in normalized_key for fragment in _SECRET_KEY_FRAGMENTS):
        return "***"
    if isinstance(value, dict):
        return {k: _mask_secret_values(v, key_name=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_secret_values(v) for v in value]
    return value


def _prompt_dataset_runtime_config_payload(
    resolved_config: ResolvedLlmRuntimeConfig,
) -> dict[str, Any]:
    """prompt dataset の run metadata に保存する runtime_config を返す。

    ``llm_api_key`` は replay 時に実行環境の秘密値から注入するため、prompt
    dataset には placeholder も保存しない。
    """

    payload = resolved_config.to_trace_dict()
    payload["llm_api_key"] = None
    return payload


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_git(args: list[str]) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", *args],
            cwd=_REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return None
    return out.strip()


def _git_metadata() -> dict[str, Any]:
    status = _run_git(["status", "--porcelain"])
    dirty_files: list[str] = []
    if status:
        dirty_files = [line[3:] for line in status.splitlines() if len(line) > 3]
    diff = _run_git(["diff", "--binary"])
    staged_diff = _run_git(["diff", "--cached", "--binary"])
    combined_diff = (diff or "") + (staged_diff or "")
    return {
        "commit": _run_git(["rev-parse", "HEAD"]),
        "branch": _run_git(["branch", "--show-current"]),
        "dirty": bool(status),
        "dirty_files": dirty_files,
        "dirty_diff_sha256": (hashlib.sha256(combined_diff.encode("utf-8")).hexdigest() if combined_diff else None),
    }


def _write_experiment_manifest(
    *,
    out_dir: Path,
    argv: list[str],
    scenario_path: Path,
    trace_path: Path,
    report_path: Path,
    html_path: Path,
    config_source: Mapping[str, Any],
    config_source_path: Path | None,
    runtime_config_source: Mapping[str, str],
    resolved_config: Any,
    max_world_ticks: int,
    snapshot_save_dir: Path | None,
    snapshot_load_dir: Path | None,
    no_html: bool,
    no_progress_jsonl: bool,
) -> tuple[Path, str]:
    source_payload = _mask_secret_values(dict(config_source))
    source_path = out_dir / "experiment.config.source.json"
    source_path.write_text(
        json.dumps(source_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    resolved_payload = {
        "schema_version": 1,
        "profile": config_source.get("profile"),
        "config_source_path": str(config_source_path) if config_source_path else None,
        "argv": list(argv),
        "cwd": str(Path.cwd()),
        "out_dir": str(out_dir),
        "scenario_path": str(scenario_path),
        "scenario_sha256": _sha256_file(scenario_path),
        "trace_path": str(trace_path),
        "report_path": str(report_path),
        "html_path": None if no_html else str(html_path),
        "progress_jsonl_path": None if no_progress_jsonl else str(out_dir / "progress.jsonl"),
        "max_world_ticks": int(max_world_ticks),
        "snapshot_save_dir": str(snapshot_save_dir) if snapshot_save_dir else None,
        "snapshot_load_dir": str(snapshot_load_dir) if snapshot_load_dir else None,
        "runtime_config_source": _mask_secret_values(dict(sorted(runtime_config_source.items()))),
        "runtime_config": resolved_config.to_trace_dict(),
        "git": _git_metadata(),
    }
    resolved_path = out_dir / "experiment.config.resolved.json"
    resolved_path.write_text(
        json.dumps(resolved_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    digest = _sha256_file(resolved_path)
    return resolved_path, digest


def _wiring_stub_from_world_runtime(runtime: Any) -> Any:
    """``WorldRuntime`` から ``ExperimentSnapshotSession`` 用の wiring stub を作る。

    Phase 6 (Issue #470): world_runtime runtime には ``LlmAgentWiringResult`` の
    全 store ハンドルが揃わない (episode store は world_runtime の
    通常経路では作られないことがある) ため、runtime の
    内部 field から **拾える分だけ** 集めて wiring 風オブジェクトを返す。
    足りない store は ``ExperimentSnapshotSession`` 側で空 in-memory に
    fallback する。
    """
    from types import SimpleNamespace

    # 注意: ``_aux_being_repository`` は private 属性 (public property なし)。
    # ``aux_being_resolver`` の方は public property があるのでそちらを使う。
    # 将来 ``aux_being_repository`` の public property が追加されたら同じ
    # 形式に揃える。
    aux_resolver = getattr(runtime, "aux_being_resolver", None)
    aux_repo = getattr(runtime, "_aux_being_repository", None)
    return SimpleNamespace(
        being_repository=aux_repo,
        being_attachment_resolver=aux_resolver,
        acquaintance_store=getattr(runtime, "_acquaintance_store", None),
        being_episode_store=getattr(runtime, "_being_episode_store", None),
        being_memo_store=getattr(runtime, "_being_memo_store", None),
        memory_turn_clock=getattr(runtime, "_memory_turn_clock", None),
        being_short_term_memory_store=getattr(runtime, "_being_short_term_memory_store", None),
    )


def _drive_scenario(
    *,
    run_id: str = "experiment",
    scenario_path: Path,
    max_world_ticks: int,
    recorder: JsonlTraceRecorder,
    progress: Any,
    runtime_config: Any | None = None,
    reporter: _ExperimentProgressReporter | None = None,
    snapshot_save_dir: Path | None = None,
    snapshot_load_dir: Path | None = None,
    prompt_dataset_sink: Any | None = None,
) -> dict[str, Any]:
    """シナリオを 1 セッション分回し、最終ステートを dict で返す。

    GameRuntimeManager を内部で使う。:class:`WorldRuntime` 経由なので
    既存の world_runtime 路線と互換。

    Args:
        max_world_ticks: ループ終了条件 (#404 P1)。``runtime.current_tick()`` が
            この値に達するまで ``advance_tick`` を呼ぶ。旧名 ``max_ticks`` は
            外側 for ループの回数だったが、``#405`` で 1 iteration = 1 world tick
            に揃ったので world tick 基準に意味論統一する。
    """
    from contextlib import ExitStack
    from tempfile import TemporaryDirectory

    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
        GameRuntimeManager,
    )
    from ai_rpg_world.presentation.spot_graph_game.schemas import (
        CharacterCreateRequest,
        SessionCreateRequest,
    )

    os.environ["SPOT_GRAPH_TICK_LOOP_ENABLED"] = "false"

    world_id = scenario_path.stem
    scenarios_dir = scenario_path.parent

    with TemporaryDirectory() as d, ExitStack() as cleanup:
        chars = Path(d) / "characters.json"
        mgr = GameRuntimeManager(
            scenarios_dir=scenarios_dir,
            characters_path=chars,
            runtime_config=runtime_config,
        )
        char = mgr.create_character(CharacterCreateRequest(name=f"exp-{scenario_path.stem}"))
        summary = mgr.create_session(SessionCreateRequest(world_id=world_id, character_ids=[char.id]))
        state = mgr._sessions[summary.session_id]
        runtime = state.runtime
        cleanup.callback(runtime.shutdown_async_events)
        state.llm_wiring.prompt_dataset_sink = prompt_dataset_sink
        # API session の UUID ではなく実験 run 名を使い、run を跨ぐ衝突を避ける。
        state.llm_wiring.llm_session_run_id = run_id
        # Phase 1d: trace recorder を runtime に注入 (LLM wiring 経路)
        runtime.set_trace_recorder(recorder)

        round_assignment = runtime.round_assignment_trace()
        if round_assignment:
            recorder.record(
                TraceEventKind.ROUND_ASSIGNMENT,
                tick=runtime.current_tick(),
                round=1,
                seed=runtime_config.scenario_random_seed if runtime_config else None,
                assignments=round_assignment,
            )

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

        # Phase 6 (Issue #470): snapshot load / save の準備。
        # - 全 player について aux Being を ensure_attached しておく (= snapshot
        #   capture / restore の前提条件)。これは ``run_turn`` でも idempotent に
        #   呼ばれる operation だが、snapshot を始める前に明示的に走らせて
        #   「Being が attach されていない」によるスキップを避ける。
        # - load 経路: snapshot_load_dir があれば全 JSON を restore。失敗は
        #   fail-fast (= 例外伝播)。
        # - save 経路は run 終了時 (= 下の try / finally) で行う。
        snapshot_session: Any | None = None
        if snapshot_save_dir is not None or snapshot_load_dir is not None:
            from ai_rpg_world.application.being.experiment_snapshot_session import (
                ExperimentSnapshotSession,
            )

            # aux Being stack を確実に初期化 (= _aux_being_repository を作る)
            if hasattr(runtime, "_wire_being_stack"):
                runtime._wire_being_stack()
            for pid in runtime.get_player_ids():
                provisioning = getattr(runtime, "_aux_being_provisioning", None)
                if provisioning is not None:
                    provisioning.ensure_attached(pid)

            wiring_stub = _wiring_stub_from_world_runtime(runtime)
            # snapshot_dir は save 用の出力先 / restore 用の入力先 両方を
            # 兼ねる。本 PR では「snapshot_dir」を共通化し、restore は
            # snapshot_load_dir から別途読む。
            snapshot_session = ExperimentSnapshotSession(
                wiring_result=wiring_stub,
                snapshot_dir=snapshot_save_dir or snapshot_load_dir,
            )

            if snapshot_load_dir is not None:
                logger.info("loading snapshots from %s ...", snapshot_load_dir)
                restore_report = snapshot_session.restore_all_from_dir(
                    snapshot_load_dir,
                    current_scenario=scenario_path.stem,
                )
                logger.info("restored %d being snapshot(s)", len(restore_report.restored))
                runtime.note_being_memories_restored(restore_report.restored)
                # Phase 9-1: world snapshot も load (= 旧 snapshot dir に
                # world.json が無ければ no-op = 後方互換)。world snapshot は
                # scenario fail-fast 方針なので例外は素通し。
                world_snapshot = snapshot_session.restore_world_from_dir(
                    runtime,
                    snapshot_load_dir,
                    current_scenario=scenario_path.stem,
                )
                # Phase 7: trace に「どの run から続きを取ったか」を残す。
                # cross-scenario transfer も明示的に payload に乗せる。
                recorder.record(
                    TraceEventKind.SNAPSHOT_LOAD,
                    directory=str(snapshot_load_dir),
                    restored_count=len(restore_report.restored),
                    restored_being_ids=[b.value for b in restore_report.restored],
                    memory_turns=snapshot_session.memory_turns(restore_report.restored),
                    cross_scenario_transfers=[
                        {
                            "being_id": b.value,
                            "source_scenario": src,
                            "current_scenario": cur,
                        }
                        for (b, src, cur) in restore_report.cross_scenario_transfers
                    ],
                    removed_world_subsystems=(
                        world_snapshot.removed_subsystem_counts if world_snapshot is not None else {}
                    ),
                    removed_memory_keys=[
                        {"being_id": b.value, "counts": counts}
                        for b, counts in restore_report.removed_memory_key_counts.items()
                    ],
                )

                if world_snapshot is not None:
                    logger.info(
                        "restored world snapshot: source_scenario=%s world_tick=%d subsystems=%s",
                        world_snapshot.source_scenario,
                        world_snapshot.world_tick,
                        sorted(world_snapshot.subsystems.keys()),
                    )
                    recorder.record(
                        TraceEventKind.WORLD_SNAPSHOT_LOAD,
                        directory=str(snapshot_load_dir),
                        source_scenario=world_snapshot.source_scenario,
                        current_scenario=scenario_path.stem,
                        world_tick=world_snapshot.world_tick,
                        restored_subsystems=sorted(
                            world_snapshot.subsystems.keys() - world_snapshot.removed_subsystem_counts.keys()
                        ),
                        removed_subsystems=world_snapshot.removed_subsystem_counts,
                    )

        for pid in runtime.get_player_ids():
            state.llm_wiring.llm_turn_trigger.schedule_turn(pid)

        outcome = "TIMEOUT"
        end_reason: str | None = None
        last_tick = 0
        t0 = time.monotonic()
        # Phase 6: Ctrl+C で snapshot save まで届かせるため、SIGINT を flag
        # 立てに変える (= KeyboardInterrupt を直接 raise させない)。
        # snapshot_save_dir 未指定時は no-op の context manager になる
        # (= 既存挙動完全互換)。
        # context manager で wrap することで、tick loop が KeyboardInterrupt
        # 以外の例外で死んでも __exit__ が必ず handler を復元する
        # (= main() 以降の Ctrl+C を壊さない)。
        import contextlib
        import signal as _signal  # local import: 既存 import top に触らない

        _interrupted = {"flag": False}

        @contextlib.contextmanager
        def _sigint_to_flag_guard():
            if snapshot_save_dir is None:
                yield
                return

            def _handler(_signum: int, _frame: Any) -> None:
                _interrupted["flag"] = True
                logger.warning("SIGINT received; will stop tick loop and capture snapshot before exit")

            old = _signal.signal(_signal.SIGINT, _handler)
            try:
                yield
            finally:
                try:
                    _signal.signal(_signal.SIGINT, old)
                except Exception:
                    logger.warning("failed to restore SIGINT handler", exc_info=True)

        with _sigint_to_flag_guard():
            # 各 player の前 tick の spot を保持して差分検出に使う
            prev_spots: dict[int, str | None] = {
                int(pid.value): runtime.get_player_spot_id(pid) for pid in runtime.get_player_ids()
            }
            # #404 P1: 外側ループを「world_tick が max_world_ticks に達するまで」に
            # 統一する。旧 ``for i in range(max_ticks)`` は外側 iteration 回数だった
            # ため、do_move のネスト advance_tick で world_tick が大量にジャンプすると
            # 「MAX_TICKS=140 なのに 14 日進まなかった」事象を生んでいた。
            # 安全弁: iteration 上限 = max_world_ticks * 2。仮に 1 iteration で
            # world_tick が進まないバグが入ってもループが暴走しないようにする。
            max_iterations = max(1, max_world_ticks * 2)
            i = 0
            while runtime.current_tick() < max_world_ticks and i < max_iterations and not _interrupted["flag"]:
                w0 = runtime.current_tick()
                # 旧 progress callable は legacy (start 通知)。新 reporter は
                # tick 完了時に ETA / per-tick wall time を出す。
                progress(f"駆動 {i + 1}/{max_world_ticks} world_tick={w0}")
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
                llm_calls: int | None = None
                travel_active: int | None = None
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
                abort_reason = _llm_abort_reason(runtime)
                if abort_reason is not None:
                    outcome = "LLM_ABORTED"
                    end_reason = abort_reason
                    message = f"LLM 障害で実験を打ち切る world_tick={last_tick}: {abort_reason}"
                    if reporter is not None:
                        reporter.message(message)
                    else:
                        progress(message)
                    logger.error(message)
                    break
                end_check = runtime.check_game_end()
                if end_check.is_ended:
                    outcome, end_reason = _outcome_and_reason(end_check)
                    team_result = runtime.team_result_trace(end_check)
                    if team_result is not None:
                        recorder.record(
                            TraceEventKind.TEAM_RESULT,
                            tick=last_tick,
                            **team_result,
                        )
                    if reporter is not None:
                        reporter.message(f"ゲーム終了検出 outcome={outcome} world_tick={last_tick}")
                    else:
                        progress(f"ゲーム終了検出 outcome={outcome} world_tick={last_tick}")
                    break
                i += 1
            if _interrupted["flag"] and outcome != "LLM_ABORTED":
                # 打ち切り済みの run を INTERRUPTED で塗り替えない。
                # 終了コードが 1 → 0 に戻り、「使えない run」の印が消える。
                outcome = "INTERRUPTED"
            if i >= max_iterations and runtime.current_tick() < max_world_ticks:
                # 安全弁が発火 = 1 iteration で world_tick が進まないバグ。
                # silent ではなく明確に log + message で警告する。
                warn = (
                    f"iteration 安全弁発火: {max_iterations} 回 advance_tick しても "
                    f"world_tick が {max_world_ticks} に達しなかった (現 "
                    f"{runtime.current_tick()})。advance_tick が無限ループ気味の "
                    f"シナリオの可能性 — trace.jsonl を確認してください。"
                )
                logger.warning(warn)
                if reporter is not None:
                    reporter.message(warn)
            elapsed = time.monotonic() - t0
        # ↑ ``with _sigint_to_flag_guard():`` を抜けた = SIGINT handler は
        # 確実に元に戻った状態でここに到達する (= main() 以降の Ctrl+C は
        # 通常通り KeyboardInterrupt を raise する)。

        # #1626: 環境を離れるので、まだ畳まれていない出来事からエピソードを書く。
        # 書いたエピソードを snapshot に入れるため、保存より前に置く。LLM が使えずに
        # 終わった run では、呼んでも失敗が並ぶだけなので書かずに理由を残す。
        runtime.write_episodes_on_leaving(skip_reason="llm_unusable" if outcome in _UNUSABLE_OUTCOMES else None)

        runtime.shutdown_async_events()

        # Phase 6: snapshot save。失敗しても run 自体は守る (= 例外を上位に飛ばさない)。
        # Phase 7: source_scenario を埋め込み + trace event 発行。
        if snapshot_session is not None and snapshot_save_dir is not None:
            try:
                report = snapshot_session.capture_all(
                    list(runtime.get_player_ids()),
                    source_scenario=scenario_path.stem,
                )
                logger.info(
                    "snapshot save: %d succeeded, %d failed (dir=%s)",
                    len(report.succeeded),
                    len(report.failed),
                    snapshot_save_dir,
                )
                for being_id, err in report.failed:
                    logger.warning(
                        "snapshot save failed for being_id=%s: %s",
                        being_id.value,
                        err,
                    )
                # Phase 7: trace に save 結果を残す。failures が空なら成功 trace、
                # 1 件でも failed があれば warning として残す (= post-hoc 分析で
                # 「ここで snapshot が部分的にしか取れなかった」を発見できる)。
                recorder.record(
                    TraceEventKind.SNAPSHOT_SAVE,
                    directory=str(snapshot_save_dir),
                    source_scenario=scenario_path.stem,
                    succeeded_count=len(report.succeeded),
                    failed_count=len(report.failed),
                    succeeded_being_ids=[b.value for b in report.succeeded],
                    memory_turns=snapshot_session.memory_turns(report.succeeded),
                    failures=[{"being_id": b.value, "error": err} for (b, err) in report.failed],
                )
            except Exception:
                logger.warning(
                    "snapshot save raised; experiment results are preserved "
                    "but resume from this run will not be possible",
                    exc_info=True,
                )
                # Phase 7: 例外で死んでも trace には「snapshot 全滅」を残す。
                try:
                    recorder.record(
                        TraceEventKind.SNAPSHOT_SAVE,
                        directory=str(snapshot_save_dir),
                        source_scenario=scenario_path.stem,
                        succeeded_count=0,
                        failed_count=-1,  # -1 = capture_all 自体が raise
                        error="capture_all raised; see logs",
                    )
                except Exception:
                    logger.warning(
                        "also failed to record SNAPSHOT_SAVE trace event",
                        exc_info=True,
                    )

            # Phase 9-1: world snapshot save。subsystem codec が未登録のため
            # subsystems={} の空 snapshot が出るが、ファイルは生成される。
            # Phase 9-2 以降で中身が埋まる。world snapshot save 失敗は
            # warning に留め、run の trace は守る (= Being snapshot と同方針)。
            try:
                snapshot_session.capture_world(
                    runtime,
                    source_scenario=scenario_path.stem,
                    world_tick=int(runtime.current_tick()),
                )
                # 公開アクセサで登録済 subsystem 名を取得 (= 観察用)。
                captured_keys = snapshot_session.world_snapshot_service.registered_subsystem_keys
                logger.info(
                    "world snapshot save: world_tick=%d subsystems=%s (dir=%s)",
                    int(runtime.current_tick()),
                    captured_keys,
                    snapshot_save_dir,
                )
                recorder.record(
                    TraceEventKind.WORLD_SNAPSHOT_SAVE,
                    directory=str(snapshot_save_dir),
                    source_scenario=scenario_path.stem,
                    world_tick=int(runtime.current_tick()),
                    captured_subsystems=captured_keys,
                )
            except Exception:
                logger.warning(
                    "world snapshot save raised; experiment results are "
                    "preserved but world state resume from this run will "
                    "not be possible",
                    exc_info=True,
                )
                try:
                    recorder.record(
                        TraceEventKind.WORLD_SNAPSHOT_SAVE,
                        directory=str(snapshot_save_dir),
                        source_scenario=scenario_path.stem,
                        world_tick=int(runtime.current_tick()),
                        error="capture_world raised; see logs",
                    )
                except Exception:
                    logger.warning(
                        "also failed to record WORLD_SNAPSHOT_SAVE trace event",
                        exc_info=True,
                    )

        # 実験用の差し替え runtime は持っていないことがある。0 件と区別するため None で返す。
        failure_counts_getter = getattr(runtime, "world_tick_failure_counts", None)
        world_tick_failure_counts = failure_counts_getter() if callable(failure_counts_getter) else None
        outcome, end_reason, llm_call_count, llm_success_count = _classify_llm_run_health(
            recorder,
            outcome=outcome,
            end_reason=end_reason,
        )
        return {
            "outcome": outcome,
            "end_reason": end_reason,
            "llm_call_count": llm_call_count,
            "llm_success_count": llm_success_count,
            "last_tick": last_tick,
            "elapsed_sec": elapsed,
            "max_world_ticks": max_world_ticks,
            "snapshot_save_dir": str(snapshot_save_dir) if snapshot_save_dir else None,
            "snapshot_load_dir": str(snapshot_load_dir) if snapshot_load_dir else None,
            "world_tick_failure_counts": world_tick_failure_counts,
            "world_tick_failure_total": (
                sum(world_tick_failure_counts.values()) if world_tick_failure_counts is not None else None
            ),
        }


def _count_llm_failures(llm_calls: list[Any]) -> dict[str, int]:
    """失敗した呼び出しを error_code ごとに数える。成功のみなら空 dict。"""
    counts: dict[str, int] = {}
    for event in llm_calls:
        if event.payload.get("success"):
            continue
        code = str(event.payload.get("error_code") or "UNKNOWN")
        counts[code] = counts.get(code, 0) + 1
    return counts


_AUX_COMPONENT_LABELS: dict[str, str] = {
    # 主観補完は #1631 で、短期記憶の長い要約は #1824 で消した。消す前の run の
    # report を読むために残す。
    "episode_subjective": "主観の書き込み",
    "short_term_long_summary": "短期記憶の長い要約",
    AuxLlmComponent.SHORT_TERM_SUMMARY.value: "短期記憶の要約",
    AuxLlmComponent.EPISODE_WRITING.value: "エピソードの書き起こし",
    AuxLlmComponent.TYPED_JUDGMENT.value: "Jev の型付き判断",
}


def _sum_or_unavailable(values: list[Any], *, money: bool) -> str:
    """None は応答に無かった値。0 に潰すと無料・0 トークンと読めるので、回数を添える (#1617)。"""
    known = [v for v in values if v is not None]
    missing = len(values) - len(known)
    if values and not known:
        return "取れない"
    total = sum(known)
    shown = f"${total:.4f}" if money else str(int(total))
    return f"{shown} + 取れない {missing} 回" if missing else shown


def _billable(payload: Mapping[str, Any], key: str) -> bool:
    """応答が届かず失敗した回は値が無くて当然なので、「取れない」に数えない。"""
    return bool(payload.get("success")) or payload.get(key) is not None


def _llm_cost_row(label: str, calls: list[Any]) -> str:
    payloads = [e.payload for e in calls]
    failures = sum(1 for p in payloads if not p.get("success"))
    latency_sec = sum(int(p.get("wall_latency_ms") or 0) for p in payloads) / 1000.0
    prompt, completion, cost = (
        _sum_or_unavailable([p.get(key) for p in payloads if _billable(p, key)], money=key == "cost_usd")
        for key in ("prompt_tokens", "completion_tokens", "cost_usd")
    )
    return f"| {label} | {len(payloads)} | {failures} | {prompt} | {completion} | {cost} | {latency_sec:.1f} |"


def _known_cost(calls: list[Any]) -> float:
    return sum(float(e.payload["cost_usd"]) for e in calls if e.payload.get("cost_usd") is not None)


def _llm_cost_header_line(llm_calls: list[Any], aux_calls: list[Any]) -> str:
    action_cost = _known_cost(llm_calls)
    aux_cost = _known_cost(aux_calls)
    line = (
        f"- 費用 (取れた分の合計): ${action_cost + aux_cost:.4f} = "
        f"行動 ${action_cost:.4f} + 記憶の部品と Jev ${aux_cost:.4f}"
    )
    missing = sum(
        1 for e in llm_calls + aux_calls if e.payload.get("cost_usd") is None and _billable(e.payload, "cost_usd")
    )
    return f"{line}。費用が取れない呼び出し {missing} 回" if missing else line


def _llm_cost_lines(llm_calls: list[Any], aux_calls: list[Any], aux_record_failures: list[Any]) -> list[str]:
    """行動の呼び出しと、記憶の部品・Jev の呼び出しを部品ごとに分けた表 (#1617)。"""
    by_component: dict[str, list[Any]] = {}
    for event in aux_calls:
        by_component.setdefault(str(event.payload.get("component")), []).append(event)
    order = [c.value for c in AuxLlmComponent]
    components = sorted(by_component, key=lambda c: (order.index(c) if c in order else len(order), c))
    lines = [
        "## LLM 呼び出しの回数と費用",
        "",
        "費用は provider が応答に載せた値 (OpenRouter の usage.cost)。"
        "記憶の部品と Jev は、応答に無かった値を「取れない」とし、0 として足さない。"
        "行動の呼び出しは、応答に費用が無くても 0 で記録される (llm_call の決まり)。",
        "",
        "| 呼び出し | 回数 | 失敗 | 入力トークン | 出力トークン | 費用 (USD) | 待ち時間の合計 (秒) |",
        "|---|---|---|---|---|---|---|",
        _llm_cost_row("行動", llm_calls),
    ]
    for component in components:
        label = _AUX_COMPONENT_LABELS.get(component, component)
        lines.append(_llm_cost_row(f"{label} ({component})", by_component[component]))
    lines.append("")
    if not aux_calls:
        lines.append("- 記憶の部品と Jev の呼び出し: 0 件")
    if aux_record_failures:
        failed = Counter(str(e.payload.get("component")) for e in aux_record_failures)
        breakdown = ", ".join(f"{c}={n}" for c, n in sorted(failed.items()))
        lines.append(f"- 記録できなかった呼び出し: {breakdown} (この回数は上の表に入っていない)")
    if not aux_calls or aux_record_failures:
        lines.append("")
    return lines


def _world_tick_failure_lines(summary: dict[str, Any]) -> list[str]:
    """世界の tick で例外を出した処理 (取りやめと後処理の失敗) の件数を、冒頭の要約に出す行 (design_decisions D1558)。"""
    label = "- 世界の tick で例外を出した処理 (のべ)"
    counts = summary.get("world_tick_failure_counts")
    if counts is None:
        return [f"{label}: 未計測"]
    total = sum(counts.values())
    if total == 0:
        return [f"{label}: 0 件"]
    breakdown = ", ".join(f"{stage}={count}" for stage, count in sorted(counts.items()))
    return [
        f"{label}: **{total} 件** ({breakdown})",
        "  - 1 体ぶんの処理を取りやめたか、後処理の失敗を残して続けた run。"
        "効果の測定に使う前に、trace の world_tick_unit_failed で原因を切り分ける"
        " (continued が後処理の失敗)。同じ対象が毎 tick 失敗すると、そのたびに数える",
    ]


def _build_report(
    *,
    scenario_path: Path,
    trace_path: Path,
    summary: dict[str, Any],
) -> str:
    """trace.jsonl を読み戻して汎用集計レポートを Markdown で返す。"""
    events = list(load_trace_events(trace_path))
    actions: list[Any] = []
    action_results: list[Any] = []
    memo_hints: list[Any] = []
    position_changes: list[Any] = []
    llm_calls: list[Any] = []
    aux_calls: list[Any] = []
    aux_record_failures: list[Any] = []
    by_player: dict[int, dict[str, int]] = {}
    for e in events:
        if e.kind == TraceEventKind.ACTION:
            actions.append(e)
        elif e.kind == TraceEventKind.ACTION_RESULT:
            action_results.append(e)
        elif e.kind == TraceEventKind.MEMO_HINT:
            memo_hints.append(e)
        elif e.kind == TraceEventKind.POSITION_CHANGE:
            position_changes.append(e)
        elif e.kind == TraceEventKind.LLM_CALL:
            llm_calls.append(e)
        elif e.kind == TraceEventKind.AUX_LLM_CALL:
            aux_calls.append(e)
        elif e.kind == TraceEventKind.AUX_LLM_CALL_RECORD_FAILED:
            aux_record_failures.append(e)
        pid = e.player_id
        if pid is None:
            continue
        bucket = by_player.setdefault(
            pid,
            {
                "actions": 0,
                "successes": 0,
                "failures": 0,
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
        elif e.kind == TraceEventKind.POSITION_CHANGE:
            # 初期配置 (from_spot_id=None) は move カウントに含めない
            from_spot = e.payload.get("from_spot_id") if isinstance(e.payload, dict) else None
            if from_spot is not None:
                bucket["moves"] += 1

    lines: list[str] = []
    lines.append(f"# Scenario experiment report — {scenario_path.stem}")
    lines.append("")
    lines.append(f"- scenario: `{scenario_path}`")
    lines.append(f"- outcome: **{summary['outcome']}**")
    if summary.get("end_reason"):
        lines.append(f"- end reason: {summary['end_reason']}")
    lines.append(f"- last tick: {summary['last_tick']} / max world ticks: {summary['max_world_ticks']}")
    lines.append(f"- elapsed: {summary['elapsed_sec']:.1f}s")
    lines.append(f"- total events: {len(events)}")
    # 層 3: 呼び出しの健全さは冒頭に出す。奥に置くと「outcome / 完走」だけを
    # 読んで閉じる (140 tick run で実際にそうなった)。
    llm_failures = _count_llm_failures(llm_calls)
    if llm_calls:
        succeeded = len(llm_calls) - sum(llm_failures.values())
        rate = succeeded * 100.0 / len(llm_calls)
        lines.append(f"- llm calls: {len(llm_calls)} (成功 {succeeded} / {rate:.0f}%)")
    lines.append(_llm_cost_header_line(llm_calls, aux_calls))
    lines.extend(_world_tick_failure_lines(summary))
    lines.append("")
    lines.extend(_llm_cost_lines(llm_calls, aux_calls, aux_record_failures))
    if llm_failures:
        lines.append("## LLM 呼び出しの失敗内訳")
        lines.append("")
        lines.append(
            "呼び出しが届かなかったぶんは行動として数えられない。"
            "**プレイヤー別集計の failures 列 (tool の失敗) とは別物。**"
        )
        lines.append("")
        for code, count in sorted(llm_failures.items()):
            lines.append(f"- {code}: {count}")
        lines.append("")
    lines.append("## イベント種別ごとの件数")
    lines.append("")
    lines.append(f"- action: {len(actions)}")
    lines.append(f"- action_result: {len(action_results)}")
    lines.append(f"- memo_hint: {len(memo_hints)}")
    lines.append(f"- position_change: {len(position_changes)}")
    lines.append("")
    if by_player:
        lines.append("## プレイヤー別集計")
        lines.append("")
        lines.append("| player_id | actions | successes | failures | moves |")
        lines.append("|-----------|---------|-----------|----------|-------|")
        for pid in sorted(by_player):
            b = by_player[pid]
            lines.append(f"| {pid} | {b['actions']} | {b['successes']} | {b['failures']} | {b.get('moves', 0)} |")
        lines.append("")
    lines.append("## 成果物")
    lines.append("")
    lines.append(f"- trace: `{trace_path}`")
    lines.append(f"- legacy HTML viewer: `{trace_path.with_suffix('.html')}`")
    lines.append(f"- map trace viewer: `{trace_path.parent / 'viewer.html'}`")
    lines.append(f"- timeline viewer: `{trace_path.parent / 'timeline.html'}`")
    lines.append("")
    return "\n".join(lines)


@dataclass(frozen=True)
class HtmlArtifactResult:
    """run 完了時に生成する HTML 成果物 1 件の結果。"""

    name: str
    path: Path
    generated: bool
    error: str | None = None


def _render_trace_html(trace_path: Path, *, title: str) -> str:
    """trace_to_html.py の legacy HTML 文字列を返す。"""
    from scripts.trace_to_html import render_html

    events = list(load_trace_events(trace_path))
    return render_html(events, title=title)


def _render_map_viewer_html(run_dir: Path, trace_path: Path, *, title: str) -> str:
    """地図つき trace viewer の HTML 文字列を返す。"""
    from scripts._viewer_vendor import VendorFetchError
    from scripts.build_trace_viewer import (
        fetch_cytoscape,
        load_scenario_topology,
        render_viewer_html,
    )

    try:
        asset = fetch_cytoscape()
    except VendorFetchError as e:
        raise RuntimeError(
            f"{e}。復旧手順: ネットワークに接続した状態で "
            "`uv run python scripts/build_trace_viewer.py <run_dir>` を一度実行し、"
            "Cytoscape vendor をキャッシュしてください。"
        ) from e
    events = list(load_trace_events(trace_path))
    topology = load_scenario_topology(run_dir / "scenario.json")
    return render_viewer_html(
        title=title,
        events=events,
        scenario_topology=topology,
        cytoscape_js_src=asset.content,
    )


def _render_timeline_viewer_html(trace_path: Path, *, title: str) -> str:
    """timeline.html の HTML 文字列を返す。"""
    from scripts.build_timeline_viewer import load_events
    from scripts.build_timeline_viewer import render_html as render_timeline_html

    events = load_events(trace_path)
    return render_timeline_html(events, title)


def _render_prompt_viewer_html(run_dir: Path) -> str:
    """prompt.html の HTML 文字列を返す。

    他 Viewer と違い trace ではなく ``prompt_dataset/calls.jsonl`` を読む。
    capture 無効の run では calls.jsonl 自体が無く FileNotFoundError になり、
    ``_write_html_artifact`` が warning にして次へ進む (= 他の成果物を
    巻き込まない)。
    """
    from scripts.build_prompt_viewer import _load_calls
    from scripts.build_prompt_viewer import render_html as render_prompt_html

    calls = _load_calls(run_dir)
    profile = ""
    run_json = run_dir / "prompt_dataset" / "run.json"
    if run_json.exists():
        try:
            profile = str(json.loads(run_json.read_text(encoding="utf-8")).get("profile") or "")
        except json.JSONDecodeError:
            profile = ""
    return render_prompt_html(calls, run_id=run_dir.name, profile=profile)


def _write_html_artifact(
    *,
    name: str,
    path: Path,
    render: Callable[[], str],
) -> HtmlArtifactResult:
    """HTML 成果物を 1 件生成し、結果を stdout と warning に残す。"""
    try:
        html_text = render()
        path.write_text(html_text, encoding="utf-8")
    except Exception as e:
        error = str(e)
        logger.warning("failed to build %s: %s", name, error)
        print(f"[html-error] {name}: {error}", flush=True)
        return HtmlArtifactResult(name=name, path=path, generated=False, error=error)
    print(f"[html] {name}: {path}", flush=True)
    return HtmlArtifactResult(name=name, path=path, generated=True)


def _emit_html_artifacts(
    *,
    run_dir: Path,
    trace_path: Path,
    trace_html_path: Path,
    title: str,
) -> list[HtmlArtifactResult]:
    """run 完了時の HTML 成果物をまとめて生成する。

    ``viewer.html`` は ``run_dir/scenario.json`` から地図を組み立てるため、
    呼び出し側は scenario copy 後にこの関数を呼ぶ。各 Viewer の失敗は
    実験データを巻き込まず、stdout と warning に残して次の生成へ進む。
    """
    artifacts: list[HtmlArtifactResult] = []
    artifacts.append(
        _write_html_artifact(
            name="trace.html",
            path=trace_html_path,
            render=lambda: _render_trace_html(trace_path, title=title),
        )
    )
    artifacts.append(
        _write_html_artifact(
            name="viewer.html",
            path=run_dir / "viewer.html",
            render=lambda: _render_map_viewer_html(run_dir, trace_path, title=title),
        )
    )
    artifacts.append(
        _write_html_artifact(
            name="timeline.html",
            path=run_dir / "timeline.html",
            render=lambda: _render_timeline_viewer_html(trace_path, title=title),
        )
    )
    artifacts.append(
        _write_html_artifact(
            name="prompt.html",
            path=run_dir / "prompt.html",
            render=lambda: _render_prompt_viewer_html(run_dir),
        )
    )
    return artifacts


def _emit_html(trace_path: Path, html_path: Path, *, title: str) -> None:
    """trace_to_html.py を呼んで legacy HTML を出力。

    既存テストや外部利用向けの互換 wrapper。通常 run では
    ``_emit_html_artifacts`` を使い、3 Viewer も併せて生成する。
    """
    html_path.write_text(_render_trace_html(trace_path, title=title), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _load_dotenv_safe()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        description="Drive a single LLM-driven scenario session and emit trace + report + HTML"
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        default=None,
        help="Path to scenario JSON (e.g. data/scenarios/forbidden_library_demo.json)",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Experiment profile name from data/experiment_profiles/<name>.json",
    )
    parser.add_argument(
        "--experiment-config",
        type=Path,
        default=None,
        help="Path to an experiment config JSON file",
    )
    parser.add_argument(
        "--max-world-ticks",
        type=int,
        default=None,
        help=("Stop when world_tick reaches this value (default 30, or experiment config max_world_ticks)"),
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
    parser.add_argument(
        "--snapshot-save-dir",
        type=Path,
        default=None,
        help=(
            "Phase 6 / Issue #470: 実験終了時に各 player の Being snapshot を "
            "JSON で書き出すディレクトリ。SIGINT (Ctrl+C) 時も capture される。"
            "未指定なら snapshot は取らない (= 既存挙動完全互換)。"
        ),
    )
    parser.add_argument(
        "--snapshot-load-dir",
        type=Path,
        default=None,
        help=(
            "Phase 6 / Issue #470: 実験開始前に読み込む snapshot ディレクトリ。"
            "前回 run の --snapshot-save-dir で生成された JSON を渡すと、"
            "前回の memory 状態から続きの実験が走る。"
        ),
    )
    args = parser.parse_args(argv)

    try:
        config_source, config_source_path = _load_experiment_config_source(
            profile=args.profile,
            config_path=args.experiment_config,
        )
        runtime_config_source = _runtime_config_mapping_from_source(config_source)
        _reject_removed_config_fields(config_source)
    except (OSError, ValueError) as e:
        parser.error(str(e))

    scenario_arg = args.scenario
    if scenario_arg is None:
        raw_scenario = config_source.get("scenario")
        if raw_scenario:
            scenario_arg = Path(str(raw_scenario))
    if scenario_arg is None:
        parser.error("scenario is required. Pass --scenario or set 'scenario' in the experiment config.")
    args.scenario = scenario_arg

    if not args.scenario.exists():
        parser.error(f"scenario not found: {args.scenario}")

    if args.max_world_ticks is None:
        if config_source.get("max_world_ticks") is not None:
            args.max_world_ticks = int(config_source["max_world_ticks"])
        else:
            args.max_world_ticks = int("30")

    out_dir = args.out
    if out_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out_dir = _REPO_ROOT / "var" / "runs" / f"{args.scenario.stem}-{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "trace.jsonl"
    report_path = out_dir / "report.md"
    html_path = out_dir / "trace.html"

    # 実験設定は profile/config の runtime_config だけから解決する。
    # 外側 shell の環境変数は読まない。
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
        ResolvedLlmRuntimeConfig,
    )

    cfg = ResolvedLlmRuntimeConfig.from_mapping(values=runtime_config_source)

    print(
        f"[run] scenario={args.scenario.name} max_world_ticks={args.max_world_ticks}",
        flush=True,
    )
    # OpenRouter provider routing: 設定されているときだけ表示
    if cfg.openrouter_provider or cfg.openrouter_quantization:
        print(
            f"[run] openrouter routing: provider={cfg.openrouter_provider or '-'} "
            f"quantization={cfg.openrouter_quantization or '-'}",
            flush=True,
        )
    print(f"[out] {out_dir}", flush=True)

    # profile が snapshot 保存を標準指定している場合は OUT/snapshots を使う。
    if args.snapshot_save_dir is None and bool(config_source.get("snapshot_save")):
        args.snapshot_save_dir = out_dir / "snapshots"

    manifest_path, manifest_sha256 = _write_experiment_manifest(
        out_dir=out_dir,
        argv=list(sys.argv if argv is None else [sys.argv[0], *argv]),
        scenario_path=args.scenario,
        trace_path=trace_path,
        report_path=report_path,
        html_path=html_path,
        config_source=config_source,
        config_source_path=config_source_path,
        runtime_config_source=runtime_config_source,
        resolved_config=cfg,
        max_world_ticks=args.max_world_ticks,
        snapshot_save_dir=args.snapshot_save_dir,
        snapshot_load_dir=args.snapshot_load_dir,
        no_html=args.no_html,
        no_progress_jsonl=args.no_progress_jsonl,
    )
    from ai_rpg_world.application.llm.services.prompt_dataset_capture import (
        PromptDatasetCaptureSink,
    )

    prompt_dataset_sink = PromptDatasetCaptureSink(
        run_dir=out_dir,
        run_id=out_dir.name,
        run_metadata={
            "source_run_dir": str(out_dir),
            "experiment_manifest_path": str(manifest_path),
            "experiment_manifest_sha256": manifest_sha256,
            "profile": config_source.get("profile"),
            "scenario_path": str(args.scenario),
            "scenario_sha256": _sha256_file(args.scenario),
            "runtime_config": _prompt_dataset_runtime_config_payload(cfg),
        },
        failure_policy=cfg.prompt_dataset_capture_failure_policy,
    )

    with JsonlTraceRecorder(trace_path) as rec:
        # PR #448: trace payload は cfg.to_trace_dict() で一括出力 + scenario /
        # max_world_ticks を追加。**API key は cfg.to_trace_dict() 内で *** に
        # マスクされる** (= 漏洩防止)。
        run_start_payload = cfg.to_trace_dict()
        run_start_payload.update(
            scenario=args.scenario.name,
            max_world_ticks=args.max_world_ticks,
            # legacy 互換 (run_start を grep する既存スクリプト向け)
            model=cfg.llm_model,
            api_base=cfg.llm_api_base,
            experiment_profile=config_source.get("profile"),
            experiment_manifest_path=str(manifest_path),
            experiment_manifest_sha256=manifest_sha256,
        )
        rec.record(TraceEventKind.RUN_START, **run_start_payload)

        def progress(msg: str) -> None:
            print(f"  {msg}", flush=True)

        # 進捗 reporter: stdout (旧来互換) + stderr inline ETA + progress.jsonl
        reporter = _ExperimentProgressReporter(
            max_world_ticks=args.max_world_ticks,
            stdout=sys.stdout,
            stderr=None if args.no_stderr_progress else sys.stderr,
            progress_jsonl=(None if args.no_progress_jsonl else (out_dir / "progress.jsonl")),
        )

        # Phase 6 (Issue #470): snapshot-load-dir が指定されていれば存在チェック。
        # 不在 dir で進めると "途中で読めない" が分かるのが load 後になり、
        # 既存 experiment data の汚染リスクが上がる。ここで早期 fail-fast。
        if args.snapshot_load_dir is not None and not args.snapshot_load_dir.exists():
            parser.error(f"snapshot-load-dir does not exist: {args.snapshot_load_dir}")
        if args.snapshot_save_dir is not None:
            args.snapshot_save_dir.mkdir(parents=True, exist_ok=True)

        try:
            summary = _drive_scenario(
                run_id=out_dir.name,
                scenario_path=args.scenario,
                max_world_ticks=args.max_world_ticks,
                recorder=rec,
                progress=progress,
                runtime_config=cfg,
                reporter=reporter,
                snapshot_save_dir=args.snapshot_save_dir,
                snapshot_load_dir=args.snapshot_load_dir,
                prompt_dataset_sink=prompt_dataset_sink,
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

    # シナリオ JSON は run dir に必ずコピーしておく。
    # viewer.html の地図 (spot graph topology) は scenario.json から組み立てる
    # ため、ここに無いと「あとで手動 publish した run」で地図が空表示になる。
    # 以前は publish 時のみコピーしていたが、--publish-gist 無しで走らせた run を
    # 後追いで build_trace_viewer / publish にかけると地図が欠ける silent failure
    # になっていた。再現性担保 (シナリオ差分) の観点でも常にコピーしてよい。
    scenario_copy = out_dir / "scenario.json"
    try:
        scenario_copy.write_bytes(args.scenario.read_bytes())
    except OSError as e:
        logger.warning("failed to copy scenario JSON into run dir: %s", e)

    if not args.no_html:
        _emit_html_artifacts(
            run_dir=out_dir,
            trace_path=trace_path,
            trace_html_path=html_path,
            title=f"{args.scenario.stem} run",
        )

    print(f"[report] {report_path}", flush=True)
    print(f"[trace] {trace_path}", flush=True)
    # 層 3: 端末で最後に見る 1 行にも呼び出しの健全さを出す。report.md を
    # 開かずに閉じる人がいるし、閾値未満の「じわ荒れ」はここだけが砦になる。
    done_line = (
        f"[done] outcome={summary['outcome']} last_tick={summary['last_tick']} elapsed={summary['elapsed_sec']:.1f}s"
    )
    tick_failures = summary.get("world_tick_failure_total")
    if tick_failures:
        done_line += f" world_tick_failures={tick_failures}"
    llm_total = int(summary.get("llm_call_count") or 0)
    if llm_total:
        llm_ok = int(summary.get("llm_success_count") or 0)
        done_line += f" llm={llm_ok}/{llm_total} ({llm_ok * 100 // llm_total}%)"
    print(done_line, flush=True)

    if args.publish_gist:
        from scripts.publish_experiment_gist import (
            GistPublishError,
            publish,
        )

        desc = args.publish_gist_desc or (
            f"llm-rpg experiment: {args.scenario.stem} outcome={summary['outcome']} tick={summary['last_tick']}"
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
    return 1 if summary["outcome"] in _UNUSABLE_OUTCOMES else 0


if __name__ == "__main__":
    raise SystemExit(main())
