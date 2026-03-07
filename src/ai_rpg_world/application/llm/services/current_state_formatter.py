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

        # 視界内オブジェクト
        if dto.visible_objects:
            lines.append(f"視界内オブジェクト (視界距離={dto.view_distance}):")
            for obj in dto.visible_objects[:20]:  # 最大20件
                lines.append(
                    f"  - タイプ={obj.object_type}, 距離={obj.distance}, "
                    f"座標=({obj.x},{obj.y},{obj.z})"
                )
            if len(dto.visible_objects) > 20:
                lines.append(f"  ... 他 {len(dto.visible_objects) - 20} 件")
        else:
            lines.append("視界内オブジェクト: なし")

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
