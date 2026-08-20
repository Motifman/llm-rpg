"""行動履歴へ残す tool 引数を、引数名ごとに分類する。

分類の軸は tool 名ではなく JSON Schema の property 名である。同じ引数名を持つ
tool が増えても同じ表示規約が効き、新しい property を分類し忘れた場合は
``create_world_runtime`` の起動時検査が止める。
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Mapping, Optional


class ActionArgumentClassificationError(RuntimeError):
    """露出する tool 引数に履歴表示上の分類が無い。"""


class ActionArgumentDisplayKind(str, Enum):
    """履歴の ``呼び出し`` 行で引数をどう扱うか。"""

    IDENTIFIER_STRING = "identifier_string"
    IDENTIFIER_JSON = "identifier_json"
    FREE_TEXT = "free_text"
    OMIT = "omit"


# 各行は tool catalog の同名 JSON Schema property を読んで分類している。
# コピー可能な値は identifier_arguments、自由文は値を保存せず引数名だけ、
# 直後の専用行と重複する主観入力は省略する。
ACTION_ARGUMENT_CLASSIFICATIONS: Mapping[str, ActionArgumentDisplayKind] = {
    # memory_recall_episodes.about: 検索した話題そのものは自由記述。
    "about": ActionArgumentDisplayKind.FREE_TEXT,
    # interact.action_name / prepare_action.action_name:
    # 表示された操作名と完全一致が必要。#853 で prepare_action の action_id を
    # この名前へ寄せたので、2 つの tool が同じ規約を共有する。
    "action_name": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # speak.channel: say / shout / whisper の列挙値と完全一致が必要。
    "channel": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # speak.content / memo_add.content: 本文を自由に書く入力。
    "content": ActionArgumentDisplayKind.FREE_TEXT,
    # travel_to.destination_label: 現在状態に出た場所名と完全一致が必要。
    "destination_label": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # expected_result: 直後の [予測: ...] 行に同じ値を表示済み。
    "expected_result": ActionArgumentDisplayKind.OMIT,
    # give_item.gives: item_label / target_player_label を持つ配列を JSON のまま渡す。
    "gives": ActionArgumentDisplayKind.IDENTIFIER_JSON,
    # goal_outcome: achieved / abandoned / null の列挙値と完全一致が必要。
    "goal_outcome": ActionArgumentDisplayKind.IDENTIFIER_JSON,
    # goal_update: 数日スケールの目的を書き直す自由記述。
    "goal_update": ActionArgumentDisplayKind.FREE_TEXT,
    # pickup_item.ground_item_label: 現在状態に出た地面アイテム名と完全一致が必要。
    "ground_item_label": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # memory_* handle: 想起結果が発行した handle と完全一致が必要。
    "handle": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # inner_thought: 直後の「心の声:」行に同じ値を表示済み。
    "inner_thought": ActionArgumentDisplayKind.OMIT,
    # use_item / drop_item の item_label: 所持品表示の名前と完全一致が必要。
    "item_label": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # trade_offer.gives / asks: 品と gold を持つオブジェクトを JSON のまま渡す。
    "gives_side": ActionArgumentDisplayKind.IDENTIFIER_JSON,
    "asks": ActionArgumentDisplayKind.IDENTIFIER_JSON,
    # trade_accept / trade_decline.offerer_player_label: 申し出た人の名前。
    "offerer_player_label": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # buy_item / sell_item.merchant_label: 「商人:」に出た商人名と完全一致が必要。
    "merchant_label": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # buy_item / sell_item.quantity: schema の整数値を JSON number のまま渡す。
    "quantity": ActionArgumentDisplayKind.IDENTIFIER_JSON,
    # market_list_item.unit_price / market_reprice.new_unit_price:
    # 1 つあたりの値段。schema の整数値を JSON number のまま渡す。
    "unit_price": ActionArgumentDisplayKind.IDENTIFIER_JSON,
    "new_unit_price": ActionArgumentDisplayKind.IDENTIFIER_JSON,
    # market_reprice / market_cancel.side: 売り注文か買い注文かを表す enum 値。
    "side": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # memo_done.memo_ids: 表示された memo ID の配列を JSON のまま渡す。
    "memo_ids": ActionArgumentDisplayKind.IDENTIFIER_JSON,
    # interact.parameters: interaction ごとに形が変わる自由入力本文。
    "parameters": ActionArgumentDisplayKind.FREE_TEXT,
    # memory_search_semantic.query: 意味記憶を探す自由記述。
    "query": ActionArgumentDisplayKind.FREE_TEXT,
    # wait.reason: 待つ理由を自由に書く入力。
    "reason": ActionArgumentDisplayKind.FREE_TEXT,
    # world action の say_inline: 行動と同時に話す自由記述。
    "say_inline": ActionArgumentDisplayKind.FREE_TEXT,
    # drop_item / pickup_item.stealth: JSON boolean をそのまま渡す。
    "stealth": ActionArgumentDisplayKind.IDENTIFIER_JSON,
    # set_sub_location.sub_location_label: 表示された補助位置名と完全一致が必要。
    "sub_location_label": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # target_label: 現在状態に出た物体・人物・敵の名前と完全一致が必要。
    "target_label": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # target_player_label: 現在状態に出た人物名と完全一致が必要。
    "target_player_label": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # memory_recall_episodes.time_range: today / yesterday 等の列挙値と完全一致が必要。
    "time_range": ActionArgumentDisplayKind.IDENTIFIER_STRING,
    # memory search top_k: schema の整数値を JSON number のまま渡す。
    "top_k": ActionArgumentDisplayKind.IDENTIFIER_JSON,
}

_FREE_TEXT_ARGUMENT_PLACEHOLDERS: Mapping[str, str] = {
    "about": "話題",
    "content": "本文",
    "goal_update": "目的",
    "parameters": "本文",
    "query": "検索語",
    "reason": "理由",
    "say_inline": "発言",
}


def unclassified_action_argument_names(
    definitions: object,
) -> tuple[str, ...]:
    """tool 定義群に在る未分類 property 名を辞書順で返す。"""

    missing: set[str] = set()
    for definition in definitions:  # type: ignore[union-attr]
        parameters = getattr(definition, "parameters", {})
        properties = parameters.get("properties", {}) if isinstance(parameters, dict) else {}
        if not isinstance(properties, dict):
            continue
        missing.update(set(properties) - set(ACTION_ARGUMENT_CLASSIFICATIONS))
    return tuple(sorted(missing))


def format_action_call_for_history(
    tool_name: Optional[str],
    identifier_arguments: Mapping[str, str],
    free_text_argument_names: tuple[str, ...],
) -> str:
    """保存済みの射影を、写せる値だけ引用した tool 呼び出し形へする。"""

    arguments: list[str] = []
    for name, value in identifier_arguments.items():
        kind = ACTION_ARGUMENT_CLASSIFICATIONS.get(name)
        rendered = (
            value
            if kind == ActionArgumentDisplayKind.IDENTIFIER_JSON
            else json.dumps(value, ensure_ascii=False)
        )
        arguments.append(f"{name}={rendered}")
    for name in free_text_argument_names:
        placeholder = _FREE_TEXT_ARGUMENT_PLACEHOLDERS.get(name, "本文")
        arguments.append(f"{name}={placeholder}")
    # tool_name の無い旧 entry に嘘の識別子を作らない。引用符の無い日本語は
    # 「そのまま引数へ写す値」ではないという既存規約にも従う。
    called_name = tool_name.strip() if tool_name and tool_name.strip() else "不明な行動"
    return f"{called_name}({', '.join(arguments)})"
