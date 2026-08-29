"""シナリオ JSON 読み取りの共通ヘルパ。"""

from __future__ import annotations

from math import isfinite
from string import Formatter
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import StateDisplayRuleValidationException
from ai_rpg_world.domain.world_graph.value_object.spot_position import SpotPosition
from ai_rpg_world.domain.world_graph.value_object.state_display_rule import (
    StateDisplayRule,
    state_display_value_identity,
)
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper

def parse_role_labels(raw: Any) -> Dict[str, str]:
    """``role_labels`` を読む。省略時は空 (呼び名を出さない)。"""
    value = raw.get("role_labels")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ScenarioLoadError("metadata.role_labels はオブジェクトで書いてください")
    labels: Dict[str, str] = {}
    for key, label in value.items():
        if not isinstance(key, str) or not isinstance(label, str) or not label.strip():
            raise ScenarioLoadError(
                f"metadata.role_labels の要素は文字列で書いてください: {key!r}: {label!r}"
            )
        labels[key] = label.strip()
    return labels

def parse_show_world_map(raw: Any) -> bool:
    """``show_world_map`` を読む。省略時は False (載せない)。

    真偽値以外は拒否する。``"true"`` と書いて常に真になると、書いた人の意図と
    結果が食い違う。
    """
    value = raw.get("show_world_map")
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ScenarioLoadError(
            f"metadata.show_world_map は true / false で書いてください: {value!r}"
        )
    return value

def parse_bool(value: Any, *, path: str) -> bool:
    """JSON の真偽値だけを受理し、文字列や整数の暗黙変換を拒否する。"""
    if not isinstance(value, bool):
        raise ScenarioLoadError(
            f"{path} must be a boolean, got {value!r}"
        )
    return value

def parse_player_outcome_messages(
    raw: Mapping[str, Any],
) -> Mapping[PlayerOutcomeEnum, str]:
    """終局結果ごとの観測文型を読み、置換可能な項目を限定する。"""
    value = raw.get("player_outcome_messages", {})
    if not isinstance(value, dict):
        raise ScenarioLoadError(
            "metadata.player_outcome_messages must be an object"
        )

    parsed: dict[PlayerOutcomeEnum, str] = {}
    for outcome_name, template_raw in value.items():
        path = f"metadata.player_outcome_messages.{outcome_name}"
        try:
            outcome = PlayerOutcomeEnum(outcome_name)
        except (TypeError, ValueError) as exc:
            raise ScenarioLoadError(
                f"{path}: unknown player outcome {outcome_name!r}"
            ) from exc
        if outcome is PlayerOutcomeEnum.UNRESOLVED:
            raise ScenarioLoadError(f"{path}: UNRESOLVED cannot be announced")
        if not isinstance(template_raw, str) or not template_raw.strip():
            raise ScenarioLoadError(f"{path} must be a non-empty string")

        template = template_raw.strip()
        try:
            fields = [
                (field_name, format_spec, conversion)
                for _, field_name, format_spec, conversion in Formatter().parse(
                    template
                )
                if field_name is not None
            ]
        except ValueError as exc:
            raise ScenarioLoadError(f"{path}: invalid message template") from exc
        unknown = [name for name, _, _ in fields if name != "player_name"]
        if unknown:
            raise ScenarioLoadError(
                f"{path}: unknown placeholder {unknown[0]!r}; "
                "only {player_name} is allowed"
            )
        unsupported_format = [
            (name, format_spec, conversion)
            for name, format_spec, conversion in fields
            if format_spec or conversion is not None
        ]
        if unsupported_format:
            raise ScenarioLoadError(
                f"{path}: format specifiers and conversions are not allowed"
            )
        if not any(name == "player_name" for name, _, _ in fields):
            raise ScenarioLoadError(f"{path} must contain {{player_name}}")
        parsed[outcome] = template
    return parsed

def parse_object_state_display(
    raw: Mapping[str, Any],
    *,
    recorded_tick_state_keys: frozenset[str] = frozenset(),
) -> Tuple[StateDisplayRule, ...]:
    """object.state_display を StateDisplayRule の列へ変換する。"""

    object_id = raw.get("id")
    raw_rules = raw.get("state_display", ())
    if raw_rules == ():
        return ()
    if not isinstance(raw_rules, list):
        raise ScenarioLoadError(f"object {object_id}.state_display must be a list")

    parsed: list[StateDisplayRule] = []
    seen: set[tuple[Any, ...]] = set()
    for index, item in enumerate(raw_rules):
        path = f"object {object_id}.state_display[{index}]"
        if not isinstance(item, dict):
            raise ScenarioLoadError(f"{path} must be an object")
        if "key" not in item:
            raise ScenarioLoadError(f"{path}.key is required")
        if "text" not in item:
            raise ScenarioLoadError(f"{path}.text is required")
        selectors = tuple(
            name for name in ("value", "at_least", "within_ticks") if name in item
        )
        if "within_ticks" in item and len(selectors) > 1:
            others = " and ".join(name for name in selectors if name != "within_ticks")
            raise ScenarioLoadError(
                f"{path} cannot specify both {others} and within_ticks"
            )
        if "value" in item and "at_least" in item:
            raise ScenarioLoadError(
                f"{path} cannot specify both value and at_least"
            )
        try:
            rule = StateDisplayRule(
                key=item["key"],
                value=item.get("value"),
                text=item["text"],
                at_least=item.get("at_least"),
                within_ticks=item.get("within_ticks"),
                requires_light=item.get("requires_light", False),
                unless_flag_set=item.get("unless_flag_set"),
            )
        except StateDisplayRuleValidationException as exc:
            raise ScenarioLoadError(f"{path}: {exc}") from exc
        if (
            rule.within_ticks is not None
            and rule.key not in recorded_tick_state_keys
        ):
            raise ScenarioLoadError(
                f"{path}.key={rule.key!r} must be written by this object's "
                "RECORD_OBJECT_STATE_TICK effect"
            )
        duplicate_key = (
            (rule.key, "within_ticks", rule.within_ticks)
            if rule.within_ticks is not None
            else (
                (rule.key, "at_least", rule.at_least)
                if rule.at_least is not None
                else (rule.key, "value", state_display_value_identity(rule.value))
            )
        )
        if duplicate_key in seen:
            raise ScenarioLoadError(
                f"{path} duplicates state_display rule for key={rule.key!r}"
            )
        seen.add(duplicate_key)
        parsed.append(rule)
    return tuple(parsed)

def parse_object_hidden_state_keys(raw: Mapping[str, Any]) -> frozenset[str]:
    """object.hidden_state_keys を文字列集合へ変換する。"""

    object_id = raw.get("id")
    raw_keys = raw.get("hidden_state_keys", ())
    if raw_keys == ():
        return frozenset()
    if not isinstance(raw_keys, list):
        raise ScenarioLoadError(f"object {object_id}.hidden_state_keys must be a list")
    parsed: set[str] = set()
    for index, key in enumerate(raw_keys):
        if not isinstance(key, str) or not key.strip():
            raise ScenarioLoadError(
                f"object {object_id}.hidden_state_keys[{index}] must be a non-empty string"
            )
        parsed.add(key)
    return frozenset(parsed)

def recorded_tick_state_keys(
    interactions: Any, own_object_id: int
) -> frozenset[str]:
    """この物体の操作が**自分に**書き込む「手番を記録する key」を集める。

    ``tick`` は世界の中に無い語 (#892)。世界の中の人が手番を数えているはずが
    ないので、記録用の key が prompt に出た時点で嘘になる。

    かつては ``visible_state`` が ``last_harvest_tick`` という**綴りを 1 つ
    直書き**して隠していた。流木や木の実はその名前を選んだので守られ、
    ``last_lit_tick`` と名付けた焚き火跡は守られずに漏れていた。

    守るのは名前ではなく「手番を記録する効果が書いた key」。名前は作家の
    自由で、engine が当てにいくものではない。

    シナリオ JSON に ``hidden_state_keys`` を書かせる案は採らない。書き忘れが
    即漏洩になる。``SpotObject.with_additional_hidden_state_keys`` の説明に
    「per-object 設定に頼ると設定漏れで漏れる (既知回帰)」とあり、同じ失敗を
    一度している。

    シナリオの ``target_object`` は、ここへ来る前に ``object_id`` (数値) へ
    読み替えられている。**自分自身を明示する書き方も多い** (``herb_planter``
    が ``target_object: herb_planter`` と書く形) ので、省略と同じものとして
    扱う。「指定があれば他所行き」と決めつけると、実際に多いほうの書き方を
    取りこぼす。

    ``object_id`` が**別の物体**を指す場合だけはここで拾えない。そちらは効果を
    適用する側が書き込みと同時に伏せる。
    """
    keys: set[str] = set()
    for interaction in interactions or ():
        for effect in getattr(interaction, "effects", ()) or ():
            if (
                getattr(effect, "effect_type", None)
                is not InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK
            ):
                continue
            params = getattr(effect, "parameters", None) or {}
            target = params.get("object_id")
            if target is not None and int(target) != int(own_object_id):
                continue
            state_key = params.get("state_key")
            if isinstance(state_key, str) and state_key:
                keys.add(state_key)
    return frozenset(keys)

def remote_recorded_tick_state_keys(
    items_raw: Sequence[Mapping[str, Any]],
    mapper: ScenarioIdMapper,
) -> Mapping[int, frozenset[str]]:
    """道具が遠隔物体へ記録する手番 key を、対象物体ごとに集める。

    物体自身の interaction だけを見ていると、道具から書かれる key は読み込み
    時に導出できず、作者へ ``hidden_state_keys`` の重複宣言を要求してしまう。
    書き忘れが生の手番を漏らす形へ戻さないため、同じ効果宣言から導出する。
    """
    collected: dict[int, set[str]] = {}
    for item in items_raw:
        for interaction in item.get("interactions", ()) or ():
            for effect in interaction.get("effects", ()) or ():
                if effect.get("effect_type") != "RECORD_OBJECT_STATE_TICK":
                    continue
                parameters = effect.get("parameters", {}) or {}
                target = parameters.get("target_object")
                state_key = parameters.get("state_key")
                if not isinstance(target, str) or not isinstance(state_key, str):
                    continue
                object_id = mapper.get_int("object", target)
                collected.setdefault(object_id, set()).add(state_key)
    return {
        object_id: frozenset(keys)
        for object_id, keys in collected.items()
    }

def iter_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    """JSON内の全objectを、配置を手動列挙せず再帰的に返す。"""
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from iter_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_mappings(child)

def parse_position_number( raw: Any, path: str) -> float:
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise ScenarioLoadError(f"{path} must be a number")
    value = float(raw)
    if not isfinite(value):
        raise ScenarioLoadError(f"{path} must be a finite number")
    return value

def parse_prominence( raw: Any, path: str) -> float:
    value = parse_position_number(raw, path)
    if not 0.0 <= value <= 1.0:
        raise ScenarioLoadError(f"{path} must be in [0.0, 1.0]")
    return value

def is_json_primitive(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool)):
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return isfinite(value)
    return False

def spot_positions_by_area(
    spots_raw: Any,
) -> Dict[str, Tuple[SpotPosition, ...]]:
    grouped: Dict[str, List[SpotPosition]] = {}
    if not isinstance(spots_raw, Sequence) or isinstance(spots_raw, (str, bytes)):
        return {}
    for spot in spots_raw:
        if not isinstance(spot, Mapping):
            continue
        area_id = spot.get("area_id")
        if not isinstance(area_id, str) or not area_id.strip():
            continue
        spot_id = str(spot.get("id", "<unknown>"))
        position_raw = spot.get("position")
        if position_raw is None:
            continue
        path = f"spots[{spot_id}].position"
        if not isinstance(position_raw, Mapping):
            raise ScenarioLoadError(f"{path} must be an object with numeric x/y")
        unknown_keys = set(position_raw) - {"x", "y"}
        if unknown_keys:
            raise ScenarioLoadError(
                f"{path} has unsupported keys: {sorted(unknown_keys)}"
            )
        position = SpotPosition(
            x=parse_position_number(position_raw.get("x"), f"{path}.x"),
            y=parse_position_number(position_raw.get("y"), f"{path}.y"),
        )
        grouped.setdefault(area_id.strip(), []).append(position)
    return {area_id: tuple(positions) for area_id, positions in grouped.items()}

def area_centroid(positions: Sequence[SpotPosition]) -> Optional[SpotPosition]:
    if not positions:
        return None
    return SpotPosition(
        x=sum(p.x for p in positions) / len(positions),
        y=sum(p.y for p in positions) / len(positions),
    )

def parse_departed_agents_enabled(raw: Dict[str, Any]) -> bool:
    value = raw.get("departed_agents_enabled", False)
    if not isinstance(value, bool):
        raise ScenarioLoadError("departed_agents_enabled は真偽値で書いてください")
    return value

def parse_item_spec_id_parameter_key(raw: Dict[str, Any]) -> Optional[str]:
    """``item_spec_id_parameter_key`` を検証して返す。

    対象所持条件でしか意味を持たないフィールドなので、他の condition_type
    に書かれていたら黙って無視せず落とす。無視すると「書いたのに効かない」
    宣言がシナリオに残り、実 run で初めて気付くことになる。
    """
    key = raw.get("item_spec_id_parameter_key")
    if key is None:
        return None
    if not isinstance(key, str) or not key.strip():
        raise ScenarioLoadError(
            "item_spec_id_parameter_key must be a non-empty string"
        )
    cond_type = raw.get("condition_type")
    if cond_type not in ("TARGET_HAS_ITEM", "TARGET_HAS_NO_ITEM"):
        raise ScenarioLoadError(
            "item_spec_id_parameter_key is only valid on TARGET_HAS_ITEM / "
            f"TARGET_HAS_NO_ITEM (got condition_type={cond_type!r})"
        )
    return key.strip()

def parse_need_type(raw: Dict[str, Any]) -> Optional[str]:
    """`need_type` が指定されていれば NeedType に存在する名前か load 時に検証する。

    ランタイムまで silent に間違いを引きずると「interaction が永久に
    発火しない」silent failure になるので boundary で弾く。
    """
    value = raw.get("need_type")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ScenarioLoadError(
            f"need_type must be a string (got {type(value).__name__})"
        )
    try:
        NeedType(value)
    except ValueError as exc:
        valid = sorted(t.value for t in NeedType)
        raise ScenarioLoadError(
            f"need_type {value!r} is not a known NeedType. Valid values: {valid}"
        ) from exc
    return value

def parse_hp_ratio(raw: Dict[str, Any]) -> Optional[float]:
    """`hp_ratio` を 0.0..1.0 の範囲で検証する。範囲外は load 時に拒否。"""
    value = raw.get("hp_ratio")
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError) as exc:
        raise ScenarioLoadError(
            f"hp_ratio must be a number (got {value!r})"
        ) from exc
    if not (0.0 <= f <= 1.0):
        raise ScenarioLoadError(
            f"hp_ratio must be in [0.0, 1.0] (got {f})"
        )
    return f

def parse_required_quantity(raw: Dict[str, Any]) -> int:
    """`required_quantity` を読みつつ `<= 0` は明確に拒否する。

    domain 側で max(1, ...) する設計だが、scenario 作家が `0` を
    書いた場合に「条件無し」と勘違いするのを防ぐため、loader 側で
    早期に弾く。
    """
    if "required_quantity" not in raw:
        return 1
    try:
        value = int(raw["required_quantity"])
    except (TypeError, ValueError) as exc:
        raise ScenarioLoadError(
            f"required_quantity must be a positive integer (got {raw['required_quantity']!r})"
        ) from exc
    if value <= 0:
        raise ScenarioLoadError(
            f"required_quantity must be >= 1 (got {value})"
        )
    return value

def optional_spot_id( value: Any, mapper: ScenarioIdMapper) -> Optional[int]:
    if not value:
        return None
    return mapper.get_int("spot", str(value))

def declared_action_names(raw: Dict[str, Any]) -> Set[str]:
    """シナリオ生データから、宣言済みの `action_name` を全部集める。"""
    names: Set[str] = set()

    def add_from(interactions: Any) -> None:
        if not isinstance(interactions, list):
            return
        for entry in interactions:
            if isinstance(entry, dict) and entry.get("action_name"):
                names.add(str(entry["action_name"]))

    for spot in raw.get("spots", []) or []:
        if not isinstance(spot, dict):
            continue
        add_from(spot.get("interactions"))
        interior = spot.get("interior") or {}
        if isinstance(interior, dict):
            for obj in interior.get("objects", []) or []:
                if isinstance(obj, dict):
                    add_from(obj.get("interactions"))
    for connection in raw.get("connections", []) or []:
        if isinstance(connection, dict):
            add_from(connection.get("interactions"))
    add_from(raw.get("player_interactions"))
    return names
