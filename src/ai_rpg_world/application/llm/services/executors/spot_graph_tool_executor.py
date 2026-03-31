"""スポットグラフ系ツールの実行"""

from __future__ import annotations

from typing import Any, Callable, Dict

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.tool_executor_helpers import exception_result
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import SpotGraphWorldServices
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
)
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId


class SpotGraphToolExecutor:
    """spot_graph_* ツールのハンドラを提供する。"""

    def __init__(
        self,
        spot_graph_world_services: SpotGraphWorldServices,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
    ) -> None:
        if spot_graph_world_services.movement is None:
            raise TypeError("SpotGraphWorldServices.movement が必要です")
        self._svc = spot_graph_world_services
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        return {
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO: self._travel_to,
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION: self._set_sub_location,
            TOOL_NAME_SPOT_GRAPH_EXPLORE: self._explore,
            TOOL_NAME_SPOT_GRAPH_INTERACT: self._interact,
        }

    def _travel_to(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        raw = args.get("destination_spot_id")
        try:
            dest = int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            return LlmCommandResultDto(
                success=False,
                message="destination_spot_id が不正です。",
                error_code="INVALID_ARGUMENT",
                remediation=get_remediation("INVALID_ARGUMENT"),
            )
        if dest <= 0:
            return LlmCommandResultDto(success=False, message="destination_spot_id は正の整数です。")
        try:
            inv = self._player_inventory_repository.find_by_id(PlayerId(player_id))
            if inv is None:
                return LlmCommandResultDto(success=False, message="インベントリが見つかりません。")
            owned = collect_owned_item_spec_ids_from_inventory(inv, self._item_repository)
            flags = self._svc.world_flags.as_frozen_set()
            self._svc.movement.start_travel_to_spot(
                PlayerId(player_id),
                SpotId.create(dest),
                owned,
                flags,
            )
            return LlmCommandResultDto(success=True, message=f"スポット {dest} への移動を開始しました。")
        except Exception as e:
            return exception_result(e)

    def _set_sub_location(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        raw = args.get("sub_location_id")
        sub: SubLocationId | None
        try:
            if raw is None or raw == 0:
                sub = None
            else:
                sub = SubLocationId.create(int(raw))
        except (TypeError, ValueError):
            return LlmCommandResultDto(success=False, message="sub_location_id が不正です。")
        try:
            self._svc.movement.move_to_sub_location(PlayerId(player_id), sub)
            return LlmCommandResultDto(success=True, message="サブロケーションを更新しました。")
        except Exception as e:
            return exception_result(e)

    def _explore(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        try:
            result = self._svc.exploration.explore_once(PlayerId(player_id))
            parts = list(result.discovery_descriptions)
            if result.item_spec_ids_granted:
                parts.append(f"アイテム付与: {len(result.item_spec_ids_granted)} 種")
            msg = "\n".join(parts) if parts else "特に新しい発見はありませんでした。"
            return LlmCommandResultDto(success=True, message=msg)
        except Exception as e:
            return exception_result(e)

    def _interact(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        try:
            oid = int(args.get("object_id", 0))
            action = str(args.get("action_name", "")).strip()
        except (TypeError, ValueError):
            return LlmCommandResultDto(success=False, message="object_id / action_name が不正です。")
        if oid <= 0 or not action:
            return LlmCommandResultDto(success=False, message="object_id と action_name を指定してください。")
        try:
            out = self._svc.interaction.execute_interaction(
                PlayerId(player_id),
                SpotObjectId.create(oid),
                action,
            )
            msg = "\n".join(out.messages) if out.messages else "操作を実行しました。"
            return LlmCommandResultDto(success=True, message=msg)
        except Exception as e:
            return exception_result(e)
