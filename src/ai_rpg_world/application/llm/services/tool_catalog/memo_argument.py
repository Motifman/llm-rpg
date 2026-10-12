"""環境の tool に付ける、メモ帳を書く引数 ``memo`` (#1628)。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.being.domain.memo_book import (
    KIND_LIMITS,
    MEMO_TEXT_MAX_LENGTH,
    MemoCertainty,
    MemoKind,
    MemoSource,
)

MEMO_FIELD_NAME = "memo"

_LIMITS_TEXT = (
    f"やること {KIND_LIMITS[MemoKind.TODO]} 件・"
    f"分かったこと {KIND_LIMITS[MemoKind.FACT]} 件・"
    f"人について {KIND_LIMITS[MemoKind.PERSON]} 件"
)


def memo_field_property(*, episode_source_offered: bool) -> dict[str, Any]:
    """``episode_source_offered`` が False なら、出どころの選択肢に ``episode`` を出さない。

    本人がエピソードの呼び名を目次で見られない設定で選ばせると、知らない呼び名を書いて
    外されるだけになる (design_decisions D1616 と同じ、無いものを指さない)。
    """
    sources = [MemoSource.SELF.value, MemoSource.HEARD.value]
    source_text = "self = 自分で確かめた、heard = 人から聞いた"
    from_text = "heard なら誰から聞いたか"
    if episode_source_offered:
        sources.append(MemoSource.EPISODE.value)
        source_text += "、episode = 思い出したエピソードから"
        from_text += "、episode ならそのエピソードの呼び名 (ep_ で始まる)"
    return {
        "type": "array",
        "description": (
            "メモ帳への書き込み。行動と一緒に書け、手番を使わない。書くことが無ければ省略する。"
            "メモは毎ターン【メモ】に全部出る。1 回に操作をいくつでも並べられ、書いた順に当てる。"
            '足す: {"do": "add", "kind": 分類, "text": 文}。'
            "分類は todo = やること (これからすること)、fact = 分かったこと (世界について分かったこと)、"
            "person = 人について (誰のことかは文の中に書く)。"
            f"fact には source ({source_text}) と certainty (sure = 確か、guess = 推測) も書き、"
            f"{from_text}を from に書く。"
            '書き換える: {"do": "edit", "id": "m_…", "text": 新しい文}。fact なら source と certainty も書き直せる。'
            '消す: {"do": "remove", "id": "m_…"}。やることが済んだら消す。'
            f"文は {MEMO_TEXT_MAX_LENGTH} 字まで。件数の上限は {_LIMITS_TEXT} で、"
            "上限に達したら消すか書き換える。"
            '例: [{"do": "add", "kind": "todo", "text": "事務所で鍵を取る"}]。'
            '例: [{"do": "add", "kind": "fact", "text": "水門の弁は目盛りが関係するかも", '
            '"source": "heard", "certainty": "guess", "from": "門番"}, '
            '{"do": "remove", "id": "m_3f2a7b"}]。'
        ),
        "items": {
            "type": "object",
            "properties": {
                "do": {"type": "string", "enum": ["add", "edit", "remove"]},
                "kind": {"type": "string", "enum": [kind.value for kind in MemoKind]},
                "text": {"type": "string", "minLength": 1, "maxLength": MEMO_TEXT_MAX_LENGTH},
                "id": {"type": "string", "description": "書き換える・消すメモの呼び名 (m_ で始まる)。"},
                "source": {"type": "string", "enum": sources},
                "certainty": {
                    "type": "string",
                    "enum": [certainty.value for certainty in MemoCertainty],
                },
                "from": {"type": "string"},
            },
            "required": ["do"],
        },
    }


def with_memo_schema(
    definition: ToolDefinitionDto, *, episode_source_offered: bool
) -> ToolDefinitionDto:
    """省略できる引数として足す。毎回書かせると、書くことが無いターンにも何かを書かせてしまう。"""
    if not isinstance(definition, ToolDefinitionDto):
        raise TypeError("definition must be ToolDefinitionDto")
    parameters = deepcopy(definition.parameters)
    properties = dict(parameters.get("properties") or {})
    properties[MEMO_FIELD_NAME] = memo_field_property(
        episode_source_offered=episode_source_offered
    )
    parameters["properties"] = properties
    return ToolDefinitionDto(
        name=definition.name,
        description=definition.description,
        parameters=parameters,
        category=definition.category,
    )


__all__ = ["MEMO_FIELD_NAME", "memo_field_property", "with_memo_schema"]
