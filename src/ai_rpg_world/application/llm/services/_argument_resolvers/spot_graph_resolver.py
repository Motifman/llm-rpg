"""スポットグラフ系ツールの引数解決（ラベル → 内部 ID）。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
    require_target,
    require_target_type,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)

_SPOT_GRAPH_TOOLS = frozenset({
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_WAIT,
})


def _inner_thought_value(args: Dict[str, Any]) -> str:
    raw = args.get("inner_thought", "")
    if not isinstance(raw, str):
        return str(raw) if raw is not None else ""
    return raw.strip()


def _with_inner_thought(base: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    out["inner_thought"] = _inner_thought_value(args)
    return out


class SpotGraphArgumentResolver:
    """spot_graph_* ツールのラベル引数を canonical 引数に解決する。"""

    def resolve_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Optional[Dict[str, Any]]:
        if tool_name not in _SPOT_GRAPH_TOOLS:
            return None
        if tool_name == TOOL_NAME_SPOT_GRAPH_TRAVEL_TO:
            return self._resolve_travel_to(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION:
            return self._resolve_set_sub_location(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_EXPLORE:
            return _with_inner_thought({}, args)
        if tool_name == TOOL_NAME_SPOT_GRAPH_WAIT:
            return _with_inner_thought(
                {"reason": str(args.get("reason", "")).strip()}, args
            )
        if tool_name == TOOL_NAME_SPOT_GRAPH_INTERACT:
            return self._resolve_interact(args, runtime_context)
        return None

    def _resolve_travel_to(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("destination_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "接続先ラベルが指定されていません。",
                "INVALID_DESTINATION_LABEL",
            )
        target = require_target_type(
            label,
            runtime_context,
            "接続先ラベル",
            (DestinationToolRuntimeTargetDto,),
            invalid_label_code="INVALID_DESTINATION_LABEL",
            invalid_kind_code="INVALID_DESTINATION_KIND",
        )
        if target.spot_id is None:
            raise ToolArgumentResolutionException(
                f"移動先として解決できないラベルです: {label}",
                "INVALID_DESTINATION_KIND",
            )
        return _with_inner_thought({"destination_spot_id": target.spot_id}, args)

    def _resolve_set_sub_location(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("sub_location_label")
        if not label:
            return _with_inner_thought({"sub_location_id": None}, args)
        target = require_target(
            label,
            runtime_context,
            "サブロケーションラベル",
            invalid_label_code="INVALID_TARGET_LABEL",
        )
        if target.sub_location_id is None:
            raise ToolArgumentResolutionException(
                f"サブロケーションとして解決できないラベルです: {label}",
                "INVALID_TARGET_KIND",
            )
        return _with_inner_thought(
            {"sub_location_id": target.sub_location_id}, args
        )

    def _resolve_interact(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("object_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "オブジェクトラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = require_target(
            label,
            runtime_context,
            "オブジェクトラベル",
            invalid_label_code="INVALID_TARGET_LABEL",
        )
        if target.world_object_id is None:
            raise ToolArgumentResolutionException(
                f"オブジェクトとして解決できないラベルです: {label}",
                "INVALID_TARGET_KIND",
            )
        action = args.get("action_name", "")
        if not isinstance(action, str) or not action.strip():
            raise ToolArgumentResolutionException(
                "action_name が指定されていません。",
                "INVALID_ARGUMENT",
            )
        return _with_inner_thought(
            {"object_id": target.world_object_id, "action_name": action.strip()},
            args,
        )
