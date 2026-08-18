"""metadata / 環境 / 会議 / 終了条件 / ongoing の読み取り。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
)
from ai_rpg_world.domain.player.value_object.death_semantics import DeathSemantics
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.day_night_cycle_def import DayNightCycleDef
from ai_rpg_world.domain.world_graph.value_object.day_night_phase_def import DayNightPhaseDef
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import GameEndCondition
from ai_rpg_world.infrastructure.scenario.declaration_site import declaring
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.models import (
    OngoingConditionDef,
    ScenarioDayNightConfig,
    ScenarioMetadata,
    ScenarioWeatherConfig,
)
from ai_rpg_world.infrastructure.scenario.parse_helpers import (
    parse_bool,
    parse_player_outcome_messages,
    parse_role_labels,
    parse_show_world_map,
)
from ai_rpg_world.infrastructure.scenario.parse_interaction_effects import (
    parse_interaction_effect,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper
from ai_rpg_world.infrastructure.scenario.validate_features import (
    _GAME_END_CONDITION_ALLOWED_SECTIONS,
)

def declared_world_flag_writers(raw: Mapping[str, Any]) -> frozenset[str]:
    """初期値と SET_FLAG から、このシナリオが成立させられる flag を集める。"""
    found: set[str] = set()
    initial_flags = raw.get("initial_flags")
    if isinstance(initial_flags, Mapping):
        found.update(
            key for key in initial_flags if isinstance(key, str) and key
        )
    elif isinstance(initial_flags, list):
        found.update(
            value for value in initial_flags if isinstance(value, str) and value
        )

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            if value.get("effect_type") == "SET_FLAG":
                parameters = value.get("parameters")
                if isinstance(parameters, Mapping):
                    flag_name = parameters.get("flag_name")
                    if isinstance(flag_name, str) and flag_name:
                        found.add(flag_name)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    # ongoing_conditions 自身の on_meeting_start は、成立中の異常を解く側で
    # あって異常を発生させる側ではない。ここまで writer と数えると、同じ
    # 宣言内で初めて立つ循環 flag を「発生可能」と誤認してしまう。
    for key, value in raw.items():
        if key != "ongoing_conditions":
            visit(value)
    return frozenset(found)

def parse_ongoing_conditions(
    raw: Any,
    *,
    declared_flag_writers: frozenset[str],
    mapper: ScenarioIdMapper,
    player_attribute_specs: PlayerAttributeSpecs,
) -> Tuple[OngoingConditionDef, ...]:
    """異常表示を厳格に読み、永遠に成立しない flag 参照を拒否する。"""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ScenarioLoadError("ongoing_conditions は配列で書いてください")

    allowed_keys = frozenset(
        {
            "flag",
            "message",
            "blocks_emergency_button",
            "resolution",
            "on_meeting_start",
        }
    )
    supported_resolution_effects = frozenset(
        {
            InteractionEffectTypeEnum.CLEAR_FLAG,
            InteractionEffectTypeEnum.SET_FLAG,
        }
    )
    supported_meeting_effects = frozenset(
        {
            InteractionEffectTypeEnum.RESOLVE_ONGOING_CONDITION,
            InteractionEffectTypeEnum.SHOW_MESSAGE,
        }
    )
    parsed: list[OngoingConditionDef] = []
    seen_flags: set[str] = set()
    for index, entry in enumerate(raw):
        path = f"ongoing_conditions[{index}]"
        if not isinstance(entry, Mapping):
            raise ScenarioLoadError(f"{path} は object で書いてください")
        unknown_keys = set(entry) - allowed_keys
        if unknown_keys:
            raise ScenarioLoadError(
                f"{path} に未知のキーがあります: {sorted(unknown_keys)}"
            )
        flag = entry.get("flag")
        if not isinstance(flag, str) or not flag.strip():
            raise ScenarioLoadError(f"{path}.flag は空でない文字列にしてください")
        flag = flag.strip()
        if flag in seen_flags:
            raise ScenarioLoadError(
                f"ongoing_conditions に flag の重複があります: {flag}"
            )
        if flag not in declared_flag_writers:
            raise ScenarioLoadError(
                f"{path}.flag={flag!r} は initial_flags にも SET_FLAG にも"
                "宣言されていません"
            )
        message = entry.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ScenarioLoadError(
                f"{path}.message は空でない文字列にしてください"
            )
        blocks_emergency_button = entry.get("blocks_emergency_button")
        if not isinstance(blocks_emergency_button, bool):
            raise ScenarioLoadError(
                f"{path}.blocks_emergency_button は true / false を"
                "明示してください"
            )
        raw_resolution = entry.get("resolution", [])
        if not isinstance(raw_resolution, list):
            raise ScenarioLoadError(f"{path}.resolution は配列で書いてください")
        if "resolution" in entry and not raw_resolution:
            raise ScenarioLoadError(f"{path}.resolution は空にできません")
        with declaring(f"{path}.resolution:"):
            resolution = tuple(
                parse_interaction_effect(
                    effect,
                    mapper,
                    actor_context="scenario_event",
                    player_attribute_specs=player_attribute_specs,
                )
                for effect in raw_resolution
            )
        unsupported_resolution = [
            effect.effect_type.name
            for effect in resolution
            if effect.effect_type not in supported_resolution_effects
        ]
        if unsupported_resolution:
            raise ScenarioLoadError(
                f"{path}.resolution にフラグ以外の効果があります: "
                f"{unsupported_resolution}. 使える効果: CLEAR_FLAG, SET_FLAG"
            )
        if resolution and not any(
            effect.effect_type is InteractionEffectTypeEnum.CLEAR_FLAG
            and effect.parameters.get("flag_name") == flag
            for effect in resolution
        ):
            raise ScenarioLoadError(
                f"{path}.resolution は成立条件の flag={flag!r} を"
                "CLEAR_FLAG で解除してください"
            )
        raw_effects = entry.get("on_meeting_start", [])
        if not isinstance(raw_effects, list):
            raise ScenarioLoadError(
                f"{path}.on_meeting_start は配列で書いてください"
            )
        if "on_meeting_start" in entry and not raw_effects:
            raise ScenarioLoadError(
                f"{path}.on_meeting_start は空にできません。会議で解かない異常は"
                "キー自体を省略してください"
            )
        with declaring(f"{path}.on_meeting_start:"):
            effects = tuple(
                parse_interaction_effect(
                    effect,
                    mapper,
                    actor_context="scenario_event",
                    player_attribute_specs=player_attribute_specs,
                )
                for effect in raw_effects
            )
        unsupported = [
            effect.effect_type.name
            for effect in effects
            if effect.effect_type not in supported_meeting_effects
        ]
        if unsupported:
            raise ScenarioLoadError(
                f"{path}.on_meeting_start に未対応の効果があります: {unsupported}. "
                "使える効果: RESOLVE_ONGOING_CONDITION, SHOW_MESSAGE"
            )
        if effects and not resolution:
            raise ScenarioLoadError(
                f"{path}.on_meeting_start を使う異常には resolution が必要です"
            )
        if effects and not any(
            effect.effect_type
            is InteractionEffectTypeEnum.RESOLVE_ONGOING_CONDITION
            and effect.parameters.get("flag") == flag
            for effect in effects
        ):
            raise ScenarioLoadError(
                f"{path}.on_meeting_start は自身の flag={flag!r} を"
                "RESOLVE_ONGOING_CONDITION で参照してください"
            )
        parsed.append(
            OngoingConditionDef(
                flag=flag,
                message=message.strip(),
                blocks_emergency_button=blocks_emergency_button,
                resolution=resolution,
                on_meeting_start=effects,
            )
        )
        seen_flags.add(flag)
    return tuple(parsed)

def validate_ongoing_condition_resolution_references(
    raw: Mapping[str, Any],
    conditions: Sequence[OngoingConditionDef],
) -> None:
    """全 effect の異常解除参照が、実体のある resolution を指すと確かめる。"""
    resolvable = {
        condition.flag for condition in conditions if condition.resolution
    }

    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            if value.get("effect_type") == "RESOLVE_ONGOING_CONDITION":
                parameters = value.get("parameters")
                flag = parameters.get("flag") if isinstance(parameters, Mapping) else None
                if not isinstance(flag, str) or not flag:
                    raise ScenarioLoadError(
                        f"{path} の RESOLVE_ONGOING_CONDITION は"
                        " parameters.flag を必要とします"
                    )
                if flag not in resolvable:
                    raise ScenarioLoadError(
                        "RESOLVE_ONGOING_CONDITION が参照する flag に"
                        f" resolution がありません: flag={flag!r}, path={path}"
                    )
            for key, child in value.items():
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(raw, "scenario")

def parse_meeting_tuning(raw: Dict[str, Any]) -> Dict[str, Optional[int]]:
    """`meeting` block の調整値を読む。書かれていない項目は None (既定)。

    **1 以上の整数だけを通す。** 0 や負を許すと、会議が始まった瞬間に
    打ち切られたり、クールダウンが効かなくなったりする。読み込み時に
    止めないと、run が終わるまで「なぜか会議が成立しない」で悩む。
    """
    block = raw.get("meeting")
    keys = (
        "tick_limit",
        "silence_limit_ticks",
        "cooldown_ticks",
        "emergency_buttons_per_player",
    )
    if not isinstance(block, dict):
        return {f"meeting_{k}": None for k in keys[:3]} | {
            "emergency_buttons_per_player": None
        }
    parsed: Dict[str, Optional[int]] = {}
    for key in keys:
        value = block.get(key)
        if value is not None:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ScenarioLoadError(
                    f"meeting.{key} は整数で指定してください"
                )
            if value < 1:
                raise ScenarioLoadError(
                    f"meeting.{key} は 1 以上である必要があります: {value}"
                )
        field = (
            key
            if key == "emergency_buttons_per_player"
            else f"meeting_{key}"
        )
        parsed[field] = value
    return parsed

def parse_death_semantics(raw: Dict[str, Any]) -> DeathSemantics:
    """`death` block を読む。書かれていない項目は engine の既定。

    `grace_ticks` は 0 を許す (即死の世界)。負は拒否する。0 と「書き
    忘れ」を区別するため、既定は None で持つ。
    """
    block = raw.get("death")
    if block is None:
        return DeathSemantics()
    if not isinstance(block, dict):
        raise ScenarioLoadError("death は object で指定してください。")
    grace = block.get("grace_ticks")
    if grace is not None:
        if not isinstance(grace, int) or isinstance(grace, bool) or grace < 0:
            raise ScenarioLoadError(
                f"death.grace_ticks は 0 以上の整数で指定してください: {grace!r}"
            )
    for key in ("announce_globally", "victim_learns_killer"):
        if key in block and not isinstance(block[key], bool):
            raise ScenarioLoadError(f"death.{key} は真偽値で指定してください。")
    return DeathSemantics(
        grace_ticks=grace,
        announce_globally=block.get("announce_globally", True),
        victim_learns_killer=block.get("victim_learns_killer", True),
    )

def parse_player_trade(raw: Dict[str, Any]) -> Tuple[bool, Optional[int]]:
    """`player_trade` block から取引の on/off と提案の期限を読む。

    block が無ければ off。書いたなら既定は on とする (書いておいて既定
    off だと、宣言したのに何も起きない静かな失敗になる)。`meeting` と
    同じ流儀。

    `offer_expires_in_ticks` は書かなければ None = engine の既定。**1 以上
    の整数だけを通す。** 0 や負を許すと、作った瞬間に流れる提案ができる。
    真偽値を弾くのは、Python では `bool` が `int` の派生で、素直に書くと
    `True` が 1 手番として通ってしまうため。
    """
    block = raw.get("player_trade")
    if block is None:
        return False, None
    if not isinstance(block, dict):
        raise ScenarioLoadError(
            "player_trade は object で指定してください。"
        )
    enabled = block.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ScenarioLoadError(
            "player_trade.enabled は真偽値で指定してください。"
        )
    expires = block.get("offer_expires_in_ticks")
    if expires is not None:
        if not isinstance(expires, int) or isinstance(expires, bool):
            raise ScenarioLoadError(
                "player_trade.offer_expires_in_ticks は整数で指定してください: "
                f"{expires!r}"
            )
        if expires < 1:
            raise ScenarioLoadError(
                "player_trade.offer_expires_in_ticks は 1 以上である必要が"
                f"あります: {expires}"
            )
    return enabled, expires

def parse_meeting_enabled(raw: Dict[str, Any]) -> bool:
    """`meeting` block の有無と `enabled` から会議機構の on/off を決める。

    block そのものが無ければ off。block を書いたなら既定は on とする
    (書いておいて既定 off だと、宣言したのに何も起きない静かな失敗になる)。
    明示的に `"enabled": false` と書いた場合だけ off に落とす。
    """
    block = raw.get("meeting")
    if block is None:
        return False
    if not isinstance(block, dict):
        raise ScenarioLoadError(
            "meeting は object で指定してください。"
        )
    enabled = block.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ScenarioLoadError(
            "meeting.enabled は真偽値で指定してください。"
        )
    return enabled

def parse_metadata( raw: Dict[str, Any]) -> ScenarioMetadata:
    return ScenarioMetadata(
        id=raw["id"],
        title=raw["title"],
        description=raw.get("description", ""),
        theme=raw.get("theme", ""),
        difficulty=raw.get("difficulty", "medium"),
        estimated_ticks=int(raw.get("estimated_ticks", 100)),
        author=raw.get("author", ""),
        tags=tuple(raw.get("tags", [])),
        llm_public_intro=str(raw.get("llm_public_intro", "") or "").strip(),
        show_world_map=parse_show_world_map(raw),
        role_labels=parse_role_labels(raw),
        llm_objective_text=str(raw.get("llm_objective_text", "") or "").strip(),
        player_outcome_messages=parse_player_outcome_messages(raw),
    )

def pre_register_ids( raw: Dict[str, Any], mapper: ScenarioIdMapper) -> None:
    """スポット・接続・オブジェクトの全 ID を先行登録する。

    interaction effect が他スポットの接続やオブジェクトを参照する場合に備え、
    実体の解析よりも先に全名前空間の ID を確定させる。
    """
    for spot in raw.get("spots", []):
        mapper.register("spot", spot["id"])
        interior = spot.get("interior", {})
        seen_object_ids: set = set()
        for obj in interior.get("objects", []):
            object_id = obj["id"]
            # **同じ spot に同じ id の object を 2 つ書くのを止める。**
            # 黙って通すと、後から書いたほうの interaction が実行時に
            # 「そんな操作は無い」で落ちる。JSON には確かに書いてあるので、
            # 原因にたどり着くまでが長い (実際にこれで詰まった)。
            if object_id in seen_object_ids:
                raise ScenarioLoadError(
                    f"spot '{spot['id']}' に object id '{object_id}' が"
                    "重複しています。後から書いたほうの interaction は"
                    "実行時に見つからなくなります"
                )
            seen_object_ids.add(object_id)
            mapper.register("object", object_id)
        for sub in interior.get("sub_locations", []):
            mapper.register("sub_location", sub["id"])
    for conn in raw.get("connections", []):
        mapper.register("connection", conn["id"])
        if parse_bool(
            conn.get("is_bidirectional", True),
            path=f"connection {conn.get('id')}.is_bidirectional",
        ):
            mapper.register("connection", conn["id"] + "__reverse")
    for player in raw.get("players", []):
        mapper.register("player", player["id"])
    for item in raw.get("item_specs", []):
        mapper.register("item_spec", item["id"])

def parse_day_night_config( raw: Dict[str, Any],
) -> Optional[ScenarioDayNightConfig]:
    """`environment.day_night` を読んで DayNightCycleDef を組み立てる。

    JSON 形式 (シナリオ作家向け契約):
    ```
    "environment": {
        "day_night": {
            "enabled": true,
            "ticks_per_day": 24,
            "starting_tick_in_day": 0,
            "announce_changes": true,
            "phases": [
                {"name": "morning", "start_ratio": 0.0,  "display_text": "朝",   "ambient_light": 0.9, "is_dark": false},
                {"name": "noon",    "start_ratio": 0.25, "display_text": "昼",   "ambient_light": 1.0, "is_dark": false},
                {"name": "evening", "start_ratio": 0.5,  "display_text": "夕暮れ","ambient_light": 0.5, "is_dark": false},
                {"name": "night",   "start_ratio": 0.66, "display_text": "夜",   "ambient_light": 0.1, "is_dark": true}
            ]
        }
    }
    ```

    - `enabled: false` または `day_night` セクション自体が無い場合は None を返し、
      runtime は昼夜サイクルを動かさない (常に時刻表示なし)
    - フェーズ列の昇順性などのバリデーションは DayNightCycleDef.__post_init__
      に任せる (作家ミスは boundary で弾く)
    """
    day_night = raw.get("day_night") if isinstance(raw, dict) else None
    if not isinstance(day_night, dict):
        return None
    if not parse_bool(
        day_night.get("enabled", False),
        path="environment.day_night.enabled",
    ):
        return None

    # 漂流島 v2 で導入された「1 tick = 1 時間」スケールに合わせ default=24
    # (旧 default=12 は monster_behavior_world_port:196 の hardcode=24 と
    # 不整合で、ticks_per_day を省略したシナリオの day_night phase 判定が
    # 2 倍速で進む silent failure を生んでいた)
    ticks_per_day = int(day_night.get("ticks_per_day", 24))
    starting_tick = int(day_night.get("starting_tick_in_day", 0))
    announce = parse_bool(
        day_night.get("announce_changes", True),
        path="environment.day_night.announce_changes",
    )
    phases_raw = day_night.get("phases", [])
    if not isinstance(phases_raw, list) or not phases_raw:
        raise ScenarioLoadError(
            "environment.day_night.phases must be a non-empty list"
        )
    required_keys = ("name", "start_ratio", "display_text", "ambient_light", "is_dark")
    phases_list: list[DayNightPhaseDef] = []
    for i, p in enumerate(phases_raw):
        # boundary 検証: 各要素が dict で必須キーを持っているかを scenario_loader
        # 層で弾く。これを怠ると未定義キーで KeyError が ScenarioLoadError を
        # 経由せず素通りし、作家へのエラーメッセージが分かりにくくなる。
        if not isinstance(p, dict):
            raise ScenarioLoadError(
                f"environment.day_night.phases[{i}] must be an object, "
                f"got {type(p).__name__}"
            )
        missing = [k for k in required_keys if k not in p]
        if missing:
            raise ScenarioLoadError(
                f"environment.day_night.phases[{i}] is missing required keys: {missing}"
            )
        phases_list.append(
            DayNightPhaseDef(
                name=str(p["name"]),
                start_ratio=float(p["start_ratio"]),
                display_text=str(p["display_text"]),
                ambient_light=float(p["ambient_light"]),
                is_dark=parse_bool(
                    p["is_dark"],
                    path=f"environment.day_night.phases[{i}].is_dark",
                ),
            )
        )
    phases = tuple(phases_list)
    cycle = DayNightCycleDef(
        ticks_per_day=ticks_per_day,
        starting_tick_in_day=starting_tick,
        phases=phases,
    )
    return ScenarioDayNightConfig(cycle=cycle, announce_changes=announce)

def parse_weather_config( raw: Dict[str, Any]) -> Optional[ScenarioWeatherConfig]:
    weather = raw.get("weather") if isinstance(raw, dict) else None
    if not isinstance(weather, dict):
        return None
    enabled = parse_bool(
        weather.get("enabled", False),
        path="environment.weather.enabled",
    )
    initial = weather.get("initial", {})
    if not isinstance(initial, dict):
        initial = {}
    weather_type = WeatherTypeEnum[str(initial.get("weather_type", "FOG"))]
    intensity = float(initial.get("intensity", 0.6))
    return ScenarioWeatherConfig(
        enabled=enabled,
        initial_state=WeatherState(weather_type=weather_type, intensity=intensity),
        update_interval_ticks=int(weather.get("update_interval_ticks", 6)),
        announce_changes=parse_bool(
            weather.get("announce_changes", True),
            path="environment.weather.announce_changes",
        ),
    )

def parse_disabled_tools( raw: Any) -> Tuple[str, ...]:
    """``disabled_tools`` を読む。

    ここでは形だけを見る。**名前が実在するかは runtime 側で確かめる。**
    ツール名の一覧は application 層にあり、infrastructure から参照すると
    依存が逆向きになる。実在しない名前を書いても黙って無視されると
    「無効化したつもりが出たまま」になるので、起動時に落とす
    (``ToolExposureConfigurationError``)。

    重複はエラーにする。同じ名前が 2 度書かれているのは、多くの場合
    片方が消し忘れか書き換え漏れで、意図が読めない。
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ScenarioLoadError("disabled_tools はリストで書いてください")
    names: list[str] = []
    for entry in raw:
        if not isinstance(entry, str) or not entry.strip():
            raise ScenarioLoadError(
                f"disabled_tools の要素は空でない文字列にしてください: {entry!r}"
            )
        name = entry.strip()
        if name in names:
            raise ScenarioLoadError(f"disabled_tools に重複があります: {name}")
        names.append(name)
    return tuple(names)

def parse_end_conditions(
    raw: Any,
    mapper: ScenarioIdMapper,
    *,
    section: str,
) -> List[GameEndCondition]:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    conditions: List[GameEndCondition] = []
    for index, item in enumerate(items):
        ctype = GameEndConditionTypeEnum[item["type"]]
        allowed_sections = _GAME_END_CONDITION_ALLOWED_SECTIONS.get(ctype)
        if allowed_sections is None:
            raise ScenarioLoadError(
                f"game_end_conditions の条件型 {ctype.value} は置き場所が"
                "未分類です"
            )
        if section not in allowed_sections:
            allowed = " / ".join(
                name for name in ("win", "lose", "end")
                if name in allowed_sections
            )
            raise ScenarioLoadError(
                f"game_end_conditions.{section} に {ctype.value} は置けません。"
                f"{allowed} に置いてください [index={index}]"
            )
        validate_end_condition_required_fields(item, ctype, index=index)
        target_spot = None
        if "target_spot" in item:
            target_spot = SpotId.create(mapper.get_int("spot", item["target_spot"]))
        conditions.append(GameEndCondition(
            condition_type=ctype,
            target_spot_id=target_spot,
            target_flag=item.get("target_flag"),
            tick_limit=item.get("tick_limit"),
            required_state=item.get("required_state"),
            max_surviving=item.get("max_surviving"),
            comparison_state=item.get("comparison_state"),
            required_flags=(
                tuple(item["required_flags"])
                if isinstance(item.get("required_flags"), list)
                else None
            ),
            min_set_count=item.get("min_set_count"),
        ))
    return conditions

def validate_end_condition_required_fields(
    item: Dict[str, Any],
    ctype: GameEndConditionTypeEnum,
    *,
    index: int,
) -> None:
    """game_end_conditions の条件型ごとの必須フィールドをロード時に検査する。"""
    if ctype is GameEndConditionTypeEnum.FLAGS_SET_AT_LEAST:
        required_flags = item.get("required_flags")
        if not isinstance(required_flags, list) or not required_flags:
            raise ScenarioLoadError(
                f"game_end_conditions の {ctype.value} には required_flags の"
                "配列が必要です (空だと開始した瞬間に成立します)"
                f" [index={index}]"
            )
        if not all(
            isinstance(name, str) and name.strip() for name in required_flags
        ):
            raise ScenarioLoadError(
                f"game_end_conditions の {ctype.value} の required_flags は"
                "空でない文字列の配列である必要があります"
                f" [index={index}]"
            )
        min_set_count = item.get("min_set_count")
        if not isinstance(min_set_count, int) or isinstance(min_set_count, bool):
            raise ScenarioLoadError(
                f"game_end_conditions の {ctype.value} には整数の min_set_count"
                "が必要です (既定を『全部』にすると書き忘れと区別できません)"
                f" [index={index}]"
            )
        # 数の整合 (0 以下 / 上限超え / 重複) は GameEndCondition の
        # __post_init__ が見る。ここで二重に書くと判断が 2 箇所に散る。
        return

    if ctype == GameEndConditionTypeEnum.FLAG_SET:
        target_flag = item.get("target_flag")
        if not isinstance(target_flag, str) or not target_flag.strip():
            raise ScenarioLoadError(
                "game_end_conditions の FLAG_SET には target_flag が必要です "
                "(scenario_events の FLAG_SET は flag_name ですが、"
                "こちらは target_flag です)"
                f" [index={index}]"
            )
        return
    if ctype == GameEndConditionTypeEnum.TICK_LIMIT:
        if item.get("tick_limit") is None:
            raise ScenarioLoadError(
                "game_end_conditions の TICK_LIMIT には tick_limit が必要です"
                f" [index={index}]"
            )
        return
    if ctype is GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST:
        required_state = item.get("required_state")
        if not isinstance(required_state, dict) or not required_state:
            raise ScenarioLoadError(
                f"game_end_conditions の {ctype.value} には required_state が"
                "必要です (誰を数えるかが決まりません)"
                f" [index={index}]"
            )
        max_surviving = item.get("max_surviving")
        if not isinstance(max_surviving, int) or isinstance(max_surviving, bool):
            raise ScenarioLoadError(
                f"game_end_conditions の {ctype.value} には整数の max_surviving が"
                "必要です (0 を既定にすると書き忘れと全滅指定を区別できません)"
                f" [index={index}]"
            )
        if max_surviving < 0:
            raise ScenarioLoadError(
                f"game_end_conditions の {ctype.value} の max_surviving は 0 以上"
                f"である必要があります: {max_surviving} [index={index}]"
            )
        return
    if (
        ctype
        is GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE
    ):
        for field_name in ("required_state", "comparison_state"):
            state = item.get(field_name)
            if not isinstance(state, dict) or not state:
                raise ScenarioLoadError(
                    f"game_end_conditions の {ctype.value} には {field_name} が"
                    f"必要です [index={index}]"
                )
        # 左右が同じ集合かは GameEndCondition が単一の判断場所として見る。
        return
    if ctype in (
        GameEndConditionTypeEnum.ALL_AT_SPOT,
        GameEndConditionTypeEnum.ANY_AT_SPOT,
    ):
        target_spot = item.get("target_spot")
        if not isinstance(target_spot, str) or not target_spot.strip():
            raise ScenarioLoadError(
                f"game_end_conditions の {ctype.value} には target_spot が必要です"
                f" [index={index}]"
            )

