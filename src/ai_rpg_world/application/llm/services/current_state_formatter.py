"""現在状態をプロンプト用テキストに変換するデフォルト実装"""

from typing import List

from ai_rpg_world.application.llm.contracts.interfaces import ICurrentStateFormatter
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto


class DefaultCurrentStateFormatter(ICurrentStateFormatter):
    """PlayerCurrentStateDto をセクション形式の現在状態テキストに変換する。"""

    def format(self, dto: PlayerCurrentStateDto) -> str:
        if not isinstance(dto, PlayerCurrentStateDto):
            raise TypeError("dto must be PlayerCurrentStateDto")
        lines: List[str] = []

        # 現在地
        if dto.current_spot_name is not None:
            lines.append(f"現在地: {dto.current_spot_name}")
            if dto.current_spot_description:
                lines.append(f"  {dto.current_spot_description}")
        else:
            lines.append("現在地: 未配置")

        if dto.area_name:
            lines.append(f"エリア: {dto.area_name}")
        if dto.x is not None and dto.y is not None:
            lines.append(f"座標: (x={dto.x}, y={dto.y}, z={dto.z or 0})")

        # 同スポットの他プレイヤー
        if dto.current_player_count > 0:
            lines.append(f"同スポットのプレイヤー: {dto.current_player_count}人")

        # 接続先
        if dto.connected_spot_names:
            names = sorted(dto.connected_spot_names)
            lines.append(f"接続先スポット: {', '.join(names)}")

        # 天気
        lines.append(f"天気: {dto.weather_type} (強度: {dto.weather_intensity})")

        # 地形
        if dto.current_terrain_type:
            lines.append(f"地形: {dto.current_terrain_type}")

        lines.append(f"視界距離: {dto.view_distance}")

        if dto.notable_objects:
            lines.append("注目対象:")
            for obj in dto.notable_objects[:10]:
                reason = f" ({obj.notable_reason})" if obj.notable_reason else ""
                lines.append(
                    f"  - {obj.display_name or obj.object_type}: 距離={obj.distance}, 方角={obj.direction_from_player}{reason}"
                )
        else:
            lines.append("注目対象: なし")

        if dto.actionable_objects:
            lines.append("今すぐ行動可能な対象:")
            for obj in dto.actionable_objects[:10]:
                action_labels: List[str] = []
                if obj.can_interact:
                    action_labels.append("相互作用")
                if obj.can_harvest:
                    action_labels.append("採集")
                if obj.can_store_in_chest:
                    action_labels.append("収納")
                if obj.can_take_from_chest:
                    action_labels.append("取り出し")
                action_suffix = f" ({', '.join(action_labels)})" if action_labels else ""
                lines.append(
                    f"  - {obj.display_name or obj.object_type}: 距離={obj.distance}, 方角={obj.direction_from_player}{action_suffix}"
                )

        # 利用可能な移動先
        if dto.available_moves is not None and dto.total_available_moves is not None:
            lines.append(f"利用可能な移動先: {dto.total_available_moves} 件")
            for move in dto.available_moves[:15]:
                status = "条件充足" if move.conditions_met else "条件未達"
                lines.append(
                    f"  - {move.spot_name}: {status}"
                    + (f" (未達: {move.failed_conditions})" if move.failed_conditions else "")
                )
            if len(dto.available_moves) > 15:
                lines.append(f"  ... 他 {len(dto.available_moves) - 15} 件")

        # 注意レベル
        lines.append(f"注意レベル: {dto.attention_level.value}")

        if dto.is_busy:
            suffix = (
                f" (busy_until={dto.busy_until_tick})"
                if dto.busy_until_tick is not None
                else ""
            )
            lines.append(f"行動状態: 実行中{suffix}")
        elif dto.has_active_path:
            lines.append("行動状態: 移動計画あり")

        return "\n".join(lines)
