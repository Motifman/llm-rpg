#!/usr/bin/env python3
"""記録済み prompt を再送し、ツール定義の変更が選択を変えるかを測る介入実験。

背景 (v4 run 002/003/004/005 の分析):

- ``speak`` は 3 run 通算 601 回中 600 回成功する = 事実上唯一失敗しない行動
- ``say_inline`` (行動しながらの一言) は 20 ツールに付いているのにほぼ未使用
  (004 では speak 以外の行動 217 件中 3 件)
- 実際の ``speak`` 本文は中央値 104 字で、``say_inline`` の 80 字上限には
  71% が入らない
- ``say_inline`` を既に持つツールでも直後に ``speak`` 専用ターンを使う率が
  17〜72% ある = 使えるだけでは行動が変わっていない

そこで「上限を上げ、説明文を書き換え、wait / explore にも足したら、LLM は
専用ターンの代わりに行動へ発話を添えるようになるか」を、**200 tick の run を
回さずに**測る。

方法:

1. ``prompt_dataset`` から記録済み call を復元する (``reconstruct_request``)
2. アーム A: 記録された toolset をそのまま再送する
3. アーム B: toolset だけ介入版に差し替えて再送する
4. 選ばれた tool と ``say_inline`` の有無を比べる

**アーム A は検証器である。** 温度が既定値 (capture の ``unset_parameters`` に
temperature が入る = 未指定) なので選択は揺らぐ。A で元と同じ tool が選ばれる
率がこの実験の信頼性の上限になる。A を測らずに B だけ回すと、差が介入なのか
揺らぎなのか区別できない。

限界: 1 ターンの反実仮想なので、発話が同席者を起こして更に発話を呼ぶ増幅の
動態は出ない。答えられるのは「その手が使えるなら使うか」だけ。本番 run の
代わりではなく、本番 run を回す価値があるかの事前判定に使う。

使い方::

    # まず A アームだけで再現率を測る (低コスト)
    python scripts/replay_prompt_intervention.py var/runs/v4coop_memo_keep_004 \\
        --arm A --limit 30 --samples 3 --out var/replay/a_only.jsonl

    # 再現率が使える水準なら A/B 両方
    python scripts/replay_prompt_intervention.py var/runs/v4coop_memo_keep_004 \\
        --arm both --limit 100 --samples 3 --out var/replay/ab.jsonl

    # LLM を呼ばずに、何を送るつもりかだけ確認する
    python scripts/replay_prompt_intervention.py var/runs/x --dry-run
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from ai_rpg_world.application.llm.services.prompt_dataset_capture import (  # noqa: E402
    reconstruct_request,
)

#: 介入後の ``say_inline`` 上限。
#:
#: 3 run 通算 601 件の speak 本文のうち 95.7% が 200 字以内に収まる
#: (80 字では 28.3%)。「多弁化を防ぐ」ために置いた 80 字上限が、中身のある
#: 調整を専用ターンへ追い出して逆に多弁を招いていたので、実測分布が収まる
#: 値へ上げる。
INTERVENTION_SAY_INLINE_MAX_LENGTH = 200

#: 介入後の ``say_inline`` の説明文。
#:
#: 現行文は「立ち去り際 / 受け渡し際」「ありがとう」「先に行く」と例示し、
#: 「長い speech が必要な場合は speak tool を別途使う」と明示的に専用ターンへ
#: 誘導していた。ここを「ふだんの共有はこちらが基本」に反転させる。
INTERVENTION_SAY_INLINE_DESCRIPTION = (
    "この行動をしながら、同じ場所と隣接する場所へ向けて発する一言 (任意、"
    "200 字以内)。仲間への報告・段取りの相談・呼びかけ・確認は、"
    "発話専用のターンを使わずここに書くのが基本。"
    "行動と発話を同時に済ませられるので、時間を無駄にしない。"
    "空文字 / 未指定なら発話しない。"
)

#: 介入後の ``speak`` の説明文に追記する一段落。
#:
#: speak は消さない。同じ場所を越えて届く shout (004 では発話の 15%)、
#: 一人に内密な whisper、target 指定、200 字を超える長話は say_inline では
#: 代替できない。役割を「専用ターンを使う価値がある発話」に絞る。
INTERVENTION_SPEAK_DESCRIPTION_SUFFIX = (
    "\n\n"
    "このツールは発話だけに 1 手を使う。次のいずれかに当てはまるときに使う:\n"
    "- 同じ場所より遠くへ届かせたい (shout)\n"
    "- 一人にだけ内密に伝えたい (whisper)\n"
    "- 行動に添えるには長すぎる話をしたい\n"
    "ふだんの報告・段取り・呼びかけは、何かの行動の say_inline に添える方が"
    "同じ時間で行動も進むため、そちらを優先する。"
)

#: ``say_inline`` を新たに足すツール。
#:
#: wait: 「その場に留まって喋る」が現状どのツールでも表現できない。無いと
#: speak を消したときに発話手段が消える。足すことで「他にやることが無くて
#: 喋った」が行動枠の集計に idle として正しく現れる。
#: explore: 3 番目に多い世界行動 (004 で 48 回) なのに、発見したことを同じ
#: ターンで伝えられない。
INTERVENTION_TOOLS_GAINING_SAY_INLINE = ("wait", "explore")

_SAY_INLINE_KEY = "say_inline"


def _say_inline_property() -> Dict[str, Any]:
    return {
        "type": "string",
        "description": INTERVENTION_SAY_INLINE_DESCRIPTION,
        "maxLength": INTERVENTION_SAY_INLINE_MAX_LENGTH,
    }


def apply_say_inline_intervention(tools: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """toolset に say_inline 介入を適用した新しい list を返す (元は変更しない)。

    3 つの変更を行う:

    1. 既に ``say_inline`` を持つツール: 上限と説明文を差し替える
    2. ``INTERVENTION_TOOLS_GAINING_SAY_INLINE`` のツール: ``say_inline`` を足す
    3. ``speak``: 説明文に「専用ターンを使う価値がある場合」の段落を足す

    ``required`` には触らない。``say_inline`` は任意引数のままにする
    (必須にすると「喋ることが強制」になり、黙って動く選択を潰す)。
    """
    out: List[Dict[str, Any]] = []
    for tool in tools:
        new_tool = copy.deepcopy(tool)
        function = new_tool.get("function")
        if not isinstance(function, dict):
            out.append(new_tool)
            continue
        name = function.get("name")
        parameters = function.get("parameters")
        if isinstance(parameters, dict):
            properties = parameters.get("properties")
            if isinstance(properties, dict):
                if _SAY_INLINE_KEY in properties:
                    properties[_SAY_INLINE_KEY] = _say_inline_property()
                elif name in INTERVENTION_TOOLS_GAINING_SAY_INLINE:
                    properties[_SAY_INLINE_KEY] = _say_inline_property()
        if name == "speak":
            base = function.get("description") or ""
            function["description"] = base + INTERVENTION_SPEAK_DESCRIPTION_SUFFIX
        out.append(new_tool)
    return out


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"{path} が無い")
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@dataclass
class ReplayTarget:
    """再送する 1 call。"""

    llm_call_id: str
    world_tick: Optional[int]
    player_id: Optional[int]
    character_name: str
    recorded_tool: str
    recorded_say_inline: bool
    kwargs: Dict[str, Any]


def _select_targets(
    run_dir: Path,
    *,
    only_tool: Optional[str],
    phase: Optional[str],
    limit: Optional[int],
    api_base: str,
) -> List[ReplayTarget]:
    dataset = run_dir / "prompt_dataset"
    calls = _load_jsonl(dataset / "calls.jsonl")
    system_prompts = {
        row["system_prompt_id"]: row for row in _load_jsonl(dataset / "system_prompts.jsonl")
    }
    toolsets = {row["toolset_id"]: row for row in _load_jsonl(dataset / "toolsets.jsonl")}

    targets: List[ReplayTarget] = []
    for call in calls:
        if phase is not None and call.get("phase") != phase:
            continue
        output = call.get("output") or {}
        tool = str(output.get("name") or "")
        if only_tool is not None and tool != only_tool:
            continue
        kwargs = reconstruct_request(call, system_prompts, toolsets)
        # capture は api_base をマスクし api_key を落とす。replay 側で戻す。
        kwargs["api_base"] = api_base
        arguments = output.get("arguments") or {}
        targets.append(
            ReplayTarget(
                llm_call_id=str(call.get("llm_call_id") or ""),
                world_tick=call.get("world_tick"),
                player_id=call.get("player_id"),
                character_name=str(call.get("character_name") or ""),
                recorded_tool=tool,
                recorded_say_inline=bool(arguments.get(_SAY_INLINE_KEY)),
                kwargs=kwargs,
            )
        )
        if limit is not None and len(targets) >= limit:
            break
    return targets


def _extract_choice(response: Any) -> Dict[str, Any]:
    """litellm の応答から tool 名と引数を取り出す。

    tool_choice=required なので通常 1 件返る。取り出せない形は
    ``{"tool": None}`` にして呼び出し側が失敗として数えられるようにする。
    """
    try:
        message = response.choices[0].message
        calls = getattr(message, "tool_calls", None) or []
        if not calls:
            return {"tool": None, "arguments": {}, "error": "no_tool_calls"}
        first = calls[0]
        name = first.function.name
        raw_args = first.function.arguments
        arguments = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        return {"tool": name, "arguments": arguments}
    except Exception as exc:  # noqa: BLE001 - 応答形は provider 依存
        return {"tool": None, "arguments": {}, "error": f"{type(exc).__name__}: {exc}"}


def _run_one(kwargs: Dict[str, Any], *, api_key: str) -> Dict[str, Any]:
    import litellm  # noqa: WPS433 - 呼ぶ直前まで import しない

    payload = dict(kwargs)
    payload["api_key"] = api_key
    response = litellm.completion(**payload)
    return _extract_choice(response)


def _summarise(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """アームごとに「元と同じ tool か」「say_inline を付けたか」を集計する。"""
    by_arm: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_arm.setdefault(row["arm"], []).append(row)
    summary: Dict[str, Any] = {}
    for arm, arm_rows in sorted(by_arm.items()):
        total = len(arm_rows)
        errors = sum(1 for r in arm_rows if r.get("error"))
        answered = total - errors
        same = sum(1 for r in arm_rows if r.get("tool") and r["tool"] == r["recorded_tool"])
        speak = sum(1 for r in arm_rows if r.get("tool") == "speak")
        with_inline = sum(
            1
            for r in arm_rows
            if r.get("tool") and r["tool"] != "speak" and (r.get("arguments") or {}).get(_SAY_INLINE_KEY)
        )
        non_speak = sum(1 for r in arm_rows if r.get("tool") and r["tool"] != "speak")
        summary[arm] = {
            "total": total,
            "answered": answered,
            "errors": errors,
            "same_tool_as_recorded": same,
            "same_tool_rate": round(same / answered, 3) if answered else None,
            "chose_speak": speak,
            "chose_speak_rate": round(speak / answered, 3) if answered else None,
            "non_speak_actions": non_speak,
            "non_speak_with_say_inline": with_inline,
            "say_inline_attach_rate": (
                round(with_inline / non_speak, 3) if non_speak else None
            ),
            "tool_histogram": dict(Counter(r.get("tool") for r in arm_rows).most_common()),
        }
    return summary


def _iter_jobs(
    targets: Sequence[ReplayTarget], arms: Sequence[str], samples: int
) -> Iterable[tuple[ReplayTarget, str, int]]:
    for target in targets:
        for arm in arms:
            for sample in range(samples):
                yield target, arm, sample


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--arm", choices=("A", "B", "both"), default="both")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--filter-tool",
        default="speak",
        help="この tool を選んだ call だけ対象にする。'' で全件 (既定: speak)",
    )
    parser.add_argument("--phase", default="one_step")
    parser.add_argument(
        "--api-base",
        default="https://openrouter.ai/api/v1",
        help="capture がマスクした api_base を戻す値",
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="LLM を呼ばず、対象件数と介入差分だけ表示する",
    )
    args = parser.parse_args(argv)

    targets = _select_targets(
        args.run_dir,
        only_tool=args.filter_tool or None,
        phase=args.phase or None,
        limit=args.limit,
        api_base=args.api_base,
    )
    arms = ["A", "B"] if args.arm == "both" else [args.arm]
    total_jobs = len(targets) * len(arms) * args.samples
    print(
        f"対象 call {len(targets)} 件 x アーム {len(arms)} x sample {args.samples}"
        f" = {total_jobs} 呼び出し",
        flush=True,
    )

    if args.dry_run:
        if targets:
            before = targets[0].kwargs["tools"]
            after = apply_say_inline_intervention(before)
            changed = [
                (b.get("function", {}).get("name"))
                for b, a in zip(before, after)
                if b != a
            ]
            print(f"介入で変わる tool ({len(changed)} 件): {changed}")
        return 0

    # run_scenario_experiment と同じく .env を読む。秘密情報は .env にだけ置く
    # 運用なので、replay も同じ経路で鍵を得る。
    try:
        from dotenv import load_dotenv  # noqa: WPS433

        load_dotenv()
    except ImportError:
        pass
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print(
            "OPENAI_API_KEY (または OPENROUTER_API_KEY) が無い。.env を読み込んで実行する。",
            file=sys.stderr,
        )
        return 2

    rows: List[Dict[str, Any]] = []
    done = 0
    for target, arm, sample in _iter_jobs(targets, arms, args.samples):
        kwargs = target.kwargs
        if arm == "B":
            kwargs = dict(kwargs)
            kwargs["tools"] = apply_say_inline_intervention(kwargs["tools"])
        try:
            result = _run_one(kwargs, api_key=api_key)
        except Exception as exc:  # noqa: BLE001 - 1 件の失敗で全体を止めない
            result = {"tool": None, "arguments": {}, "error": f"{type(exc).__name__}: {exc}"}
        rows.append(
            {
                "llm_call_id": target.llm_call_id,
                "world_tick": target.world_tick,
                "player_id": target.player_id,
                "character_name": target.character_name,
                "recorded_tool": target.recorded_tool,
                "recorded_say_inline": target.recorded_say_inline,
                "arm": arm,
                "sample": sample,
                **result,
            }
        )
        done += 1
        if done % 20 == 0:
            print(f"  {done}/{total_jobs}", flush=True)

    summary = _summarise(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        args.out.with_suffix(".summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[out] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
