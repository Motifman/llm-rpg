#!/usr/bin/env python3
"""trace.jsonl からエピソード記憶可視化 HTML を生成する。

実験 #26 (#384) で user feedback として「エピソード記憶を可視化したい (別ページ)」
が出たため、メイン viewer (build_trace_viewer.py) と独立の別ページを生成。

可視化内容:
- player ごとにエピソード一覧 (chunk written)
- 各 episode の boundary_reason / cues / recall_text_snippet
- subjective_filled の latency と 確定 recall_text
- 各 episode の recall 履歴 (誰がいつ何 candidate でこれを思い出したか)

使い方::

    python scripts/build_episodic_viewer.py var/runs/exp26_on_full_r1 \\
        --output var/runs/exp26_on_full_r1/episodic.html
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class Episode:
    """1 chunk + その後の subjective fill + recall 履歴をまとめた集約。"""

    episode_id: str
    player_id: Optional[int]
    written_tick: Optional[int]
    boundary_reason: str
    cues: List[str]
    written_snippet: str
    action_count: int
    observation_count: int
    # subjective fill (LLM 補完) の情報。未 fill ならすべて None。
    subjective_latency_ms: Optional[int] = None
    subjective_snippet: Optional[str] = None
    subjective_tick: Optional[int] = None
    # この episode が candidate になった recall 履歴
    # [{tick, player_id, was_first}]
    recalled_in: List[Dict[str, Any]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.recalled_in is None:
            self.recalled_in = []


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


def aggregate_episodes(events: List[Dict[str, Any]]) -> List[Episode]:
    """episodic_chunk_written / _subjective_filled / _recall を 1 episode_id ごとに集約。"""
    by_id: Dict[str, Episode] = {}
    for e in events:
        kind = e.get("kind")
        payload = e.get("payload") or {}
        if kind == "episodic_chunk_written":
            eid = payload.get("episode_id") or ""
            if not eid:
                continue
            by_id[eid] = Episode(
                episode_id=eid,
                player_id=e.get("player_id"),
                written_tick=e.get("tick"),
                boundary_reason=payload.get("boundary_reason") or "?",
                cues=list(payload.get("cues") or []),
                written_snippet=payload.get("recall_text_snippet") or "",
                action_count=int(payload.get("action_count") or 0),
                observation_count=int(payload.get("observation_count") or 0),
            )
        elif kind == "episodic_subjective_filled":
            eid = payload.get("episode_id") or ""
            ep = by_id.get(eid)
            if ep is None:
                continue
            ep.subjective_latency_ms = payload.get("latency_ms")
            ep.subjective_snippet = payload.get("recall_text_snippet")
            ep.subjective_tick = e.get("tick")
        elif kind == "episodic_recall":
            candidates = payload.get("candidates") or []
            for i, c in enumerate(candidates):
                eid = c.get("episode_id") or ""
                ep = by_id.get(eid)
                if ep is None:
                    continue
                ep.recalled_in.append({
                    "tick": e.get("tick"),
                    "player_id": e.get("player_id"),
                    "rank": i,  # 候補リスト内の順位
                    "snippet": c.get("recall_text_snippet") or "",
                })
    return list(by_id.values())


def render_html(episodes: List[Episode], title: str) -> str:
    """エピソード記憶ビューの HTML を返す。

    レイアウト:
    - player タブで切り替え
    - 各 player の下に episode カード列
    - カードに recall 履歴付き
    """
    # player ごとに分類
    by_player: Dict[Optional[int], List[Episode]] = defaultdict(list)
    for ep in episodes:
        by_player[ep.player_id].append(ep)
    for v in by_player.values():
        v.sort(key=lambda e: e.written_tick or 0)

    player_ids = sorted(
        [pid for pid in by_player.keys() if pid is not None]
    ) + ([None] if None in by_player else [])

    def esc(s: Any) -> str:
        return html.escape(str(s))

    def render_recall_pill(r: Dict[str, Any]) -> str:
        return (
            f'<span class="recall-pill">'
            f't={esc(r["tick"])} '
            f'<span class="recall-rank">#{esc(r["rank"]+1)}</span> '
            f'by P{esc(r["player_id"])}'
            f'</span>'
        )

    def render_episode_card(ep: Episode) -> str:
        cues_html = "".join(
            f'<span class="cue-pill">{esc(c)}</span>' for c in ep.cues[:8]
        )
        if len(ep.cues) > 8:
            cues_html += f'<span class="cue-pill more">+{len(ep.cues)-8}</span>'

        sub_block = ""
        if ep.subjective_snippet:
            sub_block = (
                f'<div class="subjective">'
                f'<div class="sub-label">'
                f'  subjective fill <span class="meta">'
                f't={esc(ep.subjective_tick)} • '
                f'{esc(ep.subjective_latency_ms)}ms</span>'
                f'</div>'
                f'<div class="sub-text">{esc(ep.subjective_snippet)}</div>'
                f'</div>'
            )

        recall_block = ""
        if ep.recalled_in:
            # 最大 10 件まで表示
            shown = sorted(
                ep.recalled_in, key=lambda r: (r["tick"], r["rank"])
            )[:10]
            extra = len(ep.recalled_in) - len(shown)
            pills = " ".join(render_recall_pill(r) for r in shown)
            extra_str = (
                f'<span class="recall-pill more">+{extra} more</span>'
                if extra > 0 else ""
            )
            recall_block = (
                f'<div class="recalls">'
                f'<span class="recall-label">recalled {len(ep.recalled_in)}×:</span> '
                f'{pills}{extra_str}'
                f'</div>'
            )

        return (
            f'<div class="episode-card">'
            f'  <div class="card-header">'
            f'    <span class="tick-badge">tick {esc(ep.written_tick)}</span>'
            f'    <span class="reason-badge reason-{esc(ep.boundary_reason)}">'
            f'      {esc(ep.boundary_reason)}'
            f'    </span>'
            f'    <span class="counts">'
            f'      {esc(ep.action_count)}act / {esc(ep.observation_count)}obs'
            f'    </span>'
            f'    <span class="ep-id">{esc(ep.episode_id[:8])}…</span>'
            f'  </div>'
            f'  <div class="cues">{cues_html}</div>'
            f'  <div class="written-snippet">{esc(ep.written_snippet)}</div>'
            f'  {sub_block}'
            f'  {recall_block}'
            f'</div>'
        )

    tabs_html = ""
    panels_html = ""
    for idx, pid in enumerate(player_ids):
        label = f"player {pid}" if pid is not None else "system"
        active_cls = " active" if idx == 0 else ""
        tabs_html += (
            f'<button class="tab{active_cls}" data-target="panel-{idx}">'
            f'  {esc(label)}'
            f'  <span class="ep-count">({len(by_player[pid])})</span>'
            f'</button>'
        )
        cards = "".join(render_episode_card(ep) for ep in by_player[pid])
        if not cards:
            cards = '<div class="empty">(no episodes)</div>'
        panels_html += (
            f'<div class="panel{active_cls}" id="panel-{idx}">'
            f'  {cards}'
            f'</div>'
        )

    css = """
:root {
  --bg: #061015;
  --panel-bg: linear-gradient(180deg, rgba(18, 35, 42, 0.96), rgba(8, 17, 22, 0.96));
  --line: #245358;
  --text: #d6e8e9;
  --muted: #6d7f80;
  --cyan: #35d4e6;
  --green: #a3e063;
  --orange: #ffce63;
  --pink: #f08ec1;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: radial-gradient(circle at 22% 12%, rgba(53, 212, 230, 0.12), transparent 18rem),
    linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px),
    #061015;
  background-size: auto, 34px 34px, 34px 34px, auto;
  color: var(--text);
  font-family: ui-sans-serif, system-ui, "Hiragino Sans", "Yu Gothic UI", sans-serif;
  font-size: 0.92rem;
  line-height: 1.5;
}
header {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--line);
  background: rgba(8, 17, 22, 0.5);
}
header h1 {
  margin: 0;
  font-size: 1.05rem;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  letter-spacing: 0.06em;
  color: #ffe0a0;
}
.tabs {
  display: flex;
  gap: 0.5rem;
  padding: 0.6rem 1.5rem;
  background: rgba(8, 17, 22, 0.4);
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}
.tab {
  background: rgba(30, 82, 89, 0.55);
  border: 1px solid var(--line);
  color: var(--text);
  padding: 0.35rem 0.75rem;
  border-radius: 4px;
  font-size: 0.78rem;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  cursor: pointer;
  letter-spacing: 0.04em;
}
.tab:hover { background: rgba(53, 212, 230, 0.22); }
.tab.active {
  background: rgba(53, 212, 230, 0.35);
  border-color: var(--cyan);
  color: #fff;
}
.ep-count { color: var(--muted); margin-left: 0.25rem; font-size: 0.7rem; }
main { padding: 1.5rem; }
.panel { display: none; }
.panel.active { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 1rem; }
.empty { color: var(--muted); padding: 2rem; text-align: center; font-style: italic; }
.episode-card {
  background: var(--panel-bg);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 0.85rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.72rem;
  flex-wrap: wrap;
}
.tick-badge {
  font-family: "JetBrains Mono", monospace;
  background: rgba(53, 212, 230, 0.2);
  color: var(--cyan);
  padding: 0.12rem 0.4rem;
  border-radius: 3px;
  font-weight: bold;
}
.reason-badge {
  padding: 0.12rem 0.4rem;
  border-radius: 3px;
  font-size: 0.65rem;
  letter-spacing: 0.04em;
  background: rgba(255, 206, 99, 0.18);
  color: var(--orange);
}
.reason-badge.reason-category_shift { background: rgba(163, 224, 99, 0.18); color: var(--green); }
.reason-badge.reason-scene_boundary_action { background: rgba(240, 142, 193, 0.18); color: var(--pink); }
.reason-badge.reason-temporal_gap { background: rgba(255, 159, 100, 0.18); color: #ff9f64; }
.reason-badge.reason-structured_keys_changed { background: rgba(120, 160, 255, 0.18); color: #78a0ff; }
.counts { color: var(--muted); font-family: "JetBrains Mono", monospace; }
.ep-id {
  margin-left: auto;
  color: var(--muted);
  font-family: "JetBrains Mono", monospace;
  font-size: 0.65rem;
}
.cues { display: flex; flex-wrap: wrap; gap: 0.25rem; }
.cue-pill {
  background: rgba(120, 160, 255, 0.12);
  color: #aac5ff;
  padding: 0.1rem 0.35rem;
  font-size: 0.65rem;
  border-radius: 3px;
  font-family: "JetBrains Mono", monospace;
}
.cue-pill.more { color: var(--muted); background: transparent; }
.written-snippet {
  color: #cfdedf;
  font-size: 0.85rem;
  padding: 0.4rem 0.6rem;
  background: rgba(0,0,0,0.2);
  border-left: 2px solid rgba(53, 212, 230, 0.5);
  border-radius: 3px;
  line-height: 1.55;
}
.subjective {
  background: rgba(163, 224, 99, 0.05);
  border-left: 2px solid var(--green);
  padding: 0.4rem 0.6rem;
  border-radius: 3px;
}
.sub-label {
  font-size: 0.7rem;
  font-family: "JetBrains Mono", monospace;
  color: var(--green);
  margin-bottom: 0.25rem;
  letter-spacing: 0.04em;
}
.sub-label .meta { color: var(--muted); font-weight: normal; margin-left: 0.5rem; }
.sub-text {
  color: #d8eac5;
  font-size: 0.86rem;
  line-height: 1.55;
}
.recalls {
  border-top: 1px dashed rgba(255, 206, 99, 0.3);
  padding-top: 0.5rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  align-items: center;
}
.recall-label {
  font-size: 0.7rem;
  color: var(--orange);
  font-family: "JetBrains Mono", monospace;
  letter-spacing: 0.04em;
  margin-right: 0.25rem;
}
.recall-pill {
  background: rgba(255, 206, 99, 0.12);
  color: #ffd980;
  padding: 0.1rem 0.4rem;
  font-size: 0.65rem;
  border-radius: 3px;
  font-family: "JetBrains Mono", monospace;
}
.recall-pill.more { background: transparent; color: var(--muted); }
.recall-pill .recall-rank {
  color: var(--orange);
  font-weight: bold;
}
"""

    js = """
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const target = tab.getAttribute('data-target');
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const panel = document.getElementById(target);
    if (panel) panel.classList.add('active');
  });
});
"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>{esc(title)} - Episodic Memory</title>
<style>{css}</style>
</head>
<body>
<header>
  <h1>{esc(title)} - Episodic Memory</h1>
</header>
<nav class="tabs">{tabs_html}</nav>
<main>{panels_html}</main>
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
    episodes = aggregate_episodes(events)

    title = args.title or args.run_dir.name
    html_text = render_html(episodes, title)

    output = args.output or (args.run_dir / "episodic.html")
    output.write_text(html_text, encoding="utf-8")
    print(f"[episodic] {output} ({len(html_text)//1024} KB, {len(episodes)} episodes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
