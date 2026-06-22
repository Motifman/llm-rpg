"""チャンク由来のルール草案に対し LLM が interpreted / recall_text / prediction_error を付与する。"""

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
from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.application.llm.exceptions import LlmApiCallException

_SYSTEM_EPISODE_SUBJECTIVE_JSON = """あなたは RPG エージェントの主観記憶を埋める助手です。
入力はルールが組み立てたエピソード草案・人物像・ソース事実のみです。
出力は JSON オブジェクトのみ（前後に説明文やコードフェンスを付けない）。
キーは次の 4 つ: interpreted, recall_text, prediction_error, heading。

heading は、この出来事を後から「ぼんやり思い出す」ときの見出しとして使う
1 行サマリ。30 文字以内。原則として「〜した」「〜が起きた」のような体言止め
または過去形 1 文で、行動と印象的な要素を 1 つだけ含める。
（例: 「司書の手記を読んだ — 水の断片語」「廊下でカイトの声を聞いた」）
分からない / 出来事の特徴が無いときは空文字列 "" にする。

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

prediction_error は「行動前の予測 (expected) と実際の結果 (observed / outcome) の
食い違い」を日本語 1〜2 文で書く。expected が無い、または予測どおりだった場合は
空文字列 "" にする。これは願望が叶わなかったという話ではなく、世界の応答が自分の
見立てとどう違ったか・何を見落としていたかを簡潔に残すもの。過去形で書く。
（例: 「声をかければ話せると思っていたが、相手は黙って立ち去った。」）

入力に無い人物・場所・アイテム・結果・成否を新たに創作しない。
キューや observed の事実と矛盾しない表現にする。"""
_MAX_SUBJECTIVE_FIELD_CHARS = 700
# heading は afterglow index で並べる 1 行見出し。長すぎると視認性を損ね、
# prompt も嵩むため切り詰める。30 文字は「行動 + 印象的な 1 要素」を入れる
# 余裕としてユーザとの議論で合意した上限。
_MAX_HEADING_CHARS = 30


def _normalize_heading(raw: Any) -> str | None:
    """LLM 出力の heading を value object に渡せる形に揃える。

    - None / 非 str / 空白のみ → None
    - 長すぎる → ``_MAX_HEADING_CHARS`` 文字で切り詰め、末尾に「…」
    後続の SubjectiveEpisode コンストラクタはここで None / 非空 str だけを
    受け取る前提のため、空文字を許さない既存の Optional フィールド規約と
    整合する。
    """
    if raw is None or not isinstance(raw, str):
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if len(stripped) <= _MAX_HEADING_CHARS:
        return stripped
    return stripped[: _MAX_HEADING_CHARS - 1].rstrip() + "…"


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
        f"expected (行動前の予測):\n{ep.expected if ep.expected else '(なし)'}",
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


def _structured_prediction_error_fallback(
    draft: SubjectiveEpisode,
    encoding_input: ChunkEncodingInput,
) -> str | None:
    """LLM 不在・失敗時の保守的な prediction_error。

    予測 (expected) があり、かつ chunk に構造的な失敗 (success=False の action) が
    含まれるときだけ、最小限の乖離を残す。「成功したが予測と違う」のような意味的な
    食い違いは LLM 判断が要るので、ここでは扱わない (= None)。誤った驚きを
    捏造しないため、構造的に観測できる差分のみに限定する。
    """
    if not (isinstance(draft.expected, str) and draft.expected.strip()):
        return None
    if not any(not a.success for a in encoding_input.action_results):
        return None
    return "予測していたが、行動の一部が失敗した。"


class EpisodicChunkSubjectiveFieldsService:
    """
    ルール草案へ interpreted / recall_text / prediction_error を付与する。

    interpreted / recall_text は LLM 失敗・不正 JSON 時に what / observed 由来の
    テンプレへ落とす。prediction_error (= 予測と結果の質的乖離) は LLM が判断し、
    LLM 値が無いときは構造的失敗のみの保守 fallback (それも無ければ None)。
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
        LLM で interpreted / recall_text / prediction_error を埋め合わせる。

        interpreted / recall_text は LLM 失敗・不正 JSON 時に what / observed 由来の
        テンプレへフォールバックする。prediction_error は LLM 値が無ければ構造的
        失敗のみの保守 fallback (それも無ければ None = 予測どおり / 予測なし)。
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
            '{"interpreted": "...", "recall_text": "...", "prediction_error": "...", "heading": "..."}',
        ]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_EPISODE_SUBJECTIVE_JSON},
            {"role": "user", "content": "\n\n".join(user_sections)},
        ]
        interp_llm: str | None = None
        recall_llm: str | None = None
        pred_err_llm: str | None = None
        heading_llm: str | None = None
        try:
            raw_obj = self._completion.complete_episode_subjective_json(messages)
            if not isinstance(raw_obj, dict):
                self._logger.warning(
                    "Episode subjective completion returned non-object; using template fallback"
                )
            else:
                interp_llm = _normalize_llm_str(raw_obj.get("interpreted"))
                recall_llm = _normalize_llm_str(raw_obj.get("recall_text"))
                pred_err_llm = _normalize_llm_str(raw_obj.get("prediction_error"))
                # heading は afterglow index 用の 1 行見出し (#526 段階 3 後続)。
                # 失敗時 / 欠落時は None に倒し、SubjectiveEpisode に渡る前に
                # 30 文字へ切り詰める (後続テストで保証)。
                heading_llm = _normalize_heading(raw_obj.get("heading"))
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
        # prediction_error は str/None 両方ありうる (予測どおり=None)。LLM 値が
        # 無ければ構造的差分のみの保守 fallback (失敗時 None)。
        prediction_error = (
            pred_err_llm
            if pred_err_llm is not None
            else _structured_prediction_error_fallback(draft, encoding_input)
        )
        merged = replace(
            draft,
            interpreted=interpreted,
            recall_text=recall_text,
            prediction_error=prediction_error,
            heading=heading_llm,
        )
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
