#!/usr/bin/env python3
"""
Issue #154 / #188 再実験: R1 / R2 / R3 を順に実走し、観測・tool_call を横断記録して表 A〜D を Markdown 生成する。

Issue #188 向け追加集計: recipient_position 分布、B の inner_thought 音関連語、
隣接音観測 tick、B の role 逸脱 tick。

Issue #190 向け追加集計: 自己三人称呼び（speech / inner_thought）、
tick=20 の A プロンプト 1 件サンプル。

前提:
  - `LLM_CLIENT=litellm`（未設定なら本スクリプトが設定）
  - SSH 越しに vLLM を使う例:
      ssh -N -L 8000:127.0.0.1:8000 user@remote
    `.env` に `OPENAI_API_BASE=http://127.0.0.1:8000/v1` と、`LLM_MODEL=openai/<vLLMのserved名>`。
    `OPENAI_API_KEY` は空でも可（OpenAI 互換ローカル向けプレースホルダ）。
  - それ以外ならクラウド用に `.env` に `OPENAI_API_KEY` 等。

環境変数:
  ISSUE154_MAX_TICKS  各試行の「外側」advance_tick 呼び出しの最大回数（既定 18）。
                      移動(do_move)や待機(do_wait)ツール内でさらに時刻が進むため、
                      表の tick 列はワールド時刻でありこの回数と一致しない。
  ISSUE154_RUNS      実行する試行キーをカンマ区切り（例: R1_default,R2_pure）。省略時は
                      「既定セット」(R1_default, R3_contention) のみ走る。R2_pure (memo OFF
                      アブレーション) は memo が既定路線になったので routine から外した。
                      使いたいときは明示的に `ISSUE154_RUNS=R2_pure` または含めて opt-in。
  LLM_TOOL_MODE      R1/R2 はスクリプトが上書き。手で固定したい場合は未指定でよい。
  LLM_MODEL          省略時はコード既定モデル。「openai/&lt;served-model-name&gt;」形式が vLLM で扱いやすいことが多い
  OPENAI_API_BASE    省略時は直 OpenAI API。`/v1` まで含めたベース URL（ローカルトンネル先 vLLM）

進捗は stderr に試行ラベル・駆動回数・world_tick を出す。

使い方:
  cd ai_rpg_world && source venv/bin/activate
  make experiment-relay          # 推奨（docs/running_scenarios.md 参照）
  python scripts/run_relay_puzzle_experiment.py -o var/issue154_report.md
  python scripts/issue154_full_tables_experiment.py -o var/issue154_report.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Dict, List, Optional, Tuple

_SOUND_KEYWORDS = ("音", "気配", "向こう", "動いた", "遠く", "金庫扉", "扉が")
_A_PLAYER_MARKERS = ("カイト", "A（オペレーター）", "player_a")
_B_PLAYER_MARKERS = ("リン", "B（侵入者）", "player_b", "B(")

# プロジェクトルートをパスに載せる（pytest 外でも動くように）
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ──────────────────────────────────────────────────────────────────
# 試行セット定義 (memo 既定路線化に伴う再編、Issue #295 後続)
#
# ALL_RUNS は「実装上選べる試行」の宣言集。``ISSUE154_RUNS`` 環境変数で
# 明示すればここから選ばれる。
# DEFAULT_RUN_KEYS は「環境変数未指定で routine 実行されるセット」。memo を
# 役に立つ既定路線として扱うため、memo OFF アブレーションの R2_pure は
# routine から外し、必要なときだけ ``ISSUE154_RUNS=R2_pure`` で opt-in する。
# ──────────────────────────────────────────────────────────────────
ALL_RUNS: dict = {
    "R1_default": ("relay_puzzle_demo", None),
    "R2_pure": ("relay_puzzle_demo", "pure_spot_graph"),
    "R3_contention": ("single_relic_contention_demo", None),
}
DEFAULT_RUN_KEYS: tuple = ("R1_default", "R3_contention")


def _select_runs(
    all_runs: dict,
    default_keys: tuple,
    filter_value: str,
) -> tuple[dict, str]:
    """``ISSUE154_RUNS`` 環境変数の値から実行する試行 dict と warning を返す。

    - filter_value が空: ``default_keys`` だけ走らせる
    - 含む: ``all_runs`` から該当キーだけ走らせる (opt-in)
    - 含むが全て不一致: default_keys にフォールバックし warning 返す
    """
    filter_value = filter_value.strip()
    if not filter_value:
        return {k: all_runs[k] for k in default_keys}, ""
    wanted = {k.strip() for k in filter_value.split(",") if k.strip()}
    selected = {k: v for k, v in all_runs.items() if k in wanted}
    if selected:
        return selected, ""
    return (
        {k: all_runs[k] for k in default_keys},
        f"ISSUE154_RUNS={filter_value!r} に一致する試行がありません。既定セットを実行します。",
    )


def _load_dotenv_safe() -> None:
    try:
        from dotenv import load_dotenv

        p = _ROOT / ".env"
        if p.is_file():
            load_dotenv(p)
    except Exception:
        pass


@dataclass
class Row:
    tick: int
    player: str
    event: str
    detail: str
    seq: int = 0


@dataclass
class RunStats:
    """G1〜G4 観察用の集計データ。"""
    label: str
    elapsed_sec: float = 0.0
    llm_invoke_count: int = 0
    game_end_result: str = "未完了"
    game_end_tick: Optional[int] = None
    # G3: relay_puzzle_demo 専用
    control_panel_found_tick: Optional[int] = None
    power_on_success_tick: Optional[int] = None
    door_latch_press_tick: Optional[int] = None
    # G4: TODO 系ツール使用回数
    todo_tool_count: int = 0
    # Issue #188: 位置ベース観測・B の状況認識
    recipient_position_counts: Counter[str] = field(default_factory=Counter)
    b_first_adjacent_sound_tick: Optional[int] = None
    b_first_sound_keyword_inner_thought_tick: Optional[int] = None
    b_role_deviation_ticks: List[int] = field(default_factory=list)
    b_sound_inner_thought_hits: List[Tuple[int, str]] = field(default_factory=list)
    adjacent_sound_observations: List[Tuple[int, str, str]] = field(default_factory=list)
    # Issue #190: 自己三人称呼び
    self_third_person_hits: List[Tuple[int, str, str, str]] = field(default_factory=list)
    prompt_sample_a_tick20: Optional[str] = None


@dataclass
class Transcript:
    rows: List[Row] = field(default_factory=list)
    _seq: int = 0

    def add(self, tick: int, player: str, event: str, detail: str) -> None:
        self._seq += 1
        self.rows.append(Row(tick, player, event, detail, seq=self._seq))


def _is_b_player(name: str) -> bool:
    return any(m in name for m in _B_PLAYER_MARKERS) or name.strip().startswith("B")


def _is_a_player(name: str) -> bool:
    return any(m in name for m in _A_PLAYER_MARKERS) or (
        name.strip().startswith("A") and "B" not in name[:3]
    )


def _self_third_person_tokens(player_name: str) -> Tuple[str, ...]:
    if _is_b_player(player_name):
        return ("リンさん", "リン、", "Bさん", "B（侵入者）")
    if _is_a_player(player_name):
        return ("カイトさん", "カイト、", "Aさん", "A（オペレーター）")
    return ()


def _note_self_third_person(
    stats: RunStats,
    tick: int,
    player_name: str,
    field: str,
    text: str,
) -> None:
    if not text:
        return
    for token in _self_third_person_tokens(player_name):
        if token in text:
            stats.self_third_person_hits.append((tick, player_name, field, text[:200]))
            return


def _extract_recent_events_from_messages(messages: Any) -> str:
    """user prompt から「直近の出来事」付近を抜き出す（なければ user 全文）。"""
    chunks: List[str] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "user":
            continue
        content = msg.get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        marker = "直近の出来事"
        if marker in content:
            idx = content.index(marker)
            chunks.append(content[idx : idx + 4000])
        else:
            chunks.append(content[:4000])
    return "\n---\n".join(chunks) if chunks else json.dumps(messages, ensure_ascii=False)[:8000]


def _extract_inner_thought(raw_args: Any) -> str:
    if isinstance(raw_args, dict):
        return str(raw_args.get("inner_thought") or "").strip()
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
            if isinstance(parsed, dict):
                return str(parsed.get("inner_thought") or "").strip()
        except json.JSONDecodeError:
            pass
    return ""


def _note_b_sound_inner_thought(stats: RunStats, tick: int, player_name: str, thought: str) -> None:
    if not thought or not _is_b_player(player_name):
        return
    if not any(k in thought for k in _SOUND_KEYWORDS):
        return
    stats.b_sound_inner_thought_hits.append((tick, thought[:180]))
    if stats.b_first_sound_keyword_inner_thought_tick is None:
        stats.b_first_sound_keyword_inner_thought_tick = tick


def _note_recipient_position(
    stats: RunStats,
    tick: int,
    player_name: str,
    st: dict[str, Any],
    prose: str,
) -> None:
    pos = st.get("recipient_position")
    if not pos:
        return
    stats.recipient_position_counts[str(pos)] += 1
    if pos != "adjacent" or not _is_b_player(player_name):
        return
    stats.adjacent_sound_observations.append((tick, player_name, prose[:200]))
    if stats.b_first_adjacent_sound_tick is None and "遠く" in prose:
        stats.b_first_adjacent_sound_tick = tick


def _install_hooks(
    runtime: Any,
    state: Any,
    transcript: Transcript,
    stats: RunStats,
    invoke_player_holder: List[Optional[Any]],
) -> None:
    buf = runtime._obs_buffer
    orig_append = buf.append

    def append_hook(
        player_id: Any,
        entry: Any,
        *,
        runtime_context: Any = None,
    ) -> None:
        tick = runtime.current_tick()
        nm = runtime.get_player_name(player_id)
        st = getattr(getattr(entry, "output"), "structured", None) or {}
        typ = st.get("type", "unknown")
        if typ == "action_failed":
            detail = (
                f"error_code={st.get('error_code')} tool_name={st.get('tool_name')}"
            )
        elif typ in ("heartbeat",):
            detail = f"tick_meta={st.get('tick')} interval={st.get('interval_ticks')}"
        elif typ == "player_spoke":
            detail = (entry.output.prose or "")[:220].replace("\n", " ")
        else:
            detail = (entry.output.prose or "")[:160].replace("\n", " ")
        _note_recipient_position(stats, tick, nm, st, entry.output.prose or "")
        transcript.add(tick, nm, f"observation:{typ}", detail)
        return orig_append(player_id, entry, runtime_context=runtime_context)

    buf.append = append_hook  # type: ignore[method-assign]

    wiring = state.llm_wiring
    orig_run = wiring.run_turn

    def run_turn_hook(pid: Any) -> Any:
        invoke_player_holder[0] = pid
        try:
            result = orig_run(pid)
            transcript.add(
                runtime.current_tick(),
                runtime.get_player_name(pid),
                "llm_turn_result",
                f"success={result.success} err={getattr(result, 'error_code', None)}"
                f" msg={(getattr(result, 'message', None) or '')[:100]}",
            )
            return result
        finally:
            invoke_player_holder[0] = None

    wiring.run_turn = run_turn_hook  # type: ignore[method-assign]

    client = wiring.llm_client
    orig_invoke = client.invoke

    _TODO_TOOL_PREFIXES = ("todo_", "create_todo", "update_todo", "list_todo", "delete_todo")

    def invoke_hook(
        messages: Any,
        tools: Any,
        tool_choice: str = "required",
    ) -> Any:
        tick = runtime.current_tick()
        pid = invoke_player_holder[0]
        nm = runtime.get_player_name(pid) if pid is not None else "?"
        if (
            stats.prompt_sample_a_tick20 is None
            and tick == 20
            and _is_a_player(nm)
        ):
            stats.prompt_sample_a_tick20 = _extract_recent_events_from_messages(messages)
        out = orig_invoke(messages, tools, tool_choice)
        stats.llm_invoke_count += 1
        if out:
            name = out.get("name", "?")
            raw_args = out.get("arguments", "")
            arg_short = raw_args if isinstance(raw_args, str) else json.dumps(
                raw_args, ensure_ascii=False
            )
            arg_short = arg_short[:200]
            transcript.add(tick, nm, "tool_call", f"{name} {arg_short}")
            thought = _extract_inner_thought(raw_args)
            _note_b_sound_inner_thought(stats, tick, nm, thought)
            _note_self_third_person(stats, tick, nm, "inner_thought", thought)
            if name == "speech_say":
                content = ""
                if isinstance(raw_args, dict):
                    content = str(raw_args.get("content") or "")
                elif isinstance(raw_args, str):
                    try:
                        parsed = json.loads(raw_args)
                        if isinstance(parsed, dict):
                            content = str(parsed.get("content") or "")
                    except json.JSONDecodeError:
                        pass
                _note_self_third_person(stats, tick, nm, "speech_content", content)
            if _is_b_player(nm) and name == "spot_graph_travel_to":
                low = arg_short.lower()
                if "control_room" in low or "制御室" in arg_short:
                    stats.b_role_deviation_ticks.append(tick)
            # G3: control_panel 発見（spot_graph_explore / interact の引数中）
            full_detail = f"{name} {arg_short}".lower()
            if "control_panel" in full_detail and stats.control_panel_found_tick is None:
                if name in ("spot_graph_explore", "spot_graph_interact", "spot_graph_travel_to"):
                    stats.control_panel_found_tick = tick
            # G3: power_on 成功（action_type=power_on / power_on ツール名）
            if "power_on" in full_detail and stats.power_on_success_tick is None:
                stats.power_on_success_tick = tick
            if (
                stats.door_latch_press_tick is None
                and name == "spot_graph_interact"
                and ("door_latch" in full_detail or "press" in full_detail or "扉固定" in arg_short)
            ):
                stats.door_latch_press_tick = tick
            # G4: TODO 系ツール
            if any(name.startswith(p) for p in _TODO_TOOL_PREFIXES) or "todo" in name.lower():
                stats.todo_tool_count += 1
        else:
            transcript.add(tick, nm, "tool_call", "(invoke returned None)")
        return out

    client.invoke = invoke_hook  # type: ignore[method-assign]


def _markdown_table_a(rows: List[Row]) -> str:
    lines = [
        "| tick | player | event | detail |",
        "|------|--------|-------|--------|",
    ]
    for r in sorted(rows, key=lambda x: (x.tick, x.seq)):
        d = r.detail.replace("|", "\\|")
        lines.append(f"| {r.tick} | {r.player} | {r.event} | {d} |")
    return "\n".join(lines)


def _markdown_table_b(run_labels: dict[str, Transcript]) -> str:
    """ツール名 -> 各試行の出現回数。"""
    from collections import Counter

    per_run: dict[str, Counter[str]] = {k: Counter() for k in run_labels}
    for label, tr in run_labels.items():
        for r in tr.rows:
            if r.event != "tool_call":
                continue
            detail = r.detail.strip()
            if detail.startswith("("):
                continue
            first = (detail.split(None, 1) or [""])[0]
            if first:
                per_run[label][first] += 1

    keys = list(run_labels.keys())
    all_tools = sorted(set().union(*(c.keys() for c in per_run.values())))
    header = "| tool | " + " | ".join(keys) + " |"
    sep = "|" + "|".join(["------"] * (1 + len(keys))) + "|"
    lines = [header, sep]
    for t in all_tools:
        cells = [t]
        for lb in keys:
            cells.append(str(per_run[lb].get(t, 0)))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _markdown_section_g1(all_stats: List[RunStats]) -> str:
    """G1: 各試行のゲーム終了結果と完了 tick。"""
    lines = [
        "| 試行 | 結果 | 終了 tick | 経過時間 (s) |",
        "|------|------|-----------|-------------|",
    ]
    for s in all_stats:
        tick_str = str(s.game_end_tick) if s.game_end_tick is not None else "—"
        lines.append(
            f"| {s.label} | {s.game_end_result} | {tick_str} | {s.elapsed_sec:.1f} |"
        )
    return "\n".join(lines)


def _markdown_section_g2(all_stats: List[RunStats]) -> str:
    """G2: LLM 呼び出し総数と所要時間の試行間比較。"""
    lines = [
        "| 試行 | LLM 呼び出し総数 | 所要時間 (s) | 呼び出し/分 |",
        "|------|----------------|-------------|------------|",
    ]
    for s in all_stats:
        rate = (s.llm_invoke_count / s.elapsed_sec * 60) if s.elapsed_sec > 0 else 0
        lines.append(
            f"| {s.label} | {s.llm_invoke_count} | {s.elapsed_sec:.1f} | {rate:.1f} |"
        )
    return "\n".join(lines)


def _markdown_section_g3(all_stats: List[RunStats]) -> str:
    """G3: relay_puzzle_demo での control_panel 発見 tick と power_on 成功 tick。"""
    relay_stats = [s for s in all_stats if "R1" in s.label or "R2" in s.label]
    if not relay_stats:
        return "_G3: relay_puzzle_demo 試行（R1/R2）が見つかりませんでした。_"
    lines = [
        "| 試行 | control_panel 発見 tick | power_on 成功 tick | 扉固定スイッチ tick |",
        "|------|------------------------|-------------------|---------------------|",
    ]
    for s in relay_stats:
        cp = str(s.control_panel_found_tick) if s.control_panel_found_tick is not None else "未発見"
        po = str(s.power_on_success_tick) if s.power_on_success_tick is not None else "未実行"
        latch = str(s.door_latch_press_tick) if s.door_latch_press_tick is not None else "未実行"
        lines.append(f"| {s.label} | {cp} | {po} | {latch} |")
    return "\n".join(lines)


def _markdown_section_issue188(all_stats: List[RunStats]) -> str:
    """Issue #188: 位置ベース観測・B の音認識・role 逸脱。"""
    relay_stats = [s for s in all_stats if "R1" in s.label or "R2" in s.label]
    if not relay_stats:
        return "_Issue #188: relay_puzzle 試行がありません。_"
    lines: List[str] = []
    for s in relay_stats:
        lines.append(f"### {s.label}\n")
        lines.append("| 指標 | 値 |")
        lines.append("|------|-----|")
        lines.append(
            f"| B 初回 adjacent 音観測 tick | "
            f"{s.b_first_adjacent_sound_tick if s.b_first_adjacent_sound_tick is not None else '—'} |"
        )
        lines.append(
            f"| B 初回音関連 inner_thought tick | "
            f"{s.b_first_sound_keyword_inner_thought_tick if s.b_first_sound_keyword_inner_thought_tick is not None else '—'} |"
        )
        dev = ", ".join(str(t) for t in s.b_role_deviation_ticks) or "—"
        lines.append(f"| B role 逸脱 tick (制御室へ travel) | {dev} |")
        rp = ", ".join(f"{k}={v}" for k, v in sorted(s.recipient_position_counts.items())) or "—"
        lines.append(f"| recipient_position 分布 | {rp} |")
        lines.append("")
        if s.adjacent_sound_observations:
            lines.append("**adjacent 音観測 (B 含む全件):**")
            for tick, pn, prose in s.adjacent_sound_observations[:12]:
                lines.append(f"- tick={tick} **{pn}**: {prose}")
            lines.append("")
        if s.b_sound_inner_thought_hits:
            lines.append("**B の音関連 inner_thought:**")
            for tick, thought in s.b_sound_inner_thought_hits[:12]:
                lines.append(f"- tick={tick}: {thought}")
            lines.append("")
    return "\n".join(lines)


def _markdown_section_issue190(all_stats: List[RunStats]) -> str:
    """Issue #190: 自己三人称呼び・プロンプトサンプル。"""
    relay_stats = [s for s in all_stats if "R1" in s.label or "R2" in s.label]
    if not relay_stats:
        return "_Issue #190: relay_puzzle 試行がありません。_"
    lines: List[str] = []
    for s in relay_stats:
        lines.append(f"### {s.label}\n")
        lines.append(f"- **自己三人称呼び出現数**: {len(s.self_third_person_hits)}")
        if s.self_third_person_hits:
            lines.append("\n**検出例（最大12件）:**")
            for tick, pn, fld, snippet in s.self_third_person_hits[:12]:
                lines.append(f"- tick={tick} **{pn}** ({fld}): {snippet}")
        else:
            lines.append("- （検出なし）")
        lines.append("")
        if s.prompt_sample_a_tick20 and "R1" in s.label:
            lines.append("**tick=20 A プロンプト（直近の出来事セクション）:**")
            lines.append("```")
            lines.append(s.prompt_sample_a_tick20[:6000])
            lines.append("```")
            lines.append("")
    return "\n".join(lines)


def _markdown_section_g4(all_stats: List[RunStats]) -> str:
    """G4: R1/R2 の TODO 系ツール使用回数。"""
    relay_stats = [s for s in all_stats if "R1" in s.label or "R2" in s.label]
    if not relay_stats:
        return "_G4: R1/R2 試行が見つかりませんでした。_"
    lines = [
        "| 試行 | TODO 系ツール呼び出し回数 |",
        "|------|------------------------|",
    ]
    for s in relay_stats:
        lines.append(f"| {s.label} | {s.todo_tool_count} |")
    return "\n".join(lines)


def _markdown_section_c(rows: List[Row], label: str) -> str:
    """action_failed の次イベント（同一 player）をざっくり列挙。"""
    out: List[str] = []
    sorted_rows = sorted(rows, key=lambda x: (x.tick, x.seq))
    for i, r in enumerate(sorted_rows):
        if r.event != "observation:action_failed":
            continue
        next_ev = None
        for r2 in sorted_rows[i + 1 :]:
            if r2.player != r.player or r2.seq <= r.seq:
                continue
            if r2.event == "tool_call":
                next_ev = r2
                break
            if r2.event == "llm_turn_result" and next_ev is None:
                next_ev = r2
        out.append(
            f"- **{r.player}** tick={r.tick}: {r.detail}"
            + (f" → next: `{next_ev.event}` {next_ev.detail[:120]}" if next_ev else " → (以降同一プレイヤーの即時応答なし)")
        )
    if not out:
        return f"_{label}: action_failed 観測は記録されませんでした。_"
    return "\n".join(out)


def _markdown_section_d(rows: List[Row]) -> str:
    speech: List[str] = []
    for r in sorted(rows, key=lambda x: (x.tick, x.seq)):
        if r.event == "observation:player_spoke" or "speech" in r.event:
            speech.append(f"- [tick {r.tick}] **{r.player}**: {r.detail}")
        elif r.event == "tool_call" and r.detail.startswith("speech_"):
            speech.append(f"- [tick {r.tick}] **{r.player}** tool: {r.detail[:180]}")
    if not speech:
        return "_speech / player_spoke 系の行はありませんでした。_"
    return "\n".join(speech)


def _run_one(
    *,
    label: str,
    world_id: str,
    max_ticks: int,
    tool_mode: Optional[str],
    scenarios_dir: Path,
    progress: Callable[[str], None],
) -> tuple[Transcript, RunStats]:
    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
        GameRuntimeManager,
    )
    from ai_rpg_world.presentation.spot_graph_game.schemas import (
        CharacterCreateRequest,
        SessionCreateRequest,
    )

    if tool_mode is None:
        os.environ.pop("LLM_TOOL_MODE", None)
    else:
        os.environ["LLM_TOOL_MODE"] = tool_mode

    os.environ.setdefault("LLM_CLIENT", "litellm")
    os.environ["SPOT_GRAPH_TICK_LOOP_ENABLED"] = "false"

    tr = Transcript()
    stats = RunStats(label=label)
    holder: List[Optional[Any]] = [None]

    with TemporaryDirectory() as d:
        chars = Path(d) / "characters.json"
        mgr = GameRuntimeManager(scenarios_dir=scenarios_dir, characters_path=chars)
        char = mgr.create_character(
            CharacterCreateRequest(name=f"Issue154-{label}キャラ")
        )
        summary = mgr.create_session(
            SessionCreateRequest(world_id=world_id, character_ids=[char.id])
        )
        state = mgr._sessions[summary.session_id]
        runtime = state.runtime
        _install_hooks(runtime, state, tr, stats, holder)

        # 初回から LLM が動くよう両者スケジュール
        for pid in runtime.get_player_ids():
            state.llm_wiring.llm_turn_trigger.schedule_turn(pid)

        t0 = time.monotonic()
        for i in range(max_ticks):
            w0 = runtime.current_tick()
            progress(
                f"{label}: 駆動 {i + 1}/{max_ticks} world_tick={w0} "
                f"(elapsed {time.monotonic() - t0:.0f}s)"
            )
            runtime.advance_tick()
            w1 = runtime.current_tick()
            progress(f"{label}:  → 駆動後 world_tick={w1}")
            end_check = runtime.check_game_end()
            if end_check.is_ended:
                # G1: 終了結果を記録
                result_raw = getattr(end_check, "result", None)
                if result_raw is not None:
                    stats.game_end_result = str(result_raw)
                else:
                    stats.game_end_result = "ended"
                stats.game_end_tick = runtime.current_tick()
                progress(
                    f"{label}: ゲーム終了検出 → ループ打ち切り "
                    f"result={stats.game_end_result} (world_tick={stats.game_end_tick})"
                )
                break
        stats.elapsed_sec = time.monotonic() - t0
        progress(
            f"{label}: 完了。経過 {stats.elapsed_sec:.1f}s。"
            f"行数 {len(tr.rows)} llm_invoke={stats.llm_invoke_count}"
        )

    return tr, stats


def main() -> int:
    _load_dotenv_safe()
    from ai_rpg_world.infrastructure.llm.litellm_client import DEFAULT_LLM_MODEL

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Markdown を書き出すパス（省略時は var/issue154_full_tables.md）",
    )
    args = ap.parse_args()

    out_path = args.output or (_ROOT / "var" / "issue154_full_tables.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    max_ticks = int(os.environ.get("ISSUE154_MAX_TICKS", "18"))
    scenarios_dir = _ROOT / "data" / "scenarios"

    def progress(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)

    llm_base = ((os.environ.get("OPENAI_API_BASE") or "").strip())
    llm_route = (
        "vLLM/OpenAI-compat (OPENAI_API_BASE set)"
        if llm_base
        else "OPENAI_API_BASE unset (cloud/direct)"
    )
    progress(
        "=== Issue #154 実験開始 "
        f"max_ticks={max_ticks} backend=litellm route={llm_route} "
        f"OPENAI_API_BASE={'set' if llm_base else 'unset'} ==="
    )

    runs, warning = _select_runs(ALL_RUNS, DEFAULT_RUN_KEYS, os.environ.get("ISSUE154_RUNS") or "")
    if warning:
        progress(warning)

    transcripts: dict[str, Transcript] = {}
    all_stats: List[RunStats] = []
    for key, (wid, mode) in runs.items():
        progress(f"--- 試行 {key} world={wid} LLM_TOOL_MODE={mode!r} ---")
        tr, st = _run_one(
            label=key,
            world_id=wid,
            max_ticks=max_ticks,
            tool_mode=mode,
            scenarios_dir=scenarios_dir,
            progress=progress,
        )
        transcripts[key] = tr
        all_stats.append(st)

    # Markdown 組み立て
    parts: List[str] = []
    parts.append("# Issue #154 再実験フル表（自動採取）\n")
    parts.append(
        f"- 各試行の**外側**シミュレーション駆動回数: **{max_ticks}**（`ISSUE154_MAX_TICKS`）。\n"
        "  表の **tick** はワールド時刻。`do_move` / `do_wait` 等が内部でさらに `advance_tick` するため、"
        "tick の最大値は駆動回数より大きくなり得る。\n"
    )
    parts.append(f"- scenarios: `{scenarios_dir}`\n")
    _model_env = (os.environ.get("LLM_MODEL") or "").strip()
    resolved_model = _model_env or DEFAULT_LLM_MODEL
    parts.append(f"- OPENAI_API_BASE: **{'configured' if llm_base else 'not configured'}**\n")
    parts.append(
        f"- LLM_MODEL: **`{resolved_model}`**"
        + ("" if _model_env else "（環境変数未設定のため liteLLM 既定文字列が送られる）")
        + "\n\n"
    )

    # G1〜G4 サマリーセクション（冒頭に配置）
    parts.append("## G1 — ゲーム終了結果サマリー\n\n")
    parts.append(_markdown_section_g1(all_stats))
    parts.append("\n\n")

    parts.append("## G2 — LLM 呼び出し数・所要時間（試行間比較）\n\n")
    parts.append(_markdown_section_g2(all_stats))
    parts.append("\n\n")

    parts.append("## G3 — control_panel 発見・power_on 成功 tick（relay_puzzle_demo）\n\n")
    parts.append(_markdown_section_g3(all_stats))
    parts.append("\n\n")

    parts.append("## G4 — TODO 系ツール使用回数（R1/R2）\n\n")
    parts.append(_markdown_section_g4(all_stats))
    parts.append("\n\n")

    parts.append("## Issue #188 — 位置ベース観測・B の音認識\n\n")
    parts.append(_markdown_section_issue188(all_stats))
    parts.append("\n\n")

    parts.append("## Issue #190 — 自己三人称呼び・プロンプトサンプル\n\n")
    parts.append(_markdown_section_issue190(all_stats))
    parts.append("\n\n")

    for key, tr in transcripts.items():
        parts.append(f"## 表 A — タイムライン ({key})\n\n")
        parts.append(_markdown_table_a(tr.rows))
        parts.append("\n\n")
        parts.append(f"### C — action_failed → 次応答 ({key})\n\n")
        parts.append(_markdown_section_c(tr.rows, key))
        parts.append("\n\n")
        parts.append(f"### D — speech / 発話 ({key})\n\n")
        parts.append(_markdown_section_d(tr.rows))
        parts.append("\n\n")

    parts.append("## 表 B — ツール呼び出し集計（試行間比較）\n\n")
    sub = transcripts
    parts.append(_markdown_table_b(sub))
    parts.append("\n")

    text = "".join(parts)
    out_path.write_text(text, encoding="utf-8")
    progress(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
