"""チャンク由来のルール草案に対し LLM が interpreted / recall_text のみを付与する。"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any


def _as_utc(value: datetime) -> datetime:
    """naive datetime を UTC aware として扱う sort 正規化ヘルパ (Issue #311 後続)。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

from ai_rpg_world.application.llm.contracts.chunk_encoding import ChunkEncodingInput
from ai_rpg_world.application.llm.contracts.episodic_chunk_subjective_llm_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.application.llm.exceptions import LlmApiCallException

_SYSTEM_EPISODE_SUBJECTIVE_JSON = """あなたは RPG エージェントの主観記憶を埋める助手です。
入力はルールが組み立てたエピソード草案・人物像・ソース事実のみです。
出力は JSON オブジェクトのみ（前後に説明文やコードフェンスを付けない）。
キーは次の 2 つだけ: interpreted, recall_text。

interpreted は「この出来事を当時どう意味づけたか」の日本語 1 文。
過去の出来事の意味付けなので、原則として過去形・完了形で書く
（例: 「〜と感じた」「〜だと気づいた」「〜が分かった」）。

recall_text は将来のプロンプトに差し込む、キャラクター本人の一人称による
TRPG リプレイ風の主観回想。250〜450 字程度で、当時の感情・見立て・手触りを含める。

**recall_text は必ず過去形で書くこと**。これは「思い出している」テキストであり、
未来の prompt で「過去にこういうことがあった」と参照される設計のため、
現在形・未来形・命令形・意志形（「〜しよう」「〜しなければ」「〜しよう」「〜したい」）は
使ってはいけない。
- OK: 「〜だった」「〜が見えた」「〜と思った」「〜していた」「〜してしまった」「〜だと気づいた」
- NG: 「〜しなきゃならない」「〜しよう」「〜する必要がある」「〜したい」「〜するつもりだ」

ただし当時の感情の余韻だけは「〜だった気がする」「今でも〜と思う」のような形を許す。
出来事の描写・行動・結果は厳格に過去形に統一する。

入力に無い人物・場所・アイテム・結果・成否を新たに創作しない。
キューや observed の事実と矛盾しない表現にする。"""
_MAX_SUBJECTIVE_FIELD_CHARS = 700


def _truncate(label: str, raw: str, *, max_chars: int) -> str:
    text = raw.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _format_draft_facts(ep: SubjectiveEpisode) -> str:
    cues_lines = "\n".join(c.to_canonical() for c in ep.cues)
    loc = ep.location
    loc_parts = [
        f"spot_id={loc.spot_id}",
        f"tile_area_ids={tuple(loc.tile_area_ids)}",
        f"sub_location_id={loc.sub_location_id}",
        f"xyz=({loc.x},{loc.y},{loc.z})",
    ]
    action_line = "(なし)"
    if ep.action is not None:
        aa = ep.action.canonical_arguments_text or ""
        action_line = f"tool_name={ep.action.tool_name}; args={aa}"
    lines = [
        f"what: {ep.what}",
        f"observed (統一タイムライン):\n{ep.observed}",
        f"outcome: {ep.outcome}",
        f"who: {', '.join(ep.who) if ep.who else '(なし)'}",
        f"location: {'; '.join(loc_parts)}",
        f"action: {action_line}",
        f"cues (canonical):\n{cues_lines if cues_lines else '(なし)'}",
    ]
    return "\n".join(lines)


def _format_source_facts(encoding_input: ChunkEncodingInput) -> str:
    obs_lines: list[str] = []
    for o in sorted(encoding_input.observations, key=lambda e: _as_utc(e.occurred_at)):
        cat = o.output.observation_category
        gt = o.game_time_label or ""
        obs_lines.append(
            f"- occurred_at={o.occurred_at.isoformat()}; category={cat}; game_time={gt!s}"
        )
    for o in sorted(
        encoding_input.observation_overflow_from_window,
        key=lambda e: _as_utc(e.occurred_at),
    ):
        cat = o.output.observation_category
        obs_lines.append(
            f"- [window_overflow] occurred_at={o.occurred_at.isoformat()}; category={cat}"
        )
    act_lines: list[str] = []
    for a in sorted(encoding_input.action_results, key=lambda e: _as_utc(e.occurred_at)):
        tn = a.tool_name or ""
        act_lines.append(
            f"- occurred_at={a.occurred_at.isoformat()}; tool={tn!s}; "
            f"success={a.success:d}; action_summary={a.action_summary!s}; "
            f"result_summary={a.result_summary!s}; error_code={a.error_code!s}"
        )
    return "観測メタ（本文は含めない）:\n" + (
        "\n".join(obs_lines) if obs_lines else "(なし)"
    ) + "\n\n行動結果（ソース事実）:\n" + ("\n".join(act_lines) if act_lines else "(なし)")


def compute_template_interpreted(what: str) -> str:
    """``interpreted`` のテンプレ既定値。``what`` をそのまま (長すぎれば省略)。

    LLM 補完が走らない / 走ったが失敗したケースで使う。``ChunkEpisodeDraftBuilder``
    が draft 構築時に埋める用途にも使えるよう、`SubjectiveEpisode` ではなく
    生文字列で受ける形にしている。
    """
    return _truncate("interpreted_fallback", what, max_chars=_MAX_SUBJECTIVE_FIELD_CHARS)


def compute_template_recall(observed: str, what: str) -> str:
    """``recall_text`` のテンプレ既定値。

    ``observed`` (統一タイムラインの bullet 連結) の最初の非空行を 1 件抜き出し、
    なければ ``what`` で代替する。LLM 補完が無いとき / 失敗したときのフォールバック
    として、また draft 時点で「最低限なにか文がある」状態にするために使う。
    """
    for raw_line in observed.splitlines():
        line = raw_line.strip().lstrip("-").strip()
        if line:
            return _truncate("recall_fallback", line, max_chars=_MAX_SUBJECTIVE_FIELD_CHARS)
    return _truncate("recall_fallback", what, max_chars=_MAX_SUBJECTIVE_FIELD_CHARS)


def _template_interpreted(ep: SubjectiveEpisode) -> str:
    return compute_template_interpreted(ep.what)


def _template_recall(ep: SubjectiveEpisode) -> str:
    return compute_template_recall(ep.observed, ep.what)


def _normalize_llm_str(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    return _truncate("llm_field", stripped, max_chars=_MAX_SUBJECTIVE_FIELD_CHARS)


def _merge_picks(
    *,
    llm_value: str | None,
    fallback: str,
) -> str:
    return llm_value if llm_value is not None else fallback


class EpisodicChunkSubjectiveFieldsService:
    """
    ルール草案へ interpreted / recall_text を付与する。

    LLM が失敗または JSON が不正な場合は、草案の what / observed から組み立てたテンプレへ落とす。
    """

    def __init__(self, completion: IEpisodicChunkSubjectiveCompletionPort) -> None:
        if not isinstance(completion, IEpisodicChunkSubjectiveCompletionPort):
            raise TypeError("completion must implement IEpisodicChunkSubjectiveCompletionPort")
        self._completion = completion
        self._logger = logging.getLogger(self.__class__.__name__)

    def merge_llm_subjective_fields(
        self,
        draft: SubjectiveEpisode,
        *,
        persona_text: str,
        encoding_input: ChunkEncodingInput,
    ) -> SubjectiveEpisode:
        """
        LLM で interpreted / recall_text のみ埋め合わせる。

        LLM が失敗・不正 JSON・想定外形以外のときは草案の what / observed 由来のテンプレへフォールバックする。
        """
        if not isinstance(draft, SubjectiveEpisode):
            raise TypeError("draft must be SubjectiveEpisode")
        if not isinstance(persona_text, str):
            raise TypeError("persona_text must be str")
        if not isinstance(encoding_input, ChunkEncodingInput):
            raise TypeError("encoding_input must be ChunkEncodingInput")

        fallback_i = _template_interpreted(draft)
        fallback_r = _template_recall(draft)
        user_sections = [
            "## 人物像（ペルソナ断片）",
            persona_text.strip() if persona_text.strip() else "(なし)",
            "## ルール草案（事実・索引はここに依存。改変禁止）",
            _format_draft_facts(draft),
            "## ソース事実（検証用メタ。新事実の根拠にしない）",
            _format_source_facts(encoding_input),
            "## 応答形式",
            '{"interpreted": "...", "recall_text": "..."}',
        ]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_EPISODE_SUBJECTIVE_JSON},
            {"role": "user", "content": "\n\n".join(user_sections)},
        ]
        interp_llm: str | None = None
        recall_llm: str | None = None
        try:
            raw_obj = self._completion.complete_episode_subjective_json(messages)
            if not isinstance(raw_obj, dict):
                self._logger.warning(
                    "Episode subjective completion returned non-object; using template fallback"
                )
            else:
                interp_llm = _normalize_llm_str(raw_obj.get("interpreted"))
                recall_llm = _normalize_llm_str(raw_obj.get("recall_text"))
        except LlmApiCallException as e:
            self._logger.warning(
                "Episode subjective LLM failed (%s); using template fallback",
                getattr(e, "error_code", "LLM_ERROR"),
            )
        except (TypeError, ValueError) as e:
            self._logger.warning("Episode subjective parse failed; using template fallback: %s", e)
        except Exception as e:
            self._logger.warning("Episode subjective LLM path failed; using template fallback: %s", e)

        interpreted = _merge_picks(llm_value=interp_llm, fallback=fallback_i)
        recall_text = _merge_picks(llm_value=recall_llm, fallback=fallback_r)
        merged = replace(draft, interpreted=interpreted, recall_text=recall_text)
        self._assert_rule_fields_unchanged(draft, merged)
        return merged

    def _assert_rule_fields_unchanged(self, draft: SubjectiveEpisode, merged: SubjectiveEpisode) -> None:
        if merged.observed != draft.observed:
            raise ValueError("observed must remain unchanged after subjective merge")
        if merged.cues != draft.cues:
            raise ValueError("cues must remain unchanged after subjective merge")
        if merged.who != draft.who:
            raise ValueError("who must remain unchanged after subjective merge")
        if merged.what != draft.what:
            raise ValueError("what must remain unchanged after subjective merge")
        if merged.outcome != draft.outcome:
            raise ValueError("outcome must remain unchanged after subjective merge")


__all__ = ["EpisodicChunkSubjectiveFieldsService"]
