"""外れた予期 30 件で、信念の材料の渡し方を 3 通りに変えて固着の LLM に問う。

A : いまの材料 (予期の文と「外れた」だけ)
B1: A に、予期を書いてから確定するまでに実際に起きたことを足す
B2: B1 に、学びを「条件 → 結果 → 次にどうするか」で書く指示を足す
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
import litellm

from ai_rpg_world.application.llm.services.belief_consolidation_coordinator import (
    _build_belief_consolidation_system_prompt,
)

RUN = sys.argv[1]
OUT = sys.argv[2]
load_dotenv()

NAMES = {"being_w1_p1": "エイダ", "being_w1_p2": "ノア", "being_w1_p3": "リオ", "being_w1_p4": "カイ"}
LABEL = {"almost_certain": "ほぼ確実", "probably": "たぶん", "even": "五分五分", "maybe": "もしかしたら"}

events = [json.loads(line) for line in open(f"{RUN}/trace.jsonl")]
formed = {}
for e in events:
    if e["kind"] == "expectation_formed":
        for f in e["payload"]["formed"]:
            formed[f["expectation_id"]] = (e["payload"]["being_id"], e["payload"]["turn"], f)
settlements = {
    (e["payload"]["being_id"], e["payload"]["turn"]): e["payload"]
    for e in events
    if e["kind"] == "expectation_settlement"
}
misses = []
for e in events:
    p = e["payload"]
    if e["kind"] == "expectation_material" and p["receiver"] == "belief_evidence" and p["outcome"] == "miss" and p["result"] == "appended":
        settle_turn = int(p["event_id"].split("@")[1])
        misses.append((p["expectation_id"], settle_turn))

def timeline(being, written_turn, settle_turn):
    s = settlements[(being, settle_turn)]
    lines = []
    for t in s["state"]["出来事の時系列"]:
        n = int(t["ターン"].replace("ターン", ""))
        if written_turn <= n <= settle_turn:
            lines += t["行動"] + t["発言"]
    return lines

SYSTEM = _build_belief_consolidation_system_prompt(attribution_enabled=True, hearsay_enabled=True)
SHAPE = """

【外れた予期から学ぶときの書き方】
evidence に「その後に実際に起きたこと」があるときは、予期と実際の食い違いの理由をそこから読み取ること。
学びは「どういう条件で → 何が起きるか → 次にどうするか」が分かる命題で書く。
例: 「流木の山は拾い尽くすと、時間がたてば波でまた戻る」
「〜とは限らない」「〜かもしれない」だけで終わる、次の行動が決まらない命題は書かない。
理由が読み取れないときは discard してよい。"""

def messages(variant, eid, settle_turn):
    being, wturn, f = formed[eid]
    text = f"{LABEL[f['likelihood']]}と思っていた予期「{f['what']}」は外れた。"
    ev = {"evidence_id": f"ev-{eid}", "source_kind": "prediction_error", "cue_signature": "expectation:miss",
          "text": text, "salience": "high" if f["likelihood"] == "almost_certain" else "low",
          "episode_ids": [eid], "observed_turn": settle_turn}
    if variant != "A":
        ev["その後に実際に起きたこと"] = timeline(being, wturn, settle_turn)
    user = {"current_turn": settle_turn, "evidence": [ev], "shortlist": []}
    system = SYSTEM + (SHAPE if variant == "B2" else "")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "以下の evidence / shortlist を読み、decisions を JSON だけで返してください。\n" + json.dumps(user, ensure_ascii=False)},
    ]

def call(args):
    variant, eid, settle_turn = args
    r = litellm.completion(
        model="openrouter/deepseek/deepseek-v4-flash-0731",
        messages=messages(variant, eid, settle_turn),
        api_base="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        extra_body={"provider": {"only": ["DeepInfra"], "allow_fallbacks": False}, "usage": {"include": True}},
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = r.choices[0].message.content
    cost = getattr(r, "usage", None)
    cost = getattr(cost, "cost", None) if cost else None
    try:
        decisions = json.loads(content).get("decisions", [])
    except Exception:
        decisions = [{"action": "parse_error", "raw": content}]
    return {"variant": variant, "expectation_id": eid, "settle_turn": settle_turn, "decisions": decisions, "cost": cost}

jobs = [(v, eid, st) for eid, st in misses for v in ("A", "B1", "B2")]
with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(call, jobs))

rows = []
for eid, st in misses:
    being, wturn, f = formed[eid]
    row = {"name": NAMES[being], "expectation_id": eid, "likelihood": f["likelihood"], "expectation": f["what"],
           "what_happened": timeline(being, wturn, st)}
    for r in results:
        if r["expectation_id"] == eid:
            row[r["variant"]] = r["decisions"]
    rows.append(row)
json.dump({"rows": rows, "costs": [r["cost"] for r in results]}, open(OUT, "w"), ensure_ascii=False, indent=2)
print(len(misses), "misses,", len(results), "calls, cost", sum(c or 0 for c in (r["cost"] for r in results)))
