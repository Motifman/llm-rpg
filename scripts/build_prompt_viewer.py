#!/usr/bin/env python3
"""prompt_dataset/calls.jsonl から「実際に LLM へ送った prompt」の閲覧 HTML を生成する。

既存 viewer (build_trace_viewer / build_episodic_viewer / build_timeline_viewer) は
trace event を見せるもので、**実際に送信した messages そのもの**を読む経路が無かった。
「停滞の表出は本当に prompt に届いていたのか」「遠景に山影が出ていたのか」のような
問いは trace の集計ではなく prompt 本文を読まないと確かめられない。

可視化内容:
- call ごとの tick / player / phase / 選ばれた tool / latency / token
- user message 本文を 【...】 見出し単位に折って表示
- LLM の出力 (tool 名と引数)
- 注目行のハイライト (停滞の表出 / 遠景 / 同席者の様子)
- player / phase / tool / 本文検索での絞り込み

使い方::

    python scripts/build_prompt_viewer.py var/runs/v4coop_memo_keep_004
    python scripts/build_prompt_viewer.py var/runs/x --output var/runs/x/prompt.html

system prompt と toolset は calls.jsonl 側では id 参照になっているが、同じ
dataset dir の ``system_prompts.jsonl`` / ``toolsets.jsonl`` に本文が入って
いるので、それを引いて実際に送った内容を出す。参照先が欠けている場合は
「解決できなかった」と明示する (= 空欄と区別する)。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


#: 本文中で目立たせたい行のパターン。
#:
#: 「気づかせる系の表出が prompt に届いているか」を目視で確かめるのが
#: この viewer の主目的なので、停滞・遠景・同席者の様子を色分けする。
#: 文言は spot_graph_ui_context_builder の _STAGNATION_OWN_HINT /
#: _STAGNATION_OTHER_DISPLAY と対応する。ずれたらハイライトが外れるだけで
#: 本文表示は壊れない (= 静かな誤りにならない)。
HIGHLIGHT_RULES: Sequence[tuple[str, str, str]] = (
    ("stagnation-strong", "停滞 (強)", "同じことばかり繰り返している焦りが拭えない"),
    ("stagnation-light", "停滞 (弱)", "何かが前に進んでいない気がする"),
    ("stagnation-other", "他者の停滞", "苛立って落ち着かない様子"),
    ("stagnation-other", "他者の停滞", "何か手詰まりの様子"),
    ("distant", "遠景", "遠くに"),
)

_SECTION_RE = re.compile(r"^【(?P<title>[^】]+)】\s*$")


@dataclass
class PromptCall:
    """1 回の LLM 呼び出し。prompt 本文と出力をまとめた表示単位。"""

    llm_call_id: str
    world_tick: Optional[int]
    player_id: Optional[int]
    character_name: str
    phase: str
    tool_name: str
    tool_arguments: Dict[str, Any]
    system_prompt_id: str
    system_content: str
    toolset_id: str
    tool_names: List[str]
    user_content: str
    metrics: Dict[str, Any]
    highlights: List[str] = field(default_factory=list)


def _load_side_table(path: Path, key: str) -> Dict[str, Dict[str, Any]]:
    """``system_prompts.jsonl`` / ``toolsets.jsonl`` を id 引きの dict にする。

    ファイルが無い run (古い capture) では空 dict を返す。呼び出し側は
    「参照を解決できなかった」として表示に出すため、ここでは失敗させない。
    """
    if not path.exists():
        return {}
    table: Dict[str, Dict[str, Any]] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            row_id = row.get(key)
            if isinstance(row_id, str) and row_id:
                table[row_id] = row
    return table


def _load_calls(run_dir: Path) -> List[PromptCall]:
    dataset_dir = run_dir / "prompt_dataset"
    path = dataset_dir / "calls.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} が無い。PROMPT_DATASET_CAPTURE_ENABLED=true で走らせた run を指定する。"
        )
    system_prompts = _load_side_table(
        dataset_dir / "system_prompts.jsonl", "system_prompt_id"
    )
    toolsets = _load_side_table(dataset_dir / "toolsets.jsonl", "toolset_id")
    calls: List[PromptCall] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                print(
                    f"warning: {path}:{line_no} を JSON として読めないので飛ばす: {exc}",
                    file=sys.stderr,
                )
                continue
            calls.append(_to_call(raw, system_prompts, toolsets))
    calls.sort(key=lambda c: (c.world_tick if c.world_tick is not None else -1))
    return calls


def _tool_names_of(row: Dict[str, Any]) -> List[str]:
    """toolsets.jsonl の 1 行から tool 名の一覧を取り出す。

    ``tool_names`` が入っていればそれを使い、無ければ ``tools`` の
    function.name から組む (schema 差異に耐えるため両方見る)。
    """
    names = row.get("tool_names")
    if isinstance(names, list) and names:
        return [str(n) for n in names]
    tools = row.get("tools")
    if isinstance(tools, str):
        try:
            tools = json.loads(tools)
        except json.JSONDecodeError:
            return []
    if not isinstance(tools, list):
        return []
    out: List[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = (tool.get("function") or {}).get("name") or tool.get("name")
        if name:
            out.append(str(name))
    return out


def _to_call(
    raw: Dict[str, Any],
    system_prompts: Optional[Dict[str, Dict[str, Any]]] = None,
    toolsets: Optional[Dict[str, Dict[str, Any]]] = None,
) -> PromptCall:
    prompt = raw.get("prompt") or {}
    messages = prompt.get("messages") or []
    system_content = ""
    user_content = ""
    for message in messages:
        role = message.get("role")
        content = message.get("content") or ""
        if role == "system":
            system_content = content
        elif role == "user":
            user_content = content
    system_prompt_id = str(prompt.get("system_prompt_id") or "")
    toolset_id = str(prompt.get("toolset_id") or "")
    # calls.jsonl 側の system は参照化されて空になっている。同じ dataset dir の
    # system_prompts.jsonl に本文があるので、そちらを優先して使う。
    if not system_content and system_prompt_id and system_prompts:
        row = system_prompts.get(system_prompt_id)
        if row:
            system_content = str(row.get("content") or "")
    tool_names: List[str] = []
    if toolset_id and toolsets:
        row = toolsets.get(toolset_id)
        if row:
            tool_names = _tool_names_of(row)
    output = raw.get("output") or {}
    call = PromptCall(
        llm_call_id=str(raw.get("llm_call_id") or ""),
        world_tick=raw.get("world_tick"),
        player_id=raw.get("player_id"),
        character_name=str(raw.get("character_name") or ""),
        phase=str(raw.get("phase") or ""),
        tool_name=str(output.get("name") or ""),
        tool_arguments=output.get("arguments") or {},
        system_prompt_id=system_prompt_id,
        system_content=system_content,
        toolset_id=toolset_id,
        tool_names=tool_names,
        user_content=user_content,
        metrics=raw.get("metrics") or {},
    )
    seen: List[str] = []
    for _cls, label, needle in HIGHLIGHT_RULES:
        if needle in user_content and label not in seen:
            seen.append(label)
    call.highlights = seen
    return call


def _line_class(line: str) -> str:
    for cls, _label, needle in HIGHLIGHT_RULES:
        if needle in line:
            return cls
    return ""


def _render_body(content: str) -> str:
    """user message を 【見出し】 単位の <details> に折って HTML 化する。

    見出しが 1 つも無い本文 (assess phase 等) は 1 ブロックとして出す。
    """
    if not content:
        return '<p class="empty">user message が空。</p>'
    blocks: List[tuple[str, List[str]]] = []
    current_title = ""
    current_lines: List[str] = []
    for line in content.split("\n"):
        matched = _SECTION_RE.match(line)
        if matched:
            if current_lines or current_title:
                blocks.append((current_title, current_lines))
            current_title = matched.group("title")
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines or current_title:
        blocks.append((current_title, current_lines))

    parts: List[str] = []
    for title, lines in blocks:
        rendered: List[str] = []
        for line in lines:
            cls = _line_class(line)
            escaped = html.escape(line) or "&nbsp;"
            if cls:
                rendered.append(f'<span class="line {cls}">{escaped}</span>')
            else:
                rendered.append(f'<span class="line">{escaped}</span>')
        body = "\n".join(rendered)
        heading = html.escape(title) if title else "(見出しなし)"
        marked = " data-marked=\"1\"" if any(_line_class(x) for x in lines) else ""
        opened = " open" if marked else ""
        parts.append(
            f'<details class="section"{opened}{marked}>'
            f"<summary>{heading}</summary>"
            f'<pre class="section-body">{body}</pre>'
            f"</details>"
        )
    return "\n".join(parts)


def _render_output(call: PromptCall) -> str:
    if not call.tool_name:
        return '<p class="empty">tool 呼び出しなし。</p>'
    rows: List[str] = []
    for key in sorted(call.tool_arguments):
        value = call.tool_arguments[key]
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        rows.append(
            f"<tr><th>{html.escape(key)}</th>"
            f"<td>{html.escape(value)}</td></tr>"
        )
    return (
        f'<p class="tool-name">{html.escape(call.tool_name)}</p>'
        f'<table class="args">{"".join(rows)}</table>'
    )


def _render_tool_names(call: PromptCall) -> str:
    """その call で実際に使えた tool 名を出す。

    「その手が選べたのか、そもそも出ていなかったのか」を prompt 側で切り分け
    られるようにする。露出漏れの調査で毎回必要になる情報。
    """
    if not call.tool_names:
        return (
            '<p class="sysnote">toolset を解決できなかった。<br>'
            f'<code>{html.escape(call.toolset_id or "-")}</code></p>'
        )
    chosen = call.tool_name
    chips = "".join(
        f'<span class="toolchip{" chosen" if n == chosen else ""}">{html.escape(n)}</span>'
        for n in call.tool_names
    )
    return f'<div class="toolset">{chips}</div>'


def _render_system(call: PromptCall) -> str:
    if not call.system_content:
        return (
            '<p class="sysnote">system prompt を解決できなかった '
            "(system_prompts.jsonl が無いか id が一致しない)。<br>"
            f'<code>{html.escape(call.system_prompt_id or "-")}</code></p>'
        )
    return (
        '<details class="section"><summary>system prompt を開く</summary>'
        f'<pre class="section-body">{html.escape(call.system_content)}</pre>'
        "</details>"
    )


def _render_call(index: int, call: PromptCall) -> str:
    tick = call.world_tick if call.world_tick is not None else "-"
    metrics = call.metrics
    latency = metrics.get("wall_latency_ms")
    latency_text = f"{latency} ms" if isinstance(latency, (int, float)) else "-"
    prompt_tokens = metrics.get("prompt_tokens")
    cached = metrics.get("cached_tokens")
    chips = "".join(
        f'<span class="chip chip-{html.escape(label)}">{html.escape(label)}</span>'
        for label in call.highlights
    )
    return f"""
<article class="call" id="call-{index}"
         data-player="{html.escape(str(call.player_id))}"
         data-phase="{html.escape(call.phase)}"
         data-tool="{html.escape(call.tool_name)}"
         data-tick="{html.escape(str(tick))}"
         data-highlights="{html.escape('|'.join(call.highlights))}">
  <header class="call-head">
    <span class="tick">t{html.escape(str(tick))}</span>
    <span class="who">{html.escape(call.character_name or f'P{call.player_id}')}</span>
    <span class="phase phase-{html.escape(call.phase)}">{html.escape(call.phase)}</span>
    <span class="tool">{html.escape(call.tool_name or '-')}</span>
    <span class="chips">{chips}</span>
    <span class="meta">{latency_text} / prompt {prompt_tokens} (cached {cached})</span>
  </header>
  <div class="call-body">
    <section class="pane">
      <h3>送信した user message <small>{len(call.user_content)} 文字</small></h3>
      {_render_body(call.user_content)}
    </section>
    <section class="pane">
      <h3>LLM の出力</h3>
      {_render_output(call)}
      <h3>使えた tool <small>{len(call.tool_names)} 種</small></h3>
      {_render_tool_names(call)}
      <h3>system prompt <small>{len(call.system_content)} 文字</small></h3>
      {_render_system(call)}
    </section>
  </div>
</article>"""


_CSS = """
:root {
  --bg: oklch(97% 0.008 250);
  --surface: oklch(100% 0 0);
  --surface-2: oklch(94% 0.01 250);
  --text: oklch(24% 0.02 260);
  --text-dim: oklch(50% 0.02 260);
  --line: oklch(88% 0.012 250);
  --accent: oklch(52% 0.16 255);
  --warn: oklch(62% 0.17 40);
  --warn-soft: oklch(94% 0.05 60);
  --good: oklch(58% 0.13 160);
  --good-soft: oklch(94% 0.05 160);
  --mono: ui-monospace, SFMono-Regular, Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: oklch(19% 0.015 260);
    --surface: oklch(24% 0.018 260);
    --surface-2: oklch(28% 0.02 260);
    --text: oklch(93% 0.01 260);
    --text-dim: oklch(68% 0.015 260);
    --line: oklch(35% 0.02 260);
    --accent: oklch(76% 0.13 255);
    --warn: oklch(78% 0.15 55);
    --warn-soft: oklch(32% 0.06 50);
    --good: oklch(76% 0.12 160);
    --good-soft: oklch(30% 0.05 160);
  }
}
:root[data-theme="dark"] {
  --bg: oklch(19% 0.015 260); --surface: oklch(24% 0.018 260);
  --surface-2: oklch(28% 0.02 260); --text: oklch(93% 0.01 260);
  --text-dim: oklch(68% 0.015 260); --line: oklch(35% 0.02 260);
  --accent: oklch(76% 0.13 255); --warn: oklch(78% 0.15 55);
  --warn-soft: oklch(32% 0.06 50); --good: oklch(76% 0.12 160);
  --good-soft: oklch(30% 0.05 160);
}
:root[data-theme="light"] {
  --bg: oklch(97% 0.008 250); --surface: oklch(100% 0 0);
  --surface-2: oklch(94% 0.01 250); --text: oklch(24% 0.02 260);
  --text-dim: oklch(50% 0.02 260); --line: oklch(88% 0.012 250);
  --accent: oklch(52% 0.16 255); --warn: oklch(62% 0.17 40);
  --warn-soft: oklch(94% 0.05 60); --good: oklch(58% 0.13 160);
  --good-soft: oklch(94% 0.05 160);
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font-family: system-ui, -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif;
  line-height: 1.65;
}
header.top {
  position: sticky; top: 0; z-index: 10;
  background: var(--surface); border-bottom: 1px solid var(--line);
  padding: 0.9rem 1.2rem; display: flex; flex-wrap: wrap;
  gap: 0.6rem 1rem; align-items: baseline;
}
header.top h1 { font-size: 1.05rem; margin: 0; letter-spacing: 0.01em; }
header.top .sub { color: var(--text-dim); font-size: 0.82rem; font-variant-numeric: tabular-nums; }
.controls { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-left: auto; }
.controls input, .controls select, .controls button {
  font: inherit; font-size: 0.82rem; padding: 0.28rem 0.5rem;
  background: var(--surface-2); color: var(--text);
  border: 1px solid var(--line); border-radius: 6px;
}
.controls input[type="search"] { min-width: 16rem; }
main { padding: 1.1rem 1.2rem 4rem; display: flex; flex-direction: column; gap: 0.9rem; }
.call { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.call[hidden] { display: none; }
.call-head {
  display: flex; flex-wrap: wrap; gap: 0.5rem 0.8rem; align-items: center;
  padding: 0.55rem 0.9rem; background: var(--surface-2);
  border-bottom: 1px solid var(--line); font-size: 0.84rem;
}
.tick { font-family: var(--mono); color: var(--accent); font-weight: 700; }
.who { font-weight: 650; }
.phase { font-size: 0.74rem; padding: 0.08rem 0.42rem; border-radius: 999px;
         border: 1px solid var(--line); color: var(--text-dim); }
.phase-assess_phase, .phase-action_phase { color: var(--accent); border-color: var(--accent); }
.tool { font-family: var(--mono); font-size: 0.8rem; }
.meta { margin-left: auto; color: var(--text-dim); font-size: 0.76rem;
        font-variant-numeric: tabular-nums; }
.chip { font-size: 0.7rem; padding: 0.06rem 0.4rem; border-radius: 999px;
        background: var(--warn-soft); color: var(--warn); border: 1px solid var(--warn); }
.call-body { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr);
             gap: 0 1rem; padding: 0.8rem 0.9rem; }
@media (max-width: 900px) { .call-body { grid-template-columns: 1fr; } }
.pane h3 { font-size: 0.82rem; margin: 0.4rem 0 0.5rem; color: var(--text-dim);
           text-transform: uppercase; letter-spacing: 0.06em; }
.pane h3 small { text-transform: none; letter-spacing: 0; font-weight: 400; }
details.section { border: 1px solid var(--line); border-radius: 7px; margin-bottom: 0.4rem; }
details.section[data-marked="1"] { border-color: var(--warn); }
details.section > summary { cursor: pointer; padding: 0.32rem 0.6rem;
  font-size: 0.82rem; font-weight: 650; background: var(--surface-2);
  border-radius: 6px; }
.section-body { margin: 0; padding: 0.5rem 0.7rem; font-family: var(--mono);
  font-size: 0.78rem; white-space: pre-wrap; word-break: break-word;
  overflow-x: auto; }
.line { display: block; }
.line.stagnation-strong { background: var(--warn-soft); color: var(--warn); font-weight: 650; }
.line.stagnation-light { background: var(--warn-soft); }
.line.stagnation-other { background: var(--surface-2); }
.line.distant { background: var(--good-soft); color: var(--good); }
.tool-name { font-family: var(--mono); font-weight: 700; margin: 0 0 0.4rem; color: var(--accent); }
table.args { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
table.args th { text-align: left; vertical-align: top; padding: 0.24rem 0.5rem 0.24rem 0;
  color: var(--text-dim); font-weight: 600; white-space: nowrap; }
table.args td { padding: 0.24rem 0; word-break: break-word; }
.toolset { display: flex; flex-wrap: wrap; gap: 0.22rem; margin-bottom: 0.3rem; }
.toolchip { font-family: var(--mono); font-size: 0.7rem; padding: 0.06rem 0.34rem;
  border: 1px solid var(--line); border-radius: 5px; color: var(--text-dim); }
.toolchip.chosen { border-color: var(--accent); color: var(--accent); font-weight: 700; }
.sysnote { font-size: 0.74rem; color: var(--text-dim); }
.sysnote code { font-family: var(--mono); font-size: 0.7rem; word-break: break-all; }
.empty { color: var(--text-dim); font-size: 0.8rem; font-style: italic; }
#count { color: var(--text-dim); font-size: 0.8rem; font-variant-numeric: tabular-nums; }
"""


_JS = """
const calls = Array.from(document.querySelectorAll('.call'));
const q = document.getElementById('q');
const fPlayer = document.getElementById('f-player');
const fPhase = document.getElementById('f-phase');
const fTool = document.getElementById('f-tool');
const fMark = document.getElementById('f-mark');
const count = document.getElementById('count');

function apply() {
  const needle = q.value.trim();
  const player = fPlayer.value, phase = fPhase.value, tool = fTool.value;
  const marked = fMark.checked;
  let shown = 0;
  for (const el of calls) {
    let ok = true;
    if (player && el.dataset.player !== player) ok = false;
    if (ok && phase && el.dataset.phase !== phase) ok = false;
    if (ok && tool && el.dataset.tool !== tool) ok = false;
    if (ok && marked && !el.dataset.highlights) ok = false;
    if (ok && needle && !el.textContent.includes(needle)) ok = false;
    el.hidden = !ok;
    if (ok) shown++;
  }
  count.textContent = shown + ' / ' + calls.length + ' 件';
}
for (const el of [q, fPlayer, fPhase, fTool, fMark]) {
  el.addEventListener('input', apply);
}
document.getElementById('fold').addEventListener('click', () => {
  const open = document.querySelectorAll('.call:not([hidden]) details.section[open]').length > 0;
  document.querySelectorAll('.call:not([hidden]) details.section')
    .forEach(d => { d.open = !open; });
});
apply();
"""


def render_html(calls: Sequence[PromptCall], *, run_id: str, profile: str) -> str:
    players = sorted({str(c.player_id) for c in calls if c.player_id is not None})
    phases = sorted({c.phase for c in calls if c.phase})
    tools = sorted({c.tool_name for c in calls if c.tool_name})

    def options(values: Sequence[str], label: str) -> str:
        opts = "".join(f'<option value="{html.escape(v)}">{html.escape(v)}</option>' for v in values)
        return f'<option value="">{html.escape(label)}</option>{opts}'

    name_by_id = {
        str(c.player_id): c.character_name for c in calls if c.player_id is not None
    }
    player_opts = "".join(
        f'<option value="{html.escape(p)}">'
        f'{html.escape(name_by_id.get(p) or ("P" + p))}</option>'
        for p in players
    )
    body = "\n".join(_render_call(i, c) for i, c in enumerate(calls))
    marked = sum(1 for c in calls if c.highlights)
    return f"""<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>prompt viewer — {html.escape(run_id)}</title>
<style>{_CSS}</style>
</head><body>
<header class="top">
  <h1>実際に送った prompt — {html.escape(run_id)}</h1>
  <span class="sub">profile {html.escape(profile)} / {len(calls)} calls /
    ハイライト該当 {marked} 件</span>
  <div class="controls">
    <select id="f-player"><option value="">全員</option>{player_opts}</select>
    <select id="f-phase">{options(phases, '全 phase')}</select>
    <select id="f-tool">{options(tools, '全 tool')}</select>
    <label><input type="checkbox" id="f-mark"> ハイライトのみ</label>
    <input type="search" id="q" placeholder="本文を検索 (例: 山影)">
    <button id="fold" type="button">全部折る / 開く</button>
    <span id="count"></span>
  </div>
</header>
<main>{body}</main>
<script>{_JS}</script>
</body></html>"""


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="run ディレクトリ")
    parser.add_argument(
        "--output", type=Path, default=None, help="出力先 (既定: <run_dir>/prompt.html)"
    )
    args = parser.parse_args(argv)

    run_dir: Path = args.run_dir
    calls = _load_calls(run_dir)
    profile = ""
    run_json = run_dir / "prompt_dataset" / "run.json"
    if run_json.exists():
        try:
            profile = str(json.loads(run_json.read_text(encoding="utf-8")).get("profile") or "")
        except json.JSONDecodeError:
            profile = ""
    output: Path = args.output or (run_dir / "prompt.html")
    output.write_text(
        render_html(calls, run_id=run_dir.name, profile=profile), encoding="utf-8"
    )
    print(f"[html] prompt.html: {output} ({len(calls)} calls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
