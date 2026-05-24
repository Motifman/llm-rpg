#!/usr/bin/env python3
"""trace + scenario から self-contained viewer HTML を生成する (Phase 1d β)。

PR α (#214) で trace に ``position_change`` event が乗るようになったので、
それを起点に空間 + event log を見せる viewer を作る。

PR β (本 PR) の範囲:
    - Cytoscape.js を inline 埋め込み (vendor ファイルを HTML に直書き)
    - scenario.json の spot graph topology からマップを描画
    - 最終的なプレイヤー位置を表示 (静的)
    - 全 event を tick 別の log として一覧表示

PR γ (次) で追加予定:
    - playback animation (時間軸に沿ってプレイヤーが動く)
    - tick scrub bar
    - memo state パネル
    - event heatmap

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


def group_events_by_tick(
    events: List[TraceEvent],
) -> "OrderedDict[Optional[int], List[TraceEvent]]":
    """event を tick 順にグルーピング。"""
    by_tick: "OrderedDict[Optional[int], List[TraceEvent]]" = OrderedDict()
    for e in events:
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
    <span>outcome: <strong>{outcome}</strong></span>
    <span>total ticks: {max_tick}</span>
    <span>events: {total_events}</span>
    <span>players: {player_summary}</span>
  </div>
  <div class="playback">
    <button id="btn-rewind" title="rewind to start">⏮</button>
    <button id="btn-step-back" title="step back (←)">◀</button>
    <button id="btn-play" title="play / pause (Space)">▶</button>
    <button id="btn-step-fwd" title="step forward (→)">▶|</button>
    <button id="btn-end" title="jump to end">⏭</button>
    <input type="range" id="scrubber" min="0" max="0" value="0" step="1" />
    <span id="tick-display">tick 0 / 0</span>
    <label class="speed-label">速度
      <select id="speed">
        <option value="1000">0.5x</option>
        <option value="500" selected>1x</option>
        <option value="250">2x</option>
        <option value="125">4x</option>
      </select>
    </label>
  </div>
</header>

<main>
  <section id="map-section">
    <h2>Map</h2>
    <div id="cy"></div>
    <div id="heatmap-wrap">
      <canvas id="heatmap" width="800" height="60"></canvas>
      <div class="heatmap-legend">
        <span><span class="hm-dot a"></span>action</span>
        <span><span class="hm-dot o"></span>observation</span>
        <span><span class="hm-dot m"></span>memo</span>
        <span><span class="hm-dot p"></span>position</span>
      </div>
    </div>
  </section>

  <section id="right-section">
    <div id="memo-panel-section">
      <h2>Active memo</h2>
      <div id="memo-panel"><div class="placeholder">(no memo)</div></div>
    </div>
    <div id="log-section">
      <h2>Event timeline</h2>
      <div id="event-log">{event_log_html}</div>
    </div>
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
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: #222;
  background: #fafafa;
}
header {
  padding: 0.75rem 1.5rem;
  background: #fff;
  border-bottom: 1px solid #ddd;
}
header h1 { margin: 0 0 0.25rem 0; font-size: 1.15rem; }
.meta { font-size: 0.82rem; color: #666; display: flex; gap: 1.2rem; flex-wrap: wrap; margin-bottom: 0.6rem; }
.meta strong { color: #222; }
.playback {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.playback button {
  border: 1px solid #bbb;
  background: #fff;
  border-radius: 4px;
  padding: 0.25rem 0.5rem;
  cursor: pointer;
  font-size: 0.9rem;
  line-height: 1;
}
.playback button:hover { background: #f0f0f0; }
.playback button.playing { background: #4a8; color: #fff; border-color: #387; }
.playback input[type=range] {
  flex: 1;
  min-width: 200px;
}
#tick-display {
  font-family: monospace;
  font-size: 0.85rem;
  min-width: 80px;
  text-align: right;
}
.speed-label { font-size: 0.8rem; color: #666; }
.speed-label select { font-size: 0.8rem; }

main {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  padding: 1rem;
  height: calc(100vh - 140px);
}
@media (max-width: 900px) {
  main { grid-template-columns: 1fr; height: auto; }
}
section, #right-section > div {
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
section h2, #right-section > div > h2 {
  margin: 0;
  padding: 0.5rem 0.9rem;
  font-size: 0.9rem;
  border-bottom: 1px solid #eee;
  background: #f5f5f5;
}
#map-section { display: flex; flex-direction: column; }
#cy {
  flex: 1;
  min-height: 300px;
  width: 100%;
  background: #fcfcfc;
}
#heatmap-wrap { padding: 0.4rem; border-top: 1px solid #eee; background: #fafafa; }
#heatmap { width: 100%; height: 60px; display: block; }
.heatmap-legend { display: flex; gap: 0.8rem; font-size: 0.72rem; color: #666; padding: 0.2rem 0 0 0; }
.hm-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  vertical-align: middle;
  margin-right: 0.25rem;
}
.hm-dot.a { background: #d44; }
.hm-dot.o { background: #46a; }
.hm-dot.m { background: #4a8; }
.hm-dot.p { background: #a73; }

#right-section {
  display: grid;
  grid-template-rows: minmax(120px, auto) 1fr;
  gap: 1rem;
  min-height: 0;
}
#memo-panel-section { min-height: 0; }
#memo-panel { padding: 0.4rem 0.9rem; overflow-y: auto; line-height: 1.5; }
#memo-panel .memo-item {
  font-size: 0.82rem;
  padding: 0.4rem 0;
  border-bottom: 1px dashed #eee;
  display: flex;
  gap: 0.6rem;
  align-items: center;
  line-height: 1.45;
}
#memo-panel .memo-item:last-child { border-bottom: none; }
#memo-panel .memo-owner {
  flex-shrink: 0;
  font-size: 0.8rem;
  color: #444;
  min-width: 60px;
  font-weight: 600;
}
#memo-panel .memo-content { flex: 1; word-break: break-word; line-height: 1.45; }
#memo-panel .memo-content.done { color: #999; text-decoration: line-through; }
#memo-panel .memo-meta { flex-shrink: 0; font-size: 0.75rem; color: #888; white-space: nowrap; }
#memo-panel .memo-meta.stale { color: #b50; font-weight: bold; }
#memo-panel .placeholder { color: #aaa; font-size: 0.85rem; padding: 0.5rem 0; }

#event-log { flex: 1; overflow-y: auto; padding: 0.5rem 0.9rem; }
.tick-block { margin-bottom: 0.6rem; padding: 0.3rem 0.4rem; border-radius: 3px; transition: background 0.2s; }
.tick-block.current { background: #fff7d6; outline: 1px solid #e8c64a; }
.tick-block.past { opacity: 0.55; }
.tick-block.future { opacity: 0.35; }
.tick-header { font-weight: bold; color: #555; font-size: 0.82rem; margin-bottom: 0.2rem; }
.event-row {
  font-size: 0.8rem;
  padding: 0.1rem 0;
  display: flex;
  gap: 0.4rem;
  align-items: baseline;
}
.event-kind {
  flex-shrink: 0;
  width: 110px;
  font-family: monospace;
  font-size: 0.72rem;
  color: #777;
}
.event-player {
  flex-shrink: 0;
  width: 60px;
  font-size: 0.76rem;
  color: #444;
}
.event-body { flex: 1; word-break: break-word; }
.event-row.kind-action_result.failed .event-body { color: #b00; }
.event-row.kind-memo_add .event-body { color: #060; }
.event-row.kind-memo_done .event-body { color: #060; }
.event-row.kind-memo_hint .event-body { color: #a60; }
.event-row.kind-position_change .event-body { color: #06a; }
"""


_VIEWER_JS_TEMPLATE = """
(function() {{
  const scenarioData = {scenario_data_json};
  const players = {players_json};
  const positionTimeline = {position_timeline_json};  // {{tick: {{player_id: spot_id}}}}
  const memoTimeline = {memo_timeline_json};          // {{tick: [memo records]}}
  const heatmap = {heatmap_json};                     // {{ticks, action, observation, memo, position_change}}
  const eventsByTick = {events_by_tick_json};         // {{tick: [{{kind, player_id, body}}]}}
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
      idealEdgeLength: 120, nodeRepulsion: 8000, padding: 30,
    }},
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

  // ---------- heatmap ----------
  const canvas = document.getElementById('heatmap');
  const ctx = canvas.getContext('2d');
  function drawHeatmap(tick) {{
    const w = canvas.width = canvas.clientWidth || canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    const ticks = heatmap.ticks;
    if (!ticks || ticks.length === 0) return;
    const colW = w / ticks.length;
    const rowH = h / 4;
    const rows = [
      {{ key: 'action', color: '#d44' }},
      {{ key: 'observation', color: '#46a' }},
      {{ key: 'memo', color: '#4a8' }},
      {{ key: 'position_change', color: '#a73' }},
    ];
    for (let i = 0; i < rows.length; i++) {{
      const r = rows[i];
      const series = heatmap[r.key] || [];
      const maxv = Math.max(1, ...series);
      for (let t = 0; t < ticks.length; t++) {{
        const v = series[t] || 0;
        if (v === 0) continue;
        const alpha = 0.2 + 0.8 * (v / maxv);
        ctx.fillStyle = r.color;
        ctx.globalAlpha = alpha;
        ctx.fillRect(t * colW, i * rowH + 2, Math.max(1, colW - 0.5), rowH - 4);
      }}
    }}
    ctx.globalAlpha = 1.0;
    // current tick cursor
    const cursorX = tick * colW + colW / 2;
    ctx.strokeStyle = '#222';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(cursorX, 0);
    ctx.lineTo(cursorX, h);
    ctx.stroke();
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
    drawHeatmap(tick);
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

  document.addEventListener('keydown', e => {{
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (e.key === ' ' || e.key === 'Spacebar') {{ e.preventDefault(); togglePlay(); }}
    else if (e.key === 'ArrowLeft') {{ pause(); setTick(currentTick - 1, true); }}
    else if (e.key === 'ArrowRight') {{ pause(); setTick(currentTick + 1, true); }}
  }});

  // ---------- bootstrap ----------
  cy.ready(function() {{
    cy.fit(undefined, 30);
    setTick(0, false);
  }});
  window.addEventListener('resize', () => drawHeatmap(currentTick));
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
    heatmap = compute_event_heatmap(events)

    return _HTML_TEMPLATE.format(
        title=html.escape(title),
        outcome=html.escape(outcome),
        last_tick=last_tick,
        max_tick=max_tick,
        total_events=len(events),
        player_summary=html.escape(player_summary),
        css=_VIEWER_CSS,
        event_log_html=_build_event_log_html(by_tick, players),
        cytoscape_js=cytoscape_js_src,
        viewer_js=_VIEWER_JS_TEMPLATE.format(
            scenario_data_json=json.dumps(scenario_topology, ensure_ascii=False),
            players_json=json.dumps(players, ensure_ascii=False),
            position_timeline_json=json.dumps(position_timeline, ensure_ascii=False),
            memo_timeline_json=json.dumps(memo_timeline, ensure_ascii=False),
            heatmap_json=json.dumps(heatmap, ensure_ascii=False),
            events_by_tick_json=json.dumps({}, ensure_ascii=False),  # 現状未使用 (将来用)
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
        for e in evs:
            kind = e.kind
            pname = (
                name_by_pid.get(e.player_id, f"#{e.player_id}")
                if e.player_id is not None
                else "—"
            )
            body = _format_event_body(e)
            classes = f"event-row kind-{html.escape(kind)}"
            if (
                kind == TraceEventKind.ACTION_RESULT
                and isinstance(e.payload, dict)
                and e.payload.get("success") is False
            ):
                classes += " failed"
            rows.append(
                f'<div class="{classes}">'
                f'<span class="event-kind">{html.escape(kind)}</span>'
                f'<span class="event-player">{html.escape(str(pname))}</span>'
                f'<span class="event-body">{body}</span>'
                f"</div>"
            )
        tick_attr = "" if tick is None else f' data-tick="{int(tick)}"'
        parts.append(
            f'<div class="tick-block"{tick_attr}>'
            f'<div class="tick-header">{html.escape(tick_label)}</div>'
            f"{''.join(rows)}</div>"
        )
    return "".join(parts)


def _format_event_body(e: TraceEvent) -> str:
    """event の payload を 1 行サマリに整形する (HTML escape 済み)。"""
    payload = e.payload if isinstance(e.payload, dict) else {}

    def esc(s: Any) -> str:
        return html.escape(str(s))

    if e.kind == TraceEventKind.OBSERVATION:
        prose = payload.get("prose") or ""
        return esc(prose)
    if e.kind == TraceEventKind.ACTION:
        tool = payload.get("tool") or "?"
        args = payload.get("arguments")
        args_str = (
            json.dumps(args, ensure_ascii=False)[:120]
            if isinstance(args, (dict, list))
            else ""
        )
        return f"<code>{esc(tool)}</code>" + (f" {esc(args_str)}" if args_str else "")
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
    # fallback: 全 payload を 1 行 JSON
    return f"<code>{esc(json.dumps(payload, ensure_ascii=False))}</code>"


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
