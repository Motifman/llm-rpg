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
        world = dto.world_state
        runtime = dto.runtime_context
        app = dto.app_session_state
        lines: List[str] = []

        # 場所
        if world.current_spot_name is not None:
            lines.append(f"現在地: {world.current_spot_name}")
            if world.current_spot_description:
                lines.append(f"  {world.current_spot_description}")
        else:
            lines.append("現在地: 未配置")

        if world.area_name:
            lines.append(f"エリア: {world.area_name}")
            if world.current_location_description and world.current_location_description.strip():
                desc = world.current_location_description.strip()
                if len(desc) > self._LOCATION_DESCRIPTION_TRUNCATE_LENGTH:
                    desc = desc[: self._LOCATION_DESCRIPTION_TRUNCATE_LENGTH] + "…"
                lines.append(f"  {desc}")
        if world.x is not None and world.y is not None:
            lines.append(f"座標: (x={world.x}, y={world.y}, z={world.z or 0})")

        # 同スポットの他プレイヤー
        if world.current_player_count > 0:
            lines.append(f"同スポットのプレイヤー: {world.current_player_count}人")

        # 接続先
        if world.connected_spot_names:
            names = sorted(world.connected_spot_names)
            lines.append(f"接続先スポット: {', '.join(names)}")

        # ゲーム内現在時刻
        if world.current_game_time_label:
            lines.append(f"現在時刻: {world.current_game_time_label}")

        # 天気・地形
        lines.append(f"天気: {world.weather_type} (強度: {world.weather_intensity})")
        if world.current_terrain_type:
            lines.append(f"地形: {world.current_terrain_type}")

        lines.append(f"視界距離: {world.view_distance}")

        # 視界タイルマップ（オプション）
        if world.visible_tile_map is not None:
            legend_parts = [
                f"{char}={label}" for char, label in sorted(world.visible_tile_map.legend.items())
            ]
            lines.append("視界タイルマップ凡例: " + " ".join(legend_parts))
            lines.append("視界タイルマップ:")
            for row in world.visible_tile_map.rows:
                lines.append(f"  {row}")

        # 高レベルな注目点（件数のみ。詳細は UiContextBuilder）
        notable_n = len(runtime.notable_objects) if runtime.notable_objects else 0
        actionable_n = len(runtime.actionable_objects) if runtime.actionable_objects else 0
        lines.append(f"注目対象: {notable_n}件")
        lines.append(f"今すぐ行動可能な対象: {actionable_n}件")

        # 利用可能な移動先（件数のみ。詳細は UiContextBuilder）
        if world.available_moves is not None and world.total_available_moves is not None:
            lines.append(f"利用可能な移動先: {world.total_available_moves} 件")

        # 注意レベル・行動状態
        lines.append(f"注意レベル: {world.attention_level.value}")

        if world.is_busy:
            suffix = (
                f" (busy_until={world.busy_until_tick})"
                if world.busy_until_tick is not None
                else ""
            )
            lines.append(f"行動状態: 実行中{suffix}")
        elif world.has_active_path:
            lines.append("行動状態: 移動計画あり")

        if runtime.active_harvest is not None:
            lines.append(
                "採集中: "
                f"{runtime.active_harvest.target_display_name}"
                f" (finish_tick={runtime.active_harvest.finish_tick})"
            )

        if app.sns_current_page_snapshot_json:
            lines.append("現在のSNS画面:")
            lines.append(app.sns_current_page_snapshot_json)

        if app.trade_current_page_snapshot_json:
            lines.append("現在の取引所画面:")
            lines.append(app.trade_current_page_snapshot_json)

        return "\n".join(lines)
