"""ツールの説明文から、この世界に無いツールに触れる文を外す。

説明文は世界を問わず 1 つの定数で書くので、ほかのツールに触れる文 (「同じ場所の相手に
渡すには give_item を使う」など) は、そのツールが無効化された世界では打てない手を勧める。
LLM に渡す直前に、`ToolExposure.is_exposed` の答えで取捨する。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto

#: 説明文のツール名 → (触れているツール, 説明文の中の文, そのツールが無いときの置き換え)。
#:
#: 文は説明文に書いたとおりに写す。`test_cross_tool_mentions.py` が、表の文が説明文に
#: 実在することと、どのツールを無いことにしても名前が残らないことを見張る。
#: 見張るのは名前だけで、置き換えた文が名前を出さずに無い手を勧めること (give_item も
#: 無い世界で tend_to_player が「食料を与える」と勧めるなど) は見えない。
CROSS_TOOL_MENTIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "use_item": (("give_item", "同じ場所の相手に渡すには give_item を使う。", ""),),
    "drop_item": (("pickup_item", "同じスポットに居る他プレイヤーが後で pickup_item で拾える。", ""),),
    "buy_item": (("give_item", "**give_item と違って部分成功しない**", "**部分成功しない**"),),
    "sell_item": (("give_item", "**give_item と違って部分成功しない**", "**部分成功しない**"),),
    "market_list_item": (
        (
            "market_reprice",
            "同じ品の出品は 1 件までで、値を変えたいときは market_reprice を使う。",
            "同じ品の出品は 1 件まで。",
        ),
    ),
    "market_cancel": (("market_reprice", "値を変えたいだけなら market_reprice の方が確実。", ""),),
    "market_bid": (
        (
            "market_reprice",
            "同じ品の買い注文は 1 件までで、値を変えたいときは market_reprice を使う。",
            "同じ品の買い注文は 1 件まで。",
        ),
    ),
    "attack": (
        (
            "travel_to",
            "連続被弾で HP を失うより、``travel_to`` で別の spot へ **逃走** する方が"
            "安全なこともあり、状況で選ぶこと。",
            "",
        ),
    ),
    "listen": (
        (
            "speak",
            "- 他プレイヤーの発話 (speak の声) はこのツールでは聞こえない。",
            "- 他プレイヤーの発話はこのツールでは聞こえない。",
        ),
    ),
    "tend_to_player": (
        (
            "speak",
            "そうした相手にはまず ``speak`` で話しかけるか食料を与えること。",
            "そうした相手には食料を与えること。",
        ),
    ),
}


def without_absent_tool_mentions(definition: ToolDefinitionDto, is_exposed: Callable[[str], bool]) -> ToolDefinitionDto:
    """``is_exposed`` が無いと答えたツールに触れる文を、説明文から外した定義を返す。"""
    description = definition.description
    for mentioned, sentence, replacement in CROSS_TOOL_MENTIONS.get(definition.name, ()):
        if not is_exposed(mentioned):
            description = description.replace(sentence, replacement)
    if description == definition.description:
        return definition
    return replace(definition, description=description)


__all__ = ["CROSS_TOOL_MENTIONS", "without_absent_tool_mentions"]
