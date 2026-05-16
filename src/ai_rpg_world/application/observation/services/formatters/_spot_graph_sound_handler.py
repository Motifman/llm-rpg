"""Phase 5: 環境音観測の formatter。

`SpotSoundHeardEvent` 専用。intensity (FAINT/MODERATE/LOUD) と
ambient_description / source_spot_id (隣接 spot からの漏れ音) を
組み合わせて prose を生成する。
"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._spot_graph_formatter_helpers import (
    _INTENSITY_PROSE,
    _SpotGraphFormatterBase,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.sound_intensity_enum import (
    SoundIntensityEnum,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotSoundHeardEvent,
)


class SpotGraphSoundHandler(_SpotGraphFormatterBase):
    """環境音観測の formatter (Phase 5)。"""

    def format(
        self, event: Any, recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, SpotSoundHeardEvent):
            return self._format_spot_sound_heard(event, recipient_player_id)
        return None

    def _format_spot_sound_heard(
        self,
        event: SpotSoundHeardEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """環境音観測 prose (Phase 5)。

        intensity (FAINT/MODERATE/LOUD) と ambient_description を組み合わせ。
        source_spot_id が spot_id と異なる (= 隣接 spot からの音、PR-2 で使う)
        場合は「どこかから漏れ聞こえる」表現に切り替える。
        """
        # 自分宛でなければ何も返さない (recipient strategy で既に絞られている
        # はずだが防御)
        if event.entity_id.value != recipient_id.value:
            return None

        # SILENT 相当の event が誤って発火された場合の防御 (Phase 5 PR-2 で
        # 減衰計算のバグで起きうる: 例えば FAINT を 1 hop 減衰すると SILENT
        # になるが event を発火してしまった等)。SILENT は「聞こえない」が
        # 意味なので prose 生成自体を止める。
        if event.intensity == "SILENT":
            return None

        intensity_prose = _INTENSITY_PROSE.get(event.intensity, "音")
        is_adjacent = event.source_spot_id != event.spot_id

        if event.ambient_description:
            if is_adjacent:
                prose = (
                    f"隣の spot から{intensity_prose}が漏れ聞こえる "
                    f"({event.ambient_description})。"
                )
            else:
                prose = f"{intensity_prose}が聞こえる ({event.ambient_description})。"
        else:
            if is_adjacent:
                prose = f"隣の spot から{intensity_prose}が漏れ聞こえる。"
            else:
                prose = f"{intensity_prose}が聞こえる。"

        structured = {
            "type": "spot_sound_heard",
            "intensity": event.intensity,
            "ambient_description": event.ambient_description,
            "source_spot_id": event.source_spot_id.value,
            "is_adjacent": is_adjacent,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            # 環境音は受動的に毎入場で発火する。turn 誘発するかは intensity で
            # 切り替え: LOUD なら緊急性が高いので turn 誘発、それ以外は静か
            # な受動観測として turn 誘発しない (LLM コスト膨張を抑制)。
            # SoundIntensityEnum.LOUD.value と比較することで、enum 側で値を
            # 変えた場合の追従漏れを防ぐ。
            schedules_turn=(event.intensity == SoundIntensityEnum.LOUD.value),
        )
