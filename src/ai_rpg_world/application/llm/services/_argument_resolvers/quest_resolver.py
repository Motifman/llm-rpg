"""クエスト系ツールの引数解決。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    GuildToolRuntimeTargetDto,
    QuestToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
    require_target_type,
    safe_int,
)
from ai_rpg_world.application.llm.services.quest_objective_target_resolver import (
    QuestObjectiveTargetResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_QUEST_ACCEPT,
    TOOL_NAME_QUEST_APPROVE,
    TOOL_NAME_QUEST_CANCEL,
    TOOL_NAME_QUEST_ISSUE,
)


class QuestArgumentResolver:
    """クエスト関連ツールの引数解決。"""

    def __init__(self, objective_resolver: QuestObjectiveTargetResolver) -> None:
        self._objective_resolver = objective_resolver

    def resolve_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Optional[Dict[str, Any]]:
        if tool_name == "quest_accept":
            return self._resolve_quest_label(args, runtime_context)
        if tool_name == "quest_cancel":
            return self._resolve_quest_label(args, runtime_context)
        if tool_name == "quest_approve":
            return self._resolve_quest_label(args, runtime_context)
        if tool_name == "quest_issue":
            return self._resolve_quest_issue(args, runtime_context)
        return None

    def _resolve_quest_label(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("quest_label")
        target = require_target_type(
            label,
            runtime_context,
            "クエストラベル",
            (QuestToolRuntimeTargetDto,),
        )
        if target.quest_id is None:
            raise ToolArgumentResolutionException(
                f"クエストとして解決できません: {label}",
                "INVALID_TARGET_KIND",
            )
        return {"quest_id": target.quest_id}

    def _resolve_quest_issue(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        raw_objectives = args.get("objectives")
        if not isinstance(raw_objectives, (list, tuple)) or len(raw_objectives) == 0:
            raise ToolArgumentResolutionException(
                "クエスト目標（objectives）が1件以上必要です。",
                "INVALID_OBJECTIVES",
            )
        objectives: list = []
        for i, obj in enumerate(raw_objectives):
            if not isinstance(obj, dict):
                raise ToolArgumentResolutionException(
                    f"目標{i + 1}が不正な形式です。",
                    "INVALID_OBJECTIVES",
                )
            ot = obj.get("objective_type")
            tid = obj.get("target_id")
            target_name = obj.get("target_name")
            rc = obj.get("required_count")
            if not isinstance(ot, str) or ot.strip() == "":
                raise ToolArgumentResolutionException(
                    f"目標{i + 1}の objective_type が不正です。",
                    "INVALID_OBJECTIVES",
                )
            ot_stripped = ot.strip()
            tid_val = self._objective_resolver.resolve_target_id(
                ot_stripped, target_name, tid
            )
            rc_val = safe_int(rc, f"objectives[{i}].required_count", min_val=1)
            objectives.append((ot_stripped, tid_val, rc_val))
        reward_gold = safe_int(args.get("reward_gold", 0), "reward_gold", min_val=0)
        reward_items = None
        raw_items = args.get("reward_items")
        if isinstance(raw_items, (list, tuple)) and len(raw_items) > 0:
            reward_items = []
            for j, item in enumerate(raw_items):
                if isinstance(item, dict):
                    spec_id = safe_int(
                        item.get("item_spec_id"), f"reward_items[{j}].item_spec_id", min_val=1
                    )
                    qty = safe_int(
                        item.get("quantity"), f"reward_items[{j}].quantity", min_val=1
                    )
                    reward_items.append((spec_id, qty))
        result: Dict[str, Any] = {
            "objectives": objectives,
            "reward_gold": reward_gold,
            "reward_exp": 0,
            "reward_items": reward_items,
        }
        guild_label = args.get("guild_label")
        if isinstance(guild_label, str) and guild_label.strip():
            guild_target = require_target_type(
                guild_label.strip(),
                runtime_context,
                "ギルドラベル",
                (GuildToolRuntimeTargetDto,),
            )
            result["guild_id"] = guild_target.guild_id
        else:
            result["guild_id"] = None
        return result
