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
    <span>tick: {last_tick} / {max_tick}</span>
    <span>events: {total_events}</span>
    <span>players: {player_summary}</span>
  </div>
</header>

<main>
  <section id="map-section">
    <h2>Map (final state)</h2>
    <div id="cy"></div>
    <p class="legend">Player markers indicate the **final** position. Animation is coming in PR γ.</p>
  </section>

  <section id="log-section">
    <h2>Event timeline</h2>
    <div id="event-log">{event_log_html}</div>
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
  padding: 1rem 1.5rem;
  background: #fff;
  border-bottom: 1px solid #ddd;
}
header h1 { margin: 0 0 0.3rem 0; font-size: 1.2rem; }
.meta { font-size: 0.85rem; color: #666; display: flex; gap: 1.5rem; flex-wrap: wrap; }
.meta strong { color: #222; }
main {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  padding: 1rem;
  height: calc(100vh - 90px);
}
@media (max-width: 900px) {
  main { grid-template-columns: 1fr; height: auto; }
}
section {
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
section h2 {
  margin: 0;
  padding: 0.75rem 1rem;
  font-size: 0.95rem;
  border-bottom: 1px solid #eee;
  background: #f5f5f5;
}
#cy {
  flex: 1;
  min-height: 400px;
  width: 100%;
  background: #fcfcfc;
}
.legend { font-size: 0.8rem; color: #888; padding: 0.5rem 1rem; margin: 0; }
#event-log { flex: 1; overflow-y: auto; padding: 0.5rem 1rem; }
.tick-block { margin-bottom: 0.8rem; padding-bottom: 0.5rem; border-bottom: 1px solid #eee; }
.tick-header { font-weight: bold; color: #555; font-size: 0.85rem; margin-bottom: 0.3rem; }
.event-row {
  font-size: 0.82rem;
  padding: 0.15rem 0;
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
}
.event-kind {
  flex-shrink: 0;
  width: 110px;
  font-family: monospace;
  font-size: 0.75rem;
  color: #777;
}
.event-player {
  flex-shrink: 0;
  width: 60px;
  font-size: 0.78rem;
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
  const playerColors = ['#2e7dd7', '#e07a26', '#5fa14a', '#a155bf'];

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
  // 接続: bidirectional でない場合のみ向き付き矢印。pair が両方ある場合は重複させない
  const seenEdges = new Set();
  for (const c of scenarioData.connections) {{
    const key = c.from + '->' + c.to;
    const rev = c.to + '->' + c.from;
    if (seenEdges.has(key)) continue;
    seenEdges.add(key);
    if (c.bidirectional) seenEdges.add(rev);
    elements.push({{
      data: {{
        id: 'edge:' + key,
        source: 'spot:' + c.from,
        target: 'spot:' + c.to,
      }},
      classes: c.bidirectional ? 'connection bi' : 'connection',
    }});
  }}
  // プレイヤーノードを最終位置スポットに配置
  for (let i = 0; i < players.length; i++) {{
    const p = players[i];
    if (!p.final_spot_id) continue;
    elements.push({{
      data: {{
        id: 'player:' + p.id,
        label: p.name,
        parent: undefined,
      }},
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
        style: {{
          'background-color': color,
          'text-outline-color': color,
        }}
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
      {{
        selector: 'edge.connection.bi',
        style: {{
          'target-arrow-shape': 'none',
        }}
      }},
    ],
    layout: {{
      name: 'cose',
      animate: false,
      idealEdgeLength: 120,
      nodeRepulsion: 8000,
      padding: 30,
    }},
  }});

  // プレイヤーを最終位置スポットの近くに固定配置 (初期 layout 後に手動補正)
  cy.ready(function() {{
    for (const p of players) {{
      if (!p.final_spot_id) continue;
      const spot = cy.getElementById('spot:' + p.final_spot_id);
      const player = cy.getElementById('player:' + p.id);
      if (spot.length && player.length) {{
        const pos = spot.position();
        // 同じスポットに複数いる場合は周囲に散らす
        const i = players.findIndex(x => x.id === p.id);
        const angle = (i * 90) * Math.PI / 180;
        player.position({{
          x: pos.x + 35 * Math.cos(angle),
          y: pos.y + 35 * Math.sin(angle),
        }});
      }}
    }}
    cy.fit(undefined, 30);
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
        parts.append(
            f'<div class="tick-block">'
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
