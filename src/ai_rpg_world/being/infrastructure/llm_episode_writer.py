"""LLM で、Being 本人がエピソードの下書きを書く (#1626、design_decisions D1824-13)。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ai_rpg_world.being.domain.episode import BODY_MAX_LENGTH, INDEX_TEXT_MAX_LENGTH, EpisodeIndex
from ai_rpg_world.being.domain.episode_writer import EpisodeDraft, EpisodeDrafts, EpisodeWriter
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeWritingResponseException,
)

MAX_EPISODES_PER_WRITING = 3
EVENTS_HEADING = "【書き残す範囲の出来事 (古い → 新しい)】"

_FIELD_LIMITS = (
    ("about", INDEX_TEXT_MAX_LENGTH),
    ("recall_when", INDEX_TEXT_MAX_LENGTH),
    ("body", BODY_MAX_LENGTH),
)

SYSTEM_PROMPT = f"""\
あなたはあるキャラクター本人として、自分の体験を、あとで思い出せる記憶として書き残します。

【分け方】
- 出来事の切れ目ごとに 1 件の記憶にする。多くても {MAX_EPISODES_PER_WRITING} 件まで
- 何も起きていなければ 0 件でよい

【1 件に書くこと】
- about: どんな記憶か。{INDEX_TEXT_MAX_LENGTH} 字まで
- recall_when: どんな時に思い出すとよいか。{INDEX_TEXT_MAX_LENGTH} 字まで。「金庫や鍵の話が出たとき」のように場面で書く
- body: 本文。{BODY_MAX_LENGTH} 字まで。そのとき見たこと・したこと・感じたことを、そのときの自分の言葉で書く。後から分かったことは混ぜない

【書かないこと】
- 番号や P1 のような呼び方。人や場所や物は、自分が知っている名前で書く
- ゲームの仕組みの言い回し (「次の行動を選べる」など)

【出力形式】JSON object (この schema を厳守):
{{
  "episodes": [
    {{"about": "どんな記憶か", "recall_when": "どんな時に思い出すか", "body": "本文"}}
  ]
}}
"""


class EpisodeWritingCompletion(ABC):
    @abstractmethod
    def complete_episode_writing_json(self, messages: list[dict[str, str]]) -> Any:
        """応答の JSON を読んだ値を返す。呼び出しに失敗したら例外を投げる。"""


class LlmEpisodeWriter(EpisodeWriter):
    def __init__(self, completion: EpisodeWritingCompletion) -> None:
        self._completion = completion

    def write(self, *, self_name: str, persona: str, events_text: str) -> EpisodeDrafts:
        if not events_text.strip():
            raise ValueError("events_text must not be blank")
        response = self._completion.complete_episode_writing_json(
            _messages(self_name=self_name, persona=persona, events_text=events_text)
        )
        return _drafts_from(response)


def _draft_from(item: object) -> EpisodeDraft:
    if not isinstance(item, dict):
        raise EpisodeWritingResponseException(f"episode must be an object, got {type(item).__name__}")
    texts: dict[str, str] = {}
    truncated: dict[str, int] = {}
    for key, limit in _FIELD_LIMITS:
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            raise EpisodeWritingResponseException(f"episode {key} must be non-blank str")
        text = value.strip()
        if len(text) > limit:
            truncated[key] = len(text)
            text = text[:limit]
        texts[key] = text
    return EpisodeDraft(
        index=EpisodeIndex(summary=texts["about"], recall_when=texts["recall_when"]),
        body=texts["body"],
        truncated=truncated,
    )


def _drafts_from(response: object) -> EpisodeDrafts:
    if not isinstance(response, dict) or not isinstance(response.get("episodes"), list):
        raise EpisodeWritingResponseException("response must be an object with an episodes list")
    items = response["episodes"]
    kept = items[:MAX_EPISODES_PER_WRITING]
    return EpisodeDrafts(
        drafts=tuple(_draft_from(item) for item in kept), dropped_count=len(items) - len(kept)
    )


def _messages(*, self_name: str, persona: str, events_text: str) -> list[dict[str, str]]:
    lines = [f"あなた = {self_name}"]
    if persona.strip():
        lines.append(f"あなたの人物像 = {persona.strip()}")
    lines += [
        "",
        EVENTS_HEADING,
        events_text,
        "",
        "上記から JSON 形式で記憶を書いてください。",
    ]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]


__all__ = [
    "EVENTS_HEADING",
    "MAX_EPISODES_PER_WRITING",
    "SYSTEM_PROMPT",
    "EpisodeWritingCompletion",
    "LlmEpisodeWriter",
]
