"""スポットグラフ用の現在状態テキスト（ICurrentStateFormatter）"""

from typing import List

from ai_rpg_world.application.llm.contracts.interfaces import ICurrentStateFormatter
from ai_rpg_world.application.llm.services.current_state_formatter import DefaultCurrentStateFormatter
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto


class SpotGraphCurrentStateFormatter(ICurrentStateFormatter):
    """spot_graph_snapshot があればスポットグラフ向けに整形し、なければデフォルトにフォールバック。"""

    def format(self, dto: PlayerCurrentStateDto) -> str:
        if not isinstance(dto, PlayerCurrentStateDto):
            raise TypeError("dto must be PlayerCurrentStateDto")
        snap = dto.spot_graph_snapshot
        if snap is None:
            return DefaultCurrentStateFormatter().format(dto)

        lines: List[str] = []
        lines.append(f"現在地: {snap.current_spot_name}")
        if snap.current_spot_description.strip():
            lines.append(f"  {snap.current_spot_description.strip()}")
        if snap.travel_status_line:
            lines.append(snap.travel_status_line)

        if snap.sub_location_lines:
            lines.append("サブロケーション:")
            lines.extend(f"  {x}" for x in snap.sub_location_lines)

        if snap.object_lines:
            lines.append("見えるオブジェクト:")
            lines.extend(f"  {x}" for x in snap.object_lines)

        if snap.ground_item_lines:
            lines.append("落ちているアイテム:")
            lines.extend(f"  {x}" for x in snap.ground_item_lines)

        if snap.connection_lines:
            lines.append("接続先:")
            lines.extend(f"  {x}" for x in snap.connection_lines)

        if dto.current_game_time_label:
            lines.append(f"現在時刻: {dto.current_game_time_label}")
        else:
            lines.append("現在時刻: 不明")

        return "\n".join(lines)
