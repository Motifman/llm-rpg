#!/usr/bin/env python3
"""trace.jsonl からプレイヤー × 時間軸タイムライン HTML を生成する。

実験 #26 (#384) user feedback として「プレイヤーと時間軸のグラフを作り、
そこに行動や言動、観測などの箱を置いて時間軸方向にスクロールして
時間軸上で出来事を確認できるページが欲しい」が出たため作成。

レイアウト:
- 縦軸: 各 player を行に
- 横軸: tick (左 → 右)
- 各 cell: action / observation / speech 等を色付き box で表示
- hover で詳細 tooltip
- 横スクロール可能

使い方::

    python scripts/build_timeline_viewer.py var/runs/exp26_on_full_r1 \\
        --output var/runs/exp26_on_full_r1/timeline.html
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# 1 tick 分の cell 幅 (px)
TICK_WIDTH = 22
# 1 player 行の高さ (px)
ROW_HEIGHT = 80
# 表示する event kind と色 + ラベル
EVENT_STYLES: Dict[str, Dict[str, str]] = {
    "action": {"color": "#35d4e6", "label": "ACT", "row": "action"},
    "observation": {"color": "#b89dff", "label": "OBS", "row": "observation"},
    "memo_add": {"color": "#a3e063", "label": "M+", "row": "memo"},
    "memo_done": {"color": "#a3e063", "label": "M✓", "row": "memo"},
    "position_change": {"color": "#65dce8", "label": "MV", "row": "move"},
    "episodic_chunk_written": {"color": "#ffce63", "label": "EW", "row": "episodic"},
    "episodic_recall": {"color": "#ff9f64", "label": "ER", "row": "episodic"},
}
# row 名 → y 内 offset (player 内の 4 段)
SUB_ROW_OFFSETS = {
    "action": 0,
    "observation": 1,
    "memo": 2,
    "move": 3,
    "episodic": 3,  # 同じ段で OK (memo と排他的)
}
NUM_SUB_ROWS = 4
SUB_ROW_HEIGHT = ROW_HEIGHT / NUM_SUB_ROWS


def load_events(trace_path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with trace_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def extract_players(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """events から player_id を見つけて (id, name) を返す。

    名前は position_change.payload.player_name 等から拾う。1 つでも名前が
    見つかったらそれを優先 (= 後の event の name で上書き)、見つからなければ
    fallback で "P{id}"。
    """
    ids: Dict[int, str] = {}
    for e in events:
        pid = e.get("player_id")
        if pid is None:
            continue
        ids.setdefault(pid, "")
        payload = e.get("payload") or {}
        name = payload.get("player_name") or ""
        # 名前が見つかったら採用 (空のまま上書きはしない)
        if name and not ids[pid]:
            ids[pid] = name
    return [
        {"id": pid, "name": ids[pid] or f"P{pid}"}
        for pid in sorted(ids)
    ]


def build_cells(
    events: List[Dict[str, Any]],
) -> Dict[int, List[Dict[str, Any]]]:
    """player_id → cells (tick / kind / detail) の list を返す。"""
    by_player: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for e in events:
        kind = e.get("kind")
        if kind not in EVENT_STYLES:
            continue
        pid = e.get("player_id")
        tick = e.get("tick")
        if pid is None or tick is None:
            continue
        payload = e.get("payload") or {}
        detail = _summarize(kind, payload)
        by_player[pid].append({
            "tick": int(tick),
            "kind": kind,
            "detail": detail,
        })
    return by_player


def _summarize(kind: str, payload: Dict[str, Any]) -> str:
    if kind == "action":
        tool = payload.get("tool") or "?"
        args = payload.get("arguments") or {}
        inner = ""
        if isinstance(args, dict):
            inner = (args.get("inner_thought") or "")[:80]
        return f"{tool}" + (f": {inner}…" if inner else "")
    if kind == "observation":
        return (payload.get("prose") or "")[:120]
    if kind == "memo_add":
        return f"+ {payload.get('content', '')[:60]}"
    if kind == "memo_done":
        return f"done id={payload.get('memo_id', '')[:8]}"
    if kind == "position_change":
        return f"{payload.get('from_spot_id', 'spawn')} → {payload.get('spot_name', '?')}"
    if kind == "episodic_chunk_written":
        return f"{payload.get('boundary_reason', '?')}: {(payload.get('recall_text_snippet') or '')[:80]}…"
    if kind == "episodic_recall":
        return f"{payload.get('candidate_count', 0)} candidates"
    return ""


def render_html(
    events: List[Dict[str, Any]],
    title: str,
) -> str:
    players = extract_players(events)
    cells_by_player = build_cells(events)
    max_tick = max(
        (int(e.get("tick") or 0) for e in events if e.get("tick") is not None),
        default=0,
    )

    def esc(s: Any) -> str:
        return html.escape(str(s))

    # 各 player row を描画
    player_rows_html: List[str] = []
    grid_width = max(TICK_WIDTH * (max_tick + 1), 1200)
    for p in players:
        cells = cells_by_player.get(p["id"], [])
        cell_html = []
        for c in cells:
            style = EVENT_STYLES[c["kind"]]
            sub_row = SUB_ROW_OFFSETS.get(style["row"], 0)
            top = sub_row * SUB_ROW_HEIGHT
            left = c["tick"] * TICK_WIDTH
            cell_html.append(
                f'<div class="cell kind-{esc(c["kind"])}" '
                f'style="left:{left}px;top:{top}px;'
                f'background:{style["color"]}" '
                f'data-detail="{esc(c["detail"])}" '
                f'data-tick="{c["tick"]}" '
                f'data-kind="{esc(c["kind"])}">'
                f'{esc(style["label"])}'
                f'</div>'
            )
        player_rows_html.append(
            f'<div class="player-row" style="height:{ROW_HEIGHT}px">'
            f'  <div class="player-cells" style="width:{grid_width}px">'
            f'    {"".join(cell_html)}'
            f'  </div>'
            f'</div>'
        )

    # player ラベル列 (sticky left)
    player_labels_html = "".join(
        f'<div class="player-label" style="height:{ROW_HEIGHT}px">'
        f'  <span class="pl-name">{esc(p["name"])}</span>'
        f'  <span class="pl-id">#{esc(p["id"])}</span>'
        f'</div>'
        for p in players
    )

    # tick ticks header (左端固定 + 横スクロール)
    tick_marks = []
    step = 5  # 5 tick ごとに目盛
    for t in range(0, max_tick + 1, step):
        tick_marks.append(
            f'<div class="tick-mark" style="left:{t*TICK_WIDTH}px">t={t}</div>'
        )
    tick_header_html = "".join(tick_marks)

    legend_html = "".join(
        f'<div class="legend-item">'
        f'<span class="legend-swatch" style="background:{s["color"]}"></span>'
        f'<span class="legend-label">{esc(s["label"])} = {esc(k)}</span>'
        f'</div>'
        for k, s in EVENT_STYLES.items()
    )

    css = f"""
:root {{
  --bg: #061015;
  --line: #245358;
  --text: #d6e8e9;
  --muted: #6d7f80;
  --cyan: #35d4e6;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background:
    radial-gradient(circle at 22% 12%, rgba(53, 212, 230, 0.12), transparent 18rem),
    linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px),
    #061015;
  background-size: auto, 34px 34px, 34px 34px, auto;
  color: var(--text);
  font-family: ui-sans-serif, system-ui, "Hiragino Sans", "Yu Gothic UI", sans-serif;
  font-size: 0.92rem;
}}
header {{
  padding: 0.85rem 1.2rem;
  border-bottom: 1px solid var(--line);
  background: rgba(8, 17, 22, 0.5);
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}}
header h1 {{
  margin: 0;
  font-size: 1rem;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  letter-spacing: 0.06em;
  color: #ffe0a0;
}}
.legend {{ display: flex; gap: 0.8rem; flex-wrap: wrap; font-size: 0.72rem; }}
.legend-item {{ display: flex; align-items: center; gap: 0.25rem; color: var(--muted); }}
.legend-swatch {{ width: 12px; height: 12px; border-radius: 2px; display: inline-block; }}
.legend-label {{ font-family: "JetBrains Mono", monospace; }}

#timeline-container {{
  display: grid;
  grid-template-columns: 130px 1fr;
  position: relative;
}}
.player-labels {{
  position: sticky;
  left: 0;
  z-index: 2;
  background: rgba(8, 17, 22, 0.95);
  border-right: 1px solid var(--line);
}}
.player-label {{
  padding: 0.4rem 0.6rem;
  border-bottom: 1px solid rgba(36, 83, 88, 0.4);
  display: flex;
  flex-direction: column;
  justify-content: center;
}}
.pl-name {{ font-weight: 600; color: var(--text); }}
.pl-id {{ font-size: 0.7rem; color: var(--muted); font-family: monospace; }}

.scroll-area {{
  overflow-x: auto;
  overflow-y: hidden;
  position: relative;
}}
.tick-header {{
  height: 22px;
  position: relative;
  border-bottom: 1px solid var(--line);
  background: rgba(8, 17, 22, 0.8);
  width: {grid_width}px;
}}
.tick-mark {{
  position: absolute;
  top: 4px;
  font-size: 0.65rem;
  color: var(--muted);
  font-family: monospace;
  transform: translateX(-50%);
}}
.player-rows {{
  position: relative;
}}
.player-row {{
  position: relative;
  border-bottom: 1px solid rgba(36, 83, 88, 0.4);
}}
.player-cells {{
  position: relative;
  height: 100%;
}}
.cell {{
  position: absolute;
  width: {TICK_WIDTH - 2}px;
  height: {SUB_ROW_HEIGHT - 1}px;
  color: #061015;
  font-family: "JetBrains Mono", monospace;
  font-size: 0.6rem;
  font-weight: bold;
  text-align: center;
  line-height: {SUB_ROW_HEIGHT - 1}px;
  border-radius: 2px;
  cursor: pointer;
  overflow: hidden;
  white-space: nowrap;
  text-shadow: 0 0 2px rgba(0,0,0,0.3);
  opacity: 0.85;
  transition: opacity 0.15s;
}}
.cell:hover {{
  opacity: 1;
  z-index: 5;
  outline: 1px solid #fff;
}}

#tooltip {{
  position: fixed;
  z-index: 100;
  background: rgba(8, 17, 22, 0.96);
  border: 1px solid var(--cyan);
  border-radius: 4px;
  padding: 0.5rem 0.7rem;
  font-size: 0.78rem;
  max-width: 360px;
  pointer-events: none;
  display: none;
  box-shadow: 0 10px 26px rgba(0,0,0,0.4);
}}
#tooltip .tt-tick {{ color: var(--cyan); font-family: monospace; margin-right: 0.5rem; }}
#tooltip .tt-kind {{ color: #ffce63; font-family: monospace; }}
#tooltip .tt-detail {{ margin-top: 0.3rem; color: #d8c8ff; word-break: break-word; }}
"""

    js = """
const tt = document.getElementById('tooltip');
function showTooltip(e, cell) {
  const tick = cell.dataset.tick;
  const kind = cell.dataset.kind;
  const detail = cell.dataset.detail;
  tt.innerHTML =
    '<span class="tt-tick">t=' + tick + '</span>' +
    '<span class="tt-kind">' + kind + '</span>' +
    '<div class="tt-detail">' + detail + '</div>';
  tt.style.display = 'block';
  positionTooltip(e);
}
function positionTooltip(e) {
  const pad = 14;
  let x = e.clientX + pad;
  let y = e.clientY + pad;
  const r = tt.getBoundingClientRect();
  if (x + r.width > window.innerWidth) x = window.innerWidth - r.width - 8;
  if (y + r.height > window.innerHeight) y = e.clientY - r.height - pad;
  tt.style.left = x + 'px';
  tt.style.top = y + 'px';
}
function hideTooltip() { tt.style.display = 'none'; }

document.querySelectorAll('.cell').forEach(cell => {
  cell.addEventListener('mouseenter', (e) => showTooltip(e, cell));
  cell.addEventListener('mousemove', positionTooltip);
  cell.addEventListener('mouseleave', hideTooltip);
});
"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>{esc(title)} - Player × Tick Timeline</title>
<style>{css}</style>
</head>
<body>
<header>
  <h1>{esc(title)} - Player × Tick Timeline</h1>
  <div class="legend">{legend_html}</div>
</header>
<div id="timeline-container">
  <div class="player-labels">
    <div class="player-label" style="height:22px;font-size:0.7rem;color:var(--muted);">tick →</div>
    {player_labels_html}
  </div>
  <div class="scroll-area">
    <div class="tick-header">{tick_header_html}</div>
    <div class="player-rows">{"".join(player_rows_html)}</div>
  </div>
</div>
<div id="tooltip"></div>
<script>{js}</script>
</body>
</html>
"""


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="run directory containing trace.jsonl")
    parser.add_argument("--output", "-o", type=Path, default=None)
    parser.add_argument("--title", type=str, default=None)
    args = parser.parse_args(argv)

    trace = args.run_dir / "trace.jsonl"
    if not trace.exists():
        print(f"trace.jsonl が見つかりません: {trace}", file=sys.stderr)
        return 2

    events = load_events(trace)
    title = args.title or args.run_dir.name
    html_text = render_html(events, title)

    output = args.output or (args.run_dir / "timeline.html")
    output.write_text(html_text, encoding="utf-8")
    print(f"[timeline] {output} ({len(html_text)//1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
