"""スポットグラフ用の現在状態テキスト（ICurrentStateFormatter）"""

from typing import Any, List

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
        for distant_line in snap.distant_view_lines:
            text = distant_line.strip()
            if text:
                lines.append(f"  {text}")
        if snap.travel_status_line:
            lines.append(snap.travel_status_line)

        if snap.atmosphere is not None:
            a = snap.atmosphere
            atmo_parts: List[str] = []
            # enum の生値を出さない (#892)。呼び名は world_briefing が持つ
            # ものを使い回す。**別々に持つと、地図の「暗い」と雰囲気の
            # 「DARK」が食い違う。**
            atmo_parts.append(f"明るさ: {_lighting_display(a.lighting)}")
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

        # 昼夜サイクル (Phase B-1): 朝 / 昼 / 夕暮れ / 夜 のような時刻帯を載せる。
        # シナリオが day_night を宣言していない場合は snap.time_of_day=None で
        # 行ごと省略される。
        if snap.time_of_day is not None:
            tod = snap.time_of_day
            dark_hint = " (暗い)" if tod.is_dark else ""
            lines.append(f"時刻帯: {tod.display_text}{dark_hint}")

        # 会議中であることは、観測ではなく現在状態に置く。
        #
        # 観測は流れて消えるが、ツールセットは会議のあいだずっと切り替わって
        # いる。**「なぜ移動できないのか」を説明する情報が文脈から消える**の
        # を避ける。現在状態は毎ターン組み直されるので消えない。
        if dto.meeting_status_line:
            lines.append(dto.meeting_status_line)

        # 作業の進み。会議と同じく、観測ではなく現在状態に置く。作業は
        # 別々の部屋で進むので、他人のぶんは観測として届かない。
        if dto.task_progress_line:
            lines.append(dto.task_progress_line)

        # シナリオに TICK_LIMIT lose_condition があれば「残り猶予」だけ伝える。
        # 勝利条件には触れない (171a: meta-info のみ。導線はシナリオ責務で別途整備)。
        if dto.tick_budget_remaining is not None:
            remaining = dto.tick_budget_remaining
            if remaining <= 0:
                lines.append("残り行動可能 tick: 0 (時間切れ寸前)")
            else:
                lines.append(f"残り行動可能 tick: {remaining}")

        # Phase 4-E: スポット内オブジェクトの動的 state は、
        # UiContextBuilder._build_object_section が「オブジェクト:」section
        # の各行 inline に ``(key=value)`` として表示する
        # (PR-X, Y_after_pr639_640 後続)。この formatter で別 section
        # として重複出力すると:
        # - 同じ事実が 2 箇所に出る (LLM 混乱・token 無駄遣い)
        # - 2 種類の異なる format (sorted vs 挿入順) で LLM が「どちらが
        #   authoritative か」を判断できない
        # よってここでは何も出さない。UiContextBuilder 側の 1 本化に任せる。

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
                appearance = str(getattr(entry, "appearance", "") or "").strip()
                if appearance:
                    lines.append(f"  見た目: {appearance}")

        # Phase 4-E: 自分の自由 state (毒・呪い・隠しフラグも含む全項目)。
        # 第三者には流れない HIDDEN も本人プロンプトには載せて自己認識させる。
        if snap.player_state:
            # engine のキーをそのまま出さない (#892)。``duty=weather`` は
            # 読み手にとって意味が無く、``role=crew`` は陣営の識別子。
            # 呼び名の出所はシナリオの宣言 (metadata.role_labels /
            # interaction の display_label) で、**ここに新しい辞書を作らない**。
            rendered = ", ".join(
                _render_own_state(
                    snap.player_state, getattr(snap, "state_display_names", None)
                )
            )
            if rendered:
                lines.append(f"自分の状態: {rendered}")

        return "\n".join(lines)



def _lighting_display(lighting: Any) -> str:
    """明るさを世界の言葉で返す。知らない値はそのまま返す。

    呼び名は world_briefing と共有する。**別々に持つと、地図の「暗い」と
    雰囲気の「DARK」が食い違う。**
    """
    from ai_rpg_world.application.llm.services.world_briefing import (
        LIGHTING_DISPLAY,
    )

    key = getattr(lighting, "value", lighting)
    return LIGHTING_DISPLAY.get(str(key), str(key))


def _render_own_state(
    player_state: Any, display_names: Any = None
) -> "list[str]":
    """自分の自由 state を、読める形の列にする。

    宣言のあるキーは呼び名に置き換える (``duty=weather`` → ``担当: 気象を
    記録する``)。呼び名の出所はシナリオ (metadata.role_labels / interaction の
    display_label) で、**ここに新しい辞書を作らない**。

    **宣言の無いキーは従来どおり ``key=value`` で残す。** 一度は落とす実装に
    したが、それだと ``cursed=true`` のような自由 state を持つ世界で
    「自分の状態」の節が丸ごと消えた。毒や呪いは本人が自己認識するために
    載せている情報で、消してよいものではない。

    そもそも ``cursed`` はシナリオが決めたキーで engine の語彙ではない。
    直したかったのは呼び名のある ``duty`` / ``role`` のほうだけだった。
    """
    names = dict(display_names or {})
    rendered: list[str] = []
    for key, value in sorted(dict(player_state or {}).items()):
        entry = names.get(f"{key}={_render_value(value)}")
        if entry:
            heading, label = entry
            rendered.append(f"{heading}: {label}")
        else:
            rendered.append(f"{key}={_render_value(value)}")
    return rendered


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
