"""現在状態をプロンプト用テキストに変換するデフォルト実装。

責務: 要約専用。場所・天気/地形・行動状態・高レベルな注目点のみ。
詳細列挙（visible targets, notable/actionable ラベル, inventory 等）は
LlmUiContextBuilder が担当し、二重に過剰列挙しない。
"""

from typing import List

from ai_rpg_world.application.llm.contracts.interfaces import ICurrentStateFormatter
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto


class DefaultCurrentStateFormatter(ICurrentStateFormatter):
    """PlayerCurrentStateDto を要約テキストに変換する。詳細は UiContextBuilder に委譲。"""

    _LOCATION_DESCRIPTION_TRUNCATE_LENGTH = 200

    def format(self, dto: PlayerCurrentStateDto) -> str:
        if not isinstance(dto, PlayerCurrentStateDto):
            raise TypeError("dto must be PlayerCurrentStateDto")
        lines: List[str] = []

        # 場所
        if dto.current_spot_name is not None:
            lines.append(f"現在地: {dto.current_spot_name}")
            if dto.current_spot_description:
                lines.append(f"  {dto.current_spot_description}")
        else:
            lines.append("現在地: 未配置")

        if dto.area_name:
            lines.append(f"エリア: {dto.area_name}")
            if dto.current_location_description and dto.current_location_description.strip():
                desc = dto.current_location_description.strip()
                if len(desc) > self._LOCATION_DESCRIPTION_TRUNCATE_LENGTH:
                    desc = desc[: self._LOCATION_DESCRIPTION_TRUNCATE_LENGTH] + "…"
                lines.append(f"  {desc}")
        if dto.x is not None and dto.y is not None:
            lines.append(f"座標: (x={dto.x}, y={dto.y}, z={dto.z or 0})")

        # 同スポットの他プレイヤー
        if dto.current_player_count > 0:
            lines.append(f"同スポットのプレイヤー: {dto.current_player_count}人")

        # 接続先
        if dto.connected_spot_names:
            names = sorted(dto.connected_spot_names)
            lines.append(f"接続先スポット: {', '.join(names)}")

        # 天気・地形
        lines.append(f"天気: {dto.weather_type} (強度: {dto.weather_intensity})")
        if dto.current_terrain_type:
            lines.append(f"地形: {dto.current_terrain_type}")

        lines.append(f"視界距離: {dto.view_distance}")

        # 視界タイルマップ（オプション）
        if dto.visible_tile_map is not None:
            legend_parts = [
                f"{char}={label}" for char, label in sorted(dto.visible_tile_map.legend.items())
            ]
            lines.append("視界タイルマップ凡例: " + " ".join(legend_parts))
            lines.append("視界タイルマップ:")
            for row in dto.visible_tile_map.rows:
                lines.append(f"  {row}")

        # 高レベルな注目点（件数のみ。詳細は UiContextBuilder）
        notable_n = len(dto.notable_objects) if dto.notable_objects else 0
        actionable_n = len(dto.actionable_objects) if dto.actionable_objects else 0
        lines.append(f"注目対象: {notable_n}件")
        lines.append(f"今すぐ行動可能な対象: {actionable_n}件")

        # 利用可能な移動先（件数のみ。詳細は UiContextBuilder）
        if dto.available_moves is not None and dto.total_available_moves is not None:
            lines.append(f"利用可能な移動先: {dto.total_available_moves} 件")

        # 注意レベル・行動状態
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
