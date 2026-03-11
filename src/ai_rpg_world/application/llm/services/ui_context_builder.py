"""LLM 用の一時ラベル付き UI コンテキストを組み立てる。

責務: 詳細列挙専用。CurrentStateFormatter の要約に重ねて、
visible targets / notable labels / actionable labels / inventory / chest /
conversation / skills のラベル付き一覧を付与する。
同一対象が要約（formatter）と詳細（本 builder）で二重に過剰列挙されないよう、
formatter は件数のみ出力し本 builder がラベル一覧を担当する。
"""

from typing import Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    AttentionLevelToolRuntimeTargetDto,
    ChestToolRuntimeTargetDto,
    ChestItemToolRuntimeTargetDto,
    ConversationChoiceToolRuntimeTargetDto,
    DestinationToolRuntimeTargetDto,
    GuildToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    LlmUiContextDto,
    MonsterToolRuntimeTargetDto,
    NpcToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    QuestToolRuntimeTargetDto,
    ResourceToolRuntimeTargetDto,
    ShopListingToolRuntimeTargetDto,
    ShopToolRuntimeTargetDto,
    SkillToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
    TradeToolRuntimeTargetDto,
    VisibleToolRuntimeTargetDto,
    WorldObjectToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILlmUiContextBuilder
from ai_rpg_world.application.world.contracts.dtos import (
    ActiveQuestSummaryDto,
    AttentionLevelOptionDto,
    AvailableTradeSummaryDto,
    ChestItemDto,
    ConversationChoiceDto,
    GuildMembershipSummaryDto,
    InventoryItemDto,
    NearbyShopSummaryDto,
    PlayerCurrentStateDto,
    ShopListingSummaryDto,
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

        counters: Dict[str, int] = {
            "P": 0, "N": 0, "M": 0, "O": 0, "S": 0, "I": 0, "C": 0, "R": 0, "K": 0, "A": 0,
            "Q": 0, "G": 0, "GM": 0, "SH": 0, "L": 0, "D": 0, "T": 0,
        }
        runtime_targets: Dict[str, ToolRuntimeTargetDto] = {}
        lines = [current_state_text.rstrip()]

        visible_lines, labels_by_object_id = self._build_visible_target_lines(
            current_state.visible_objects,
            current_state,
            counters,
            runtime_targets,
        )
        notable_lines = self._build_object_summary_lines(
            current_state.notable_objects,
            labels_by_object_id,
            include_reason=True,
        )
        if notable_lines:
            lines.append("")
            lines.append("注目対象ラベル:")
            lines.extend(notable_lines)

        actionable_lines = self._build_object_summary_lines(
            current_state.actionable_objects,
            labels_by_object_id,
            include_actions=True,
        )
        if actionable_lines:
            lines.append("")
            lines.append("今すぐ行動可能な対象ラベル:")
            lines.extend(actionable_lines)

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

        quest_lines, quest_targets = self._build_active_quest_lines(
            current_state.active_quests, counters, runtime_targets
        )
        if quest_lines:
            lines.append("")
            lines.append("受託中クエスト:")
            lines.extend(quest_lines)
            runtime_targets.update(quest_targets)

        guild_lines, guild_targets = self._build_guild_membership_lines(
            current_state.guild_memberships, counters, runtime_targets
        )
        if guild_lines:
            lines.append("")
            lines.append("所属ギルド:")
            lines.extend(guild_lines)
            runtime_targets.update(guild_targets)

        shop_lines, shop_targets = self._build_nearby_shop_lines(
            current_state.nearby_shops, counters, runtime_targets
        )
        if shop_lines:
            lines.append("")
            lines.append("近隣ショップ:")
            lines.extend(shop_lines)
            runtime_targets.update(shop_targets)

        trade_lines, trade_targets = self._build_available_trade_lines(
            current_state.available_trades, counters, runtime_targets
        )
        if trade_lines:
            lines.append("")
            lines.append("宛先取引:")
            lines.extend(trade_lines)
            runtime_targets.update(trade_targets)

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
                current_spot_id=current_state.current_spot_id,
                current_area_ids=tuple(current_state.area_ids) if current_state.area_ids else None,
            ),
        )

    def _build_visible_target_lines(
        self,
        visible_objects: list[VisibleObjectDto],
        current_state: PlayerCurrentStateDto,
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> tuple[list[str], dict[int, str]]:
        lines: list[str] = []
        labels_by_object_id: dict[int, str] = {}
        for obj in visible_objects:
            if obj.is_self:
                continue
            kind = obj.object_kind or "object"
            prefix = _VISIBLE_LABEL_PREFIX.get(kind, "O")
            counters[prefix] += 1
            label = f"{prefix}{counters[prefix]}"
            labels_by_object_id[obj.object_id] = label
            display_name = obj.display_name or obj.object_type
            direction = obj.direction_from_player or "不明"
            kind_label = _VISIBLE_KIND_LABEL.get(kind, kind)
            action_hint = self._format_action_hint(obj.available_interactions)
            notable_hint = ""
            if obj.is_notable:
                notable_hint = f", 注目({obj.notable_reason or 'notable'})"
            lines.append(
                f"- {label}: {display_name}（{kind_label}, {direction}, 距離 {obj.distance}{action_hint}{notable_hint}）"
            )
            runtime_targets[label] = self._build_visible_target(
                label=label,
                kind=kind,
                display_name=display_name,
                obj=obj,
                current_state=current_state,
            )
        return lines, labels_by_object_id

    def _build_object_summary_lines(
        self,
        objects: list[VisibleObjectDto],
        labels_by_object_id: dict[int, str],
        *,
        include_reason: bool = False,
        include_actions: bool = False,
    ) -> list[str]:
        lines: list[str] = []
        seen_object_ids: set[int] = set()
        for obj in objects:
            if obj.is_self or obj.object_id in seen_object_ids:
                continue
            label = labels_by_object_id.get(obj.object_id)
            if label is None:
                continue
            seen_object_ids.add(obj.object_id)
            details: list[str] = []
            if include_reason and obj.notable_reason:
                details.append(f"理由: {obj.notable_reason}")
            if include_actions:
                action_labels = self._action_labels(obj.available_interactions)
                if action_labels:
                    details.append(f"可能: {', '.join(action_labels)}")
            detail_text = f"（{'; '.join(details)}）" if details else ""
            lines.append(f"- {label}: {obj.display_name or obj.object_type}{detail_text}")
        return lines

    def _format_action_hint(self, available_interactions: list[str]) -> str:
        labels = self._action_labels(available_interactions)
        if not labels:
            return ""
        return ", " + ", ".join(labels)

    def _action_labels(self, available_interactions: list[str]) -> list[str]:
        labels: list[str] = []
        if "interact" in available_interactions:
            labels.append("相互作用可能")
        if "harvest" in available_interactions:
            labels.append("採集可能")
        if "store_in_chest" in available_interactions:
            labels.append("収納可能")
        if "take_from_chest" in available_interactions:
            labels.append("取り出し可能")
        return labels

    def _build_visible_target(
        self,
        *,
        label: str,
        kind: str,
        display_name: str,
        obj: VisibleObjectDto,
        current_state: PlayerCurrentStateDto,
    ) -> ToolRuntimeTargetDto:
        common_kwargs = dict(
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
        if kind == "player":
            return PlayerToolRuntimeTargetDto(**common_kwargs)
        if kind == "npc":
            return NpcToolRuntimeTargetDto(**common_kwargs)
        if kind == "monster":
            return MonsterToolRuntimeTargetDto(**common_kwargs)
        if kind == "chest":
            return ChestToolRuntimeTargetDto(**common_kwargs)
        if kind == "resource":
            return ResourceToolRuntimeTargetDto(**common_kwargs)
        if kind in {"door", "object"}:
            return WorldObjectToolRuntimeTargetDto(**common_kwargs)
        return VisibleToolRuntimeTargetDto(**common_kwargs)

    def _build_move_lines(
        self,
        current_state: PlayerCurrentStateDto,
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> list[str]:
        has_moves = bool(current_state.available_moves)
        has_locations = bool(current_state.available_location_areas)
        has_objects = bool(current_state.actionable_objects)
        if not has_moves and not has_locations and not has_objects:
            return []

        lines: list[str] = []
        if current_state.available_moves:
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
                runtime_targets[label] = DestinationToolRuntimeTargetDto(
                    label=label,
                    kind="destination",
                    display_name=move.spot_name,
                    spot_id=move.spot_id,
                    destination_type="spot",
                )
        if current_state.available_location_areas and current_state.current_spot_id is not None:
            for loc in current_state.available_location_areas:
                counters["L"] += 1
                label = f"L{counters['L']}"
                lines.append(f"- {label}: {loc.name}（同一スポット内ロケーション）")
                runtime_targets[label] = DestinationToolRuntimeTargetDto(
                    label=label,
                    kind="destination",
                    display_name=loc.name,
                    spot_id=current_state.current_spot_id,
                    location_area_id=loc.location_area_id,
                    destination_type="location",
                )
        if current_state.actionable_objects and current_state.current_spot_id is not None:
            for obj in current_state.actionable_objects:
                if obj.is_self:
                    continue
                counters["D"] += 1
                label = f"D{counters['D']}"
                display_name = obj.display_name or obj.object_type
                lines.append(f"- {label}: {display_name}（オブジェクトへ向かう）")
                runtime_targets[label] = DestinationToolRuntimeTargetDto(
                    label=label,
                    kind="destination",
                    display_name=display_name,
                    spot_id=current_state.current_spot_id,
                    world_object_id=obj.object_id,
                    target_x=obj.x,
                    target_y=obj.y,
                    target_z=obj.z,
                    destination_type="object",
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
            available = ("place_object", "drop_item") if item.is_placeable else ("drop_item",)
            runtime_targets[label] = InventoryToolRuntimeTargetDto(
                label=label,
                kind="inventory_item",
                display_name=item.display_name,
                item_instance_id=item.item_instance_id,
                inventory_slot_id=item.inventory_slot_id,
                is_placeable=item.is_placeable,
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
            runtime_targets[label] = ChestItemToolRuntimeTargetDto(
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
            runtime_targets[label] = ConversationChoiceToolRuntimeTargetDto(
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
            runtime_targets[label] = SkillToolRuntimeTargetDto(
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
            runtime_targets[label] = AttentionLevelToolRuntimeTargetDto(
                label=label,
                kind="attention_level",
                display_name=option.display_name,
                attention_level_value=option.value,
            )
        return lines

    def _build_active_quest_lines(
        self,
        quests: list[ActiveQuestSummaryDto],
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> tuple[list[str], Dict[str, ToolRuntimeTargetDto]]:
        lines: list[str] = []
        targets: Dict[str, ToolRuntimeTargetDto] = {}
        for q in quests:
            counters["Q"] += 1
            label = f"Q{counters['Q']}"
            lines.append(f"- {label}: クエスト {q.quest_id} {q.summary_text}（{q.objectives_completed}/{q.objectives_total}）")
            targets[label] = QuestToolRuntimeTargetDto(
                label=label,
                kind="quest",
                display_name=f"クエスト {q.quest_id}",
                quest_id=q.quest_id,
            )
        return lines, targets

    def _build_guild_membership_lines(
        self,
        memberships: list[GuildMembershipSummaryDto],
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> tuple[list[str], Dict[str, ToolRuntimeTargetDto]]:
        lines: list[str] = []
        targets: Dict[str, ToolRuntimeTargetDto] = {}
        for m in memberships:
            counters["G"] += 1
            label = f"G{counters['G']}"
            base = f"- {label}: {m.guild_name}（ID:{m.guild_id}, 役職:{m.role}）"
            if m.description:
                base += f" {m.description}"
            lines.append(base)
            targets[label] = GuildToolRuntimeTargetDto(
                label=label,
                kind="guild",
                display_name=m.guild_name,
                guild_id=m.guild_id,
            )
            if m.members:
                for mem in m.members:
                    counters["GM"] += 1
                    gm_label = f"GM{counters['GM']}"
                    lines.append(f"  - {gm_label}: {mem.player_name}（{mem.role}）")
                    targets[gm_label] = PlayerToolRuntimeTargetDto(
                        label=gm_label,
                        kind="player",
                        display_name=mem.player_name,
                        player_id=mem.player_id,
                    )
        return lines, targets

    def _build_nearby_shop_lines(
        self,
        shops: list[NearbyShopSummaryDto],
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> tuple[list[str], Dict[str, ToolRuntimeTargetDto]]:
        lines: list[str] = []
        targets: Dict[str, ToolRuntimeTargetDto] = {}
        for s in shops:
            counters["SH"] += 1
            shop_label = f"SH{counters['SH']}"
            base = f"- {shop_label}: {s.shop_name}（ID:{s.shop_id}, 出品:{s.listing_count}件）"
            if s.description:
                base += f" {s.description}"
            lines.append(base)
            targets[shop_label] = ShopToolRuntimeTargetDto(
                label=shop_label,
                kind="shop",
                display_name=s.shop_name,
                shop_id=s.shop_id,
            )
            for listing in s.listings:
                counters["L"] += 1
                listing_label = f"L{counters['L']}"
                lines.append(
                    f"  - {listing_label}: {listing.item_name}（{listing.price_per_unit}G, ID:{listing.listing_id}）"
                )
                targets[listing_label] = ShopListingToolRuntimeTargetDto(
                    label=listing_label,
                    kind="shop_listing",
                    display_name=listing.item_name,
                    shop_id=s.shop_id,
                    listing_id=listing.listing_id,
                )
        return lines, targets

    def _build_available_trade_lines(
        self,
        trades: list[AvailableTradeSummaryDto],
        counters: Dict[str, int],
        runtime_targets: Dict[str, ToolRuntimeTargetDto],
    ) -> tuple[list[str], Dict[str, ToolRuntimeTargetDto]]:
        lines: list[str] = []
        targets: Dict[str, ToolRuntimeTargetDto] = {}
        for t in trades:
            counters["T"] += 1
            label = f"T{counters['T']}"
            lines.append(f"- {label}: 取引 {t.trade_id} {t.item_name}（希望価格: {t.requested_gold}G）")
            targets[label] = TradeToolRuntimeTargetDto(
                label=label,
                kind="trade",
                display_name=t.item_name,
                trade_id=t.trade_id,
            )
        return lines, targets
