"""LLM 用の一時ラベル付き UI コンテキストを組み立てる。"""

from typing import Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmUiContextDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILlmUiContextBuilder
from ai_rpg_world.application.world.contracts.dtos import (
    AttentionLevelOptionDto,
    ChestItemDto,
    ConversationChoiceDto,
    InventoryItemDto,
    PlayerCurrentStateDto,
    UsableSkillDto,
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

        counters: Dict[str, int] = {"P": 0, "N": 0, "M": 0, "O": 0, "S": 0, "I": 0, "C": 0, "R": 0, "K": 0, "A": 0}
        runtime_targets: Dict[str, ToolRuntimeTargetDto] = {}
        lines = [current_state_text.rstrip()]

        visible_lines = self._build_visible_target_lines(
            current_state.visible_objects,
            current_state,
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

        inventory_lines = self._build_inventory_lines(current_state.inventory_items, counters, runtime_targets)
        if inventory_lines:
            lines.append("")
            lines.append("インベントリアイテム:")
            lines.extend(inventory_lines)

        chest_item_lines = self._build_chest_item_lines(current_state.chest_items, counters, runtime_targets)
        if chest_item_lines:
            lines.append("")
            lines.append("開いているチェストの中身:")
            lines.extend(chest_item_lines)

        conversation_lines = self._build_conversation_lines(current_state, counters, runtime_targets)
        if conversation_lines:
            lines.append("")
            lines.append("会話中:")
            lines.extend(conversation_lines)

        skill_lines = self._build_skill_lines(current_state.usable_skills, counters, runtime_targets)
        if skill_lines:
            lines.append("")
            lines.append("使用可能スキル:")
            lines.extend(skill_lines)

        attention_lines = self._build_attention_lines(current_state.attention_level_options, counters, runtime_targets)
        if attention_lines:
            lines.append("")
            lines.append("注意レベル変更:")
            lines.extend(attention_lines)

        if current_state.can_destroy_placeable:
            lines.append("")
            lines.append("前方の設置物は破壊可能です。")

        return LlmUiContextDto(
            current_state_text="\n".join(lines).rstrip(),
            tool_runtime_context=ToolRuntimeContextDto(
                targets=runtime_targets,
                current_x=current_state.x,
                current_y=current_state.y,
                current_z=current_state.z,
            ),
        )

    def _build_visible_target_lines(
        self,
        visible_objects: list[VisibleObjectDto],
        current_state: PlayerCurrentStateDto,
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
            action_hint = self._format_action_hint(obj.available_interactions)
            lines.append(
                f"- {label}: {display_name}（{kind_label}, {direction}, 距離 {obj.distance}{action_hint}）"
            )
            runtime_targets[label] = self._build_visible_target(
                label=label,
                kind=kind,
                display_name=display_name,
                obj=obj,
                current_state=current_state,
            )
        return lines

    def _format_action_hint(self, available_interactions: list[str]) -> str:
        if not available_interactions:
            return ""

        labels: list[str] = []
        if "interact" in available_interactions:
            labels.append("相互作用可能")
        if "harvest" in available_interactions:
            labels.append("採集可能")
        if "store_in_chest" in available_interactions:
            labels.append("収納可能")
        if "take_from_chest" in available_interactions:
            labels.append("取り出し可能")
        if not labels:
            return ""
        return ", " + ", ".join(labels)

    def _build_visible_target(
        self,
        *,
        label: str,
        kind: str,
        display_name: str,
        obj: VisibleObjectDto,
        current_state: PlayerCurrentStateDto,
    ) -> ToolRuntimeTargetDto:
        return ToolRuntimeTargetDto(
            label=label,
            kind=kind,
            display_name=display_name,
            player_id=obj.player_id_value,
            world_object_id=obj.object_id,
            distance=obj.distance,
            direction=obj.direction_from_player or "不明",
            target_x=obj.x,
            target_y=obj.y,
            target_z=obj.z,
            relative_dx=obj.x - current_state.x if current_state.x is not None else None,
            relative_dy=obj.y - current_state.y if current_state.y is not None else None,
            relative_dz=obj.z - current_state.z if current_state.z is not None else None,
            interaction_type=obj.interaction_type,
            available_interactions=tuple(obj.available_interactions),
        )

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

    def _build_inventory_lines(
        self,
        inventory_items: list[InventoryItemDto],
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> list[str]:
        lines: list[str] = []
        for item in inventory_items:
            counters["I"] += 1
            label = f"I{counters['I']}"
            hints: list[str] = []
            if item.is_placeable:
                hints.append("設置可能")
            lines.append(
                f"- {label}: {item.display_name} x{item.quantity}"
                + (f"（{', '.join(hints)}）" if hints else "")
            )
            available = ("place_object",) if item.is_placeable else ()
            runtime_targets[label] = ToolRuntimeTargetDto(
                label=label,
                kind="inventory_item",
                display_name=item.display_name,
                item_instance_id=item.item_instance_id,
                inventory_slot_id=item.inventory_slot_id,
                available_interactions=available,
            )
        return lines

    def _build_chest_item_lines(
        self,
        chest_items: list[ChestItemDto],
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> list[str]:
        lines: list[str] = []
        for item in chest_items:
            counters["C"] += 1
            label = f"C{counters['C']}"
            lines.append(
                f"- {label}: {item.display_name} x{item.quantity}（{item.chest_display_name}）"
            )
            runtime_targets[label] = ToolRuntimeTargetDto(
                label=label,
                kind="chest_item",
                display_name=item.display_name,
                item_instance_id=item.item_instance_id,
                chest_world_object_id=item.chest_world_object_id,
            )
        return lines

    def _build_conversation_lines(
        self,
        current_state: PlayerCurrentStateDto,
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> list[str]:
        convo = current_state.active_conversation
        if convo is None:
            return []
        lines = [
            f"- 相手: {convo.npc_display_name}",
            f"- 発話: {convo.node_text}",
        ]
        for choice in convo.choices:
            counters["R"] += 1
            label = f"R{counters['R']}"
            suffix = "（次へ）" if choice.is_next else ""
            lines.append(f"- {label}: {choice.display_text}{suffix}")
            runtime_targets[label] = ToolRuntimeTargetDto(
                label=label,
                kind="conversation_choice",
                display_name=choice.display_text,
                world_object_id=convo.npc_world_object_id,
                conversation_choice_index=choice.choice_index,
            )
        return lines

    def _build_skill_lines(
        self,
        skills: list[UsableSkillDto],
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> list[str]:
        lines: list[str] = []
        for skill in skills:
            counters["K"] += 1
            label = f"K{counters['K']}"
            cost_parts = []
            if skill.mp_cost:
                cost_parts.append(f"MP {skill.mp_cost}")
            if skill.stamina_cost:
                cost_parts.append(f"ST {skill.stamina_cost}")
            if skill.hp_cost:
                cost_parts.append(f"HP {skill.hp_cost}")
            suffix = f"（{', '.join(cost_parts)}）" if cost_parts else ""
            lines.append(f"- {label}: {skill.display_name}{suffix}")
            runtime_targets[label] = ToolRuntimeTargetDto(
                label=label,
                kind="skill",
                display_name=skill.display_name,
                skill_loadout_id=skill.skill_loadout_id,
                skill_slot_index=skill.skill_slot_index,
            )
        return lines

    def _build_attention_lines(
        self,
        options: list[AttentionLevelOptionDto],
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> list[str]:
        lines: list[str] = []
        for option in options:
            counters["A"] += 1
            label = f"A{counters['A']}"
            lines.append(f"- {label}: {option.display_name}（{option.description}）")
            runtime_targets[label] = ToolRuntimeTargetDto(
                label=label,
                kind="attention_level",
                display_name=option.display_name,
                attention_level_value=option.value,
            )
        return lines
