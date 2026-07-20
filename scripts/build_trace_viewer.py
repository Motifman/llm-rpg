#!/usr/bin/env python3
"""trace + scenario から self-contained viewer HTML を生成する (Phase 1d β)。

PR α (#214) で trace に ``position_change`` event が乗るようになったので、
それを起点に空間 + event log を見せる viewer を作る。

主な表示:
    - Cytoscape.js を inline 埋め込み (vendor ファイルを HTML に直書き)
    - scenario.json の spot graph topology からマップを描画
    - 時間軸に沿ってプレイヤー位置を再生
    - tick scrub bar
    - tick 別 event log
    - category filter 付き Event timeline
    - 折りたたみ式 memo state パネル

使い方::

    python scripts/build_trace_viewer.py var/runs/exp11_r1/
        → var/runs/exp11_r1/viewer.html を出力

設計判断:
    - 単一 HTML ファイル出力 (外部リソースゼロ) → gist + htmlpreview で動く
    - viewer は read-only の事後分析 UI (実行ではなく振り返り)
    - scenario.json が無くても trace.jsonl 単体で動く (map なしで event log のみ)
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import sys
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (_REPO_ROOT, _REPO_ROOT / "src"):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from ai_rpg_world.application.trace.events import TraceEvent, TraceEventKind  # noqa: E402
from ai_rpg_world.application.trace.recorder import load_trace_events  # noqa: E402

from scripts._viewer_vendor import fetch_cytoscape  # noqa: E402

logger = logging.getLogger("build_trace_viewer")


# ---------------------------------------------------------------------------
# データ抽出ロジック
# ---------------------------------------------------------------------------


def load_scenario_topology(scenario_path: Path) -> Dict[str, Any]:
    """scenario.json から viewer 描画に必要な spot graph topology を抽出。

    Returns:
        ``{"spots": [{"id": ..., "name": ...}], "connections": [{"from": ..., "to": ...}]}``
        scenario の structure が想定外なら空の topology。
    """
    if not scenario_path.exists():
        logger.info("scenario file not present: %s (map disabled)", scenario_path)
        return {"spots": [], "connections": []}
    try:
        data = json.loads(scenario_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("failed to parse scenario JSON: %s", e)
        return {"spots": [], "connections": []}

    # シナリオ JSON は 2 つの構造を許容:
    #  - top-level: {"spots": [...], "connections": [...]} (現行 data/scenarios/*.json)
    #  - 旧/将来案: {"spot_graph": {"spots": [...], "connections": [...]}}
    spot_graph = data.get("spot_graph") or {}
    spots_raw = data.get("spots") or spot_graph.get("spots") or []
    connections_raw = data.get("connections") or spot_graph.get("connections") or []

    spots: List[Dict[str, Any]] = []
    for s in spots_raw:
        sid = s.get("id")
        if sid is None:
            continue
        spots.append(
            {
                "id": str(sid),
                "name": str(s.get("name") or sid),
            }
        )

    connections: List[Dict[str, Any]] = []
    for c in connections_raw:
        src = c.get("from_spot_id") or c.get("from")
        dst = c.get("to_spot_id") or c.get("to")
        if src is None or dst is None:
            continue
        connections.append(
            {
                "from": str(src),
                "to": str(dst),
                "bidirectional": bool(c.get("is_bidirectional", False)),
            }
        )
    return {"spots": spots, "connections": connections}


def collect_players(
    events: List[TraceEvent],
    *,
    spot_name_to_id: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """trace から登場プレイヤー一覧 (id + 名前 + 最終位置) を抽出。

    Args:
        events: trace events
        spot_name_to_id: scenario の {spot_name: spot_id} 逆引きマップ。
            trace の ``to_spot_id`` が scenario の ``id`` と一致しない場合に
            ``spot_name`` を介してマップする (例: 内部数値 id vs シナリオ
            文字列 id の不一致)。
    """
    name_map = spot_name_to_id or {}
    names: Dict[int, str] = {}
    final_position: Dict[int, str] = {}
    final_position_name: Dict[int, str] = {}
    for e in events:
        if e.player_id is None:
            continue
        if isinstance(e.payload, dict):
            pname = e.payload.get("player_name")
            if pname:
                names.setdefault(e.player_id, str(pname))
            if e.kind == TraceEventKind.POSITION_CHANGE:
                to_spot = e.payload.get("to_spot_id")
                spot_name = e.payload.get("spot_name")
                # scenario id と trace id が違う場合、spot_name 経由で
                # scenario id を解決する。一致するものが無ければ raw 値を保持
                resolved = None
                if spot_name and spot_name in name_map:
                    resolved = name_map[spot_name]
                if resolved is None and to_spot is not None:
                    resolved = str(to_spot)
                if resolved is not None:
                    final_position[e.player_id] = resolved
                if spot_name is not None:
                    final_position_name[e.player_id] = str(spot_name)
    players: List[Dict[str, Any]] = []
    for pid in sorted({e.player_id for e in events if e.player_id is not None}):
        players.append(
            {
                "id": int(pid),
                "name": names.get(pid, f"player_{pid}"),
                "final_spot_id": final_position.get(pid),
                "final_spot_name": final_position_name.get(pid),
            }
        )
    return players


# Event timeline で表示しないノイズ系 kind (実験 #26 user フィードバック)。
# prompt_section_breakdown と llm_call は性能計測用で人間視点では本筋を埋もれ
# させるため、UI のイベントログからは除外する (trace.jsonl 自体には残る)。
_EVENT_TIMELINE_HIDDEN_KINDS = frozenset({
    "prompt_section_breakdown",
    "llm_call",
})

_EVENT_FILTER_CATEGORIES: tuple[tuple[str, str, bool], ...] = (
    ("speech", "発言", True),
    ("action", "行動", True),
    ("action_result", "行動結果", True),
    ("observation", "重要観測", True),
    ("failure", "失敗", True),
    ("memo", "メモ", False),
    ("recall", "記憶想起", False),
    ("belief", "信念", False),
    ("goal", "目的", False),
    ("system", "システム", False),
    ("other", "その他", False),
)


def group_events_by_tick(
    events: List[TraceEvent],
    *,
    hide_metrics_kinds: bool = True,
    dedupe_observations: bool = True,
) -> "OrderedDict[Optional[int], List[TraceEvent]]":
    """event を tick 順にグルーピング。

    Args:
        hide_metrics_kinds: True で性能計測系 (llm_call / prompt_section_breakdown)
            を timeline から除外。
        dedupe_observations: True で同 tick / 同 prose / 同 structured type の
            observation を最初の 1 件だけ残す (= 4 player にブロードキャストされた
            同一 prose が 4 連続並ぶのを抑える)。
    """
    by_tick: "OrderedDict[Optional[int], List[TraceEvent]]" = OrderedDict()
    # dedup key: (tick, prose, observation_type)
    seen_obs: set = set()
    speech_obs_index: dict[tuple[Any, ...], tuple[Optional[int], int]] = {}
    for e in events:
        if hide_metrics_kinds and e.kind in _EVENT_TIMELINE_HIDDEN_KINDS:
            continue
        if dedupe_observations and e.kind == "observation":
            payload = e.payload if isinstance(e.payload, dict) else {}
            structured = payload.get("structured") or {}
            obs_type = structured.get("type") if isinstance(structured, dict) else None
            if obs_type == "player_spoke" and isinstance(structured, dict):
                speech_key = (
                    e.tick,
                    structured.get("speaker_player_id"),
                    structured.get("speaker"),
                    structured.get("channel"),
                    structured.get("content"),
                )
                recipient = e.player_id
                recipient_info = {
                    "player_id": recipient,
                    "sound_clarity": structured.get("sound_clarity"),
                    "source_connection_name": structured.get("source_connection_name"),
                }
                if speech_key in speech_obs_index:
                    tick_key, row_idx = speech_obs_index[speech_key]
                    existing = by_tick[tick_key][row_idx]
                    existing_payload = dict(existing.payload)
                    recipients = list(existing_payload.get("_viewer_recipients") or [])
                    if recipient is not None and not any(
                        isinstance(r, dict)
                        and r.get("player_id") == recipient
                        and r.get("sound_clarity") == recipient_info["sound_clarity"]
                        and r.get("source_connection_name")
                        == recipient_info["source_connection_name"]
                        for r in recipients
                    ):
                        recipients.append(recipient_info)
                    existing_payload["_viewer_recipients"] = recipients
                    by_tick[tick_key][row_idx] = replace(
                        existing, payload=existing_payload
                    )
                    continue
                new_payload = dict(payload)
                new_payload["_viewer_recipients"] = (
                    [recipient_info] if recipient is not None else []
                )
                e = replace(e, payload=new_payload)
                by_tick.setdefault(e.tick, []).append(e)
                speech_obs_index[speech_key] = (e.tick, len(by_tick[e.tick]) - 1)
                continue
            prose = payload.get("prose") or ""
            key = (e.tick, prose, obs_type)
            if key in seen_obs:
                continue
            seen_obs.add(key)
        by_tick.setdefault(e.tick, []).append(e)
    return by_tick


def build_position_timeline(
    events: List[TraceEvent],
    *,
    spot_name_to_id: Optional[Dict[str, str]] = None,
) -> Dict[int, Dict[int, str]]:
    """tick → {player_id: spot_id} のスナップショットを構築 (PR γ playback 用)。

    各 tick の終わり時点での各プレイヤーの居場所を保持。tick が抜けている
    (位置変化なし) 場合は前 tick の値が続く前提なので、出てきた tick のみ
    記録すれば JS 側で前進補間できる。
    """
    name_map = spot_name_to_id or {}
    timeline: Dict[int, Dict[int, str]] = {}
    current: Dict[int, str] = {}
    sorted_events = sorted(events, key=lambda e: e.seq)
    for e in sorted_events:
        if e.kind != TraceEventKind.POSITION_CHANGE:
            continue
        if e.player_id is None or not isinstance(e.payload, dict):
            continue
        spot_name = e.payload.get("spot_name")
        to_spot = e.payload.get("to_spot_id")
        resolved = None
        if spot_name and spot_name in name_map:
            resolved = name_map[spot_name]
        if resolved is None and to_spot is not None:
            resolved = str(to_spot)
        if resolved is None:
            continue
        current[int(e.player_id)] = resolved
        tick = e.tick if e.tick is not None else 0
        timeline[tick] = dict(current)
    return timeline


def build_memo_state_timeline(
    events: List[TraceEvent],
) -> Dict[int, List[Dict[str, Any]]]:
    """tick → 各 memo の状態 list (PR γ memo panel 用)。

    Returns:
        ``{tick: [{memo_id, content, player_id, added_tick, status, done_tick?}]}``
        status は ``"active"`` / ``"done"``。
    """
    timeline: Dict[int, List[Dict[str, Any]]] = {}
    memos: Dict[str, Dict[str, Any]] = {}
    sorted_events = sorted(events, key=lambda e: e.seq)
    for e in sorted_events:
        if not isinstance(e.payload, dict):
            continue
        tick = e.tick if e.tick is not None else 0
        if e.kind == TraceEventKind.MEMO_ADD:
            memo_id = str(e.payload.get("memo_id") or "")
            if memo_id:
                memos[memo_id] = {
                    "memo_id": memo_id,
                    "content": str(e.payload.get("content") or ""),
                    "player_id": e.player_id,
                    "added_tick": tick,
                    "status": "active",
                }
        elif e.kind == TraceEventKind.MEMO_DONE:
            memo_id = str(e.payload.get("memo_id") or "")
            if memo_id in memos:
                memos[memo_id] = dict(memos[memo_id])
                memos[memo_id]["status"] = "done"
                memos[memo_id]["done_tick"] = tick
        # snapshot at this tick
        timeline[tick] = [dict(m) for m in memos.values()]
    return timeline


def compute_event_heatmap(
    events: List[TraceEvent],
) -> Dict[str, List[int]]:
    """kind 種別ごとに tick→件数 の配列を返す (PR γ heatmap 用)。

    Returns:
        ``{"ticks": [0, 1, ...], "action": [n0, n1, ...], "observation": [...], "memo": [...]}``
        memo は memo_add/done/hint をまとめてカウント。
    """
    max_tick = max((e.tick for e in events if e.tick is not None), default=0)
    ticks = list(range(0, max_tick + 1))
    series: Dict[str, List[int]] = {
        "ticks": ticks,
        "action": [0] * len(ticks),
        "observation": [0] * len(ticks),
        "memo": [0] * len(ticks),
        "position_change": [0] * len(ticks),
    }
    for e in events:
        if e.tick is None or e.tick < 0 or e.tick >= len(ticks):
            continue
        if e.kind == TraceEventKind.ACTION:
            series["action"][e.tick] += 1
        elif e.kind == TraceEventKind.OBSERVATION:
            series["observation"][e.tick] += 1
        elif e.kind in (
            TraceEventKind.MEMO_ADD,
            TraceEventKind.MEMO_DONE,
            TraceEventKind.MEMO_HINT,
        ):
            series["memo"][e.tick] += 1
        elif e.kind == TraceEventKind.POSITION_CHANGE:
            series["position_change"][e.tick] += 1
    return series


def build_speech_timeline(
    events: List[TraceEvent],
    *,
    bubble_persistence: int = 1,
    max_chars: int = 100,
) -> Dict[int, List[Dict[str, Any]]]:
    """tick → 各 player が「いま喋っている / 考えている」bubble の list (PR η)。

    speech 系ツール (``speech_say`` / ``speech_whisper`` / ``say``) と
    action.arguments.inner_thought をそれぞれ拾い、発生 tick + 続く
    ``bubble_persistence - 1`` tick の間、map に表示する。
    同じ player が次の発言を出したら上書き (旧 bubble は消える)。

    Args:
        events: trace events
        bubble_persistence: 表示継続 tick 数 (既定 2 = 発生 tick + 次 1 tick)
        max_chars: bubble に表示する最大文字数 (超えたら truncate + "…")

    Returns:
        ``{tick: [{player_id, kind ("speech"|"thought"), text, source_tick}]}``
        kind="speech" は実線吹き出し、"thought" は破線雲型として描画される想定。
    """
    # 各 player の「現在 active な bubble (kind 別)」を追跡
    # active_bubbles[player_id][kind] = {text, source_tick, expires_at}
    active: Dict[int, Dict[str, Dict[str, Any]]] = {}
    sorted_events = sorted(events, key=lambda e: e.seq)

    def _trim(s: str) -> str:
        if len(s) <= max_chars:
            return s
        return s[: max(0, max_chars - 1)] + "…"

    # 1 pass で「発生 tick で発火 → expires_at = tick + persistence - 1」を構築
    # 同 player の同 kind に対し、新しい bubble は古いものを置き換える
    raw_bubbles: List[Dict[str, Any]] = []  # 時系列の bubble 発生記録
    for e in sorted_events:
        if e.kind != TraceEventKind.ACTION:
            continue
        if e.player_id is None or not isinstance(e.payload, dict):
            continue
        tick = e.tick if e.tick is not None else 0
        tool = str(e.payload.get("tool") or "")
        arguments = e.payload.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}

        # speech 系ツール (公開発言)
        is_speech = (
            tool in ("say", "whisper")
            or tool.startswith("speech_")
        )
        if is_speech:
            message = (
                arguments.get("message")
                or arguments.get("content")
                or arguments.get("text")
                or ""
            )
            if message:
                raw_bubbles.append(
                    {
                        "player_id": int(e.player_id),
                        "kind": "speech",
                        "text": _trim(str(message).strip()),
                        "source_tick": tick,
                        "tool": tool,
                    }
                )

        # inner_thought (action.arguments.inner_thought)
        inner = arguments.get("inner_thought")
        if isinstance(inner, str) and inner.strip():
            raw_bubbles.append(
                {
                    "player_id": int(e.player_id),
                    "kind": "thought",
                    "text": _trim(inner.strip()),
                    "source_tick": tick,
                    "tool": tool,
                }
            )

    # 各 (player, kind) について、source_tick から persistence tick 表示
    # 同 (player, kind) の次の bubble は前の bubble を上書き (overlap しない)
    timeline: Dict[int, List[Dict[str, Any]]] = {}
    # bubble ごとに表示終了 tick を計算: 次の同 (player, kind) の発生 tick - 1
    # ただし persistence で打ち切られる
    by_key: Dict[tuple, List[Dict[str, Any]]] = {}
    for b in raw_bubbles:
        by_key.setdefault((b["player_id"], b["kind"]), []).append(b)
    for key, bubbles in by_key.items():
        for i, b in enumerate(bubbles):
            start = b["source_tick"]
            natural_end = start + bubble_persistence - 1
            next_start = (
                bubbles[i + 1]["source_tick"] - 1 if i + 1 < len(bubbles) else natural_end
            )
            end_tick = min(natural_end, next_start)
            for t in range(start, end_tick + 1):
                timeline.setdefault(t, []).append(b)
    return timeline


def compute_trace_moments(
    events: List[TraceEvent],
) -> List[Dict[str, Any]]:
    """trace の中から「振り返って見てほしい瞬間」を自動検出してマーカー化する。

    Returns:
        ``[{tick, kind, label, detail, score, player_id}, ...]`` の list。
        tick 昇順 (同 tick 内は seq 順)。Trace navigator の moment rail で
        マーカーとして配置され、クリックで該当 tick にジャンプできる。

    kind 区分 (CSS で枠色が異なる):
        - ``start``: trace 開始 (常に t=0 で 1 件)
        - ``end``: WIN/LOSE 確定 (RUN_END で 1 件)
        - ``memo``: memo_add (戦略の決定)
        - ``memo_done``: memo_done (達成 / 撤回)
        - ``hint``: memo_hint (fuzzy match 発火)
        - ``failed``: action_result.success=false (失敗、要分析)
        - ``move``: position_change (spot 跨ぎ。初期配置は除外)
        - ``result``: 重要な success result (現状は heuristic、key fields に
          ``true``/``OPEN`` などが含まれる場合)

    score: 優先度 (0-100)。長尺 trace で上位 N 件だけ拾うために将来使う。
    """
    moments: List[Dict[str, Any]] = []
    max_tick = 0
    for e in sorted(events, key=lambda x: x.seq):
        if e.tick is not None and e.tick > max_tick:
            max_tick = e.tick
        payload = e.payload if isinstance(e.payload, dict) else {}
        if e.kind == TraceEventKind.RUN_START:
            moments.append(
                {
                    "tick": 0,
                    "kind": "start",
                    "label": "START",
                    "detail": "trace begins",
                    "score": 100,
                    "player_id": None,
                }
            )
        elif e.kind == TraceEventKind.RUN_END:
            outcome = str(payload.get("outcome") or "END")
            moments.append(
                {
                    "tick": max_tick if e.tick is None else int(e.tick),
                    "kind": "end",
                    "label": outcome.upper(),
                    "detail": "trace finished",
                    "score": 100,
                    "player_id": None,
                }
            )
        elif e.kind == TraceEventKind.MEMO_ADD:
            moments.append(
                {
                    "tick": int(e.tick or 0),
                    "kind": "memo",
                    "label": "memo added",
                    "detail": str(payload.get("content") or ""),
                    "score": 65,
                    "player_id": e.player_id,
                }
            )
        elif e.kind == TraceEventKind.MEMO_DONE:
            moments.append(
                {
                    "tick": int(e.tick or 0),
                    "kind": "memo_done",
                    "label": "memo done",
                    "detail": str(payload.get("memo_id") or ""),
                    "score": 78,
                    "player_id": e.player_id,
                }
            )
        elif e.kind == TraceEventKind.MEMO_HINT:
            moments.append(
                {
                    "tick": int(e.tick or 0),
                    "kind": "hint",
                    "label": "memo hint",
                    "detail": str(payload.get("memo_id") or ""),
                    "score": 58,
                    "player_id": e.player_id,
                }
            )
        elif e.kind == TraceEventKind.ACTION_RESULT:
            if payload.get("success") is False:
                moments.append(
                    {
                        "tick": int(e.tick or 0),
                        "kind": "failed",
                        "label": "failed action",
                        "detail": str(payload.get("result_summary") or ""),
                        "score": 85,
                        "player_id": e.player_id,
                    }
                )
            else:
                summary = str(payload.get("result_summary") or "")
                # 状態変化らしき結果は弱めに拾う (true / OPEN / latch などの語)
                if any(k in summary for k in ("=true", "OPEN", "latch", "engaged")):
                    moments.append(
                        {
                            "tick": int(e.tick or 0),
                            "kind": "result",
                            "label": "state changed",
                            "detail": summary,
                            "score": 45,
                            "player_id": e.player_id,
                        }
                    )
        elif e.kind == TraceEventKind.POSITION_CHANGE:
            if payload.get("from_spot_id") is None:
                # 初期配置は moment にしない (start と冗長)
                continue
            spot_name = payload.get("spot_name") or payload.get("to_spot_id") or ""
            moments.append(
                {
                    "tick": int(e.tick or 0),
                    "kind": "move",
                    "label": f"move: {spot_name}",
                    "detail": str(spot_name),
                    "score": 50,
                    "player_id": e.player_id,
                }
            )
    return moments


# ---------------------------------------------------------------------------
# HTML 組み立て
# ---------------------------------------------------------------------------


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<title>{title} - llm-rpg trace viewer</title>
<style>
{css}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="meta">
    <span class="badge outcome">{outcome}</span>
    <span>tick <strong>0 / {max_tick}</strong></span>
    <span>events <strong>{total_events}</strong></span>
    <span>players <strong>{player_summary}</strong></span>
    <span class="viewer-links">
      <a href="episodic.html" data-sibling="episodic.html" title="episodic memory viewer" class="vlink">📖 episodic</a>
      <a href="timeline.html" data-sibling="timeline.html" title="player × tick timeline" class="vlink">📊 timeline</a>
    </span>
  </div>
  <div class="playback">
    <button id="btn-rewind" title="rewind to start">⏮</button>
    <button id="btn-step-back" title="step back (←)">◀</button>
    <button id="btn-play" title="play / pause (Space)">▶</button>
    <button id="btn-step-fwd" title="step forward (→)">▶|</button>
    <button id="btn-end" title="jump to end">⏭</button>
    <input type="range" id="scrubber" min="0" max="0" value="0" step="1" />
    <span id="tick-display">tick 0 / 0</span>
    <label class="speed-label">speed
      <select id="speed">
        <option value="1000">0.5x</option>
        <option value="500" selected>1x</option>
        <option value="250">2x</option>
        <option value="125">4x</option>
      </select>
    </label>
    <label class="toggle-label" title="player の inner_thought を吹き出し表示する">
      <input type="checkbox" id="toggle-thoughts" />
      inner thought
    </label>
  </div>
</header>

<main>
  <section id="timeline-section">
    <div id="log-section">
      <h2>Event timeline</h2>
      {event_filter_html}
      <div id="event-log">{event_log_html}</div>
    </div>
    <div id="memo-panel-section">
      <h2>Objectives / Active memo
        <label class="toggle-label" title="memo パネルの表示・非表示を切り替え"
               style="font-size: 0.65rem; font-weight: normal; margin-left: 0.5rem;">
          <input type="checkbox" id="toggle-memo-panel">
          show
        </label>
      </h2>
      <div id="memo-panel" style="display:none"><div class="placeholder">(no memo)</div></div>
    </div>
  </section>

  <section id="map-section">
    <h2>Tactical map</h2>
    <div id="cy"></div>
  </section>
</main>

<!-- Cytoscape.js (inline-embedded, no external CDN) -->
<script>
{cytoscape_js}
</script>
<script>
{viewer_js}
</script>
</body>
</html>
"""


_VIEWER_CSS = """

* { box-sizing: border-box; }
:root {
  --bg: #071014;
  --panel: #0d1a1f;
  --panel-2: #12232a;
  --panel-soft: #182b31;
  --ink: #f4ead2;
  --muted: #9daaa8;
  --line: rgba(218, 170, 86, 0.38);
  --line-soft: rgba(117, 210, 220, 0.22);
  --gold: #d9aa56;
  --cyan: #35d4e6;
  --blue: #4a8cff;
  --coral: #f06d55;
  --green: #7bd66f;
  --orange: #ee9b42;
  --font-ui: "Hiragino Maru Gothic ProN", "Yu Gothic", "Trebuchet MS", "Avenir Next", system-ui, sans-serif;
  --font-display: "Copperplate", "Papyrus", "Hiragino Maru Gothic ProN", "Yu Mincho", fantasy, serif;
  --font-mono: "SFMono-Regular", "Menlo", "Consolas", monospace;
}
body {
  margin: 0;
  min-width: 960px;
  font-family: var(--font-ui);
  color: var(--ink);
  background:
    linear-gradient(rgba(53, 212, 230, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(53, 212, 230, 0.035) 1px, transparent 1px),
    radial-gradient(circle at 15% 0%, rgba(53, 212, 230, 0.12), transparent 36rem),
    radial-gradient(circle at 95% 25%, rgba(217, 170, 86, 0.10), transparent 32rem),
    var(--bg);
  background-size: 28px 28px, 28px 28px, auto, auto, auto;
}
header {
  padding: 0.75rem 1rem 0.85rem;
  background: linear-gradient(180deg, rgba(18, 35, 42, 0.96), rgba(8, 17, 22, 0.96));
  border-bottom: 1px solid var(--line);
  box-shadow: 0 10px 30px rgba(0,0,0,0.25);
}
header h1 {
  margin: 0 0 0.45rem 0;
  font-size: 1.35rem;
  font-family: var(--font-display);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  text-shadow: 0 0 12px rgba(217, 170, 86, 0.22);
}
.meta {
  font-size: 0.82rem;
  color: var(--muted);
  display: flex;
  gap: 0.65rem;
  flex-wrap: wrap;
  margin-bottom: 0.65rem;
  align-items: center;
}
.meta span {
  border: 1px solid rgba(217, 170, 86, 0.28);
  background: rgba(5, 10, 13, 0.38);
  border-radius: 5px;
  padding: 0.28rem 0.55rem;
}
.meta strong { color: var(--ink); font-weight: 700; }
.meta .badge.outcome {
  color: #0b1712;
  background: linear-gradient(180deg, #f4c86e, #9fd66f);
  border-color: rgba(255, 236, 168, 0.7);
  font-weight: 900;
  letter-spacing: 0.08em;
}
.viewer-links { display: inline-flex; gap: 0.5rem; margin-left: auto; }
.viewer-links .vlink {
  text-decoration: none;
  background: rgba(53, 212, 230, 0.18);
  color: #aaecf5;
  border: 1px solid var(--line);
  border-radius: 3px;
  padding: 0.18rem 0.55rem;
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  font-family: var(--font-display);
}
.viewer-links .vlink:hover {
  background: rgba(53, 212, 230, 0.35);
  color: #fff;
}
.playback {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.playback button {
  border: 1px solid var(--line);
  background: linear-gradient(180deg, #17262d, #0b1418);
  color: var(--ink);
  border-radius: 5px;
  min-width: 2.35rem;
  height: 2rem;
  padding: 0.25rem 0.55rem;
  cursor: pointer;
  font-size: 0.9rem;
  line-height: 1;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04);
}
.playback button:hover { border-color: var(--cyan); color: var(--cyan); }
.playback button.playing {
  background: linear-gradient(180deg, rgba(53, 212, 230, 0.42), rgba(32, 117, 127, 0.42));
  color: #f7fdff;
  border-color: var(--cyan);
  box-shadow: 0 0 16px rgba(53, 212, 230, 0.24);
}
.playback input[type=range] {
  flex: 1;
  min-width: 200px;
  accent-color: var(--cyan);
}
#tick-display {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  min-width: 90px;
  text-align: right;
  color: var(--ink);
}
.speed-label { font-size: 0.8rem; color: var(--muted); }
.speed-label select {
  font-size: 0.8rem;
  color: var(--ink);
  background: #101d23;
  border: 1px solid var(--line);
  border-radius: 4px;
}
.toggle-label {
  font-size: 0.78rem;
  color: var(--muted);
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  cursor: pointer;
  user-select: none;
}
.toggle-label input { accent-color: var(--green); }

/* Speech / thought bubbles on map (PR η).
   Position is computed at JS runtime relative to the player marker.
   z-index: kept above Cytoscape canvas. */
.bubble-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  z-index: 5;
}
.bubble {
  position: absolute;
  pointer-events: auto;
  max-width: 220px;
  padding: 0.42rem 0.6rem;
  font-size: 0.78rem;
  line-height: 1.4;
  background: rgba(11, 23, 28, 0.96);
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: 0 6px 16px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.04);
  transform: translate(-50%, -100%);
  opacity: 0;
  transition: opacity 180ms ease, transform 180ms ease;
}
.bubble.visible { opacity: 1; transform: translate(-50%, -110%); }
.bubble.speech { border-color: var(--cyan); }
.bubble.speech::after {
  content: ""; position: absolute; left: 50%; bottom: -7px;
  width: 12px; height: 12px; background: rgba(11, 23, 28, 0.96);
  border-right: 1px solid var(--cyan); border-bottom: 1px solid var(--cyan);
  transform: translateX(-50%) rotate(45deg);
}
.bubble.thought {
  border-color: var(--green);
  border-style: dashed;
  border-radius: 18px;
  background: rgba(11, 30, 22, 0.96);
}
.bubble .bubble-who {
  font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--cyan); font-weight: 700; display: block; margin-bottom: 0.15rem;
}
.bubble.thought .bubble-who { color: var(--green); }

main {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(340px, 2fr);
  gap: 0.85rem;
  padding: 1rem;
  height: calc(100vh - 150px);
  min-height: 410px;
}
@media (max-width: 900px) {
  main { grid-template-columns: 1fr; height: auto; }
}
section, #timeline-section > div {
  background: linear-gradient(180deg, rgba(18, 35, 42, 0.94), rgba(8, 17, 22, 0.94));
  border: 1px solid var(--line);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  box-shadow: 0 14px 26px rgba(0,0,0,0.25), inset 0 0 0 1px rgba(255,255,255,0.03);
  overflow: hidden;
}
section h2, #timeline-section > div > h2 {
  margin: 0;
  padding: 0.55rem 0.9rem;
  font-size: 0.84rem;
  font-family: var(--font-display);
  text-transform: uppercase;
  letter-spacing: 0.09em;
  color: #ffe0a0;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(90deg, rgba(30, 82, 89, 0.55), rgba(61, 36, 26, 0.25));
}
#timeline-section {
  background: transparent;
  border: 0;
  box-shadow: none;
  display: grid;
  grid-template-rows: minmax(180px, 1fr) auto;
  gap: 0.85rem;
  overflow: visible;
}
#map-section { display: flex; flex-direction: column; }
#cy {
  flex: 1;
  min-height: 300px;
  width: 100%;
  background:
    radial-gradient(circle at 22% 12%, rgba(53, 212, 230, 0.12), transparent 18rem),
    linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px),
    #071318;
  background-size: auto, 34px 34px, 34px 34px, auto;
}
#memo-panel-section { min-height: 0; }
#memo-panel { padding: 0.55rem 0.75rem; overflow-y: auto; line-height: 1.5; }
#memo-panel .memo-item {
  font-size: 0.82rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--line-soft);
  border-left: 4px solid var(--blue);
  border-radius: 5px;
  background: rgba(11, 25, 32, 0.85);
  display: grid;
  grid-template-columns: minmax(56px, auto) 1fr auto;
  gap: 0.65rem;
  align-items: center;
  line-height: 1.45;
  margin-bottom: 0.45rem;
}
#memo-panel .memo-item:last-child { margin-bottom: 0; }
#memo-panel .memo-owner {
  font-size: 0.8rem;
  color: var(--cyan);
  min-width: 0;
  font-weight: 600;
}
#memo-panel .memo-content { flex: 1; word-break: break-word; line-height: 1.45; }
#memo-panel .memo-content.done { color: #80908e; text-decoration: line-through; }
#memo-panel .memo-meta { font-size: 0.75rem; color: var(--muted); white-space: nowrap; }
#memo-panel .memo-meta.stale { color: #ffba67; font-weight: bold; }
#memo-panel .placeholder { color: var(--muted); font-size: 0.85rem; padding: 0.5rem 0; }

#event-filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 0.55rem;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid rgba(217, 170, 86, 0.18);
  background: rgba(4, 12, 16, 0.42);
}
.event-filter-item {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.74rem;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
}
.event-filter-item input { accent-color: var(--cyan); }

#event-log { flex: 1; overflow-y: auto; padding: 0.55rem 0.75rem; }
.tick-block {
  margin-bottom: 0.55rem;
  padding: 0.48rem 0.55rem;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 5px;
  background: rgba(7, 16, 20, 0.55);
  transition: background 0.2s, border-color 0.2s, box-shadow 0.2s;
}
.tick-block.current {
  background: linear-gradient(90deg, rgba(240, 109, 85, 0.22), rgba(217, 170, 86, 0.12));
  border-color: rgba(240, 109, 85, 0.8);
  box-shadow: 0 0 16px rgba(240, 109, 85, 0.16);
}
.tick-block.past { opacity: 0.58; }
.tick-block.future { opacity: 0.36; }
.tick-header {
  font-weight: bold;
  color: #ffe0a0;
  font-size: 0.8rem;
  margin-bottom: 0.25rem;
  font-family: var(--font-mono);
}
.event-row {
  font-size: 0.8rem;
  padding: 0.12rem 0;
  display: flex;
  gap: 0.4rem;
  align-items: baseline;
}
.event-row.filtered-hidden { display: none; }
.tick-block.all-filtered { display: none; }
.event-kind {
  flex-shrink: 0;
  width: 118px;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--muted);
}
.event-player {
  flex-shrink: 0;
  width: 60px;
  font-size: 0.76rem;
  color: var(--cyan);
  font-weight: 700;
}
.event-body { flex: 1; word-break: break-word; }
.event-body code {
  color: #f5d07a;
  background: rgba(217, 170, 86, 0.12);
  border: 1px solid rgba(217, 170, 86, 0.20);
  border-radius: 3px;
  padding: 0 0.24rem;
}
.event-row.kind-action_result.failed .event-body { color: #ff8f7b; }
.event-row.kind-memo_add .event-body { color: #9bea91; }
.event-row.kind-memo_done .event-body { color: #9bea91; }
.event-row.kind-memo_hint .event-body { color: #ffd07a; }
.event-row.kind-position_change .event-body { color: #65dce8; }
/* Issue #276: 観測 prose は LLM が読んでいる「世界からの情報」なので、
   action / result とは色を分けて視認性を上げる。 */
.event-row.kind-observation .event-kind { color: #b89dff; }
.event-row.kind-observation .event-body { color: #d8c8ff; }
/* Issue #283 後続: episodic memory pipeline の trace。記憶系は黄緑寄りで
   action / observation と区別する。 */
.event-row.kind-episodic_chunk_written .event-kind { color: #a3e063; }
.event-row.kind-episodic_chunk_written .event-body { color: #c5edaa; }
.event-row.kind-episodic_recall .event-kind { color: #ffce63; }
.event-row.kind-episodic_recall .event-body { color: #ffe3a3; }
.event-row.category-speech .event-kind { color: #35d4e6; }
.event-row.category-speech .event-body { color: #e5fbff; }
.speech-channel, .speech-recipients {
  color: var(--muted);
  font-size: 0.74rem;
}
.event-inner-thought {
  display: none;
  color: #9bea91;
  font-style: italic;
  margin-left: 0.35rem;
}
body.show-inner-thoughts .event-inner-thought { display: inline; }
.event-row .dim { color: #8fa0a3; font-style: italic; }


"""


_VIEWER_JS_TEMPLATE = """
(function() {{
  // 兄弟ファイル (episodic.html / timeline.html) への遷移リンク補正。
  // 相対 href のままだと htmlpreview.github.io 経由で開いたとき raw gist URL
  // (text/plain) に解決され、HTML がソースコードとして表示されてしまう。
  // viewer 自身が htmlpreview 経由で配信されている場合は、兄弟リンクも
  // htmlpreview でラップした URL に書き換える。ローカル / 直接配信なら
  // 相対 href のまま動くので何もしない。
  (function fixSiblingLinks() {{
    if (window.location.hostname !== 'htmlpreview.github.io') return;
    // htmlpreview の URL 形式: https://htmlpreview.github.io/?<raw url of this html>
    const raw = window.location.search.slice(1);  // 先頭の '?' を落とす
    if (!raw) return;
    const base = raw.replace(/\\/[^/]+$/, '/');  // 末尾のファイル名を剥がす
    document.querySelectorAll('a[data-sibling]').forEach(function(a) {{
      const file = a.getAttribute('data-sibling');
      a.href = 'https://htmlpreview.github.io/?' + base + file;
    }});
  }})();

  const scenarioData = {scenario_data_json};
  const players = {players_json};
  const positionTimeline = {position_timeline_json};  // {{tick: {{player_id: spot_id}}}}
  const memoTimeline = {memo_timeline_json};          // {{tick: [memo records]}}
  const speechTimeline = {speech_timeline_json};      // {{tick: [{{player_id, kind, text, source_tick}}]}}
  const maxTick = {max_tick};
  const STALE_AGE = 20;

  const playerColors = ['#2e7dd7', '#e07a26', '#5fa14a', '#a155bf'];
  const playerNameById = {{}};
  for (const p of players) {{ playerNameById[p.id] = p.name; }}

  // ---------- map (Cytoscape) ----------
  if (typeof cytoscape === 'undefined') {{
    document.getElementById('cy').innerHTML =
      '<p style="padding:1rem;color:#a00">Cytoscape failed to load.</p>';
    return;
  }}
  const elements = [];
  for (const spot of scenarioData.spots) {{
    elements.push({{
      data: {{ id: 'spot:' + spot.id, label: spot.name }},
      classes: 'spot'
    }});
  }}
  const seenEdges = new Set();
  for (const c of scenarioData.connections) {{
    const key = c.from + '->' + c.to;
    if (seenEdges.has(key)) continue;
    seenEdges.add(key);
    if (c.bidirectional) seenEdges.add(c.to + '->' + c.from);
    elements.push({{
      data: {{
        id: 'edge:' + key,
        source: 'spot:' + c.from,
        target: 'spot:' + c.to,
      }},
      classes: c.bidirectional ? 'connection bi' : 'connection',
    }});
  }}
  for (let i = 0; i < players.length; i++) {{
    const p = players[i];
    elements.push({{
      data: {{ id: 'player:' + p.id, label: p.name }},
      classes: 'player player-' + (i % playerColors.length),
    }});
  }}

  const cy = cytoscape({{
    container: document.getElementById('cy'),
    elements: elements,
    style: [
      {{
        selector: 'node.spot',
        style: {{
          'background-color': '#f0eef5',
          'border-color': '#7a6db8',
          'border-width': 2,
          'label': 'data(label)',
          'text-valign': 'center',
          'text-halign': 'center',
          'font-size': 12,
          'width': 80,
          'height': 50,
          'shape': 'round-rectangle',
        }}
      }},
      {{
        selector: 'node.player',
        style: {{
          'background-color': '#222',
          'shape': 'ellipse',
          'width': 22,
          'height': 22,
          'label': 'data(label)',
          'color': '#fff',
          'text-valign': 'center',
          'text-halign': 'center',
          'font-size': 10,
          'text-outline-color': '#000',
          'text-outline-width': 1.5,
          'border-width': 0,
        }}
      }},
      ...playerColors.map((color, idx) => ({{
        selector: 'node.player-' + idx,
        style: {{ 'background-color': color, 'text-outline-color': color }}
      }})),
      {{
        selector: 'edge.connection',
        style: {{
          'width': 2,
          'line-color': '#bbb',
          'target-arrow-color': '#bbb',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
        }}
      }},
      {{ selector: 'edge.connection.bi', style: {{ 'target-arrow-shape': 'none' }} }},
    ],
    layout: {{
      name: 'cose', animate: false,
      // Phase 2 (実験 #26 user feedback): 初期グラフが縦長になり横スペースが
      // 余っていた問題への対応。aspect ratio を container に合わせるため
      // boundingBox を container 比 (横長) で与え、cose にレイアウト範囲の
      // 縦横比を伝える。
      boundingBox: (() => {{
        const c = document.getElementById('cy');
        const w = c ? c.clientWidth : 1200;
        const h = c ? c.clientHeight : 600;
        // ノード周辺に少し余白を残す (各辺 5%)
        const padX = w * 0.05;
        const padY = h * 0.05;
        return {{ x1: padX, y1: padY, x2: w - padX, y2: h - padY }};
      }})(),
      idealEdgeLength: 95,
      nodeRepulsion: 6500,
      padding: 12,
      // 横方向の広がりを優先するため重力を弱める
      gravity: 0.25,
    }},
  }});
  // layout 完了後に fit し直して container いっぱいに広げる
  cy.ready(() => {{
    cy.fit(undefined, 22);
  }});
  // resize 時に再 fit (sidebar 開閉 / window リサイズで縦長になりがち)
  window.addEventListener('resize', () => {{
    if (cy && typeof cy.fit === 'function') {{
      cy.fit(undefined, 22);
    }}
  }});

  // playback state
  let currentTick = 0;
  let isPlaying = false;
  let intervalMs = 500;
  let playTimer = null;

  function playerSpotAtTick(playerId, tick) {{
    // 一番近い t <= tick で記録のあるスナップショットを返す
    for (let t = tick; t >= 0; t--) {{
      const snap = positionTimeline[t];
      if (snap && snap[playerId] !== undefined) return snap[playerId];
    }}
    return null;
  }}

  function playerOffsetAtSpot(playerId, spotId) {{
    // 同じスポットにいる複数 player を周囲に散らす
    const cohabitants = players
      .filter(p => playerSpotAtTick(p.id, currentTick) === spotId)
      .map(p => p.id);
    const idx = cohabitants.indexOf(playerId);
    if (idx < 0 || cohabitants.length <= 1) return {{x: 0, y: 0}};
    const angle = (idx * 360 / cohabitants.length) * Math.PI / 180;
    return {{ x: 35 * Math.cos(angle), y: 35 * Math.sin(angle) }};
  }}

  function animatePlayersToTick(tick, animate) {{
    for (const p of players) {{
      const spotId = playerSpotAtTick(p.id, tick);
      if (!spotId) continue;
      const spotEl = cy.getElementById('spot:' + spotId);
      const playerEl = cy.getElementById('player:' + p.id);
      if (!spotEl.length || !playerEl.length) continue;
      const spotPos = spotEl.position();
      const off = playerOffsetAtSpot(p.id, spotId);
      const target = {{ x: spotPos.x + off.x, y: spotPos.y + off.y }};
      if (animate) {{
        playerEl.animate({{ position: target }}, {{ duration: Math.min(intervalMs * 0.6, 400) }});
      }} else {{
        playerEl.position(target);
      }}
    }}
  }}

  // ---------- speech / thought bubbles on map (PR η) ----------
  let showThoughts = false;
  // Cytoscape の container 内に bubble overlay layer を 1 つ作る
  const cyContainer = document.getElementById('cy');
  let bubbleLayer = document.getElementById('bubble-layer');
  if (!bubbleLayer && cyContainer) {{
    bubbleLayer = document.createElement('div');
    bubbleLayer.id = 'bubble-layer';
    bubbleLayer.className = 'bubble-layer';
    cyContainer.style.position = 'relative';
    cyContainer.appendChild(bubbleLayer);
  }}
  function renderSpeechBubbles(tick) {{
    if (!bubbleLayer) return;
    bubbleLayer.innerHTML = '';
    const bubbles = (speechTimeline && speechTimeline[tick]) || [];
    if (bubbles.length === 0) return;
    // 同 player に複数 bubble (speech + thought) → speech を下 (player に近く)、
    // thought をその上に積む。実 DOM 高さを測ってから再配置するため、まず
    // 仮の top で append → 次フレームで offsetHeight ベースに stack し直す。
    const byPlayer = {{}};
    for (const b of bubbles) {{
      if (b.kind === 'thought' && !showThoughts) continue;
      (byPlayer[b.player_id] = byPlayer[b.player_id] || []).push(b);
    }}
    const groups = [];  // [{{pid, pos, elements: [{{el, kind}}, ...]}}, ...]
    for (const pidStr of Object.keys(byPlayer)) {{
      const pid = parseInt(pidStr, 10);
      const playerNode = cy.getElementById('player:' + pid);
      if (!playerNode.length) continue;
      const pos = playerNode.renderedPosition();
      // speech が先 (idx 0 = 下), thought がその上に積まれるよう並び替え
      const items = byPlayer[pid].slice().sort((a, b) => {{
        // speech を先頭に
        if (a.kind === b.kind) return 0;
        return a.kind === 'speech' ? -1 : 1;
      }});
      const elements = items.map(b => {{
        const el = document.createElement('div');
        el.className = 'bubble ' + (b.kind === 'thought' ? 'thought' : 'speech');
        el.style.left = pos.x + 'px';
        el.style.top = (pos.y - 14) + 'px';  // 仮 top
        const name = playerNameById[pid] || ('#' + pid);
        const whoLabel = b.kind === 'thought' ? name + ' (inner)' : name;
        el.innerHTML = '<span class="bubble-who">' + escapeHtml(whoLabel) + '</span>' + escapeHtml(b.text);
        bubbleLayer.appendChild(el);
        return {{ el, kind: b.kind }};
      }});
      groups.push({{ pid, pos, elements }});
    }}
    // 次フレームで実 height を測って再配置 + visible 付与
    requestAnimationFrame(() => {{
      const GAP = 10;       // bubble 間の余白
      const PLAYER_GAP = 18; // player marker と最下 bubble の隙間
      // Phase 2 (実験 #26 user feedback): 複数 player が同 spot に居ると
      // bubble が水平方向に重なる。各 player の bubble stack を「同 spot
      // 内の他 player の bubble と縦に積み重ねる」ことで重なりを回避する。
      // まず spot id ごとに group を分類。
      const groupsBySpot = new Map();
      for (const g of groups) {{
        const spotId = playerSpotAtTick(g.pid, currentTick);
        if (!spotId) {{
          (groupsBySpot.get('orphan') || groupsBySpot.set('orphan', []).get('orphan')).push(g);
          continue;
        }}
        if (!groupsBySpot.has(spotId)) groupsBySpot.set(spotId, []);
        groupsBySpot.get(spotId).push(g);
      }}
      // spot ごとに stack を作る (= 同 spot の player の bubble を全部
      // 1 つの縦列にまとめる。x は spot 中心、y は下から上へ積む)。
      for (const [spotId, gs] of groupsBySpot.entries()) {{
        if (gs.length === 0) continue;
        // 同 spot の中心 x = player marker 位置の平均
        const meanX = gs.reduce((s, g) => s + g.pos.x, 0) / gs.length;
        let yCursor = Math.min(...gs.map(g => g.pos.y)) - PLAYER_GAP;
        for (const g of gs) {{
          for (const item of g.elements) {{
            item.el.style.left = meanX + 'px';
            item.el.style.top = yCursor + 'px';
            yCursor = yCursor - item.el.offsetHeight - GAP;
            item.el.classList.add('visible');
          }}
        }}
      }}
    }});
  }}

  // ---------- memo panel toggle (実験 #26 user feedback) ----------
  const memoPanelSection = document.getElementById('memo-panel-section');
  const memoToggle = document.getElementById('toggle-memo-panel');
  if (memoToggle && memoPanelSection) {{
    memoToggle.addEventListener('change', () => {{
      const panel = document.getElementById('memo-panel');
      if (panel) {{
        panel.style.display = memoToggle.checked ? '' : 'none';
      }}
    }});
  }}

  // ---------- memo panel ----------
  const memoPanel = document.getElementById('memo-panel');
  function renderMemoPanel(tick) {{
    // 最も近い t <= tick のスナップショット
    let snap = null;
    for (let t = tick; t >= 0; t--) {{
      if (memoTimeline[t]) {{ snap = memoTimeline[t]; break; }}
    }}
    if (!snap || snap.length === 0) {{
      memoPanel.innerHTML = '<div class="placeholder">(no memo at tick ' + tick + ')</div>';
      return;
    }}
    const parts = [];
    for (const m of snap) {{
      const owner = playerNameById[m.player_id] || ('#' + m.player_id);
      const age = tick - m.added_tick;
      const isStale = m.status === 'active' && age >= STALE_AGE;
      const ageLabel = m.status === 'done'
        ? ('completed t=' + m.done_tick)
        : (age + ' tick' + (isStale ? ' [STALE]' : ''));
      parts.push(
        '<div class="memo-item">' +
          '<span class="memo-owner">' + escapeHtml(owner) + '</span>' +
          '<span class="memo-content ' + (m.status === 'done' ? 'done' : '') + '">' + escapeHtml(m.content) + '</span>' +
          '<span class="memo-meta ' + (isStale ? 'stale' : '') + '">' + ageLabel + '</span>' +
        '</div>'
      );
    }}
    memoPanel.innerHTML = parts.join('');
  }}
  function escapeHtml(s) {{
    return String(s).replace(/[&<>"']/g, ch => ({{
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }})[ch]);
  }}

  // ---------- event category filters ----------
  function applyEventFilters() {{
    const enabled = {{}};
    document.querySelectorAll('.event-filter-checkbox').forEach(cb => {{
      enabled[cb.dataset.filterCategory] = cb.checked;
    }});
    document.querySelectorAll('.event-row[data-category]').forEach(row => {{
      const category = row.dataset.category || 'other';
      row.classList.toggle('filtered-hidden', enabled[category] === false);
    }});
    document.querySelectorAll('.tick-block').forEach(block => {{
      const visibleRows = block.querySelectorAll('.event-row:not(.filtered-hidden)');
      block.classList.toggle('all-filtered', visibleRows.length === 0);
    }});
  }}
  document.querySelectorAll('.event-filter-checkbox').forEach(cb => {{
    cb.addEventListener('change', applyEventFilters);
  }});

  // ---------- event log highlight ----------
  function updateEventLogHighlight(tick) {{
    const blocks = document.querySelectorAll('.tick-block');
    let target = null;
    blocks.forEach(block => {{
      const t = parseInt(block.dataset.tick, 10);
      block.classList.remove('current', 'past', 'future');
      if (isNaN(t)) return;
      if (t === tick) {{ block.classList.add('current'); target = block; }}
      else if (t < tick) block.classList.add('past');
      else block.classList.add('future');
    }});
    if (target) target.scrollIntoView({{ block: 'nearest', behavior: 'smooth' }});
  }}

  // ---------- main state setter ----------
  function setTick(tick, animate) {{
    tick = Math.max(0, Math.min(maxTick, tick));
    currentTick = tick;
    document.getElementById('scrubber').value = String(tick);
    document.getElementById('tick-display').textContent = 'tick ' + tick + ' / ' + maxTick;
    animatePlayersToTick(tick, animate !== false);
    renderMemoPanel(tick);
    updateEventLogHighlight(tick);
    // bubble は player marker のアニメーション後に位置を取りたいので
    // 短い delay で配置 (animate duration ~ 240ms に追従)
    setTimeout(() => renderSpeechBubbles(tick), animate !== false ? 240 : 0);
  }}

  // ---------- playback loop ----------
  function play() {{
    if (isPlaying) return;
    isPlaying = true;
    document.getElementById('btn-play').textContent = '⏸';
    document.getElementById('btn-play').classList.add('playing');
    playTimer = setInterval(() => {{
      if (currentTick >= maxTick) {{ pause(); return; }}
      setTick(currentTick + 1, true);
    }}, intervalMs);
  }}
  function pause() {{
    if (!isPlaying) return;
    isPlaying = false;
    document.getElementById('btn-play').textContent = '▶';
    document.getElementById('btn-play').classList.remove('playing');
    if (playTimer) {{ clearInterval(playTimer); playTimer = null; }}
  }}
  function togglePlay() {{ isPlaying ? pause() : play(); }}

  // ---------- UI wiring ----------
  const scrubber = document.getElementById('scrubber');
  scrubber.max = String(maxTick);
  scrubber.addEventListener('input', e => {{ pause(); setTick(parseInt(e.target.value, 10), false); }});
  document.getElementById('btn-rewind').addEventListener('click', () => {{ pause(); setTick(0, false); }});
  document.getElementById('btn-end').addEventListener('click', () => {{ pause(); setTick(maxTick, false); }});
  document.getElementById('btn-step-back').addEventListener('click', () => {{ pause(); setTick(currentTick - 1, true); }});
  document.getElementById('btn-step-fwd').addEventListener('click', () => {{ pause(); setTick(currentTick + 1, true); }});
  document.getElementById('btn-play').addEventListener('click', togglePlay);
  document.getElementById('speed').addEventListener('change', e => {{
    intervalMs = parseInt(e.target.value, 10);
    if (isPlaying) {{ pause(); play(); }}
  }});

  const toggleThoughts = document.getElementById('toggle-thoughts');
  if (toggleThoughts) {{
    toggleThoughts.addEventListener('change', e => {{
      showThoughts = !!e.target.checked;
      document.body.classList.toggle('show-inner-thoughts', showThoughts);
      renderSpeechBubbles(currentTick);
    }});
  }}

  // Cytoscape の pan/zoom で player marker 位置が変わるので bubble を追随
  cy.on('pan zoom', () => renderSpeechBubbles(currentTick));

  document.addEventListener('keydown', e => {{
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (e.key === ' ' || e.key === 'Spacebar') {{ e.preventDefault(); togglePlay(); }}
    else if (e.key === 'ArrowLeft') {{ pause(); setTick(currentTick - 1, true); }}
    else if (e.key === 'ArrowRight') {{ pause(); setTick(currentTick + 1, true); }}
  }});

  // ---------- bootstrap ----------
  cy.ready(function() {{
    cy.fit(undefined, 22);
    applyEventFilters();
    setTick(0, false);
  }});
  window.addEventListener('resize', () => {{
    renderSpeechBubbles(currentTick);
  }});
}})();
"""


def render_viewer_html(
    *,
    title: str,
    events: List[TraceEvent],
    scenario_topology: Dict[str, Any],
    cytoscape_js_src: str,
) -> str:
    """viewer.html の文字列を組み立てて返す。"""
    # spot_name → scenario spot id の逆引きマップ (trace の to_spot_id が
    # scenario id と違うケース用)
    spot_name_to_id = {
        str(s.get("name") or ""): str(s.get("id"))
        for s in scenario_topology.get("spots", [])
        if s.get("name") and s.get("id") is not None
    }
    players = collect_players(events, spot_name_to_id=spot_name_to_id)
    by_tick = group_events_by_tick(events)
    last_tick = max((t for t in by_tick if t is not None), default=0)
    max_tick = last_tick

    # ヘッダ用サマリ
    outcome = "?"
    for e in events:
        if e.kind == TraceEventKind.RUN_END and isinstance(e.payload, dict):
            outcome = str(e.payload.get("outcome") or "?")
            break

    player_summary = ", ".join(f"{p['name']} (#{p['id']})" for p in players) or "(none)"

    position_timeline = build_position_timeline(events, spot_name_to_id=spot_name_to_id)
    memo_timeline = build_memo_state_timeline(events)
    speech_timeline = build_speech_timeline(events)

    return _HTML_TEMPLATE.format(
        title=html.escape(title),
        outcome=html.escape(outcome),
        max_tick=max_tick,
        total_events=len(events),
        player_summary=html.escape(player_summary),
        css=_VIEWER_CSS,
        event_filter_html=_build_event_filter_html(),
        event_log_html=_build_event_log_html(by_tick, players),
        cytoscape_js=cytoscape_js_src,
        viewer_js=_VIEWER_JS_TEMPLATE.format(
            scenario_data_json=json.dumps(scenario_topology, ensure_ascii=False),
            players_json=json.dumps(players, ensure_ascii=False),
            position_timeline_json=json.dumps(position_timeline, ensure_ascii=False),
            memo_timeline_json=json.dumps(memo_timeline, ensure_ascii=False),
            speech_timeline_json=json.dumps(speech_timeline, ensure_ascii=False),
            max_tick=max_tick,
        ),
    )


def _build_event_log_html(
    by_tick: "OrderedDict[Optional[int], List[TraceEvent]]",
    players: List[Dict[str, Any]],
) -> str:
    """tick 別の event log HTML を組み立てる。"""
    name_by_pid = {p["id"]: p["name"] for p in players}
    parts: List[str] = []
    for tick, evs in by_tick.items():
        tick_label = "(no tick)" if tick is None else f"tick {tick}"
        rows: List[str] = []
        visible_row_count = 0
        for e in evs:
            kind = e.kind
            category = _event_timeline_category(e)
            default_visible = _event_category_default_visible(category)
            if default_visible:
                visible_row_count += 1
            pname = (
                name_by_pid.get(e.player_id, f"#{e.player_id}")
                if e.player_id is not None
                else "—"
            )
            body = _format_event_body(e)
            classes = (
                f"event-row kind-{html.escape(kind)} "
                f"category-{html.escape(category)}"
            )
            if not default_visible:
                classes += " filtered-hidden"
            if (
                kind == TraceEventKind.ACTION_RESULT
                and isinstance(e.payload, dict)
                and e.payload.get("success") is False
            ):
                classes += " failed"
            rows.append(
                f'<div class="{classes}" data-category="{html.escape(category)}">'
                f'<span class="event-kind">{html.escape(kind)}</span>'
                f'<span class="event-player">{html.escape(str(pname))}</span>'
                f'<span class="event-body">{body}</span>'
                f"</div>"
            )
        tick_attr = "" if tick is None else f' data-tick="{int(tick)}"'
        tick_classes = "tick-block" + (
            " all-filtered" if rows and visible_row_count == 0 else ""
        )
        parts.append(
            f'<div class="{tick_classes}"{tick_attr}>'
            f'<div class="tick-header">{html.escape(tick_label)}</div>'
            f"{''.join(rows)}</div>"
        )
    return "".join(parts)


def _build_event_filter_html() -> str:
    """Event timeline のカテゴリフィルタ UI を返す。"""
    parts = ['<div id="event-filter-bar" aria-label="event filters">']
    for category, label, default_visible in _EVENT_FILTER_CATEGORIES:
        checked = " checked" if default_visible else ""
        default_attr = "true" if default_visible else "false"
        parts.append(
            '<label class="event-filter-item">'
            f'<input type="checkbox" class="event-filter-checkbox" '
            f'data-filter-category="{html.escape(category)}" '
            f'data-default-visible="{default_attr}"{checked}>'
            f"{html.escape(label)}</label>"
        )
    parts.append("</div>")
    return "".join(parts)


def _event_category_default_visible(category: str) -> bool:
    """カテゴリの初期表示設定を返す。"""
    for key, _label, default_visible in _EVENT_FILTER_CATEGORIES:
        if key == category:
            return default_visible
    return False


def _event_timeline_category(e: TraceEvent) -> str:
    """timeline 上の粗い表示カテゴリを返す。"""
    payload = e.payload if isinstance(e.payload, dict) else {}
    kind = str(e.kind)
    if kind == TraceEventKind.ACTION_RESULT and payload.get("success") is False:
        return "failure"
    if _is_speak_action(e) or _is_player_spoke_observation(e):
        return "speech"
    if kind == TraceEventKind.ACTION:
        return "action"
    if kind == TraceEventKind.ACTION_RESULT:
        return "action_result"
    if kind == TraceEventKind.OBSERVATION:
        return "observation"
    if kind in {TraceEventKind.MEMO_ADD, TraceEventKind.MEMO_DONE, TraceEventKind.MEMO_HINT}:
        return "memo"
    if kind in {
        TraceEventKind.EPISODIC_CHUNK_WRITTEN,
        TraceEventKind.EPISODIC_RECALL,
        "semantic_passive_recall",
    }:
        return "recall"
    if kind.startswith("belief_"):
        return "belief"
    if kind.startswith("goal_") or "stagnation" in kind:
        return "goal"
    if kind in {
        "prediction_outcome",
        "side_handler_failed",
        "SIDE_HANDLER_FAILED",
        "llm_call",
        "snapshot_save",
        "snapshot_load",
        "world_snapshot_save",
        "world_snapshot_load",
        "prompt_section_breakdown",
    }:
        return "system"
    return "other"


def _is_speak_action(e: TraceEvent) -> bool:
    """speak 系 tool 呼び出しかどうかを返す。"""
    if e.kind != TraceEventKind.ACTION or not isinstance(e.payload, dict):
        return False
    tool = str(e.payload.get("tool") or "").lower()
    return tool in {"speak", "say"} or tool.startswith("speech_")


def _is_player_spoke_observation(e: TraceEvent) -> bool:
    """player_spoke 構造化観測かどうかを返す。"""
    if e.kind != TraceEventKind.OBSERVATION or not isinstance(e.payload, dict):
        return False
    structured = e.payload.get("structured")
    return isinstance(structured, dict) and structured.get("type") == "player_spoke"


def _format_event_body(e: TraceEvent) -> str:
    """event の payload を 1 行サマリに整形する (HTML escape 済み)。"""
    payload = e.payload if isinstance(e.payload, dict) else {}

    def esc(s: Any) -> str:
        return html.escape(str(s))

    def short(s: Any, limit: int = 90) -> str:
        text = str(s or "")
        return text if len(text) <= limit else text[: limit - 1] + "…"

    if e.kind == TraceEventKind.OBSERVATION:
        structured = payload.get("structured")
        if isinstance(structured, dict) and structured.get("type") == "player_spoke":
            speaker = (
                structured.get("speaker")
                or structured.get("speaker_name")
                or structured.get("speaker_player_id")
                or payload.get("speaker_player_id")
                or "?"
            )
            channel = structured.get("channel") or payload.get("channel") or "speak"
            content = structured.get("content") or payload.get("content") or payload.get("prose") or ""
            recipients = payload.get("_viewer_recipients")
            recipient_part = ""
            if isinstance(recipients, list) and recipients:
                labels = ", ".join(_format_speech_recipient(r) for r in recipients[:6])
                if len(recipients) > 6:
                    labels += f", …(+{len(recipients) - 6})"
                recipient_part = (
                    f" <span class='speech-recipients'>届いた相手: {labels}</span>"
                )
            return (
                f"発言 <span class='speech-channel'>[{esc(channel)}]</span> "
                f"{esc(speaker)}: {esc(content)}{recipient_part}"
            )
        prose = payload.get("prose") or ""
        return esc(prose)
    if e.kind == TraceEventKind.ACTION:
        tool = payload.get("tool") or "?"
        args = payload.get("arguments")
        if _is_speak_action(e) and isinstance(args, dict):
            content = args.get("content") or args.get("message") or ""
            channel = args.get("channel") or tool
            inner = args.get("inner_thought")
            inner_part = (
                f" <span class='event-inner-thought'>内心: {esc(short(inner, 120))}</span>"
                if inner
                else ""
            )
            return (
                f"発言 <span class='speech-channel'>[{esc(channel)}]</span>: "
                f"{esc(content)}{inner_part}"
            )
        args_str = _compact_payload_summary(args) if isinstance(args, (dict, list)) else ""
        inner = args.get("inner_thought") if isinstance(args, dict) else None
        inner_part = (
            f" <span class='event-inner-thought'>内心: {esc(short(inner, 120))}</span>"
            if inner
            else ""
        )
        return (
            f"<code>{esc(tool)}</code>"
            + (f" {esc(args_str)}" if args_str else "")
            + inner_part
        )
    if e.kind == TraceEventKind.ACTION_RESULT:
        success = payload.get("success")
        mark = "OK" if success else "NG"
        summary = payload.get("result_summary") or ""
        return f"[{esc(mark)}] {esc(summary)}"
    if e.kind == TraceEventKind.MEMO_ADD:
        return f"+ {esc(payload.get('content', ''))} (id={esc(payload.get('memo_id', ''))})"
    if e.kind == TraceEventKind.MEMO_DONE:
        return f"✓ done (id={esc(payload.get('memo_id', ''))})"
    if e.kind == TraceEventKind.MEMO_HINT:
        sim = payload.get("similarity")
        return f"hint memo {esc(payload.get('memo_id', ''))} sim={esc(round(float(sim), 2)) if sim is not None else '?'}"
    if e.kind == TraceEventKind.POSITION_CHANGE:
        from_id = payload.get("from_spot_id")
        to_name = payload.get("spot_name") or payload.get("to_spot_id") or ""
        if from_id is None:
            return f"spawn at {esc(to_name)}"
        return f"{esc(from_id)} → {esc(to_name)}"
    if e.kind == TraceEventKind.EPISODIC_CHUNK_WRITTEN:
        # write 経路: どの境界理由で何が保存されたかの 1 行サマリ
        ep_short = (payload.get("episode_id") or "")[:6]
        reason = payload.get("boundary_reason") or "?"
        snippet = (payload.get("recall_text_snippet") or "")[:60]
        snippet_part = (
            f" <span class='dim'>{esc(snippet)}</span>"
            if snippet and "{" not in snippet and "}" not in snippet
            else ""
        )
        return (
            f"✎ chunk written id={esc(ep_short)}… "
            f"reason={esc(reason)}{snippet_part}"
        )
    if e.kind == TraceEventKind.EPISODIC_RECALL:
        # read 経路: 想起 candidate と発火 cue の 1 行サマリ
        cand_count = int(payload.get("candidate_count") or 0)
        candidates = payload.get("candidates") or []
        first_ep = ""
        if candidates:
            first_ep_id = (candidates[0].get("episode_id") or "")[:6]
            first_snippet = (candidates[0].get("recall_text_snippet") or "")[:60]
            first_ep = (
                f" first={esc(first_ep_id)}…: "
                f"<span class='dim'>{esc(first_snippet)}</span>"
            )
        return f"⟲ recall {cand_count} candidates{first_ep}"
    kind = str(e.kind)
    if kind == "semantic_passive_recall":
        cand_count = int(payload.get("candidate_count") or len(payload.get("candidates") or []))
        top_k = payload.get("top_k")
        first = _first_text_from_candidates(payload.get("candidates"))
        first_part = (
            f" first: <span class='dim'>{esc(short(first, 90))}</span>"
            if first
            else ""
        )
        return f"semantic recall: {cand_count} candidates" + (
            f" / top_k={esc(top_k)}" if top_k is not None else ""
        ) + first_part
    if kind == "prediction_outcome":
        outcome = (
            payload.get("outcome")
            or payload.get("prediction_error")
            or payload.get("summary")
            or payload.get("result")
            or _compact_payload_summary(payload)
        )
        return f"prediction outcome: {esc(short(outcome, 140))}"
    if kind.startswith("belief_"):
        text = (
            payload.get("belief")
            or payload.get("text")
            or payload.get("text_snippet")
            or payload.get("evidence_text")
            or payload.get("source_text")
            or payload.get("summary")
            or payload.get("belief_evidence")
            or payload.get("evidence")
            or _first_text_from_candidates(payload.get("decisions"))
            or _compact_payload_summary(payload)
        )
        return f"belief: {esc(short(text, 140))}"
    if kind.startswith("goal_") or "stagnation" in kind:
        text = (
            payload.get("goal")
            or payload.get("summary")
            or payload.get("reason")
            or payload.get("band")
            or _compact_payload_summary(payload)
        )
        return f"goal: {esc(short(text, 140))}"
    if kind.lower() == "side_handler_failed":
        handler = payload.get("handler") or "?"
        event_type = payload.get("event_type") or "?"
        player_id = payload.get("player_id")
        err = payload.get("error_type") or "?"
        player_part = f" player=#{esc(player_id)}" if player_id is not None else ""
        return (
            f"side handler failed: {esc(handler)} / {esc(event_type)}"
            f"{player_part} ({esc(err)})"
        )
    return esc(_compact_payload_summary(payload))


def _format_speech_recipient(value: Any) -> str:
    """発言の受信者情報を短く表示する。"""
    if not isinstance(value, dict):
        return f"#{html.escape(str(value))}"
    player_id = value.get("player_id")
    label = f"#{html.escape(str(player_id))}" if player_id is not None else "#?"
    clarity = value.get("sound_clarity")
    if clarity:
        label += f" {html.escape(str(clarity))}"
    connection = value.get("source_connection_name")
    if connection:
        label += f" via {html.escape(str(connection))}"
    return label


def _first_text_from_candidates(value: Any) -> str:
    """候補配列から人間が読む本文断片を 1 つ取り出す。"""
    if not isinstance(value, list):
        return ""
    for item in value:
        if not isinstance(item, dict):
            continue
        for key in (
            "text_snippet",
            "recall_text_snippet",
            "summary",
            "content",
            "belief",
            "new_text",
            "revised_text",
            "text",
        ):
            text = item.get(key)
            if text:
                return str(text)
    return ""


def _compact_payload_summary(value: Any) -> str:
    """生 JSON を撒かず、payload を短い key=value 要約にする。"""
    if isinstance(value, dict):
        parts: List[str] = []
        for key, item in value.items():
            if key in {"situation_cues", "cues", "inner_thought"}:
                continue
            if isinstance(item, dict):
                parts.append(f"{key}={len(item)} keys")
            elif isinstance(item, list):
                parts.append(f"{key}={len(item)} items")
            else:
                text = str(item)
                if len(text) > 48:
                    text = text[:47] + "…"
                parts.append(f"{key}={text}")
            if len(parts) >= 4:
                break
        return ", ".join(parts) if parts else "(no detail)"
    if isinstance(value, list):
        return f"{len(value)} items"
    return str(value or "")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a self-contained trace viewer HTML (Phase 1d β)"
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help="Run directory containing trace.jsonl (and optionally scenario.json)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path (default: <run_dir>/viewer.html)",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Title to embed (default: run_dir name)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Do not download vendor JS; require it to be cached already",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    run_dir = args.run_dir
    if not run_dir.is_dir():
        parser.error(f"run_dir is not a directory: {run_dir}")

    trace_path = run_dir / "trace.jsonl"
    if not trace_path.exists():
        parser.error(f"trace.jsonl not found in {run_dir}")
    scenario_path = run_dir / "scenario.json"  # optional

    events = list(load_trace_events(trace_path))
    topology = load_scenario_topology(scenario_path)

    asset = fetch_cytoscape(offline=args.offline)
    print(f"[vendor] cytoscape@{asset.version} ({len(asset.content)//1024} KB)", flush=True)

    out_path = args.output or (run_dir / "viewer.html")
    title = args.title or run_dir.name
    html_str = render_viewer_html(
        title=title,
        events=events,
        scenario_topology=topology,
        cytoscape_js_src=asset.content,
    )
    out_path.write_text(html_str, encoding="utf-8")
    print(f"[viewer] {out_path} ({len(html_str)//1024} KB, {len(events)} events)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
