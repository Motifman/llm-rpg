"""【思い出せる出来事】の目次の一行を、本人が書き直すツール (#1623、#2261)。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ai_rpg_world.being.domain.episode import INDEX_TEXT_MAX_LENGTH, EpisodeIndex
from ai_rpg_world.being.domain.working_memory import EPISODE_INDEX_HEADING

HANDLE = "handle"
ABOUT = "about"
RECALL_WHEN = "recall_when"
_FREE_TEXT_PLACEHOLDERS = {ABOUT: "話題", RECALL_WHEN: "本文"}
_ARGUMENT_NAMES = {"summary": ABOUT, "recall_when": RECALL_WHEN}

MALFORMED_INDEX_REVISION_TEXT = (
    f"handle には【{EPISODE_INDEX_HEADING}】の ep_ で始まる呼び名を、"
    "about にはどんな記憶か、recall_when にはどんな時に思い出すかを、それぞれ文で書いてください。"
)
INDEX_NOT_REVISED_TEXT = "目次を直せなかった。"


def episode_index_revision_description() -> str:
    return (
        f"【{EPISODE_INDEX_HEADING}】の目次の一行 (どんな記憶か・どんな時に思い出すか) を書き直す。"
        "呼び出した本文が目次の書き方と合っていなかったとき、"
        "思い出すべき場面が目次に書いた場面と違ったときに使う。"
        "本文は変わらず、前の目次も消えずに残る。直すのに手番を 1 回使う。"
        f"about と recall_when はそれぞれ {INDEX_TEXT_MAX_LENGTH} 字まで。"
        "世界の出来事は起こさない。"
    )


def episode_index_revision_parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            HANDLE: {
                "type": "string",
                "description": f"直したい記憶の、【{EPISODE_INDEX_HEADING}】の行の先頭にある ep_ で始まる呼び名。",
            },
            ABOUT: {"type": "string", "description": "どんな記憶か。"},
            RECALL_WHEN: {
                "type": "string",
                "description": "どんな時に思い出すとよいか。「金庫や鍵の話が出たとき」のように場面で書く。",
            },
        },
        "required": [HANDLE, ABOUT, RECALL_WHEN],
    }


@dataclass(frozen=True)
class IndexRevisionRequest:
    """``truncated`` は、上限を超えて切り詰めた項目 (about・recall_when) と切り詰める前の長さ。"""

    handle: str
    index: EpisodeIndex
    truncated: dict[str, int] = field(default_factory=dict)


def read_index_revision(arguments: Mapping[str, object]) -> IndexRevisionRequest | None:
    """崩れていれば None。"""
    handle = arguments.get(HANDLE)
    about = arguments.get(ABOUT)
    recall_when = arguments.get(RECALL_WHEN)
    if not isinstance(handle, str) or not handle.strip():
        return None
    if not isinstance(about, str) or not about.strip() or not isinstance(recall_when, str) or not recall_when.strip():
        return None
    fitted = EpisodeIndex.fitted(summary=about.strip(), recall_when=recall_when.strip())
    return IndexRevisionRequest(
        handle=handle.strip(),
        index=fitted.index,
        truncated={_ARGUMENT_NAMES[name]: length for name, length in fitted.truncated.items()},
    )


def unknown_handle_text(handle: str) -> str:
    return f"{handle} という記憶は無い。【{EPISODE_INDEX_HEADING}】の呼び名を使ってください。"


def index_revised_text(handle: str, index: EpisodeIndex) -> str:
    return f"[{handle}] の目次を直した: {index.summary} — 思い出すとき: {index.recall_when}"


def index_revision_call_text(tool_name: str, arguments: Mapping[str, object]) -> str:
    """書き直した文は、次に写して使う値ではないので引用しない。"""
    parts = [f"{HANDLE}={json.dumps(arguments[HANDLE], ensure_ascii=False)}"] if HANDLE in arguments else []
    parts += [f"{name}={_FREE_TEXT_PLACEHOLDERS[name]}" for name in (ABOUT, RECALL_WHEN) if name in arguments]
    return f"{tool_name}({', '.join(parts)})"


class EpisodeIndexRevisionResult(Enum):
    REVISED = "revised"
    REJECTED = "rejected"
    FAILED = "failed"


class IndexRevisionRejectReason(Enum):
    MALFORMED = "malformed"
    UNKNOWN_HANDLE = "unknown_handle"


@dataclass(frozen=True)
class EpisodeIndexRevisionOutcome:
    """断った直しも残す。残さないと、直そうとして断られたのか、直そうとしなかったのかを見分けられない。"""

    handle: str | None
    outcome: EpisodeIndexRevisionResult
    reject_reason: IndexRevisionRejectReason | None = None
    before: EpisodeIndex | None = None
    after: EpisodeIndex | None = None
    truncated: Mapping[str, int] = field(default_factory=dict)


__all__ = [
    "ABOUT",
    "HANDLE",
    "INDEX_NOT_REVISED_TEXT",
    "MALFORMED_INDEX_REVISION_TEXT",
    "RECALL_WHEN",
    "EpisodeIndexRevisionOutcome",
    "EpisodeIndexRevisionResult",
    "IndexRevisionRejectReason",
    "IndexRevisionRequest",
    "episode_index_revision_description",
    "episode_index_revision_parameters",
    "index_revised_text",
    "index_revision_call_text",
    "read_index_revision",
    "unknown_handle_text",
]
