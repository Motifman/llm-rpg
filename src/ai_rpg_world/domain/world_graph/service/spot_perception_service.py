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
    ) -> LightingEnum:
        """実効照明レベルを返す。

        光源を持つエージェントがスポットに1人でもいれば、
        暗闇でも DIM（薄暗い）まで引き上げる。
        光は空間を照らすので、自分/他人の区別はしない。
        """
        if atmosphere is None:
            return LightingEnum.BRIGHT
        base = atmosphere.lighting
        if base in (LightingEnum.DARK, LightingEnum.PITCH_BLACK):
            if spot_has_any_light_bearer:
                return LightingEnum.DIM
        return base

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
