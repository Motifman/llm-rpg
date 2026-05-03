#!/usr/bin/env python3
"""
MVP `SubjectiveEpisode` 向け: vLLM が `interpreted` / `recall_text` だけを JSON で返す安定性を検証する。

- 本番配線・orchestrator・store には触れない（ローカル実験のみ）。
- LLM に変更させるのは `interpreted` と `recall_text` のみ。
  `who` / `where`（location）/ `observed` / `outcome` / `cues` / `source` は決定論ドラフト側で固定し、
  マージ後も不変であることを検証する。
- `intended_next` を復活させず、cue を LLM に生成させない。

入力:
  - `ActionEpisodeDraftBuilder` 等で組んだ決定論ドラフト（`SubjectiveEpisode`）
  - source facts（ドラフトから抽出した文字列集合・ハルシネーション簡易チェック用）

出力:
  - `local_experiments/runs/subjective_episode_mvp_vllm_<timestamp>.md`
  - `local_experiments/runs/subjective_episode_mvp_vllm_<timestamp>.json`

Dry-run（vLLM 不要）:
  SUBJECTIVE_EPISODE_VLLM_DRY_RUN=1 python .../subjective_episode_mvp_vllm_experiment.py
  または `--dry-run`

vLLM 実行例:
  source venv/bin/activate
  VLLM_BASE_URL=http://127.0.0.1:8001/v1 VLLM_MODEL=gemma-4-31b-it-nvfp4 \\
    VLLM_TEMPERATURE=0.2 python local_experiments/subjective_episode_mvp_vllm_experiment.py

単体テスト可能な関数はモジュール先頭付近に置き、httpx は実行経路でのみ使用する。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from ai_rpg_world.application.llm.contracts.dtos import (  # noqa: E402
    LlmCommandResultDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.contracts.episodic_memory import (  # noqa: E402
    EpisodicCue,
    EpisodicCueSource,
    EpisodeAction,
    EpisodeLocation,
    EpisodeSource,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.services.action_episode_draft_builder import (  # noqa: E402
    ActionEpisodeDraftBuilder,
)

RUNS_DIR = _ROOT / "local_experiments" / "runs"

MAX_INTERPRETED_CHARS = 160
MAX_RECALL_CHARS = 240

SYSTEM_PROMPT_JA = """あなたはロールプレイングゲームの「主観記憶」生成の一部だけを担当する。
ユーザーが渡す JSON には、すでに確定した事実（who / 場所 / 観測 observed / 結果 outcome / cue / ソース）が含まれる。
あなたはその事実を書き換えてはならず、次の 2 フィールドだけを JSON で返す。

- interpreted: 当時その出来事をどう意味づけたか。1 文。入力にない人物・場所・物体名を新たに足さない。不要なら null。
- recall_text: 後から prompt に差し込む短い想起文。最大 2 文程度。入力にない固有名を足さない。

出力は JSON オブジェクトのみ（説明文やコードフェンス禁止）。
"""


def openai_subjective_llm_response_format() -> Dict[str, Any]:
    """OpenAI Chat Completions `response_format` 用（vLLM structured output と整合）。"""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "interpreted": {
                "anyOf": [
                    {"type": "string", "maxLength": MAX_INTERPRETED_CHARS},
                    {"type": "null"},
                ]
            },
            "recall_text": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_RECALL_CHARS,
            },
        },
        "required": ["interpreted", "recall_text"],
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "subjective_episode_mvp_llm_fields",
            "strict": True,
            "schema": schema,
        },
    }


def immutable_snapshot(ep: SubjectiveEpisode) -> Tuple[Any, ...]:
    """LLM に変更させてはならないフィールドの比較用スナップショット。"""
    loc = ep.location
    cues_canon = tuple(c.to_canonical() for c in ep.cues)
    return (
        ep.source.event_ids,
        (
            loc.spot_id,
            loc.tile_area_ids,
            loc.sub_location_id,
            loc.x,
            loc.y,
            loc.z,
        ),
        ep.who,
        ep.observed,
        ep.outcome,
        cues_canon,
    )


def source_fact_strings(ep: SubjectiveEpisode) -> List[str]:
    """入力ドラフトから「許容語彙」用の事実文字列を列挙する（簡易ハルシネーション検査の入力）。"""
    loc = ep.location
    parts: List[str] = [
        *(f"event:{e}" for e in ep.source.event_ids),
        *ep.who,
        ep.observed,
        ep.outcome,
        ep.what,
        *(c.to_canonical() for c in ep.cues),
    ]
    if ep.why:
        parts.append(ep.why)
    if ep.expected:
        parts.append(ep.expected)
    if ep.prediction_error:
        parts.append(ep.prediction_error)
    if ep.game_time_label:
        parts.append(ep.game_time_label)
    if ep.action:
        parts.append(ep.action.tool_name)
        if ep.action.canonical_arguments_text:
            parts.append(ep.action.canonical_arguments_text)
    # 場所（where）
    if loc.spot_id is not None:
        parts.append(f"spot:{loc.spot_id}")
    if loc.tile_area_ids:
        parts.append("areas:" + ",".join(str(a) for a in loc.tile_area_ids))
    if loc.sub_location_id is not None:
        parts.append(f"sub_loc:{loc.sub_location_id}")
    if loc.x is not None and loc.y is not None:
        parts.append(f"coord:{loc.x},{loc.y},{loc.z}")
    return [p for p in parts if p.strip()]


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, tuple):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, SubjectiveEpisode):
        return _json_safe(asdict(obj))
    if hasattr(obj, "__dataclass_fields__"):
        return _json_safe(asdict(obj))
    return obj


def build_user_prompt_payload(
    *,
    draft: SubjectiveEpisode,
    persona_hint: str,
) -> Dict[str, Any]:
    """LLM user メッセージ用 JSON（ドラフトのうち事実固定部分＋生成対象のプレースホルダ説明）。"""
    locked_context = {
        "episode_id": draft.episode_id,
        "player_id": draft.player_id,
        "occurred_at": draft.occurred_at.isoformat(),
        "game_time_label": draft.game_time_label,
        "source": _json_safe(draft.source),
        "location": _json_safe(draft.location),
        "action": _json_safe(draft.action) if draft.action else None,
        "who": list(draft.who),
        "what": draft.what,
        "why": draft.why,
        "observed": draft.observed,
        "expected": draft.expected,
        "outcome": draft.outcome,
        "prediction_error": draft.prediction_error,
        "felt": draft.felt,
        "cues": [{"axis": c.axis, "value": c.value, "source": c.source.value} for c in draft.cues],
        "interpreted_before_llm": draft.interpreted,
        "recall_text_template_before_llm": draft.recall_text,
    }
    return {
        "persona_hint": persona_hint,
        "immutable_episode_context": locked_context,
        "source_facts": source_fact_strings(draft),
        "task": (
            "interpreted と recall_text だけを生成し JSON で返す。"
            " immutable_episode_context の事実は変更しない（出力に繰り返し書かない）。"
        ),
    }


def validate_llm_pair(
    *,
    interpreted: str | None,
    recall_text: str,
) -> List[str]:
    """文字数目上限と recall の非空を検証。問題があれば人間可読なエラー文字列を返す。"""
    errs: List[str] = []
    if interpreted is not None and len(interpreted) > MAX_INTERPRETED_CHARS:
        errs.append(
            f"interpreted length {len(interpreted)} exceeds {MAX_INTERPRETED_CHARS}"
        )
    if not recall_text.strip():
        errs.append("recall_text must be non-empty")
    if len(recall_text) > MAX_RECALL_CHARS:
        errs.append(f"recall_text length {len(recall_text)} exceeds {MAX_RECALL_CHARS}")
    return errs


def apply_llm_to_draft(
    draft: SubjectiveEpisode,
    *,
    interpreted: str | None,
    recall_text: str,
) -> SubjectiveEpisode:
    """interpreted / recall_text のみ差し替え（他フィールドはそのまま）。"""
    return replace(draft, interpreted=interpreted, recall_text=recall_text.strip())


def heuristic_hallucination_hits(
    interpreted: str | None,
    recall_text: str,
    corpus_parts: Sequence[str],
) -> List[str]:
    """
    入力にないかもしれないトークンを簡易検出する（参考用・誤検知ありうる）。

    - 4 文字以上の ASCII 単語: 結合コーパス（小文字）に部分文字列として無ければ列挙
    - 2 文字以上の連続 CJK: コーパス文字列に現れなければ列挙
    """
    corpus = " ".join(corpus_parts)
    corpus_lower = corpus.casefold()
    text = f"{interpreted or ''} {recall_text}"
    hits: List[str] = []

    for m in re.finditer(r"[A-Za-z][A-Za-z0-9]{3,}", text):
        w = m.group(0)
        if w.casefold() not in corpus_lower:
            hits.append(w)

    for m in re.finditer(r"[\u3040-\u30ff\u3400-\u9fff]{2,}", text):
        t = m.group(0)
        if t not in corpus:
            hits.append(t)

    return list(dict.fromkeys(hits))


def _extract_first_json_object(text: str) -> str:
    """思考タグや前後テキストを含む応答から先頭 JSON オブジェクトを抽出する。"""
    s = text.strip()
    if not s:
        return s
    s = re.sub(
        r"<think>[\s\S]*?</think>",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"<redacted_reasoning>[\s\S]*?</redacted_reasoning>",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = s.strip()
    try:
        obj = json.loads(s)
        return json.dumps(obj, ensure_ascii=False)
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    if start < 0:
        return s
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return s


def parse_llm_object(data: Mapping[str, Any]) -> Tuple[str | None, str, List[str]]:
    """API が返した dict から interpreted / recall を取り出し検証する。"""
    if "interpreted" not in data or "recall_text" not in data:
        return (
            None,
            "",
            ["missing required keys: interpreted and/or recall_text"],
        )
    raw_i = data.get("interpreted")
    if raw_i is not None and not isinstance(raw_i, str):
        return None, "", [f"interpreted must be str or null, got {type(raw_i)!r}"]
    recall = data.get("recall_text")
    if not isinstance(recall, str):
        return raw_i if isinstance(raw_i, str) else None, "", ["recall_text must be str"]

    interpreted: str | None
    if raw_i is None:
        interpreted = None
    else:
        stripped = raw_i.strip()
        interpreted = stripped if stripped else None

    errs = validate_llm_pair(interpreted=interpreted, recall_text=recall)
    return interpreted, recall, errs


def dry_run_synthetic_outputs(draft: SubjectiveEpisode) -> Tuple[str | None, str]:
    """ネットワーク無しでパイプライン検証するための決定論的な疑似 LLM 出力。"""
    base_obs = draft.observed.strip()
    snippet = base_obs[: min(70, len(base_obs))]
    interpreted = "（dry-run）当日は結果が予想と違うと感じた。"
    if len(interpreted) > MAX_INTERPRETED_CHARS:
        interpreted = interpreted[:MAX_INTERPRETED_CHARS]
    recall = f"（dry-run想起）{snippet}"
    if len(recall) > MAX_RECALL_CHARS:
        recall = recall[:MAX_RECALL_CHARS]
    return interpreted, recall


def _npc_target(player_id: int) -> ToolRuntimeTargetDto:
    return ToolRuntimeTargetDto(
        label="g",
        kind="monster",
        display_name="Goblin",
        player_id=player_id,
    )


def scenario_defs() -> List[Dict[str, Any]]:
    """
    代表 5 ケース。すべて決定論ドラフト（builder または最小 dataclass）。
    """
    builder = ActionEpisodeDraftBuilder()

    def utc(*a: int) -> datetime:
        return datetime(*a, tzinfo=timezone.utc)

    # 1: 罠・失敗
    trap_ep = builder.build(
        player_id=1,
        occurred_at=utc(2026, 5, 3, 10, 0),
        tool_name="spot_graph_interact",
        canonical_arguments={"intention": "箱を開ける", "emotion_hint": "caution"},
        runtime_context=ToolRuntimeContextDto(targets={}, current_spot_id=12),
        command_result=LlmCommandResultDto(
            success=False,
            message="罠が発動した。床が抜けた。",
            error_code="TRAP_TRIGGERED",
        ),
        action_summary="古い箱に手を伸ばした",
        result_summary="罠が発動した。床が抜けた。",
        episodic_cues=(),
    )

    # 2: 成功 + NPC
    ok_ep = builder.build(
        player_id=2,
        occurred_at=utc(2026, 5, 3, 11, 0),
        tool_name="spot_graph_interact",
        canonical_arguments={"emotion_hint": "curiosity"},
        runtime_context=ToolRuntimeContextDto(targets={"g": _npc_target(99)}, current_spot_id=7),
        command_result=LlmCommandResultDto(success=True, message="鍵が開いた。"),
        action_summary="錠前を調べた",
        result_summary="鍵が開いた。",
        episodic_cues=(
            EpisodicCue(
                axis="action",
                value="spot_graph_interact",
                source=EpisodicCueSource.TOOL,
            ),
        ),
    )

    # 3: 移動失敗
    move_fail = builder.build(
        player_id=3,
        occurred_at=utc(2026, 5, 3, 12, 0),
        tool_name="move_to_destination",
        canonical_arguments={"emotion_hint": "frustration"},
        runtime_context=ToolRuntimeContextDto.empty(),
        command_result=LlmCommandResultDto(
            success=False,
            message="足元が崩れた。",
            error_code="MOVE_BLOCKED",
        ),
        action_summary="移動を試みた",
        result_summary="足元が崩れた。",
        episodic_cues=(),
    )

    # 4: 待機（cue 複数を明示）
    wait_ep = builder.build(
        player_id=4,
        occurred_at=utc(2026, 5, 3, 13, 0),
        tool_name="wait_turn",
        canonical_arguments={"emotion_hint": "neutral"},
        runtime_context=ToolRuntimeContextDto(
            targets={},
            current_spot_id=3,
            current_area_ids=(10, 11),
        ),
        command_result=LlmCommandResultDto(success=True, message="待機した"),
        action_summary="待機",
        result_summary="待機した",
        episodic_cues=(
            EpisodicCue(
                axis="place_spot",
                value="3",
                source=EpisodicCueSource.RUNTIME_CONTEXT,
            ),
            EpisodicCue(
                axis="outcome",
                value="success",
                source=EpisodicCueSource.TOOL,
            ),
        ),
    )

    # 5: dataclass 直接（長い observed・cue 多め）
    rich = SubjectiveEpisode(
        episode_id="fixture-rich-1",
        player_id=5,
        occurred_at=utc(2026, 5, 3, 14, 30),
        game_time_label="夕刻",
        source=EpisodeSource(event_ids=("obs_evt_9001", "action_evt_9002")),
        location=EpisodeLocation(
            spot_id=44,
            tile_area_ids=(5, 6),
            sub_location_id=2,
            x=10,
            y=4,
            z=0,
        ),
        action=EpisodeAction(
            tool_name="spot_graph_look",
            canonical_arguments_text=None,
        ),
        who=("entity:npc:alice", "player:self"),
        what="spot_graph_look — 床の文様を追った",
        why="安全な足場だけを選びたかった",
        observed=(
            "蝋燭の列が途切れ、床の溝にだけ煤が残っている。"
            "奥から乾いた金属音が一度だけした。"
        ),
        expected="異常がなければそのまま進める",
        outcome="観察のみ（危害なし）",
        prediction_error=None,
        felt="anxiety",
        interpreted=None,
        cues=(
            EpisodicCue(
                axis="entity",
                value="alice",
                source=EpisodicCueSource.OBSERVATION_STRUCTURED,
            ),
            EpisodicCue(
                axis="schema_hint",
                value="unease",
                source=EpisodicCueSource.TOOL,
            ),
        ),
        recall_text="placeholder recall before llm",
    )

    return [
        {"id": "1_trap_failure", "title": "罠・tool 失敗", "episode": trap_ep},
        {"id": "2_success_npc", "title": "成功・NPC target あり", "episode": ok_ep},
        {"id": "3_move_failure", "title": "移動失敗", "episode": move_fail},
        {"id": "4_wait_cues", "title": "待機・複数 cue", "episode": wait_ep},
        {"id": "5_rich_fixture", "title": "長い observed・手組み fixture", "episode": rich},
    ]


def _persona_from_env() -> str:
    return (
        os.environ.get("SUBJECTIVE_EPISODE_VLLM_PERSONA") or (
            "一人称の主観で短く。入力 facts にない固有名詞や新しい登場人物を足さない。"
        )
    ).strip()


def _use_json_schema_from_env() -> bool:
    raw = (os.environ.get("SUBJECTIVE_EPISODE_VLLM_USE_JSON_SCHEMA") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _vllm_meta(enable_thinking: bool) -> Tuple[str, str, int, float, Dict[str, Any]]:
    base = (os.environ.get("VLLM_BASE_URL") or "http://127.0.0.1:8001/v1").rstrip("/")
    model = os.environ.get("VLLM_MODEL") or "gemma-4-31b-it-nvfp4"
    max_tokens = int(os.environ.get("VLLM_MAX_THINKING_TOKENS") or os.environ.get("VLLM_MAX_TOKENS") or "512")
    temperature = float(os.environ.get("VLLM_TEMPERATURE") or "0.2")
    meta = {
        "base_url": base,
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "enable_thinking": enable_thinking,
    }
    return base, model, max_tokens, temperature, meta


def _enable_thinking_from_env() -> bool:
    raw = (os.environ.get("SUBJECTIVE_EPISODE_VLLM_THINKING") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def run_one_case_vllm(
    *,
    draft: SubjectiveEpisode,
    persona: str,
    use_json_schema: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    """1 ケース分の実行メタ＋結果を dict で返す。"""
    payload = build_user_prompt_payload(draft=draft, persona_hint=persona)
    user_prompt = json.dumps(payload, ensure_ascii=False, indent=2)
    facts = source_fact_strings(draft)
    snap_before = immutable_snapshot(draft)

    if dry_run:
        syn_i, syn_r = dry_run_synthetic_outputs(draft)
        raw_content = json.dumps(
            {"interpreted": syn_i, "recall_text": syn_r},
            ensure_ascii=False,
        )
        interpreted, recall_text, parse_errs = parse_llm_object(json.loads(raw_content))
        http_status = 0
        latency_ms = 0.0
        req_meta = {"dry_run": True}
    else:
        import httpx

        enable_thinking = _enable_thinking_from_env()
        base, model, max_tokens, temperature, req_meta = _vllm_meta(enable_thinking)
        req_meta["response_format_json_schema"] = use_json_schema
        body: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_JA},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": enable_thinking},
            "skip_special_tokens": False,
        }
        if use_json_schema:
            body["response_format"] = openai_subjective_llm_response_format()
        t0 = time.perf_counter()
        with httpx.Client(timeout=httpx.Timeout(300.0)) as client:
            response = client.post(
                f"{base}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer EMPTY",
                },
                json=body,
            )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        http_status = response.status_code
        try:
            rj = response.json()
        except json.JSONDecodeError:
            raw_content = response.text
            interpreted, recall_text, parse_errs = None, "", ["invalid HTTP JSON body"]
        else:
            choices = rj.get("choices") or []
            if http_status != 200:
                raw_content = json.dumps(rj, ensure_ascii=False)
                interpreted, recall_text, parse_errs = (
                    None,
                    "",
                    [f"HTTP status {http_status}"],
                )
            elif not choices:
                raw_content = json.dumps(rj, ensure_ascii=False)
                interpreted, recall_text, parse_errs = None, "", ["no choices in response"]
            else:
                msg = choices[0].get("message") or {}
                raw_content = str(msg.get("content") or "")
                extracted = _extract_first_json_object(raw_content)
                try:
                    data = json.loads(extracted)
                except json.JSONDecodeError as e:
                    interpreted, recall_text, parse_errs = None, "", [f"json decode: {e}"]
                else:
                    interpreted, recall_text, parse_errs = parse_llm_object(data)

    merged_errs = list(parse_errs)
    merged: SubjectiveEpisode | None = None
    immutable_ok = False
    hallucination_hits: List[str] = []

    if not merged_errs:
        merged = apply_llm_to_draft(draft, interpreted=interpreted, recall_text=recall_text)
        immutable_ok = immutable_snapshot(merged) == snap_before
        if not immutable_ok:
            merged_errs.append("immutable fields changed after merge (unexpected)")
        hallucination_hits = heuristic_hallucination_hits(
            interpreted,
            recall_text,
            facts,
        )

    ok = bool(
        merged is not None
        and not merged_errs
        and immutable_ok
        and http_status in (0, 200)
    )

    return {
        "episode_id": draft.episode_id,
        "title_slug": draft.episode_id,
        "user_prompt": user_prompt,
        "request_meta": req_meta if not dry_run else {"dry_run": True},
        "http_status": http_status,
        "latency_ms": latency_ms,
        "raw_content": raw_content,
        "interpreted": interpreted,
        "recall_text": recall_text if not merged_errs else None,
        "parse_errors": merged_errs,
        "immutable_ok": immutable_ok,
        "hallucination_hits": hallucination_hits,
        "merged_episode": merged,
        "ok": ok,
        "source_facts": facts,
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SubjectiveEpisode MVP vLLM generation experiment")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="vLLM を呼ばず決定論出力でパイプラインのみ検証する",
    )
    return p.parse_args(argv)


def _dry_run_from_env(argv: Sequence[str] | None) -> bool:
    env_flag = (os.environ.get("SUBJECTIVE_EPISODE_VLLM_DRY_RUN") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if argv is None:
        return env_flag
    ns = _parse_args(argv)
    return env_flag or ns.dry_run


def main(argv: Sequence[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    dry = _dry_run_from_env(argv)

    persona = _persona_from_env()
    use_schema = _use_json_schema_from_env()
    scenarios = scenario_defs()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_md = RUNS_DIR / f"subjective_episode_mvp_vllm_{stamp}.md"
    out_json = RUNS_DIR / f"subjective_episode_mvp_vllm_{stamp}.json"

    print("=== SubjectiveEpisode MVP vLLM experiment ===")
    print(f"dry_run={dry}  use_json_schema={use_schema}  runs={RUNS_DIR}")

    rows: List[Dict[str, Any]] = []
    md_lines: List[str] = [
        "# SubjectiveEpisode MVP — vLLM（interpreted / recall_text のみ）",
        "",
        f"- 実行時刻: {datetime.now().isoformat(timespec='seconds')}",
        f"- dry_run: **{dry}**（`--dry-run` または `SUBJECTIVE_EPISODE_VLLM_DRY_RUN=1`）",
        f"- `response_format` JSON Schema: **{use_schema}**",
        "",
        "## System prompt",
        "",
        "```text",
        SYSTEM_PROMPT_JA.strip(),
        "```",
        "",
    ]

    all_ok = True
    for sc in scenarios:
        cid = sc["id"]
        title = sc["title"]
        ep: SubjectiveEpisode = sc["episode"]
        print(f"--- case {cid}: {title} ---")
        row = run_one_case_vllm(
            draft=ep,
            persona=persona,
            use_json_schema=use_schema,
            dry_run=dry,
        )
        row["scenario_id"] = cid
        row["scenario_title"] = title
        # merged_episode は JSON 化のため dict に
        me = row.pop("merged_episode", None)
        if me is not None:
            row["merged_episode_dict"] = _json_safe(me)
        rows.append(row)
        if not row["ok"]:
            all_ok = False

        md_lines.append(f"### {cid}: {title}")
        md_lines.append("")
        md_lines.append(f"- ok: **{row['ok']}**")
        md_lines.append(f"- http: `{row['http_status']}`  latency_ms: `{row['latency_ms']:.1f}`")
        md_lines.append(f"- immutable_ok: **{row['immutable_ok']}**")
        if row.get("parse_errors"):
            md_lines.append(f"- parse_errors: `{row['parse_errors']}`")
        if row.get("hallucination_hits"):
            md_lines.append(f"- hallucination_hits（参考）: `{row['hallucination_hits']}`")
        md_lines.append("")
        md_lines.append("#### interpreted / recall_text")
        md_lines.append("")
        md_lines.append("```json")
        md_lines.append(
            json.dumps(
                {"interpreted": row["interpreted"], "recall_text": row["recall_text"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        md_lines.append("```")
        md_lines.append("")
        md_lines.append("#### user prompt（抜粋）")
        md_lines.append("")
        md_lines.append("```json")
        up = row["user_prompt"]
        md_lines.append(up[:6000] + ("\n... (truncated)" if len(up) > 6000 else ""))
        md_lines.append("```")
        md_lines.append("")
        md_lines.append("#### raw model output（先頭）")
        md_lines.append("")
        md_lines.append("```")
        raw = row.get("raw_content") or ""
        md_lines.append(raw[:4000] + ("\n... (truncated)" if len(raw) > 4000 else ""))
        md_lines.append("```")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    bundle = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry,
        "use_json_schema": use_schema,
        "cases": rows,
    }
    out_json.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"Wrote {out_md}")
    print(f"Wrote {out_json}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
