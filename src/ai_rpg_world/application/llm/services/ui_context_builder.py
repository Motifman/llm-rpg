"""LLM 用の一時ラベル付き UI コンテキストを組み立てる。"""

from typing import Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmUiContextDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILlmUiContextBuilder
from ai_rpg_world.application.world.contracts.dtos import (
    PlayerCurrentStateDto,
    VisibleObjectDto,
)


_VISIBLE_LABEL_PREFIX = {
    "player": "P",
    "npc": "N",
    "monster": "M",
    "destination": "S",
}

_VISIBLE_KIND_LABEL = {
    "player": "プレイヤー",
    "npc": "NPC",
    "monster": "モンスター",
    "chest": "宝箱",
    "door": "ドア",
    "resource": "資源",
    "ground_item": "落ちているアイテム",
    "object": "オブジェクト",
    "destination": "移動先",
}


class DefaultLlmUiContextBuilder(ILlmUiContextBuilder):
    """現在状態テキストにラベル付き対象一覧を重ねて返す。"""

    def build(
        self,
        current_state_text: str,
        current_state: Optional[PlayerCurrentStateDto],
    ) -> LlmUiContextDto:
        if not isinstance(current_state_text, str):
            raise TypeError("current_state_text must be str")
        if current_state is not None and not isinstance(current_state, PlayerCurrentStateDto):
            raise TypeError("current_state must be PlayerCurrentStateDto or None")

        if current_state is None:
            return LlmUiContextDto(
                current_state_text=current_state_text,
                tool_runtime_context=ToolRuntimeContextDto.empty(),
            )

        counters: Dict[str, int] = {"P": 0, "N": 0, "M": 0, "O": 0, "S": 0}
        runtime_targets: Dict[str, ToolRuntimeTargetDto] = {}
        lines = [current_state_text.rstrip()]

        visible_lines = self._build_visible_target_lines(
            current_state.visible_objects,
            counters,
            runtime_targets,
        )
        if visible_lines:
            lines.append("")
            lines.append("視界内の対象ラベル:")
            lines.extend(visible_lines)

        move_lines = self._build_move_lines(
            current_state,
            counters,
            runtime_targets,
        )
        if move_lines:
            lines.append("")
            lines.append("移動先ラベル:")
            lines.extend(move_lines)

        return LlmUiContextDto(
            current_state_text="\n".join(lines).rstrip(),
            tool_runtime_context=ToolRuntimeContextDto(targets=runtime_targets),
        )

    def _build_visible_target_lines(
        self,
        visible_objects: list[VisibleObjectDto],
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> list[str]:
        lines: list[str] = []
        sort_key = lambda obj: (
            obj.distance,
            obj.display_name or "",
            obj.object_kind or "",
            obj.object_id,
        )
        for obj in sorted(visible_objects, key=sort_key):
            if obj.is_self:
                continue
            kind = obj.object_kind or "object"
            prefix = _VISIBLE_LABEL_PREFIX.get(kind, "O")
            counters[prefix] += 1
            label = f"{prefix}{counters[prefix]}"
            display_name = obj.display_name or obj.object_type
            direction = obj.direction_from_player or "不明"
            kind_label = _VISIBLE_KIND_LABEL.get(kind, kind)
            lines.append(
                f"- {label}: {display_name}（{kind_label}, {direction}, 距離 {obj.distance}）"
            )
            runtime_targets[label] = ToolRuntimeTargetDto(
                label=label,
                kind=kind,
                display_name=display_name,
                player_id=obj.player_id_value,
                world_object_id=obj.object_id,
                distance=obj.distance,
                direction=direction,
            )
        return lines

    def _build_move_lines(
        self,
        current_state: PlayerCurrentStateDto,
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> list[str]:
        if not current_state.available_moves:
            return []

        lines: list[str] = []
        for move in current_state.available_moves:
            counters["S"] += 1
            label = f"S{counters['S']}"
            status = "移動可能" if move.conditions_met else "条件未達"
            extra = (
                f"（{status}: {', '.join(move.failed_conditions)}）"
                if move.failed_conditions
                else f"（{status}）"
            )
            lines.append(f"- {label}: {move.spot_name}{extra}")
            runtime_targets[label] = ToolRuntimeTargetDto(
                label=label,
                kind="destination",
                display_name=move.spot_name,
                spot_id=move.spot_id,
                destination_type="spot",
            )
        return lines
