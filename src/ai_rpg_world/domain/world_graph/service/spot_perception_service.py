"""スポットの知覚判定ドメインサービス（stateless）。

世界の状態は変えず、エージェントがスポットで「何が見えるか」を計算する。
照明 + 光源（自分 or 同居者）から実効照明レベルを導き、
オブジェクトが知覚可能かどうかを判定する。

設計原則:
- 世界はひとつ（状態共有）だが知覚は物理法則に従う
- 光は空間を照らす: 松明持ちが1人でもいれば全員見える
"""

from __future__ import annotations

from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere


class SpotPerceptionService:
    """スポットの知覚状態を判定する。"""

    def compute_effective_lighting(
        self,
        atmosphere: SpotAtmosphere | None,
        spot_has_any_light_bearer: bool,
        *,
        is_outdoor: bool = False,
        time_of_day_is_dark: bool = False,
        weather_obscures_vision: bool = False,
    ) -> LightingEnum:
        """実効照明レベルを返す。

        計算順序:
        1. base = atmosphere.lighting (atmosphere が None なら BRIGHT)
        2. **屋外で夜 or 悪天候**: base を 1 段階暗くする (BRIGHT→DIM, DIM→DARK)。
           屋内/洞窟は空の影響を受けないので skip。
           夜と悪天候が両立しても 2 段は下げない (上限 1 段)。
        3. **光源持ち**: DARK/PITCH_BLACK → DIM に引き上げ。
           光は空間を照らすので、自分/他人の区別はしない。

        Args:
            atmosphere: spot の静的照明 (None なら屋外想定で BRIGHT)
            spot_has_any_light_bearer: 同 spot に光源持ちが居るか
            is_outdoor: spot が屋外 (空が見える) か。
                夜 / 悪天候の影響を受けるのは屋外のみ
            time_of_day_is_dark: 現在 dark な時間帯 (= night) か
            weather_obscures_vision: 嵐や濃霧で視界が悪い天候か
        """
        if atmosphere is None:
            return LightingEnum.BRIGHT
        base = atmosphere.lighting
        # 屋外限定: 夜 or 悪天候で 1 段階暗くする
        if is_outdoor and (time_of_day_is_dark or weather_obscures_vision):
            base = self._step_down_lighting(base)
        # 光源持ちは依然として DARK/PITCH_BLACK を DIM に引き上げる
        if base in (LightingEnum.DARK, LightingEnum.PITCH_BLACK):
            if spot_has_any_light_bearer:
                return LightingEnum.DIM
        return base

    @staticmethod
    def _step_down_lighting(level: LightingEnum) -> LightingEnum:
        """照明レベルを 1 段階暗くする (BRIGHT→DIM, DIM→DARK, DARK→PITCH_BLACK)。

        PITCH_BLACK はこれ以上下がらない。屋外で夜 + 嵐が重なっても 1 段だけ
        下げる (重複適用しない)。
        """
        mapping = {
            LightingEnum.BRIGHT: LightingEnum.DIM,
            LightingEnum.DIM: LightingEnum.DARK,
            LightingEnum.DARK: LightingEnum.PITCH_BLACK,
            LightingEnum.PITCH_BLACK: LightingEnum.PITCH_BLACK,
        }
        return mapping[level]

    def can_see_objects(self, effective_lighting: LightingEnum) -> bool:
        """オブジェクトが視認可能か。DARK/PITCH_BLACK では見えない。"""
        return effective_lighting in (LightingEnum.BRIGHT, LightingEnum.DIM)

    def describe_lighting_perception(
        self,
        base_lighting: LightingEnum,
        effective_lighting: LightingEnum,
        viewer_has_light: bool,
        light_bearer_name: str | None,
    ) -> str | None:
        """照明に関する知覚テキストを生成する。補足が不要なら None。"""
        if base_lighting in (LightingEnum.BRIGHT, LightingEnum.DIM):
            return None

        if effective_lighting == LightingEnum.DIM:
            if viewer_has_light:
                return "手元の光源で周囲がぼんやりと照らされている。"
            if light_bearer_name:
                return f"{light_bearer_name}の持つ光源で周囲がぼんやりと照らされている。"
            return "わずかな光で周囲がぼんやりと見える。"

        # 暗闇のまま
        if base_lighting == LightingEnum.PITCH_BLACK:
            return "完全な暗闇だ。何も見えない。"
        return "暗くてほとんど何も見えない。"
