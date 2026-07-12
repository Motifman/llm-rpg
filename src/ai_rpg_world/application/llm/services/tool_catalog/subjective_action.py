"""世界へ作用する tool 用の主観入力 schema と判定。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from ai_rpg_world.application.llm.contracts.dtos import (
    EMOTION_HINT_VALUES,
    ToolDefinitionDto,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_NO_OP,
    TOOL_NAME_PREFIX_TODO,
)

SUBJECTIVE_ACTION_FIELDS = (
    "inner_thought",
    "intention",
    "expected_result",
    "emotion_hint",
)

SUBJECTIVE_ACTION_TEXT_FIELDS = (
    "inner_thought",
    "intention",
    "expected_result",
)

SUBJECTIVE_ACTION_FIELD_PROPERTIES: Dict[str, Dict[str, Any]] = {
    "inner_thought": {
        "type": "string",
        "description": (
            "システムメッセージ先頭の【ペルソナ】に揃えた、この行動を選ぶ直前の "
            "**あなた自身の頭の中の独白** を短い一文で書く。"
            "読者・観測者に見せるための演技や情景描写ではなく、いま頭の中で"
            "実際に考えている言葉そのものを書くこと。未発見の事実を知った体で書かない。"
        ),
        "minLength": 1,
        "maxLength": 500,
    },
    "intention": {
        "type": "string",
        "description": "この行動で何を達成したいか。予測結果や感情ではなく、行動目的を書く。",
        "minLength": 1,
        "maxLength": 500,
    },
    "expected_result": {
        "type": "string",
        "description": (
            "この行動をした結果、何が分かる・何が起きると予測しているか。"
            "願望や目的ではなく、行動前の予測を書く。"
        ),
        "minLength": 1,
        "maxLength": 500,
    },
    "emotion_hint": {
        "type": "string",
        "description": "行動直前の主要感情。検索・集計しやすい単一ラベルで選ぶ。",
        "enum": list(EMOTION_HINT_VALUES),
    },
}


# P6 (目的の見直し / G2): world-action tool へ足す optional フィールド。
# **GOAL_REVISION_ENABLED が ON の run では全ターンで常時露出する** (ターン
# 非依存 = tick 間で schema byte 不変。設計判断 #1 遵守。旧案の「見直しターン
# だけ露出」は prefix cache を壊すため撤回済み)。null (または省略) なら
# 「目的は変えない」。非 null なら orchestrator が goal store を supersede
# 更新する。inner_thought 等と違い required にはしない (毎ターン必須にすると
# 目的が揺れる誘惑を作る)。
GOAL_UPDATE_FIELD_NAME = "goal_update"
GOAL_UPDATE_FIELD_PROPERTY: Dict[str, Any] = {
    "type": ["string", "null"],
    "description": (
        "数日スケールの方針を捨てて立て直すときにだけ書く。"
        "次の 1 手の意図は intention に書くこと (それはここではない)。"
        "目的を変えることは、これまでの自分の方針を捨てることでもある。"
        "続けるなら書かない (null)。"
    ),
    "maxLength": 200,
}


# P8 (目的の清算 / goal_outcome 自己申告): goal_update と同じ同乗フィールド機構・
# 同じ GOAL_REVISION_ENABLED で常時露出する optional / nullable な enum。
# 「達成したのか、見切ったのか」を知っているのは本人だけなので、ルールや reflect
# ではなく本人に宣言させる (reflect は助言のまま = P7 不変条件維持)。組み合わせの
# 意味論: goal_update のみ = 言い直し (SUPERSEDED) / goal_outcome + goal_update =
# 旧目的を清算して次へ / goal_outcome のみ = 閉じて無目的に戻る。null なら「まだ
# 閉じない」。required にはしない (毎ターン必須にすると目的を急いで閉じる誘惑になる)。
GOAL_OUTCOME_FIELD_NAME = "goal_outcome"
GOAL_OUTCOME_ACHIEVED = "achieved"
GOAL_OUTCOME_ABANDONED = "abandoned"
GOAL_OUTCOME_FIELD_PROPERTY: Dict[str, Any] = {
    "type": ["string", "null"],
    "enum": [GOAL_OUTCOME_ACHIEVED, GOAL_OUTCOME_ABANDONED, None],
    "description": (
        "直前の目的を閉じるときだけ書く。成し遂げて閉じるなら achieved、"
        "見切って捨てるなら abandoned。ただの言い直し (目的は同じで表現を"
        "変えるだけ) なら書かない (null)。続けるなら書かない。"
    ),
}


def with_goal_outcome_schema(definition: ToolDefinitionDto) -> ToolDefinitionDto:
    """対象 tool の JSON Schema に optional な ``goal_outcome`` を足した定義を返す。

    ``with_goal_update_schema`` と同じく GOAL_REVISION_ENABLED が ON の run で
    全 subjective action tool に常時適用する (ターン非依存。tick 間 byte 不変)。
    required には入れない (optional / nullable)。
    """
    if not isinstance(definition, ToolDefinitionDto):
        raise TypeError("definition must be ToolDefinitionDto")
    if not is_subjective_action_tool(definition.name):
        return definition
    parameters = deepcopy(definition.parameters)
    properties = dict(parameters.get("properties") or {})
    properties[GOAL_OUTCOME_FIELD_NAME] = deepcopy(GOAL_OUTCOME_FIELD_PROPERTY)
    parameters["properties"] = properties
    return ToolDefinitionDto(
        name=definition.name,
        description=definition.description,
        parameters=parameters,
        category=definition.category,
    )


def with_goal_update_schema(definition: ToolDefinitionDto) -> ToolDefinitionDto:
    """対象 tool の JSON Schema に optional な ``goal_update`` を足した定義を返す。

    GOAL_REVISION_ENABLED が ON の run で ``get_tool_definitions`` が全 tool に
    対し常時適用する (ターン非依存。tick 間で schema 不変)。subjective action
    tool 以外には足さない。required には入れない (optional / nullable)。
    """
    if not isinstance(definition, ToolDefinitionDto):
        raise TypeError("definition must be ToolDefinitionDto")
    if not is_subjective_action_tool(definition.name):
        return definition
    parameters = deepcopy(definition.parameters)
    properties = dict(parameters.get("properties") or {})
    properties[GOAL_UPDATE_FIELD_NAME] = deepcopy(GOAL_UPDATE_FIELD_PROPERTY)
    parameters["properties"] = properties
    # required には足さない (optional)。
    return ToolDefinitionDto(
        name=definition.name,
        description=definition.description,
        parameters=parameters,
        category=definition.category,
    )


def is_subjective_action_tool(tool_name: str) -> bool:
    """世界へ作用する主観入力付き tool かどうか。"""

    if not isinstance(tool_name, str):
        return False
    if tool_name == TOOL_NAME_NO_OP:
        return False
    if tool_name.startswith(TOOL_NAME_PREFIX_TODO):
        return False
    return bool(tool_name)


def with_subjective_action_schema(definition: ToolDefinitionDto) -> ToolDefinitionDto:
    """対象 tool の JSON Schema に主観入力を足した定義を返す。"""

    if not isinstance(definition, ToolDefinitionDto):
        raise TypeError("definition must be ToolDefinitionDto")
    if not is_subjective_action_tool(definition.name):
        return definition

    parameters = deepcopy(definition.parameters)
    properties = dict(parameters.get("properties") or {})
    required = list(parameters.get("required") or [])
    for name, prop in SUBJECTIVE_ACTION_FIELD_PROPERTIES.items():
        properties[name] = deepcopy(prop)
        if name not in required:
            required.append(name)
    parameters["properties"] = properties
    parameters["required"] = required
    return ToolDefinitionDto(
        name=definition.name,
        description=definition.description,
        parameters=parameters,
        category=definition.category,
    )


def with_expected_result_schema(
    definition: ToolDefinitionDto, *, required: bool
) -> ToolDefinitionDto:
    """``expected_result`` (行動前の予測) だけを tool schema に足した定義を返す (#526 v0)。

    予測誤差駆動の学習ループ (PR1-3) の入口。``with_subjective_action_schema`` が
    4 facet を一括必須化するのに対し、本関数は予測ループの駆動因である
    ``expected_result`` 一本だけを選択露出する (intention / emotion_hint は v0 では
    出さない = 機能を束ねない)。

    Args:
        required: ``True`` なら ``required`` にも追加し毎ターン必須化。``False`` なら
            ``properties`` にのみ足し、LLM が予測を持つときだけ書ける optional 露出。
    """
    if not isinstance(definition, ToolDefinitionDto):
        raise TypeError("definition must be ToolDefinitionDto")

    parameters = deepcopy(definition.parameters)
    properties = dict(parameters.get("properties") or {})
    properties["expected_result"] = deepcopy(
        SUBJECTIVE_ACTION_FIELD_PROPERTIES["expected_result"]
    )
    parameters["properties"] = properties
    if required:
        required_fields = list(parameters.get("required") or [])
        if "expected_result" not in required_fields:
            required_fields.append("expected_result")
        parameters["required"] = required_fields
    return ToolDefinitionDto(
        name=definition.name,
        description=definition.description,
        parameters=parameters,
        category=definition.category,
    )
