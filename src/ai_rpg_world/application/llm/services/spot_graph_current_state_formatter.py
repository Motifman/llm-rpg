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

        if snap.atmosphere is not None:
            a = snap.atmosphere
            atmo_parts: List[str] = []
            atmo_parts.append(f"明るさ: {a.lighting}")
            if a.sound_ambient:
                atmo_parts.append(f"音: {a.sound_ambient}")
            atmo_parts.append(f"気温: {a.temperature}")
            if a.smell:
                atmo_parts.append(f"匂い: {a.smell}")
            lines.append("雰囲気: " + " / ".join(atmo_parts))

        if dto.current_game_time_label:
            lines.append(f"現在時刻: {dto.current_game_time_label}")
        else:
            lines.append("現在時刻: 不明")

        return "\n".join(lines)
