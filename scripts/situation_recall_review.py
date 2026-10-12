"""状況の想起で載った信念が場面に合っているかを、人が当否を付けられる表にし、手法ごとに数える (#1454)。

``situation_recall_probe.py`` の結果から、場面ごとに、比べた手法のどれかが載せた信念を重ねずに並べる。
probe と状況の想起は #1631 で消した。過去の結果の JSON を読み直すためだけに残す。
行には通し番号を振り、当否は番号で結びつける。当否は Claude と人で別のファイルに持つ。

- ``items``: 結果から行を作る。並びを変えると当否の番号がずれるので、既存の行は ``--overwrite`` が無ければ上書きしない
- ``html``: 行と Claude の当否から、人が当否を付ける ``review.html`` を作る。押した当否はブラウザに残り、JSON で書き出せる
- ``tally``: 当否のファイルごとに、手法の載せた枠のうち「合う」の数を数える

当否の付け方 (Claude も人も同じ):

- Y: この場面で次に何をするかを決める材料になる。場面の課題・相手・場所・体の具合に関わり、場面と食い違わない
- ?: 関わりはあるが判断にはほとんど効かない、または読んでも決められない
- N: この場面の判断に関わらない、または場面と食い違う (もう古い、別の場所の話など)

使い方:
    uv run python scripts/situation_recall_review.py items \\
        --results docs/experiments/issue_1454_embedding_comparison/results.json \\
        --methods old,char_bigram_bm25,qwen3_embedding_8b_openrouter,ruri_v3_30m,ruri_v3_310m \\
        --out docs/experiments/issue_1454_embedding_comparison/review_items.json
    uv run python scripts/situation_recall_review.py html \\
        --items docs/experiments/issue_1454_embedding_comparison/review_items.json \\
        --labels docs/experiments/issue_1454_embedding_comparison/labels_claude.json \\
        --out docs/experiments/issue_1454_embedding_comparison/review.html
    uv run python scripts/situation_recall_review.py tally \\
        --items docs/experiments/issue_1454_embedding_comparison/review_items.json \\
        --labels docs/experiments/issue_1454_embedding_comparison/labels_claude.json
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

#: 体の危険の語。消した situation_recall_probe.py と同じだった。
_DANGER = re.compile(r"攻撃|怪我|血|痛|危|倒れ|瀕死|HP|空腹|飢|毒|噛|襲")
_LABELS = ("Y", "?", "N")

METHOD_LABELS = {
    "old": "前の想起 (cue)",
    "char_bigram_bm25": "2 字組",
    "qwen3_embedding_8b_openrouter": "Qwen3 (API)",
    "ruri_v3_30m": "Ruri v3 30m",
    "ruri_v3_70m": "Ruri v3 70m",
    "ruri_v3_130m": "Ruri v3 130m",
    "ruri_v3_310m": "Ruri v3 310m",
}


def build_items(result: dict[str, Any], methods: Sequence[str]) -> dict[str, Any]:
    """場面ごとに、手法の載せた信念を重ねずに並べ、行に通し番号を振る。"""
    unknown = [m for m in methods if m != "old" and m not in result["narrowers"]]
    if unknown:
        raise ValueError(f"methods not in the results: {unknown}")
    fell_back = sorted(
        {
            f"{player['name']} {scene['index']} {method}"
            for player in result["players"]
            for scene in player["scenes"]
            for method in scene.get("fallback", {})
            if method in methods
        }
    )
    if fell_back:
        # 縮退した場面の結果は 2 字組のもの。その手法の枠として数えない。試算をやり直す。
        raise ValueError(f"these scenes fell back to another narrower: {fell_back}")
    texts = result["texts"]
    scenes = []
    number = 0
    for player in result["players"]:
        for scene in player["scenes"]:
            picks: dict[str, dict[str, int]] = {}
            for method in methods:
                ids = scene["old"] if method == "old" else scene["new"][method]
                for rank, entry_id in enumerate(ids, start=1):
                    picks.setdefault(entry_id, {})[method] = rank
            rows = []
            for entry_id, by_method in picks.items():
                if entry_id not in texts:
                    raise ValueError(f"no text for belief {entry_id}")
                number += 1
                rows.append({"n": number, "id": entry_id, "t": texts[entry_id], "picks": by_method})
            scenes.append(
                {
                    "who": player["name"],
                    "prompt": scene["index"],
                    "place": scene["place"],
                    "danger": any(_DANGER.search(t) for t in scene["situation"]["いま起きたこと"]),
                    "situation": scene["situation"],
                    "rows": rows,
                }
            )
    return {"results": result.get("run_dir"), "methods": list(methods), "scenes": scenes}


def items_id(items: dict[str, Any]) -> str:
    """行の中身から作る印。ブラウザの保存先と書き出す当否に付け、作り直した行に古い当否が当たらないようにする。"""
    canonical = json.dumps(items["scenes"], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def tally(items: dict[str, Any], labels: dict[str, str]) -> dict[str, dict[str, Any]]:
    """手法ごとに、載せた枠の当否を数える。当否の無い枠は「未」に数える。"""
    out: dict[str, dict[str, Any]] = {}
    for method in items["methods"]:
        counts = {label: 0 for label in (*_LABELS, "未")}
        danger = {label: 0 for label in (*_LABELS, "未")}
        for scene in items["scenes"]:
            for row in scene["rows"]:
                if method not in row["picks"]:
                    continue
                label = labels.get(str(row["n"]), "未")
                counts[label] += 1
                if scene["danger"]:
                    danger[label] += 1
        out[method] = {"all": counts, "danger": danger}
    return out


def _read_labels(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text("utf-8"))
    labels = data.get("labels", data)
    bad = {k: v for k, v in labels.items() if v not in _LABELS}
    if bad:
        raise ValueError(f"{path}: labels must be one of {_LABELS}: {bad}")
    return labels


def _print_tally(items: dict[str, Any], path: Path) -> None:
    written_for = json.loads(path.read_text("utf-8")).get("items_id")
    if written_for is not None and written_for != items_id(items):
        raise ValueError(f"{path}: items_id {written_for} does not match the rows {items_id(items)}")
    labels = _read_labels(path)
    print(f"## {path.name}")
    print("| 手法 | 合う (Y) | ? | 合わない (N) | 未 | 体が危ない場面の Y |")
    print("|---|---|---|---|---|---|")
    for method, counts in tally(items, labels).items():
        a, d = counts["all"], counts["danger"]
        slots_danger = sum(d.values())
        print(
            f"| {METHOD_LABELS.get(method, method)} | {a['Y']} | {a['?']} | {a['N']} | {a['未']} "
            f"| {d['Y']}/{slots_danger} |"
        )


_CSS = """
:root {
  --bg: #f3f4f1; --surface: #ffffff; --fg: #1f2a24; --muted: #5d6b63; --line: #d9ddd6;
  --accent: #2f6f57; --accent-soft: #e2efe8;
  --y: #2f6f57; --q: #9a6b12; --n: #8a3b32;
  --y-soft: #e2efe8; --q-soft: #f6ecd6; --n-soft: #f5e1de; --focus: #2f6f57;
  --font-body: "Zen Kaku Gothic New", "Hiragino Sans", "Yu Gothic", sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #151a17; --surface: #1e2420; --fg: #e4e9e5; --muted: #9aa8a0; --line: #323a35;
  --accent: #7cc4a5; --accent-soft: #23362d; --y: #7cc4a5; --q: #e0b25a; --n: #e58a7f;
  --y-soft: #23362d; --q-soft: #3a3020; --n-soft: #3d2623; --focus: #7cc4a5; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #151a17; --surface: #1e2420; --fg: #e4e9e5; --muted: #9aa8a0; --line: #323a35;
  --accent: #7cc4a5; --accent-soft: #23362d; --y: #7cc4a5; --q: #e0b25a; --n: #e58a7f;
  --y-soft: #23362d; --q-soft: #3a3020; --n-soft: #3d2623; --focus: #7cc4a5; color-scheme: dark }
body { background: var(--bg); color: var(--fg); font-family: var(--font-body); font-size: 15px; line-height: 1.6; margin: 0; }
.wrap { max-width: 900px; margin: 0 auto; padding-inline: 16px; padding-block: 20px 80px; display: grid; gap: 16px; }
h1 { font-size: 1.3rem; margin: 0; }
.lede, .legend { color: var(--muted); font-size: .88rem; margin: 4px 0 0; }
.legend kbd { font-family: var(--font-mono); font-size: .75rem; border: 1px solid var(--line); border-radius: 3px; padding: 0 4px; background: var(--surface); }
.bar { position: sticky; top: 0; z-index: 2; background: var(--bg); padding-block: 10px; border-bottom: 1px solid var(--line); display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
.progress { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: .9rem; }
.meter { flex: 1 1 160px; height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; min-width: 120px; }
.meter > i { display: block; height: 100%; background: var(--accent); width: 0; }
.filters { display: flex; gap: 12px; flex-wrap: wrap; font-size: .85rem; color: var(--muted); }
.filters label { display: inline-flex; gap: 4px; align-items: center; cursor: pointer; }
.bar button { font: inherit; font-size: .82rem; padding: 4px 10px; border: 1px solid var(--line); border-radius: 5px; background: var(--surface); color: var(--fg); cursor: pointer; }
.status { font-size: .8rem; color: var(--muted); width: 100%; }
.status.warn { color: var(--n); }
table.tally { border-collapse: collapse; font-size: .82rem; width: 100%; background: var(--surface); }
table.tally th, table.tally td { border: 1px solid var(--line); padding: 4px 8px; text-align: right; font-variant-numeric: tabular-nums; }
table.tally th:first-child, table.tally td:first-child { text-align: left; }
.group { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.ghead { padding: 12px 14px; border-bottom: 1px solid var(--line); display: grid; gap: 6px; }
.gmeta { display: flex; gap: 8px; align-items: center; font-size: .8rem; color: var(--muted); flex-wrap: wrap; }
.danger { font-size: .72rem; padding: 0 6px; border-radius: 3px; color: var(--n); border: 1px solid var(--n); }
dl.sit { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 2px 10px; font-size: .84rem; }
dl.sit dt { color: var(--muted); }
dl.sit dd { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.row { display: grid; grid-template-columns: 1fr auto; gap: 6px 12px; padding: 10px 14px; border-top: 1px solid var(--line); align-items: start; }
.row.focus { outline: 2px solid var(--focus); outline-offset: -2px; }
.row.done { background: color-mix(in srgb, var(--accent-soft) 45%, transparent); }
.text { min-width: 0; display: grid; gap: 4px; }
.kind { font-size: .72rem; color: var(--muted); }
.facts { display: flex; gap: 6px; align-items: center; font-size: .78rem; color: var(--muted); flex-wrap: wrap; }
.pick { font-family: var(--font-mono); font-size: .72rem; padding: 0 6px; border-radius: 3px; border: 1px solid var(--line); }
body.hide-picks .pick { display: none; }
.chip { font-family: var(--font-mono); font-size: .75rem; padding: 0 6px; border-radius: 3px; }
.chip.Y { background: var(--y-soft); color: var(--y); }
.chip.q { background: var(--q-soft); color: var(--q); }
.chip.N { background: var(--n-soft); color: var(--n); }
.btns { display: flex; gap: 4px; }
.btns button { font: inherit; font-size: .8rem; min-width: 40px; padding: 4px 8px; border: 1px solid var(--line); border-radius: 5px; background: var(--surface); color: var(--fg); cursor: pointer; }
.btns button:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.btns button.sel.ok { background: var(--accent); color: var(--surface); border-color: var(--accent); }
.btns button.sel.Y { background: var(--y); color: var(--surface); border-color: var(--y); }
.btns button.sel.q { background: var(--q); color: var(--surface); border-color: var(--q); }
.btns button.sel.N { background: var(--n); color: var(--surface); border-color: var(--n); }
.btns button:disabled { opacity: .5; cursor: default; }
@media (max-width: 560px) { .row { grid-template-columns: 1fr; } dl.sit { grid-template-columns: 1fr; } }
"""

_JS = r"""
const cls = (l) => (l === "?" ? "q" : l);
const STORE_KEY = `issue1454-recall-reviews-${ITEMS_ID}`;
let storeBroken = false;
const reviews = (() => {
  let raw = null;
  try { raw = localStorage.getItem(STORE_KEY); } catch (_) { return {}; }
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
  } catch (_) { /* 下で壊れた保存として扱う */ }
  storeBroken = true;
  return {};
})();
// 壊れた保存を空として扱うと、次の保存で上書きして消してしまう。
const canWrite = !storeBroken;
let focusN = null;
const $ = (id) => document.getElementById(id);
const allRows = SCENES.flatMap((s) => s.rows.map((r) => ({ ...r, s })));

function visibleRows() {
  const o = $("only-open").checked, d = $("only-danger").checked;
  return allRows.filter((r) => (!o || !reviews[r.n]) && (!d || r.s.danger));
}

function renderTally() {
  const body = $("tally-body");
  body.replaceChildren();
  for (const m of METHODS) {
    const c = { Y: 0, "?": 0, N: 0, 未: 0 }, cd = { Y: 0, all: 0 };
    for (const r of allRows) {
      if (!(m.key in r.picks)) continue;
      const l = reviews[r.n]?.label || "未";
      c[l] += 1;
      if (r.s.danger) { cd.all += 1; if (l === "Y") cd.Y += 1; }
    }
    const tr = document.createElement("tr");
    for (const v of [m.label, c.Y, c["?"], c.N, c.未, `${cd.Y}/${cd.all}`]) {
      const td = document.createElement("td");
      td.textContent = v;
      tr.append(td);
    }
    body.append(tr);
  }
}

function render() {
  const done = allRows.filter((r) => reviews[r.n]).length;
  $("progress").textContent = `確認済み ${done} / ${allRows.length}`;
  $("meter").style.width = `${(100 * done) / allRows.length}%`;
  const vis = new Set(visibleRows().map((r) => r.n));
  const frag = document.createDocumentFragment();
  for (const s of SCENES) {
    const rows = s.rows.filter((r) => vis.has(r.n));
    if (!rows.length) continue;
    const sec = document.createElement("section");
    sec.className = "group";
    const head = document.createElement("div");
    head.className = "ghead";
    const meta = document.createElement("div");
    meta.className = "gmeta";
    const who = document.createElement("span");
    who.textContent = `${s.who} / プロンプト ${s.prompt} / ${s.place || "場所なし"}`;
    meta.append(who);
    if (s.danger) { const d = document.createElement("span"); d.className = "danger"; d.textContent = "体の危険の語あり"; meta.append(d); }
    const dl = document.createElement("dl");
    dl.className = "sit";
    for (const [field, values] of Object.entries(s.situation)) {
      if (!values.length) continue;
      const dt = document.createElement("dt"); dt.textContent = field;
      const dd = document.createElement("dd"); dd.textContent = values.join("\n");
      dl.append(dt, dd);
    }
    head.append(meta, dl);
    sec.append(head);
    for (const r of rows) sec.append(row(r));
    frag.append(sec);
  }
  $("list").replaceChildren(frag);
  if (focusN != null) document.querySelector(`[data-n="${focusN}"]`)?.classList.add("focus");
  renderTally();
}

function row(r) {
  const el = document.createElement("div");
  const rev = reviews[r.n];
  el.className = "row" + (rev ? " done" : "");
  el.dataset.n = r.n;
  const text = document.createElement("div");
  text.className = "text";
  const kind = document.createElement("span");
  kind.className = "kind";
  kind.textContent = `#${r.n}`;
  const body = document.createElement("span");
  body.textContent = r.t;
  const facts = document.createElement("div");
  facts.className = "facts";
  for (const m of METHODS) {
    if (!(m.key in r.picks)) continue;
    const p = document.createElement("span");
    p.className = "pick";
    p.textContent = `${m.label} ${r.picks[m.key]}位`;
    facts.append(p);
  }
  const claude = document.createElement("span");
  claude.append("Claude ");
  const chip = document.createElement("span");
  chip.className = `chip ${cls(r.c)}`;
  chip.textContent = r.c || "-";
  claude.append(chip);
  facts.append(claude);
  text.append(kind, body, facts);
  const btns = document.createElement("div");
  btns.className = "btns";
  for (const [key, label, value] of [["ok", "そのまま", r.c], ["Y", "Y", "Y"], ["q", "?", "?"], ["N", "N", "N"]]) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.className = key;
    b.disabled = !canWrite || (key === "ok" && !r.c);
    if (rev && ((key === "ok" && rev.agreed) || (key !== "ok" && !rev.agreed && rev.label === value))) b.classList.add("sel");
    b.addEventListener("click", () => decide(r, value));
    btns.append(b);
  }
  el.append(text, btns);
  el.addEventListener("click", (e) => { if (e.target.tagName !== "BUTTON") setFocus(r.n); });
  return el;
}

function setFocus(n) {
  document.querySelector(".row.focus")?.classList.remove("focus");
  focusN = n;
  const el = document.querySelector(`[data-n="${n}"]`);
  if (el) { el.classList.add("focus"); el.scrollIntoView({ block: "nearest" }); }
}

function decide(r, value) {
  if (!canWrite || !value) return;
  reviews[r.n] = { label: value, agreed: value === r.c };
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(reviews));
    setStatus("このブラウザに保存しました。");
  } catch (_) {
    // 保存できない開き方 (data: など) でも付けた当否は捨てない。閉じると消えるので書き出しを促す。
    setStatus("このブラウザには保存できません。付けた当否は開いている間だけ残るので、閉じる前に「当否を書き出す」で保存してください。", true);
  }
  render();
  const vis = visibleRows();
  const next = vis.find((x) => x.n > r.n && !reviews[x.n]) || vis.find((x) => !reviews[x.n]);
  if (next) setFocus(next.n);
}

function setStatus(text, warn) {
  const s = $("status");
  s.textContent = text;
  s.classList.toggle("warn", !!warn);
}

function exportLabels() {
  const labels = {};
  for (const [n, v] of Object.entries(reviews)) labels[n] = v.label;
  const blob = new Blob([JSON.stringify({ labeled_by: "人", items_id: ITEMS_ID, labels }, null, 1)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "labels_human.json";
  a.click();
  // すぐ取り消すと、環境によっては保存が始まる前に消える。
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

document.addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey || e.target.closest("input, button")) return;
  const vis = visibleRows();
  if (!vis.length) return;
  const idx = vis.findIndex((x) => x.n === focusN);
  if (e.key === "j" || e.key === "k") {
    const ni = e.key === "j" ? Math.min(vis.length - 1, idx + 1) : Math.max(0, idx - 1);
    setFocus(vis[idx < 0 ? 0 : ni].n);
    e.preventDefault();
    return;
  }
  const r = vis[idx];
  if (!r) return;
  const map = { Enter: r.c, y: "Y", "/": "?", "?": "?", n: "N" };
  if (e.key in map) { decide(r, map[e.key]); e.preventDefault(); }
});

for (const id of ["only-open", "only-danger"]) $(id).addEventListener("change", render);
$("show-picks").addEventListener("change", (e) => document.body.classList.toggle("hide-picks", !e.target.checked));
$("export").addEventListener("click", exportLabels);
document.body.classList.add("hide-picks");
render();
const first = visibleRows()[0];
if (first) setFocus(first.n);
setStatus(storeBroken ? "このブラウザの保存が読めないので、上書きしないよう表示だけにしています。" : Object.keys(reviews).length ? "前回の続きから。押すたびにこのブラウザに保存します。" : "押すたびにこのブラウザに保存します。", storeBroken);
"""


def render_html(items: dict[str, Any], labels: dict[str, str]) -> str:
    scenes = [
        {**scene, "rows": [{**row, "c": labels.get(str(row["n"]))} for row in scene["rows"]]}
        for scene in items["scenes"]
    ]
    methods = [{"key": m, "label": METHOD_LABELS.get(m, m)} for m in items["methods"]]
    data = json.dumps(scenes, ensure_ascii=False).replace("</", "<\\/")
    method_data = json.dumps(methods, ensure_ascii=False).replace("</", "<\\/")
    total = sum(len(s["rows"]) for s in scenes)
    method_names = "、".join(html.escape(m["label"]) for m in methods)
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>想起の当否チェック</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{_CSS}</style></head><body>
<div class="wrap">
  <header>
    <h1>想起の当否チェック</h1>
    <p class="lede">#1454 の比較 ({len(scenes)} 場面、{total} 行)。各行は「この信念は、この場面で次に何をするかを決める材料になるか」。{method_names} のどれかが上位 3 件に載せた信念を、場面ごとに重ねずに並べた。どの手法が載せたかは、当否を付けたあとに見られるよう既定で隠している。</p>
    <p class="legend">Y: 判断の材料になる (場面の課題・相手・場所・体の具合に関わり、食い違わない) / ?: 関わりはあるが判断にほとんど効かない、決められない / N: 関わらない、または場面と食い違う。<br>
    キー: <kbd>j</kbd>/<kbd>k</kbd> 移動 <kbd>Enter</kbd> Claude と同じ <kbd>y</kbd> <kbd>/</kbd> <kbd>n</kbd> で Y / ? / N。押すと次の未確認へ進む。付け終えたら「当否を書き出す」で labels_human.json を保存する。</p>
  </header>
  <div class="bar">
    <span class="progress" id="progress"></span>
    <span class="meter"><i id="meter"></i></span>
    <div class="filters">
      <label><input type="checkbox" id="only-open"> 未確認だけ</label>
      <label><input type="checkbox" id="only-danger"> 体の危険の語がある場面だけ</label>
      <label><input type="checkbox" id="show-picks"> どの手法が載せたかを見る</label>
    </div>
    <button type="button" id="export">当否を書き出す</button>
    <span class="status" id="status"></span>
  </div>
  <details><summary>人の当否での手法ごとの数 (付けた分だけ)</summary>
    <table class="tally"><thead><tr><th>手法</th><th>Y</th><th>?</th><th>N</th><th>未</th><th>体の危険の語がある場面の Y</th></tr></thead><tbody id="tally-body"></tbody></table>
  </details>
  <main id="list"></main>
</div>
<script>
const SCENES = {data};
const METHODS = {method_data};
const ITEMS_ID = "{items_id(items)}";
{_JS}
</script>
</body></html>
"""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_items = sub.add_parser("items")
    p_items.add_argument("--results", type=Path, required=True)
    p_items.add_argument("--methods", required=True)
    p_items.add_argument("--out", type=Path, required=True)
    p_items.add_argument("--overwrite", action="store_true")
    p_html = sub.add_parser("html")
    p_html.add_argument("--items", type=Path, required=True)
    p_html.add_argument("--labels", type=Path)
    p_html.add_argument("--out", type=Path, required=True)
    p_tally = sub.add_parser("tally")
    p_tally.add_argument("--items", type=Path, required=True)
    p_tally.add_argument("--labels", type=Path, action="append", required=True)
    args = parser.parse_args(argv)

    if args.command == "items":
        if args.out.exists() and not args.overwrite:
            parser.error(f"{args.out} exists; labels are tied to its row numbers (use --overwrite)")
        methods = [m.strip() for m in args.methods.split(",") if m.strip()]
        items = build_items(json.loads(args.results.read_text("utf-8")), methods)
        args.out.write_text(json.dumps(items, ensure_ascii=False, indent=1), "utf-8")
        print(f"{sum(len(s['rows']) for s in items['scenes'])} rows in {len(items['scenes'])} scenes")
    elif args.command == "html":
        items = json.loads(args.items.read_text("utf-8"))
        labels = _read_labels(args.labels) if args.labels else {}
        args.out.write_text(render_html(items, labels), "utf-8")
    else:
        items = json.loads(args.items.read_text("utf-8"))
        for path in args.labels:
            _print_tally(items, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
