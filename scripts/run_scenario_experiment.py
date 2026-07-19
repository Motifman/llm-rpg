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
        --max-world-ticks 30 \\
        --out var/runs/relay-foo

    # 出力:
    #   var/runs/relay-foo/trace.jsonl
    #   var/runs/relay-foo/report.md
    #   var/runs/relay-foo/trace.html
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, TextIO

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

_EXPERIMENT_PROFILE_DIR = _REPO_ROOT / "data" / "experiment_profiles"


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
        stderr: Optional[TextIO],
        progress_jsonl: Optional[Path],
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
        remaining_ticks = max(0, self._max_world_ticks - (i + 1))
        eta = avg * remaining_ticks
        pct = (i + 1) / self._max_world_ticks * 100.0
        nested_world_ticks: Optional[int] = None
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
            entry: Dict[str, Any] = {
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
    profile: Optional[str],
    config_path: Optional[Path],
) -> tuple[dict[str, Any], Optional[Path]]:
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
            raise ValueError(
                "experiment config runtime_config keys must be non-empty strings"
            )
        rendered_values[key] = _json_config_value(value)
    return rendered_values


_SECRET_KEY_FRAGMENTS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD")


def _mask_secret_values(value: Any, *, key_name: str = "") -> Any:
    """manifest に秘密値が残らないよう再帰的に伏せる。"""
    normalized_key = key_name.upper()
    if any(fragment in normalized_key for fragment in _SECRET_KEY_FRAGMENTS):
        return "***"
    if isinstance(value, dict):
        return {
            k: _mask_secret_values(v, key_name=str(k))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask_secret_values(v) for v in value]
    return value


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_git(args: list[str]) -> Optional[str]:
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
        "dirty_diff_sha256": (
            hashlib.sha256(combined_diff.encode("utf-8")).hexdigest()
            if combined_diff
            else None
        ),
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
    config_source_path: Optional[Path],
    runtime_config_source: Mapping[str, str],
    resolved_config: Any,
    max_world_ticks: int,
    snapshot_save_dir: Optional[Path],
    snapshot_load_dir: Optional[Path],
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
        "runtime_config_source": _mask_secret_values(
            dict(sorted(runtime_config_source.items()))
        ),
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
    全 store ハンドルが揃わない (semantic / memory_link / recall_buffer /
    journal は world_runtime の通常経路では作られない) ため、runtime の
    内部 field から **拾える分だけ** 集めて wiring 風オブジェクトを返す。
    足りない store は ``ExperimentSnapshotSession`` 側で空 in-memory に
    fallback する。
    """
    from types import SimpleNamespace

    # episode_store は _episodic_stack が None のときは None。
    episodic_stack = getattr(runtime, "_episodic_stack", None)
    episode_store = (
        getattr(episodic_stack, "episode_store", None)
        if episodic_stack is not None
        else None
    )
    # 注意: ``_aux_being_repository`` は private 属性 (public property なし)。
    # ``aux_being_resolver`` の方は public property があるのでそちらを使う。
    # 将来 ``aux_being_repository`` の public property が追加されたら同じ
    # 形式に揃える。
    aux_resolver = getattr(runtime, "aux_being_resolver", None)
    aux_repo = getattr(runtime, "_aux_being_repository", None)
    # #526 後続: SEMANTIC_PASSIVE_TOP_K / SEMANTIC_LLM_GIST_ENABLED が ON だと
    # episodic_stack が semantic store + memory link store を持つ。あれば snapshot に
    # 拾う (OFF なら従来どおり None = 空 in-memory fallback)。link store も拾わないと
    # semantic entries だけ保存され、昇格根拠の link graph が空 fallback になる。
    semantic_store = (
        getattr(episodic_stack, "semantic_memory_store", None)
        if episodic_stack is not None
        else None
    )
    memory_link_store = (
        getattr(episodic_stack, "memory_link_store", None)
        if episodic_stack is not None
        else None
    )
    # #558 レビュー反映 (MEDIUM-2): reinterpretation (段1) ON のとき episodic_stack が
    # in-memory の recall_buffer / journal を持つ。snapshot surface で None ハードコード
    # だと、再解釈 journal と pending recall buffer が save/load で silent に失われ、
    # 再開時の記憶連続性 (自己の継続性) が壊れる。semantic と同じく stack から拾う
    # (OFF なら None = 従来どおり空 in-memory fallback)。
    recall_buffer_store = (
        getattr(episodic_stack, "recall_buffer_store", None)
        if episodic_stack is not None
        else None
    )
    reinterpretation_journal_store = (
        getattr(episodic_stack, "reinterpretation_journal", None)
        if episodic_stack is not None
        else None
    )
    # U2 (証拠台帳統一設計): BELIEF_EVIDENCE_ENABLED ON のとき episodic_stack が
    # belief evidence buffer store を持つ。checklist #27 (memory_full_003 で
    # stub 追従漏れが実際に起きた教訓) に従い、ここで拾わないと flag ON でも
    # evidence が save/load で silent に失われる。OFF なら None = 従来どおり
    # 空 in-memory fallback。
    belief_evidence_buffer_store = (
        getattr(episodic_stack, "belief_evidence_buffer_store", None)
        if episodic_stack is not None
        else None
    )
    # U9b (予測誤差統一設計 部品5・想起の信用割り当て): RECALL_HIT_BOOST_ENABLED
    # ON のとき episodic_stack が的中側 sidecar store を持つ。checklist #27
    # (memory_full_003 で stub 追従漏れが実際に起きた教訓) に従い、ここで
    # 拾わないと flag ON でも的中回数が save/load で silent に失われる。
    # OFF なら None = 空 in-memory fallback。
    recall_success_store = (
        getattr(episodic_stack, "recall_success_store", None)
        if episodic_stack is not None
        else None
    )
    # U10a (予測誤差統一設計 部品6・pending prediction): PENDING_PREDICTION_ENABLED
    # ON のとき episodic_stack が pending prediction store を持つ。checklist #27
    # (memory_full_003 で stub 追従漏れが実際に起きた教訓) に従い、ここで拾わ
    # ないと flag ON でも保留中の予測 (約束) が save/load で silent に失われる。
    # OFF なら None = 空 in-memory fallback。
    pending_prediction_store = (
        getattr(episodic_stack, "pending_prediction_store", None)
        if episodic_stack is not None
        else None
    )
    # P5 (目的層): GOAL_STORE_ENABLED ON のとき world_runtime が goal store を
    # 構築し ``_goal_journal_store`` に保持する。checklist #27 に従い拾う。
    # OFF なら None = 空 in-memory fallback。
    goal_journal_store = getattr(runtime, "_goal_journal_store", None)
    # P-U2 (停滞感 store): STAGNATION_PRESSURE_ENABLED ON のとき world_runtime が
    # 停滞感カウンタ store を構築し ``_stagnation_pressure_store`` に保持する。
    # checklist #27 に従い拾う。OFF なら None = 空 in-memory fallback。
    stagnation_pressure_store = getattr(runtime, "_stagnation_pressure_store", None)
    # PR-G (想起階層: slot / afterglow / habituation): #526 段階 3 で
    # episodic_stack に生えた 3 store。checklist #27 の追従漏れが実際に
    # 起きていた箇所 (ExperimentSnapshotSession 側は getattr で拾う準備が
    # 済んでいたが、この stub がここまで一度も拾っていなかった)。ここで
    # 拾わないと enable 時でも想起スロット / afterglow index / 慣化状態が
    # save/load で silent に失われる。OFF なら None = 空 in-memory fallback。
    recall_slot_store = (
        getattr(episodic_stack, "recall_slot_store", None)
        if episodic_stack is not None
        else None
    )
    afterglow_store = (
        getattr(episodic_stack, "afterglow_store", None)
        if episodic_stack is not None
        else None
    )
    recall_habituation_store = (
        getattr(episodic_stack, "recall_habituation_store", None)
        if episodic_stack is not None
        else None
    )
    return SimpleNamespace(
        memo_store=getattr(runtime, "_todo_store", None),
        semantic_memory_store=semantic_store,
        memory_link_store=memory_link_store,
        episodic_recall_buffer_store=recall_buffer_store,
        episodic_reinterpretation_journal_store=reinterpretation_journal_store,
        episodic_episode_store=episode_store,
        being_repository=aux_repo,
        being_attachment_resolver=aux_resolver,
        belief_evidence_buffer_store=belief_evidence_buffer_store,
        recall_success_store=recall_success_store,
        pending_prediction_store=pending_prediction_store,
        goal_journal_store=goal_journal_store,
        stagnation_pressure_store=stagnation_pressure_store,
        recall_slot_store=recall_slot_store,
        afterglow_store=afterglow_store,
        recall_habituation_store=recall_habituation_store,
    )


def _drive_scenario(
    *,
    scenario_path: Path,
    max_world_ticks: int,
    recorder: JsonlTraceRecorder,
    progress: Any,
    runtime_config: Optional[Any] = None,
    reporter: Optional[_ExperimentProgressReporter] = None,
    snapshot_save_dir: Optional[Path] = None,
    snapshot_load_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """シナリオを 1 セッション分回し、最終ステートを dict で返す。

    GameRuntimeManager を内部で使う。:class:`WorldRuntime` 経由なので
    既存の world_runtime / relay_puzzle 路線と互換。

    Args:
        max_world_ticks: ループ終了条件 (#404 P1)。``runtime.current_tick()`` が
            この値に達するまで ``advance_tick`` を呼ぶ。旧名 ``max_ticks`` は
            外側 for ループの回数だったが、``#405`` で 1 iteration = 1 world tick
            に揃ったので world tick 基準に意味論統一する。
    """
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

    with TemporaryDirectory() as d:
        chars = Path(d) / "characters.json"
        mgr = GameRuntimeManager(
            scenarios_dir=scenarios_dir,
            characters_path=chars,
            runtime_config=runtime_config,
        )
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

        # Phase 6 (Issue #470): snapshot load / save の準備。
        # - 全 player について aux Being を ensure_attached しておく (= snapshot
        #   capture / restore の前提条件)。これは ``run_turn`` でも idempotent に
        #   呼ばれる operation だが、snapshot を始める前に明示的に走らせて
        #   「Being が attach されていない」によるスキップを避ける。
        # - load 経路: snapshot_load_dir があれば全 JSON を restore。失敗は
        #   fail-fast (= 例外伝播)。
        # - save 経路は run 終了時 (= 下の try / finally) で行う。
        snapshot_session: Optional[Any] = None
        if snapshot_save_dir is not None or snapshot_load_dir is not None:
            from ai_rpg_world.application.being.experiment_snapshot_session import (
                ExperimentSnapshotSession,
            )

            # aux Being stack を確実に初期化 (= _aux_being_repository を作る)
            if hasattr(runtime, "_wire_auxiliary_tool_stack"):
                runtime._wire_auxiliary_tool_stack()
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
                logger.info(
                    "loading snapshots from %s ...", snapshot_load_dir
                )
                restore_report = snapshot_session.restore_all_from_dir(
                    snapshot_load_dir,
                    current_scenario=scenario_path.stem,
                )
                logger.info(
                    "restored %d being snapshot(s)", len(restore_report.restored)
                )
                # Phase 7: trace に「どの run から続きを取ったか」を残す。
                # cross-scenario transfer も明示的に payload に乗せる。
                recorder.record(
                    TraceEventKind.SNAPSHOT_LOAD,
                    directory=str(snapshot_load_dir),
                    restored_count=len(restore_report.restored),
                    restored_being_ids=[b.value for b in restore_report.restored],
                    cross_scenario_transfers=[
                        {
                            "being_id": b.value,
                            "source_scenario": src,
                            "current_scenario": cur,
                        }
                        for (b, src, cur) in restore_report.cross_scenario_transfers
                    ],
                )

                # Phase 9-1: world snapshot も load (= 旧 snapshot dir に
                # world.json が無ければ no-op = 後方互換)。world snapshot は
                # scenario fail-fast 方針なので例外は素通し。
                world_snapshot = snapshot_session.restore_world_from_dir(
                    runtime,
                    snapshot_load_dir,
                    current_scenario=scenario_path.stem,
                )
                if world_snapshot is not None:
                    logger.info(
                        "restored world snapshot: source_scenario=%s "
                        "world_tick=%d subsystems=%s",
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
                            world_snapshot.subsystems.keys()
                        ),
                    )

        for pid in runtime.get_player_ids():
            state.llm_wiring.llm_turn_trigger.schedule_turn(pid)

        outcome = "TIMEOUT"
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
                logger.warning(
                    "SIGINT received; will stop tick loop and capture "
                    "snapshot before exit"
                )

            old = _signal.signal(_signal.SIGINT, _handler)
            try:
                yield
            finally:
                try:
                    _signal.signal(_signal.SIGINT, old)
                except Exception:
                    logger.warning(
                        "failed to restore SIGINT handler", exc_info=True
                    )
        with _sigint_to_flag_guard():
            # 各 player の前 tick の spot を保持して差分検出に使う
            prev_spots: Dict[int, Optional[str]] = {
                int(pid.value): runtime.get_player_spot_id(pid)
                for pid in runtime.get_player_ids()
            }
            # #404 P1: 外側ループを「world_tick が max_world_ticks に達するまで」に
            # 統一する。旧 ``for i in range(max_ticks)`` は外側 iteration 回数だった
            # ため、do_move のネスト advance_tick で world_tick が大量にジャンプすると
            # 「MAX_TICKS=140 なのに 14 日進まなかった」事象を生んでいた。
            # 安全弁: iteration 上限 = max_world_ticks * 2。仮に 1 iteration で
            # world_tick が進まないバグが入ってもループが暴走しないようにする。
            max_iterations = max(1, max_world_ticks * 2)
            i = 0
            while (
                runtime.current_tick() < max_world_ticks
                and i < max_iterations
                and not _interrupted["flag"]
            ):
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
                i += 1
            if _interrupted["flag"]:
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

        # Phase 6: snapshot save。**runtime.shutdown より前** に行う理由:
        # async LLM scheduler の drain が終わると episode_store に最後の
        # 主観文 episode が書き込まれる可能性があるが、その後に capture
        # すると snapshot 経路が ``shutdown=True`` の store を触る恐れがある。
        # 「shutdown 前の last consistent state」を写し取るのが安全。
        # 失敗しても run 自体は守る (= 例外を上位に飛ばさない)。
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
                    failures=[
                        {"being_id": b.value, "error": err}
                        for (b, err) in report.failed
                    ],
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
                captured_keys = (
                    snapshot_session.world_snapshot_service.registered_subsystem_keys
                )
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
            "max_world_ticks": max_world_ticks,
            "snapshot_save_dir": str(snapshot_save_dir) if snapshot_save_dir else None,
            "snapshot_load_dir": str(snapshot_load_dir) if snapshot_load_dir else None,
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
        f"- last tick: {summary['last_tick']} / max world ticks: {summary['max_world_ticks']}"
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
        default=None,
        help="Path to scenario JSON (e.g. data/scenarios/relay_puzzle_demo.json)",
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
        help=(
            "Stop when world_tick reaches this value (default 30, "
            "or experiment config max_world_ticks)"
        ),
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
    except (OSError, ValueError) as e:
        parser.error(str(e))

    scenario_arg = args.scenario
    if scenario_arg is None:
        raw_scenario = config_source.get("scenario")
        if raw_scenario:
            scenario_arg = Path(str(raw_scenario))
    if scenario_arg is None:
        parser.error(
            "scenario is required. Pass --scenario or set 'scenario' in the experiment config."
        )
    args.scenario = scenario_arg

    if not args.scenario.exists():
        parser.error(f"scenario not found: {args.scenario}")

    if args.max_world_ticks is None:
        if config_source.get("max_world_ticks") is not None:
            args.max_world_ticks = int(config_source["max_world_ticks"])
        else:
            args.max_world_ticks = int(
                "30"
            )

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
    print(
        f"[run] section_order={cfg.prompt_section_order} "
        "(runtime_config.PROMPT_SECTION_ORDER)",
        flush=True,
    )
    print(
        f"[run] episodic_explore_related={'on' if cfg.episodic_explore_related_enabled else 'off'} "
        "(runtime_config.EPISODIC_EXPLORE_RELATED_ENABLED)",
        flush=True,
    )
    print(
        f"[run] semantic_llm_gist={'on' if cfg.semantic_llm_gist_enabled else 'off'} "
        "(runtime_config.SEMANTIC_LLM_GIST_ENABLED)",
        flush=True,
    )
    print(
        f"[run] semantic_passive_top_k={cfg.semantic_passive_top_k} "
        "(runtime_config.SEMANTIC_PASSIVE_TOP_K)",
        flush=True,
    )
    print(
        f"[run] semantic_search={'on' if cfg.semantic_search_enabled else 'off'} "
        "(runtime_config.SEMANTIC_SEARCH_ENABLED)",
        flush=True,
    )
    print(
        f"[run] short_term_memory_kind={cfg.short_term_memory_kind} "
        "(runtime_config.SHORT_TERM_MEMORY_KIND)",
        flush=True,
    )
    print(
        f"[run] short_term_memory_scheduler_mode={cfg.short_term_memory_scheduler_mode} "
        "(runtime_config.SHORT_TERM_MEMORY_SCHEDULER_MODE)",
        flush=True,
    )
    # OpenRouter provider routing: 設定されているときだけ表示
    if cfg.openrouter_provider or cfg.openrouter_quantization or cfg.openrouter_require_params:
        print(
            f"[run] openrouter routing: provider={cfg.openrouter_provider or '-'} "
            f"quantization={cfg.openrouter_quantization or '-'} "
            f"require_params={'true' if cfg.openrouter_require_params else '-'}",
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
            progress_jsonl=(
                None if args.no_progress_jsonl else (out_dir / "progress.jsonl")
            ),
        )

        # Phase 6 (Issue #470): snapshot-load-dir が指定されていれば存在チェック。
        # 不在 dir で進めると "途中で読めない" が分かるのが load 後になり、
        # 既存 experiment data の汚染リスクが上がる。ここで早期 fail-fast。
        if args.snapshot_load_dir is not None and not args.snapshot_load_dir.exists():
            parser.error(
                f"snapshot-load-dir does not exist: {args.snapshot_load_dir}"
            )
        if args.snapshot_save_dir is not None:
            args.snapshot_save_dir.mkdir(parents=True, exist_ok=True)

        try:
            summary = _drive_scenario(
                scenario_path=args.scenario,
                max_world_ticks=args.max_world_ticks,
                recorder=rec,
                progress=progress,
                runtime_config=cfg,
                reporter=reporter,
                snapshot_save_dir=args.snapshot_save_dir,
                snapshot_load_dir=args.snapshot_load_dir,
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
