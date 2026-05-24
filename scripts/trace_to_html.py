"""JSONL Trace を self-contained HTML に変換する CLI (Issue #188 Phase 1d)。

使い方:
    python scripts/trace_to_html.py path/to/trace.jsonl
        → 同じディレクトリに trace.html を出力
    python scripts/trace_to_html.py path/to/trace.jsonl -o out.html
        → 任意の出力先

出力 HTML 構成:
    1. メタ情報 (run_id / 総 tick / プレイヤー一覧 / 総イベント数)
    2. Mermaid sequenceDiagram: プレイヤー間の action / observation を時系列で
    3. tick ごとに collapsible な詳細セクション (memo / hint / inner_thought)

設計指針:
    - 外部 CDN 1 本 (mermaid.min.js) のみで動く 1 ファイル HTML
    - 大規模 trace でも mermaid が落ちないように observation / action のみを
      sequence に出し、その他は per-tick セクションで補う
    - 元 JSONL も <details> 内に raw として埋め込む (検証時に grep できる)
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# 直接実行と `python -m scripts.trace_to_html` 両対応のため src を path に追加
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from ai_rpg_world.application.trace.events import TraceEvent, TraceEventKind
from ai_rpg_world.application.trace.recorder import load_trace_events


MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js"


def render_html(events: List[TraceEvent], *, title: str = "Trace") -> str:
    """TraceEvent 列を self-contained HTML 文字列に変換する。"""
    meta = _collect_meta(events)
    mermaid_src = _build_mermaid_sequence(events, meta["player_labels"])
    per_tick_html = _build_per_tick_sections(events)
    raw_jsonl = "\n".join(
        json.dumps(e.to_jsonable(), ensure_ascii=False) for e in events
    )
    return _HTML_TEMPLATE.format(
        title=html.escape(title),
        total_events=meta["total_events"],
        tick_range=meta["tick_range_label"],
        player_lines=meta["player_html"],
        mermaid_cdn=MERMAID_CDN,
        # NOTE: mermaid_src は HTML エスケープしない。`->>` / `-->>` の `>` が
        # `&gt;` になるとブラウザ環境によっては Mermaid パーサが decode
        # しきれず syntax error を出すため。代わりに `_build_mermaid_sequence`
        # 内でユーザーデータ ('<', '>', '&', '"') を事前にサニタイズしている。
        mermaid_src=mermaid_src,
        # raw_jsonl は html.escape のままで OK (<pre> 内に表示するだけなので)
        mermaid_src_for_fallback=html.escape(mermaid_src),
        per_tick=per_tick_html,
        raw_jsonl=html.escape(raw_jsonl),
    )


def _collect_meta(events: List[TraceEvent]) -> Dict[str, object]:
    """ヘッダに出すメタ情報を集める。"""
    ticks = [e.tick for e in events if e.tick is not None]
    player_ids = sorted({e.player_id for e in events if e.player_id is not None})
    labels: Dict[int, str] = {}
    for e in events:
        if e.player_id is None:
            continue
        name = e.payload.get("player_name") if isinstance(e.payload, dict) else None
        if name and e.player_id not in labels:
            labels[e.player_id] = str(name)
    for pid in player_ids:
        labels.setdefault(pid, f"player_{pid}")
    if ticks:
        tick_range = f"{min(ticks)} 〜 {max(ticks)}"
    else:
        tick_range = "(なし)"
    player_html = "".join(
        f"<li><code>{pid}</code>: {html.escape(labels[pid])}</li>"
        for pid in player_ids
    )
    return {
        "total_events": len(events),
        "tick_range_label": tick_range,
        "player_labels": labels,
        "player_html": player_html or "<li>(なし)</li>",
    }


def _build_mermaid_sequence(
    events: List[TraceEvent], player_labels: Dict[int, str]
) -> str:
    """sequence 図用の mermaid ソースを組み立てる。

    Note (memo / hint / scene 等) は sequence 図ではなく per-tick セクションに
    回す。sequence 図は「誰が誰に向けて / 世界に対して何をしたか」だけに絞る。
    """
    lines = ["sequenceDiagram", "    autonumber"]
    actor_alias = {}
    for pid, label in player_labels.items():
        alias = f"P{pid}"
        actor_alias[pid] = alias
        lines.append(f'    actor {alias} as {_mermaid_actor_label(label)}')
    # 世界 (World) を共通の peer として用意
    lines.append("    participant W as 世界")

    for e in events:
        if e.player_id is None:
            continue
        actor = actor_alias.get(e.player_id)
        if actor is None:
            continue
        if e.kind == TraceEventKind.OBSERVATION:
            prose = _short(_payload_str(e.payload, "prose"), 60)
            label = _mermaid_label(f"t{e.tick}: {prose}")
            lines.append(f"    W-->>{actor}: {label}")
        elif e.kind == TraceEventKind.ACTION:
            tool = _payload_str(e.payload, "tool") or "?"
            label = _mermaid_label(f"t{e.tick}: {tool}")
            lines.append(f"    {actor}->>W: {label}")
        elif e.kind == TraceEventKind.ACTION_RESULT:
            success = e.payload.get("success") if isinstance(e.payload, dict) else None
            mark = "OK" if success else "NG"
            text = _short(_payload_str(e.payload, "result_summary"), 60)
            label = _mermaid_label(f"t{e.tick}: [{mark}] {text}")
            lines.append(f"    W-->>{actor}: {label}")
    return "\n".join(lines)


def _build_per_tick_sections(events: List[TraceEvent]) -> str:
    """tick ごとに <details> セクションを HTML 文字列で組み立てる。"""
    by_tick: "OrderedDict[Optional[int], List[TraceEvent]]" = OrderedDict()
    for e in events:
        by_tick.setdefault(e.tick, []).append(e)

    parts: List[str] = []
    for tick, evs in by_tick.items():
        title = "(tick 無し)" if tick is None else f"tick {tick}"
        rows: List[str] = []
        for e in evs:
            actor_label = (
                f"player {e.player_id}" if e.player_id is not None else "system"
            )
            payload_text = json.dumps(e.payload, ensure_ascii=False)
            rows.append(
                "<tr>"
                f"<td><code>{e.seq}</code></td>"
                f"<td>{html.escape(e.kind)}</td>"
                f"<td>{html.escape(actor_label)}</td>"
                f"<td><pre class='payload'>{html.escape(payload_text)}</pre></td>"
                "</tr>"
            )
        table = (
            "<table>"
            "<thead><tr><th>#</th><th>kind</th><th>actor</th><th>payload</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
        parts.append(
            f"<details><summary>{html.escape(title)} ({len(evs)} events)</summary>{table}</details>"
        )
    return "".join(parts)


def _payload_str(payload: object, key: str) -> str:
    if isinstance(payload, dict):
        v = payload.get(key)
        if v is None:
            return ""
        return str(v)
    return ""


def _short(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)] + "…"


def _mermaid_label(s: str) -> str:
    """mermaid のメッセージラベルとして安全な文字列に整形する。

    観点:
        - mermaid 構文: ``;`` / ``"`` / 改行はメッセージ区切りに化けるので置換
        - HTML 構文: ``<`` / ``>`` / ``&`` は raw 出力時にタグ解釈されないよう
          全角に置換 (mermaid_src 自体は HTML エスケープしないため、
          ユーザーデータ側で防御する)
    """
    return (
        s.replace("<", "＜")
        .replace(">", "＞")
        .replace("&", "＆")
        .replace(";", ",")
        .replace('"', "'")
        .replace("\n", " ")
    )


def _mermaid_actor_label(s: str) -> str:
    """actor 名 (`as` 右辺) として安全に整形する。

    HTML 特殊文字 + mermaid の特殊文字を最小限に置換。actor 名は短いので
    積極的に全角化する (タグ解釈リスクの排除を優先)。
    """
    return _mermaid_label(s)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<title>{title} - llm-rpg trace</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; max-width: 1100px; }}
  h1 {{ border-bottom: 2px solid #444; padding-bottom: 0.3rem; }}
  h2 {{ margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; margin-top: 0.5rem; }}
  th, td {{ border: 1px solid #ccc; padding: 4px 6px; text-align: left; vertical-align: top; }}
  pre.payload {{ margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 0.8rem; }}
  details {{ margin: 0.25rem 0; padding: 0.25rem 0.5rem; border-left: 3px solid #888; background: #fafafa; }}
  details summary {{ cursor: pointer; font-weight: bold; }}
  .meta li {{ margin: 0.1rem 0; }}
  pre.mermaid {{ background: #fff; padding: 1rem; border: 1px solid #ddd; overflow-x: auto; font-family: inherit; white-space: pre; }}
  pre.raw-mermaid {{ background: #f4f4f4; padding: 0.5rem; font-size: 0.8rem; overflow-x: auto; }}
  p.hint {{ font-size: 0.85rem; color: #666; margin-top: 0.25rem; }}
</style>
</head>
<body>
<h1>{title}</h1>
<section>
  <h2>メタ情報</h2>
  <ul class="meta">
    <li>総イベント数: <strong>{total_events}</strong></li>
    <li>tick 範囲: <strong>{tick_range}</strong></li>
    <li>プレイヤー:
      <ul>{player_lines}</ul>
    </li>
  </ul>
</section>

<section>
  <h2>シーケンス図 (observation / action / result)</h2>
  <p class="hint">下のブロックが描画されない場合は外部 CDN (Mermaid) がブロックされています。
    末尾の「mermaid raw source」をコピーして <a href="https://mermaid.live/" target="_blank" rel="noopener">mermaid.live</a> に貼れば見られます。</p>
  <pre class="mermaid">
{mermaid_src}
  </pre>
  <details>
    <summary>mermaid raw source (CDN が使えないとき用)</summary>
    <pre class="raw-mermaid">{mermaid_src_for_fallback}</pre>
  </details>
</section>

<section>
  <h2>tick 別タイムライン</h2>
  {per_tick}
</section>

<section>
  <h2>raw JSONL</h2>
  <details><summary>クリックで展開 (grep / jq 用)</summary>
    <pre>{raw_jsonl}</pre>
  </details>
</section>

<script src="{mermaid_cdn}"
  onerror="document.getElementById('mermaid-load-error').style.display='block';"></script>
<div id="mermaid-load-error" style="display:none; color:#a00; padding:0.5rem; border:1px solid #a00; margin-top:1rem;">
  Mermaid CDN の読み込みに失敗しました。raw source を mermaid.live に貼って描画してください。
</div>
<script>
  if (typeof mermaid !== "undefined") {{
    mermaid.initialize({{ startOnLoad: true, securityLevel: 'loose', theme: 'default' }});
  }}
</script>
</body>
</html>
"""


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a TraceEvent JSONL file to a self-contained HTML viewer")
    parser.add_argument("input", type=Path, help="Path to .jsonl file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output HTML path. Defaults to <input>.html in the same dir",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Title to embed in the HTML (defaults to input filename)",
    )
    args = parser.parse_args(argv)

    events = list(load_trace_events(args.input))
    if not events:
        print(f"[warn] no events in {args.input}", file=sys.stderr)
    title = args.title or args.input.stem
    out_path = args.output or args.input.with_suffix(".html")
    out_path.write_text(render_html(events, title=title), encoding="utf-8")
    print(f"wrote {out_path} ({len(events)} events)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
