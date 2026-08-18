"""players / monsters / personas の読み取り。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
)
from ai_rpg_world.infrastructure.scenario.declaration_site import declaring
from ai_rpg_world.infrastructure.scenario.validate_attribute_values import (
    reject_values_the_world_does_not_have,
)
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterTemplateValidationException
from ai_rpg_world.domain.monster.value_object.attack_status_effect_chance import AttackStatusEffectChance
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.models import (
    InitialItemSpec,
    PlayerSpawnConfig,
    ScenarioMonsterPlacement,
    ScenarioMonsterSpawnCondition,
    ScenarioMonsterTemplate,
)
from ai_rpg_world.infrastructure.scenario.parse_economy import parse_initial_item
from ai_rpg_world.infrastructure.scenario.parse_helpers import parse_bool
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper
from ai_rpg_world.infrastructure.scenario.validate_features import (
    _MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS,
)

def parse_mutually_known_roles(
    raw: Any,
    players: Sequence[PlayerSpawnConfig],
) -> Tuple[str, ...]:
    """互いを知る role を読み、実在する複数人の集合だけを受理する。

    一人しかいない role は印を一つも生成せず、作者が開示したつもりのまま
    静かに効かない。少なくとも二人いることまで読み込み時に確かめる。
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ScenarioLoadError("mutually_known_roles は配列で書いてください")
    roles: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            raise ScenarioLoadError(
                "mutually_known_roles は空でない role 名の配列にしてください"
            )
        role = value.strip()
        if role in roles:
            raise ScenarioLoadError(
                f"mutually_known_roles に重複があります: {role}"
            )
        count = sum(
            1 for player in players if player.initial_state.get("role") == role
        )
        if count < 2:
            raise ScenarioLoadError(
                f"mutually_known_roles の {role} には二人以上必要です: {count}人"
            )
        roles.append(role)
    return tuple(roles)

def parse_role_personas(
    raw: Any,
    players: Sequence[PlayerSpawnConfig],
) -> Mapping[str, str]:
    """役職共通文を検証し、宣言順を保った mapping として返す。"""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ScenarioLoadError("role_personas は role 名から文章への object で書いてください")

    declared_roles = {
        role
        for player in players
        if isinstance((role := player.initial_state.get("role")), str) and role
    }
    parsed: Dict[str, str] = {}
    for role, persona in raw.items():
        if not isinstance(role, str) or not role.strip():
            raise ScenarioLoadError("role_personas のキーは空でない role 名にしてください")
        normalized_role = role.strip()
        if normalized_role in parsed:
            raise ScenarioLoadError(
                f"role_personas に正規化後の重複があります: {normalized_role}"
            )
        if normalized_role not in declared_roles:
            raise ScenarioLoadError(
                f"role_personas に player が一人も持たない role があります: {normalized_role}"
            )
        if not isinstance(persona, str) or not persona.strip():
            raise ScenarioLoadError(
                f"role_personas.{normalized_role} は空でない文字列にしてください"
            )
        parsed[normalized_role] = persona.strip()
    return parsed

def parse_monsters_block( raw: Optional[Dict[str, Any]], mapper: ScenarioIdMapper,
) -> Tuple[Tuple[ScenarioMonsterTemplate, ...], Tuple[ScenarioMonsterPlacement, ...]]:
    """`monsters.templates` と `monsters.initial_placements` を読み込む (Phase B-2a)。

    JSON 形式:
    ```
    "monsters": {
      "templates": [
        {
          "id": "wild_dog",
          "name": "野犬",
          "description": "...",
          "race": "WOLF",                  // Race enum 名
          "faction": "ENEMY",              // MonsterFactionEnum 名
          "base_stats": {                  // 必須キー全部
            "max_hp": 30, "max_mp": 0, "attack": 8, "defense": 4,
            "speed": 6, "critical_rate": 0.05, "evasion_rate": 0.1
          },
          "reward": {"exp": 10, "gold": 0},
          "respawn": {"interval_ticks": 50, "auto": true},
          "vision_range": 4,
          "flee_threshold": 0.2
        }
      ],
      "initial_placements": [
        {"template": "wild_dog", "spot": "deep_forest", "coordinate": {"x": 0, "y": 0}}
      ]
    }
    ```

    Phase B-2a では initial_placements は static (シナリオ起動時のみ配置)。
    spawn_condition による動的 spawn は Phase B-2b で扱う。
    """
    if not isinstance(raw, dict):
        return ((), ())
    templates_raw = raw.get("templates", [])
    placements_raw = raw.get("initial_placements", [])
    if not isinstance(templates_raw, list):
        raise ScenarioLoadError("monsters.templates must be a list")
    if not isinstance(placements_raw, list):
        raise ScenarioLoadError("monsters.initial_placements must be a list")

    templates = tuple(
        parse_monster_template(t, mapper, i)
        for i, t in enumerate(templates_raw)
    )
    placements = tuple(
        parse_monster_placement(p, i)
        for i, p in enumerate(placements_raw)
    )
    return templates, placements

def parse_monster_template( raw: Any, mapper: ScenarioIdMapper, index: int,
) -> ScenarioMonsterTemplate:
    """1 monster template を MonsterTemplate に変換する。"""
    if not isinstance(raw, dict):
        raise ScenarioLoadError(
            f"monsters.templates[{index}] must be an object, got {type(raw).__name__}"
        )
    string_id = raw.get("id")
    if not isinstance(string_id, str) or not string_id:
        raise ScenarioLoadError(
            f"monsters.templates[{index}].id must be a non-empty string"
        )
    # 文字列 ID → 連番 int を id_mapper に登録 (将来 cross-reference する場面用)
    template_int_id = mapper.register("monster_template", string_id)

    base = raw.get("base_stats", {})
    if not isinstance(base, dict):
        raise ScenarioLoadError(
            f"monsters.templates[{index}].base_stats must be an object"
        )
    try:
        base_stats = BaseStats(
            max_hp=int(base.get("max_hp", 30)),
            max_mp=int(base.get("max_mp", 0)),
            attack=int(base.get("attack", 5)),
            defense=int(base.get("defense", 3)),
            speed=int(base.get("speed", 5)),
            critical_rate=float(base.get("critical_rate", 0.05)),
            evasion_rate=float(base.get("evasion_rate", 0.05)),
        )
    except (TypeError, ValueError) as e:
        raise ScenarioLoadError(
            f"monsters.templates[{index}].base_stats parse error: {e}"
        ) from e

    reward_raw = raw.get("reward", {})
    reward = RewardInfo(
        exp=int(reward_raw.get("exp", 0)),
        gold=int(reward_raw.get("gold", 0)),
    )
    respawn_raw = raw.get("respawn", {})
    respawn = RespawnInfo(
        respawn_interval_ticks=int(respawn_raw.get("interval_ticks", 50)),
        is_auto_respawn=parse_bool(
            respawn_raw.get("auto", True),
            path=f"monsters.templates[{index}].respawn.auto",
        ),
    )

    race_name = str(raw.get("race", "WOLF"))
    try:
        race = Race[race_name]
    except KeyError as e:
        valid = [r.name for r in Race]
        raise ScenarioLoadError(
            f"monsters.templates[{index}].race must be one of {valid}, got {race_name}"
        ) from e
    faction_name = str(raw.get("faction", "ENEMY"))
    try:
        faction = MonsterFactionEnum[faction_name]
    except KeyError as e:
        valid = [f.name for f in MonsterFactionEnum]
        raise ScenarioLoadError(
            f"monsters.templates[{index}].faction must be one of {valid}, got {faction_name}"
        ) from e

    template = MonsterTemplate(
        template_id=MonsterTemplateId(template_int_id),
        name=str(raw.get("name", string_id)),
        base_stats=base_stats,
        reward_info=reward,
        respawn_info=respawn,
        race=race,
        faction=faction,
        description=str(raw.get("description", "")),
        skill_ids=[],  # Phase B-2a ではスキル無し
        vision_range=int(raw.get("vision_range", 5)),
        flee_threshold=float(raw.get("flee_threshold", 0.2)),
        attack_status_effects=parse_monster_attack_status_effects(
            raw.get("attack_status_effects", []), index,
        ),
    )
    return ScenarioMonsterTemplate(string_id=string_id, template=template)

def parse_monster_attack_status_effects( raw: Any, template_index: int,
) -> tuple[AttackStatusEffectChance, ...]:
    """攻撃時状態異常のJSON宣言を、検証済みドメイン値へ変換する。"""
    path = f"monsters.templates[{template_index}].attack_status_effects"
    if not isinstance(raw, list):
        raise ScenarioLoadError(f"{path} must be a list")
    parsed: list[AttackStatusEffectChance] = []
    for effect_index, item in enumerate(raw):
        item_path = f"{path}[{effect_index}]"
        if not isinstance(item, dict):
            raise ScenarioLoadError(f"{item_path} must be an object")
        effect_type_raw = item.get("effect_type")
        try:
            effect_type = StatusEffectType(effect_type_raw)
        except (TypeError, ValueError) as exc:
            raise ScenarioLoadError(
                f"{item_path}.effect_type must be a StatusEffectType value, "
                f"got {effect_type_raw!r}"
            ) from exc
        try:
            parsed.append(AttackStatusEffectChance(
                effect_type=effect_type,
                chance=item.get("chance"),
                duration_ticks=item.get("duration_ticks"),
                value=item.get("value", 1.0),
            ))
        except MonsterTemplateValidationException as exc:
            raise ScenarioLoadError(f"{item_path}: {exc}") from exc
    return tuple(parsed)

def parse_monster_placement( raw: Any, index: int,
) -> ScenarioMonsterPlacement:
    if not isinstance(raw, dict):
        raise ScenarioLoadError(
            f"monsters.initial_placements[{index}] must be an object"
        )
    template_id = raw.get("template")
    spot_id = raw.get("spot")
    if not isinstance(template_id, str) or not template_id:
        raise ScenarioLoadError(
            f"monsters.initial_placements[{index}].template must be a non-empty string"
        )
    if not isinstance(spot_id, str) or not spot_id:
        raise ScenarioLoadError(
            f"monsters.initial_placements[{index}].spot must be a non-empty string"
        )
    coord = raw.get("coordinate", {})
    if not isinstance(coord, dict):
        coord = {}
    spawn_condition = parse_monster_spawn_condition(
        raw.get("spawn_condition"), index,
    )
    return ScenarioMonsterPlacement(
        template_string_id=template_id,
        spot_string_id=spot_id,
        coordinate_x=int(coord.get("x", 0)),
        coordinate_y=int(coord.get("y", 0)),
        coordinate_z=int(coord.get("z", 0)),
        spawn_condition=spawn_condition,
    )

def parse_monster_spawn_condition( raw: Any, placement_index: int,
) -> Optional[ScenarioMonsterSpawnCondition]:
    """placement の spawn_condition ブロックを ScenarioMonsterSpawnCondition に変換。

    JSON 形式:
    ```
    "spawn_condition": {
      "day_night_phases": ["night"],
      "required_flags": ["high_tide"],
      "forbidden_flags": [],
      "weather_types": ["STORM"]
    }
    ```
    いずれか 1 つでも軸が指定されれば条件付き。すべて空 / セクション欠落
    なら null を返し、placement は常時 spawn (static) 扱い。

    WeatherTypeEnum 名は boundary で検証する (作家ミスを早期に弾く)。
    day_night_phases は scenario 内で自由命名できるので事前検証しない。
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ScenarioLoadError(
            f"monsters.initial_placements[{placement_index}].spawn_condition "
            f"must be an object, got {type(raw).__name__}"
        )
    unknown_keys = set(raw) - set(
        _MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS
    )
    if unknown_keys:
        raise ScenarioLoadError(
            f"monsters.initial_placements[{placement_index}].spawn_condition "
            f"contains unknown keys: {sorted(unknown_keys)}"
        )

    def _as_str_tuple(value: Any, key: str) -> Tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, list):
            raise ScenarioLoadError(
                f"monsters.initial_placements[{placement_index}]."
                f"spawn_condition.{key} must be a list of strings"
            )
        return tuple(str(v) for v in value)

    values = {
        key: _as_str_tuple(raw.get(key), key)
        for key in _MONSTER_SPAWN_CONDITION_FEATURE_REQUIREMENTS
    }
    phases = values["day_night_phases"]
    required_flags = values["required_flags"]
    forbidden_flags = values["forbidden_flags"]
    weathers = values["weather_types"]

    # WeatherTypeEnum 名は事前検証する。作家ミスは boundary で弾く。
    for w in weathers:
        try:
            WeatherTypeEnum[w]
        except KeyError as e:
            valid = [x.name for x in WeatherTypeEnum]
            raise ScenarioLoadError(
                f"monsters.initial_placements[{placement_index}]."
                f"spawn_condition.weather_types contains invalid value {w!r}. "
                f"Valid values: {valid}"
            ) from e

    return ScenarioMonsterSpawnCondition(
        day_night_phase_names=phases,
        required_flags=required_flags,
        forbidden_flags=forbidden_flags,
        weather_type_names=weathers,
    )

def parse_players(
    players_raw: List[Dict[str, Any]],
    mapper: ScenarioIdMapper,
    *,
    player_attribute_specs: PlayerAttributeSpecs,
) -> List[PlayerSpawnConfig]:
    spawns: List[PlayerSpawnConfig] = []
    for p in players_raw:
        pid = mapper.register("player", p["id"])
        spot_sid = p["spawn_spot"]
        spot_id = SpotId.create(mapper.get_int("spot", spot_sid))
        items = tuple(
            parse_initial_item(raw, mapper, owner_id=p["id"])
            for raw in p.get("initial_items", [])
        )
        _require_initial_items_fit(items, owner_id=p["id"])
        initial_state = parse_player_initial_state(
            p.get("initial_state", {}), owner_id=p["id"],
        )
        # 初期値そのものは変更ではないので `mutable` は見ない。見るのは
        # 「世界がその値を持っているか」だけ。
        with declaring(f"players[{p['id']}].initial_state:"):
            reject_values_the_world_does_not_have(
                initial_state, player_attribute_specs, what="initial_state",
            )
        persona_raw = p.get("persona_prompt")
        persona_prompt: Optional[str] = None
        if persona_raw is not None:
            if not isinstance(persona_raw, str):
                raise ValueError(
                    f"player '{p['id']}': persona_prompt must be a string, "
                    f"got {type(persona_raw).__name__}"
                )
            # 前後 whitespace を削るが内側の改行は保持する (多行プロンプトを許容)
            stripped = persona_raw.strip()
            persona_prompt = stripped if stripped else None
        objective = parse_player_objective(
            p.get("objective"), owner_id=p["id"],
        )
        goal_locked = parse_player_goal_locked(
            p.get("goal_locked"), owner_id=p["id"],
        )
        initial_gold = parse_player_initial_gold(
            p.get("initial_gold"), owner_id=p["id"],
        )
        spawns.append(PlayerSpawnConfig(
            string_id=p["id"],
            player_id=pid,
            name=p["name"],
            spawn_spot_id=spot_id,
            initial_items=items,
            initial_state=initial_state,
            persona_prompt=persona_prompt,
            objective=objective,
            goal_locked=goal_locked,
            initial_gold=initial_gold,
        ))
    return spawns

def parse_player_initial_gold(raw: Any, *, owner_id: str) -> int:
    """``players[].initial_gold`` を検証する (経済統合 Phase 0)。

    省略は「無一文で始まる」と同義なので 0 に畳む。負値は Gold 値
    オブジェクトの下限 0 に反するため、実行前に落とす。bool を除くのは
    True が int として通ると 1 gold の宣言と見分けが付かなくなるため。
    """
    if raw is None:
        return 0
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ScenarioLoadError(
            f"players[{owner_id}].initial_gold は整数で宣言してください "
            f"(got {raw!r})"
        )
    if raw < 0:
        raise ScenarioLoadError(
            f"players[{owner_id}].initial_gold は 0 以上で宣言してください "
            f"(got {raw})"
        )
    return raw

def parse_player_objective(raw: Any, *, owner_id: str) -> Optional[str]:
    """``players[].objective`` を検証して正規化する (目的層 G6)。

    persona_prompt と同じ規約: 前後の whitespace は削るが内側の改行は
    保持する (箇条書きの目的文を許容するため)。空文字・空白のみは None に
    畳んで「未指定」と同じ扱いにする — 空文字で seed すると GoalEntry の
    VO 不変条件に弾かれて静かに目的が消えるため、入口で潰す。
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError(
            f"player '{owner_id}': objective must be a string, "
            f"got {type(raw).__name__}"
        )
    stripped = raw.strip()
    if not stripped:
        # 空白のみを黙って None に畳むと「個別目的を書いたつもりが共通目的で
        # seed される」静かな失敗になる。共通目的文が非空の通常シナリオでは
        # fail-fast にも掛からないので、ここで痕跡を残すしかない。
        logging.getLogger(__name__).warning(
            "player '%s': objective is whitespace-only; treating it as unset "
            "and falling back to metadata.llm_objective_text",
            owner_id,
        )
        return None
    return stripped

def parse_player_goal_locked(raw: Any, *, owner_id: str) -> Optional[bool]:
    """``players[].goal_locked`` を検証する (目的層 G6)。

    None (未指定) はシナリオ全体の性質から導出する意味なので、False とは
    区別して保持する。bool 以外は誤記として弾く — 0 / 1 / "true" を暗黙に
    受けると「locked のつもりが unlocked」の取り違えが静かに通るため。
    """
    if raw is None:
        return None
    if not isinstance(raw, bool):
        raise ValueError(
            f"player '{owner_id}': goal_locked must be a boolean, "
            f"got {type(raw).__name__}"
        )
    return raw

def parse_player_initial_state(
    raw: Any, *, owner_id: str,
) -> Dict[str, Any]:
    """`players[].initial_state` を JSON プリミティブの flat dict に正規化。

    `PlayerStatusAggregate.state` の制約 (str / int / float / bool / None) に
    合わない値はシナリオ load 時点で `ScenarioLoadError` として弾く。
    domain 層側でも `PlayerStateValidationException` として再検証されるが、
    load 時点で落とせば「実行直前まで気付かない」事故が減る。
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ScenarioLoadError(
            f"players[{owner_id}].initial_state must be an object "
            f"(got {type(raw).__name__})"
        )
    allowed = (str, int, float, bool, type(None))
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ScenarioLoadError(
                f"players[{owner_id}].initial_state key must be string "
                f"(got {type(key).__name__}: {key!r})"
            )
        if not isinstance(value, allowed):
            raise ScenarioLoadError(
                f"players[{owner_id}].initial_state[{key!r}] must be a JSON primitive "
                f"(str / int / float / bool / null), got {type(value).__name__}"
            )
    return dict(raw)



def _require_initial_items_fit(items: tuple, *, owner_id: str) -> None:
    """初期所持品が所持枠に収まっていることを、読み込みの時点で確かめる。

    枠を超えるぶんは `acquire_item` が**黙って捨てる**。run が始まってから
    足元に落ちていても、シナリオ作家は自分の宣言が効いていないことに気づけない
    (#830 / #840 と同じ形)。

    効果として与えられる品 (採取・報酬) は「持ちきれず落ちた」で良いが、
    こちらはまだ誰も居ない起動前の話で、落とす先も無い。**作者の誤りであって、
    世界の出来事ではない。**
    """
    from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
        PlayerInventoryAggregate,
    )

    DEFAULT_MAX_SLOTS = PlayerInventoryAggregate.DEFAULT_MAX_SLOTS

    if len(items) <= DEFAULT_MAX_SLOTS:
        return
    raise ScenarioLoadError(
        f"players[{owner_id!r}].initial_items が所持枠に収まりません "
        f"({len(items)} 個を宣言していますが、枠は {DEFAULT_MAX_SLOTS} 個です)。"
        "枠を超えたぶんは持たせられないので、宣言を減らしてください。"
    )
