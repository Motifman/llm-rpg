"""スポットグラフ用の現在状態テキスト（ICurrentStateFormatter）"""

from typing import List

from ai_rpg_world.application.llm.contracts.interfaces import ICurrentStateFormatter
from ai_rpg_world.application.llm.services.current_state_formatter import DefaultCurrentStateFormatter
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_monster_view import (
    HEALTH_BUCKET_JP,
)


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

        if snap.weather is not None:
            w = snap.weather
            _WEATHER_JP = {
                "CLEAR": "晴れ", "CLOUDY": "曇り", "RAIN": "雨",
                "HEAVY_RAIN": "大雨", "SNOW": "雪", "BLIZZARD": "吹雪",
                "FOG": "霧", "STORM": "嵐",
            }
            wname = _WEATHER_JP.get(w.weather_type, w.weather_type)
            intensity_label = ""
            if w.weather_intensity < 0.3:
                intensity_label = "弱い"
            elif w.weather_intensity > 0.7:
                intensity_label = "激しい"
            lines.append(f"天候: {intensity_label}{wname}（屋外）")

        if dto.current_game_time_label:
            lines.append(f"現在時刻: {dto.current_game_time_label}")
        else:
            lines.append("現在時刻: 不明")

        # Phase 4-E: スポット内のオブジェクトに動的 state があれば表示。
        # 「燭台: lit=True」のように LLM が読める形にする。
        object_state_lines = []
        for entry in snap.objects:
            if entry.state:
                rendered = ", ".join(
                    f"{k}={_render_value(v)}" for k, v in sorted(entry.state.items())
                )
                object_state_lines.append(f"- {entry.name}: {rendered}")
        if object_state_lines:
            lines.append("スポット内オブジェクトの状態:")
            lines.extend(object_state_lines)

        # 同スポットに居るモンスター個体。ラベルは UiContextBuilder 側で付与
        # するため、ここでは概要だけ載せる（M1/M2 等のラベル付き行は
        # SpotGraphUiContextBuilder._build_monster_section が augmented_text に追記）。
        # 暗闇等で snapshot に居なければ何も出さない。
        if snap.monsters_at_spot:
            lines.append("同じ場所に居るモンスター:")
            for entry in snap.monsters_at_spot:
                if entry.is_dead:
                    lines.append(f"- {entry.display_name}（死骸）")
                else:
                    health_label = HEALTH_BUCKET_JP.get(
                        entry.health_bucket, entry.health_bucket
                    )
                    lines.append(
                        f"- {entry.display_name}（{entry.behavior_label}・{health_label}）"
                    )

        # Phase 4-E: 自分の自由 state (毒・呪い・隠しフラグも含む全項目)。
        # 第三者には流れない HIDDEN も本人プロンプトには載せて自己認識させる。
        if snap.player_state:
            rendered = ", ".join(
                f"{k}={_render_value(v)}"
                for k, v in sorted(snap.player_state.items())
            )
            lines.append(f"自分の状態: {rendered}")

        return "\n".join(lines)


def _render_value(value: object) -> str:
    """state 値を LLM 向けに短く表示する。dict/list は repr に倒す。"""
    if value is None:
        # repr(None) は "None" になり LLM が「文字列の "None"」と読んでしまう
        # 余地があるので、明示的に null を出す。
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    return repr(value)
