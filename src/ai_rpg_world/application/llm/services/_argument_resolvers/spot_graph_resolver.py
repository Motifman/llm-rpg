"""スポットグラフ系ツールの引数解決（ラベル → 内部 ID）。"""

import logging
from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    MonsterToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
    require_target,
    require_target_type,
)

logger = logging.getLogger(__name__)


def _find_target_by_display_name(
    runtime_context: ToolRuntimeContextDto,
    *,
    kind: str,
    display_name: str,
) -> Optional[ToolRuntimeTargetDto]:
    """`runtime_context.targets` を全スキャンし、同 kind かつ display_name 一致の最初の target を返す。

    LLM が会話履歴に残った `S1` などのスポット相対ラベルを次 turn でも再利用すると、
    自スポット移動後にラベルの指す先が反転して bouncing が起きる。これを避けるため、
    スポット名 (display_name) そのものを引数として受け付け、不変な意味で解決できるようにする。

    同名スポットが複数ある場合は最初にマッチしたものを採用しつつ warning を残す。
    シナリオ規約として同名禁止が望ましいが、ここでは防御的に最初の 1 件で先へ進める。
    """
    matches: list[ToolRuntimeTargetDto] = []
    for target in runtime_context.targets.values():
        if target.kind == kind and target.display_name == display_name:
            matches.append(target)
    if not matches:
        return None
    if len(matches) > 1:
        logger.warning(
            "Multiple runtime targets share the same display_name; "
            "using the first match. kind=%s display_name=%s labels=%s",
            kind,
            display_name,
            [t.label for t in matches],
        )
    return matches[0]
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
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
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
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
        if tool_name == TOOL_NAME_SPOT_GRAPH_LISTEN:
            return _with_inner_thought({}, args)
        if tool_name == TOOL_NAME_SPOT_GRAPH_INTERACT:
            return self._resolve_interact(args, runtime_context)
        if tool_name == TOOL_NAME_SPOT_GRAPH_ATTACK:
            return self._resolve_attack(args, runtime_context)
        return None

    def _resolve_attack(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        """`spot_graph_attack` の target_label をモンスター ID に解決する。

        ラベルが MonsterToolRuntimeTargetDto に解決できない場合、または
        monster_id が None の場合は `INVALID_TARGET_LABEL` で弾く。
        """
        label = args.get("target_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "攻撃対象ラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = require_target_type(
            label,
            runtime_context,
            "攻撃対象ラベル",
            (MonsterToolRuntimeTargetDto,),
            invalid_label_code="INVALID_TARGET_LABEL",
            invalid_kind_code="INVALID_TARGET_KIND",
        )
        if target.monster_id is None:
            raise ToolArgumentResolutionException(
                f"このラベルは攻撃対象ではありません: {label}",
                "INVALID_TARGET_KIND",
            )
        return _with_inner_thought(
            {
                "monster_id": target.monster_id,
                "target_display_name": target.display_name,
            },
            args,
        )

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
        # まず既存のラベル経由 (S1 等) で解決を試み、失敗したらスポット名 (display_name)
        # でフォールバックする。S1 系のラベルは「現在地から見た first neighbor」という
        # スポット相対の意味しか持たないので、会話履歴に残った tool_call を再利用すると
        # 移動後に意味が反転する。スポット名は不変なので意味が安定する。
        target: Optional[ToolRuntimeTargetDto]
        if label in runtime_context.targets:
            target = require_target_type(
                label,
                runtime_context,
                "接続先ラベル",
                (DestinationToolRuntimeTargetDto,),
                invalid_label_code="INVALID_DESTINATION_LABEL",
                invalid_kind_code="INVALID_DESTINATION_KIND",
            )
        else:
            target = _find_target_by_display_name(
                runtime_context,
                kind="spot_graph_destination",
                display_name=label,
            )
            if target is None:
                raise ToolArgumentResolutionException(
                    f"指定された対象ラベルは現在の候補にありません: {label}",
                    "INVALID_DESTINATION_LABEL",
                )
            if not isinstance(target, DestinationToolRuntimeTargetDto):
                raise ToolArgumentResolutionException(
                    f"接続先ラベルとして使えないラベルです: {label}",
                    "INVALID_DESTINATION_KIND",
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
        # destination と同じく、SL1 等のラベルだけでなくサブロケーション名 (文字列) も
        # 受け付ける。理由は _resolve_travel_to と同じく label leak 対策。
        if label in runtime_context.targets:
            target = require_target(
                label,
                runtime_context,
                "サブロケーションラベル",
                invalid_label_code="INVALID_TARGET_LABEL",
            )
        else:
            found = _find_target_by_display_name(
                runtime_context,
                kind="spot_graph_sub_location",
                display_name=label,
            )
            if found is None:
                raise ToolArgumentResolutionException(
                    f"指定された対象ラベルは現在の候補にありません: {label}",
                    "INVALID_TARGET_LABEL",
                )
            target = found
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
