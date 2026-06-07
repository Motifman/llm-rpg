#!/usr/bin/env python3
"""trace.jsonl からプレイヤー × 時間軸タイムライン HTML を生成する。

設計改修 (PR #1 後続): hover に隠さず、1 セルに **行動内容 / 発話内容 /
観測 prose** を直書きする。tick を縦軸、player を横カラムに置く tabular
レイアウトで、上から下に時間順スクロールできる。発火 event がない tick は
スキップして読みやすくする。

旧実装 (横軸 = tick, ACT/OBS 記号のみ) は「一目で何が起きたか分からない」
というユーザ feedback (実験 #29 OFF 分析) を受けた書き換え。

使い方::

    python scripts/build_timeline_viewer.py var/runs/exp29_off_r1 \\
        --output var/runs/exp29_off_r1/timeline.html
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# 表示する event kind と色 + ラベル
EVENT_STYLES: Dict[str, Dict[str, str]] = {
    "action": {"color": "#35d4e6", "label": "ACT"},
    "observation": {"color": "#b89dff", "label": "OBS"},
    "memo_add": {"color": "#a3e063", "label": "M+"},
    "memo_done": {"color": "#7fc24a", "label": "M✓"},
    "position_change": {"color": "#65dce8", "label": "MV"},
    "episodic_chunk_written": {"color": "#ffce63", "label": "EW"},
    "episodic_recall": {"color": "#ff9f64", "label": "ER"},
}

# event kind ごとの表示順 (同 tick 内で並べる順序)。
# 行動 → 観測 → memo → 位置変化 → episodic の順が読みやすい。
KIND_ORDER = {
    "action": 0,
    "observation": 1,
    "memo_add": 2,
    "memo_done": 2,
    "position_change": 3,
    "episodic_chunk_written": 4,
    "episodic_recall": 4,
}


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
    """events から (id, name) を返す。位置変化 / action / observation 等で
    payload.player_name が立っているものを優先採用する。
    """
    ids: Dict[int, str] = {}
    for e in events:
        pid = e.get("player_id")
        if pid is None:
            continue
        ids.setdefault(pid, "")
        payload = e.get("payload") or {}
        name = payload.get("player_name") or ""
        if name and not ids[pid]:
            ids[pid] = name
    return [
        {"id": pid, "name": ids[pid] or f"P{pid}"}
        for pid in sorted(ids)
    ]


def build_cells(
    events: List[Dict[str, Any]],
) -> Dict[int, List[Dict[str, Any]]]:
    """player_id → cells (tick / kind / detail) の list を返す (旧 API 互換)。"""
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
    """1 行で内容が読める要約を返す。

    旧実装は短い (~60 chars) tooltip 想定だったが、改修後は行に直書きするので
    やや長め (~200 chars) でも問題ない。speech_say は content を最優先に含める。
    """
    if kind == "action":
        tool = payload.get("tool") or "?"
        args = payload.get("arguments") or {}
        if not isinstance(args, dict):
            return tool
        # speech_say / speech_whisper / speech_shout は content を最優先で見せる
        if isinstance(tool, str) and tool.startswith("speech_"):
            content = (args.get("content") or "").strip()
            target = args.get("target_label") or ""
            verb = {"speech_say": "say", "speech_whisper": "whisper", "speech_shout": "shout"}.get(
                tool, "speech"
            )
            head = f"{verb}"
            if target:
                head += f"→{target}"
            return f"{head}: 「{content[:160]}」" if content else head
        # memo 系
        if tool in ("memo_add",):
            text = (args.get("content") or args.get("text") or "").strip()
            return f"memo_add: {text[:160]}"
        # 汎用 action: tool 名 + 主要引数 + inner_thought 先頭
        main_args = []
        for key in (
            "destination_label",
            "destination_spot_id",
            "object_label",
            "item_label",
            "target_label",
            "target_player_label",
            "ground_item_label",
            "sub_location_label",
            "action_name",
        ):
            v = args.get(key)
            if v:
                main_args.append(f"{key}={v}")
        head = tool
        if main_args:
            head += f"({', '.join(main_args)})"
        inner = (args.get("inner_thought") or "").strip()
        if inner:
            head += f" — 内心: {inner[:120]}"
        return head
    if kind == "observation":
        prose = (payload.get("prose") or "").strip()
        cat = payload.get("observation_category") or ""
        head = f"[{cat}] " if cat else ""
        return f"{head}{prose[:200]}"
    if kind == "memo_add":
        text = (payload.get("content") or "").strip()
        return f"+ {text[:160]}"
    if kind == "memo_done":
        memo_id = str(payload.get("memo_id") or "")[:12]
        return f"done id={memo_id}"
    if kind == "position_change":
        from_spot = payload.get("from_spot_id") or "spawn"
        to_spot = payload.get("spot_name") or payload.get("to_spot_id") or "?"
        return f"{from_spot} → {to_spot}"
    if kind == "episodic_chunk_written":
        reason = payload.get("boundary_reason") or "?"
        snippet = (payload.get("recall_text_snippet") or "").strip()
        return f"{reason}: {snippet[:160]}"
    if kind == "episodic_recall":
        n = payload.get("candidate_count", 0)
        cands = payload.get("candidates") or []
        first = ""
        if cands and isinstance(cands, list) and isinstance(cands[0], dict):
            first = (cands[0].get("recall_text_snippet") or "").strip()
        return f"{n} candidates" + (f" — top: {first[:120]}" if first else "")
    return ""


def render_html(
    events: List[Dict[str, Any]],
    title: str,
) -> str:
    players = extract_players(events)
    cells_by_player = build_cells(events)

    # tick → player_id → [cell] に再編する。
    by_tick_player: Dict[int, Dict[int, List[Dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for pid, cells in cells_by_player.items():
        for c in cells:
            by_tick_player[c["tick"]][pid].append(c)

    # 各 tick 内の cell を kind 優先度順 → 元の順序 でソートする (安定)。
    for tdict in by_tick_player.values():
        for pid in list(tdict.keys()):
            tdict[pid].sort(key=lambda c: KIND_ORDER.get(c["kind"], 99))

    sorted_ticks = sorted(by_tick_player.keys())

    def esc(s: Any) -> str:
        return html.escape(str(s))

    # ────────── 各 tick block を組み立てる ──────────
    tick_blocks: List[str] = []
    for t in sorted_ticks:
        per_player_cols: List[str] = []
        for p in players:
            cells = by_tick_player[t].get(p["id"], [])
            cell_html: List[str] = []
            for c in cells:
                style = EVENT_STYLES[c["kind"]]
                cell_html.append(
                    f'<div class="cell kind-{esc(c["kind"])}" '
                    f'data-kind="{esc(c["kind"])}">'
                    f'<span class="badge" style="background:{style["color"]}">'
                    f'{esc(style["label"])}</span>'
                    f'<span class="text">{esc(c["detail"])}</span>'
                    f'</div>'
                )
            if not cell_html:
                cell_html = ['<div class="cell empty">—</div>']
            per_player_cols.append(
                f'<div class="player-col">{"".join(cell_html)}</div>'
            )
        tick_blocks.append(
            f'<div class="tick-row" id="t{t}">'
            f'<div class="tick-label">t={t}</div>'
            f'<div class="player-grid">{"".join(per_player_cols)}</div>'
            f'</div>'
        )

    # player ヘッダー列 (sticky top で表示)
    player_headers_html = "".join(
        f'<div class="player-header">'
        f'<span class="pl-name">{esc(p["name"])}</span>'
        f'<span class="pl-id">#{esc(p["id"])}</span>'
        f'</div>'
        for p in players
    )

    legend_html = "".join(
        f'<div class="legend-item">'
        f'<span class="legend-swatch" style="background:{s["color"]}"></span>'
        f'<span class="legend-label">{esc(s["label"])} = {esc(k)}</span>'
        f'</div>'
        for k, s in EVENT_STYLES.items()
    )

    player_count = max(1, len(players))

    css = f"""
:root {{
  --bg: #061015;
  --line: #245358;
  --text: #d6e8e9;
  --muted: #6d7f80;
  --cyan: #35d4e6;
  --tick-label-w: 80px;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background:
    radial-gradient(circle at 22% 12%, rgba(53, 212, 230, 0.10), transparent 22rem),
    linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px),
    #061015;
  background-size: auto, 34px 34px, 34px 34px, auto;
  color: var(--text);
  font-family: ui-sans-serif, system-ui, "Hiragino Sans", "Yu Gothic UI", sans-serif;
  font-size: 0.92rem;
}}
header {{
  padding: 0.85rem 1.2rem;
  border-bottom: 1px solid var(--line);
  background: rgba(8, 17, 22, 0.92);
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  position: sticky;
  top: 0;
  z-index: 10;
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

.player-header-row {{
  display: grid;
  grid-template-columns: var(--tick-label-w) repeat({player_count}, minmax(0, 1fr));
  position: sticky;
  top: 0;
  z-index: 5;
  background: rgba(8, 17, 22, 0.95);
  border-bottom: 1px solid var(--line);
  padding: 0.4rem 0;
}}
.player-header-row .corner {{
  font-size: 0.7rem;
  color: var(--muted);
  padding: 0 0.6rem;
  display: flex;
  align-items: center;
}}
.player-header {{
  padding: 0.2rem 0.8rem;
  border-left: 1px solid rgba(36, 83, 88, 0.4);
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}}
.player-header .pl-name {{ font-weight: 600; color: var(--text); }}
.player-header .pl-id {{ font-size: 0.7rem; color: var(--muted); font-family: monospace; }}

.tick-row {{
  display: grid;
  grid-template-columns: var(--tick-label-w) 1fr;
  border-bottom: 1px solid rgba(36, 83, 88, 0.3);
  min-height: 36px;
}}
.tick-row:hover {{
  background: rgba(53, 212, 230, 0.04);
}}
.tick-label {{
  padding: 0.45rem 0.6rem;
  font-family: "JetBrains Mono", monospace;
  font-size: 0.8rem;
  color: var(--cyan);
  border-right: 1px solid rgba(36, 83, 88, 0.5);
  background: rgba(8, 17, 22, 0.5);
  display: flex;
  align-items: flex-start;
}}
.player-grid {{
  display: grid;
  grid-template-columns: repeat({player_count}, minmax(0, 1fr));
}}
.player-col {{
  padding: 0.3rem 0.5rem;
  border-left: 1px solid rgba(36, 83, 88, 0.25);
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}}
.player-col:first-child {{ border-left: none; }}

.cell {{
  display: flex;
  gap: 0.4rem;
  align-items: flex-start;
  font-size: 0.78rem;
  line-height: 1.35;
  word-break: break-word;
  overflow-wrap: anywhere;
}}
.cell .badge {{
  flex: 0 0 auto;
  font-family: "JetBrains Mono", monospace;
  font-size: 0.62rem;
  font-weight: 700;
  padding: 0.05rem 0.35rem;
  border-radius: 3px;
  color: #061015;
  letter-spacing: 0.04em;
}}
.cell .text {{
  flex: 1 1 auto;
  color: var(--text);
}}
.cell.empty {{
  font-size: 0.7rem;
  color: rgba(109, 127, 128, 0.6);
}}

/* kind 別の細かい強調 */
.cell.kind-action .text {{ color: #d8f6ff; }}
.cell.kind-observation .text {{ color: #d8c8ff; }}
.cell.kind-memo_add .text, .cell.kind-memo_done .text {{ color: #cee8a8; }}
.cell.kind-position_change .text {{ color: #c8effd; }}
.cell.kind-episodic_chunk_written .text,
.cell.kind-episodic_recall .text {{ color: #ffd9a3; }}
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
<div class="player-header-row">
  <div class="corner">tick ↓ / player →</div>
  {player_headers_html}
</div>
<div class="tick-header">
  {''.join(tick_blocks)}
</div>
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
    sys.exit(main())
