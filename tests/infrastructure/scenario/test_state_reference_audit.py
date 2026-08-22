"""全シナリオの状態・フラグ参照に、同じ世界内の書き手が存在することを保証する。

状態キーの typo は JSON として正しいため、loader の型検査だけでは止まらない。
条件が永久に成立せず、高コストの実験を最後まで走らせてから気づく形になる。
条件・効果の種別から名前空間を区別し、参照と初期宣言・更新効果を突き合わせる。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ai_rpg_world.domain.world_graph.entity.spot_object import (
    _STOCK_POOL_STATE_KEYS,
)
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    SIGN_AUTHOR_STATE_KEY,
    SIGN_HIDDEN_STATE_KEYS,
    SIGN_TEXT_STATE_KEY,
)

SCENARIO_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"
FIXTURE_SCENARIO_DIR = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "scenarios"
)
NAMESPACES = ("object", "item", "player", "flag")


# condition_type は、読む名前空間を一意に決める。scenario event 条件は enum を
# 持たないが同じ文字列表現を使うため、ここで同じ表へ合流させる。
_CONDITION_READ_NAMESPACES: Mapping[str, str] = {
    "OBJECT_STATE": "object",
    "OBJECT_STATE_INT_AT_LEAST": "object",
    "OBJECT_STATE_TICK_AT_LEAST": "object",
    "OBJECT_STOCK_AT_LEAST": "object",
    "ITEM_INSTANCE_STATE": "item",
    "TARGET_ITEM_INSTANCE_STATE": "item",
    "PLAYER_STATE_IS": "player",
    "TARGET_PLAYER_STATE_IS": "player",
    "FLAG_SET": "flag",
    "FLAG_NOT_SET": "flag",
}

# 状態を読まないと決めた条件。InteractionConditionTypeEnum の新要素がどちらの
# 表にも無ければ網羅テストが落ち、監査対象への追加忘れを黙って通さない。
_NON_STATE_INTERACTION_CONDITIONS = frozenset({
    "ALWAYS",
    "HAS_ITEM",
    "PLAYERS_AT_SPOT",
    "PREPARED_ACTION",
    "PUZZLE_INPUT_MATCH",
    "HAS_ITEMS",
    "PLAYER_NEED_AT_LEAST",
    "PLAYER_GOLD_AT_LEAST",
    "PLAYER_HP_RATIO_BELOW",
    "PLAYER_HP_RATIO_AT_LEAST",
    "TIME_OF_DAY_IS",
    "TIME_OF_DAY_IS_NOT",
    "WEATHER_IS",
    "WEATHER_IS_NOT",
    "TARGET_PLAYER_IS_INCAPACITATED",
    "TARGET_HAS_ITEM",
    "TARGET_HAS_NO_ITEM",
    "SPOT_LIGHTING_IS",
    "SPOT_LIGHTING_IS_NOT",
    "AT_SPOT_IS",
    "AT_SPOT_IS_NOT",
})

# ScenarioEventCondition は enum が無いため、シナリオに実在する非状態条件を
# 明示する。新しい condition_type が JSON に入れば走査テストが落ちる。
_NON_STATE_SCENARIO_EVENT_CONDITIONS = frozenset({
    "ALWAYS",
    "AND",
    "GAME_PHASE_IS",
    "ITEM_REQUIRED",
    "NOT",
    "OR",
    "PLAYER_AT_SPOT",
    "PLAYERS_AT_SPOT",
    "PROBABILITY",
    "SEARCH_COUNT",
    "TICK_AT_LEAST",
    "WEATHER_IS",
})


_EFFECT_WRITE_NAMESPACES: Mapping[InteractionEffectTypeEnum, str] = {
    InteractionEffectTypeEnum.CHANGE_OBJECT_STATE: "object",
    InteractionEffectTypeEnum.INCREMENT_OBJECT_STATE: "object",
    InteractionEffectTypeEnum.RECORD_OBJECT_STATE_TICK: "object",
    InteractionEffectTypeEnum.DEPOSIT_ITEM_TO_OBJECT: "object",
    InteractionEffectTypeEnum.DEPOSIT_GOLD_TO_OBJECT: "object",
    InteractionEffectTypeEnum.CONSUME_OBJECT_STOCK: "object",
    InteractionEffectTypeEnum.WRITE_PLAYER_TEXT: "object",
    InteractionEffectTypeEnum.CHANGE_ITEM_INSTANCE_STATE: "item",
    InteractionEffectTypeEnum.RECORD_ITEM_INSTANCE_STATE_TICK: "item",
    InteractionEffectTypeEnum.CHANGE_TARGET_ITEM_INSTANCE_STATE: "item",
    InteractionEffectTypeEnum.RECORD_TARGET_ITEM_INSTANCE_STATE_TICK: "item",
    InteractionEffectTypeEnum.CHANGE_PLAYER_STATE: "player",
    InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK: "player",
    InteractionEffectTypeEnum.SET_FLAG: "flag",
}

_EFFECT_READ_NAMESPACES: Mapping[InteractionEffectTypeEnum, str] = {
    InteractionEffectTypeEnum.CONSUME_OBJECT_STOCK: "object",
    InteractionEffectTypeEnum.SHOW_PLAYER_TEXT: "object",
    InteractionEffectTypeEnum.RESOLVE_ONGOING_CONDITION: "flag",
}

# 状態を除去するが、参照先を成立させる producer にはならない効果。
_STATE_CLEARING_EFFECTS = frozenset({InteractionEffectTypeEnum.CLEAR_FLAG})

_NON_STATE_EFFECTS = frozenset({
    InteractionEffectTypeEnum.GIVE_ITEM,
    InteractionEffectTypeEnum.REMOVE_ITEM,
    InteractionEffectTypeEnum.REVEAL_OBJECT,
    InteractionEffectTypeEnum.REVEAL_SUB_LOCATION,
    InteractionEffectTypeEnum.SHOW_MESSAGE,
    InteractionEffectTypeEnum.SHOW_ROOM_OCCUPANCY,
    InteractionEffectTypeEnum.APPLY_DAMAGE,
    InteractionEffectTypeEnum.APPLY_STATUS_EFFECT,
    InteractionEffectTypeEnum.TELEPORT_ENTITY,
    InteractionEffectTypeEnum.CHANGE_ATMOSPHERE,
    InteractionEffectTypeEnum.COMBINE_ITEMS,
    InteractionEffectTypeEnum.CREATE_CONNECTION,
    InteractionEffectTypeEnum.DESTROY_CONNECTION,
    InteractionEffectTypeEnum.CHANGE_PASSAGE_STATE,
    InteractionEffectTypeEnum.SATISFY_NEED,
    InteractionEffectTypeEnum.GIVE_FROM_LOOT_TABLE,
    InteractionEffectTypeEnum.CALL_MEETING,
})


@dataclass(frozen=True)
class StateReference:
    """状態・フラグを読む位置を、修正可能な経路つきで表す。"""

    namespace: str
    key: str
    path: str


@dataclass(frozen=True)
class ScenarioStateAudit:
    """1シナリオ内の参照と書き手、および孤児参照を保持する。"""

    references: tuple[StateReference, ...]
    written: Mapping[str, frozenset[str]]

    @property
    def orphans(self) -> tuple[StateReference, ...]:
        """同じシナリオ内に書き手が無い参照を返す。"""
        return tuple(
            ref for ref in self.references if ref.key not in self.written[ref.namespace]
        )


def _walk(
    value: Any,
    visit: Callable[[Mapping[str, Any], str], None],
    *,
    path: str = "$",
) -> None:
    """JSON全体を再帰走査し、mappingの位置をvisitへ渡す。"""
    if isinstance(value, Mapping):
        visit(value, path)
        for key, child in value.items():
            _walk(child, visit, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk(child, visit, path=f"{path}[{index}]")


def _mapping_keys(value: Any) -> Iterable[str]:
    """mappingなら文字列キーを返し、それ以外は空にする。"""
    if not isinstance(value, Mapping):
        return ()
    return (key for key in value if isinstance(key, str) and key)


def audit_scenario_state_references(document: Mapping[str, Any]) -> ScenarioStateAudit:
    """1シナリオを走査し、4名前空間の参照と書き手を返す。"""
    written: dict[str, set[str]] = {namespace: set() for namespace in NAMESPACES}
    references: list[StateReference] = []

    def add_reference(namespace: str, key: Any, path: str) -> None:
        if isinstance(key, str) and key:
            references.append(StateReference(namespace, key, path))

    def visit(node: Mapping[str, Any], path: str) -> None:
        condition_type = node.get("condition_type")
        namespace = _CONDITION_READ_NAMESPACES.get(str(condition_type))
        if namespace is not None:
            for key in _mapping_keys(node.get("required_state")):
                add_reference(namespace, key, f"{path}.required_state.{key}")
            add_reference(namespace, node.get("state_key"), f"{path}.state_key")
            if condition_type == "OBJECT_STOCK_AT_LEAST":
                for key in _STOCK_POOL_STATE_KEYS:
                    add_reference("object", key, f"{path}.<engine-stock-key>")
            add_reference(namespace, node.get("flag_name"), f"{path}.flag_name")

        effect_type_raw = node.get("effect_type")
        try:
            effect_type = InteractionEffectTypeEnum[str(effect_type_raw)]
        except KeyError:
            effect_type = None
        parameters = node.get("parameters")
        if not isinstance(parameters, Mapping):
            parameters = {}

        if effect_type is not None:
            write_namespace = _EFFECT_WRITE_NAMESPACES.get(effect_type)
            if write_namespace is not None:
                written[write_namespace].update(_mapping_keys(parameters.get("state_updates")))
                written[write_namespace].update(_mapping_keys(parameters.get("new_state")))
                state_key = parameters.get("state_key")
                if isinstance(state_key, str) and state_key:
                    written[write_namespace].add(state_key)

            if effect_type is InteractionEffectTypeEnum.SET_FLAG:
                flag_name = parameters.get("flag_name")
                if isinstance(flag_name, str) and flag_name:
                    written["flag"].add(flag_name)
            elif effect_type is InteractionEffectTypeEnum.CONSUME_OBJECT_STOCK:
                written["object"].update({"stock", "stock_tick"})
                for key in _STOCK_POOL_STATE_KEYS:
                    add_reference("object", key, f"{path}.<engine-stock-key>")
            elif effect_type is InteractionEffectTypeEnum.WRITE_PLAYER_TEXT:
                written["object"].update(SIGN_HIDDEN_STATE_KEYS)
            elif effect_type is InteractionEffectTypeEnum.SHOW_PLAYER_TEXT:
                add_reference("object", SIGN_TEXT_STATE_KEY, f"{path}.<sign-text>")
                add_reference("object", SIGN_AUTHOR_STATE_KEY, f"{path}.<sign-author>")
            elif effect_type is InteractionEffectTypeEnum.RESOLVE_ONGOING_CONDITION:
                add_reference("flag", parameters.get("flag"), f"{path}.parameters.flag")

        # objectの付随宣言。初期state自体は構造上のspots配下から後で収集する。
        if "object_type" in node:
            for key in node.get("hidden_state_keys") or ():
                add_reference("object", key, f"{path}.hidden_state_keys")

        # reactive object bindingは条件成立・不成立時にobject stateを書く。
        for field_name in ("on_true_state_updates", "on_false_state_updates"):
            written["object"].update(_mapping_keys(node.get(field_name)))

        # state_display ruleはobject stateを読み、unless_flag_set は解決
        # フラグを読む。時限規則も監査から落とさない。
        if "text" in node and (
            "value" in node or "at_least" in node or "within_ticks" in node
        ):
            add_reference("object", node.get("key"), f"{path}.key")
            add_reference(
                "flag",
                node.get("unless_flag_set"),
                f"{path}.unless_flag_set",
            )

        # description variantのrequired_stateは、そのobjectのstateを読む。
        if "description" in node and condition_type is None and "type" not in node:
            for key in _mapping_keys(node.get("required_state")):
                add_reference("object", key, f"{path}.required_state.{key}")

        # distant cueのsource.kind=object_stateは対象objectのstateを読む。
        if node.get("kind") == "object_state":
            add_reference("object", node.get("state_key"), f"{path}.state_key")

        # description variant等が読むworld flag。
        add_reference("flag", node.get("required_flag"), f"{path}.required_flag")

        # game_end_conditionsはcondition_typeでなくtypeを使う。
        if node.get("type") == "FLAG_SET":
            add_reference("flag", node.get("target_flag"), f"{path}.target_flag")
        if node.get("type") == "FLAGS_SET_AT_LEAST":
            for index, flag in enumerate(node.get("required_flags") or ()):
                add_reference("flag", flag, f"{path}.required_flags[{index}]")
        if node.get("type") == "SURVIVING_PLAYERS_WITH_STATE_AT_MOST":
            for key in _mapping_keys(node.get("required_state")):
                add_reference("player", key, f"{path}.required_state.{key}")
        if node.get("type") == "SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE":
            for field_name in ("required_state", "comparison_state"):
                for key in _mapping_keys(node.get(field_name)):
                    add_reference("player", key, f"{path}.{field_name}.{key}")

    _walk(document, visit)

    # object初期状態はobject_typeという任意フィールドでなく、spots配下の構造から
    # 収集する。新しいobjectがobject_typeを省略しても監査から外れない。
    for spot in document.get("spots") or ():
        if not isinstance(spot, Mapping):
            continue
        interior = spot.get("interior")
        if not isinstance(interior, Mapping):
            continue
        for obj in interior.get("objects") or ():
            if isinstance(obj, Mapping):
                written["object"].update(_mapping_keys(obj.get("state")))

    for player in document.get("players") or ():
        if not isinstance(player, Mapping):
            continue
        written["player"].update(_mapping_keys(player.get("initial_state")))
        # item instanceの初期状態はitem_specsではなく、各playerのinitial_itemsにある。
        for item in player.get("initial_items") or ():
            if isinstance(item, Mapping):
                written["item"].update(_mapping_keys(item.get("state")))

    initial_flags = document.get("initial_flags")
    if isinstance(initial_flags, Mapping):
        written["flag"].update(str(key) for key in initial_flags)
    elif isinstance(initial_flags, list):
        written["flag"].update(
            flag for flag in initial_flags if isinstance(flag, str) and flag
        )

    return ScenarioStateAudit(
        references=tuple(references),
        written={key: frozenset(value) for key, value in written.items()},
    )


def _load_raw_scenarios() -> list[tuple[Path, Mapping[str, Any]]]:
    """実験用と試験用のシナリオJSONを手動列挙せずに全件読む。"""
    loaded: list[tuple[Path, Mapping[str, Any]]] = []
    for directory in (SCENARIO_DIR, FIXTURE_SCENARIO_DIR):
        for path in sorted(directory.glob("*.json")):
            with open(path, encoding="utf-8") as file:
                loaded.append((path, json.load(file)))
    return loaded


def _format_orphans(path: Path, audit: ScenarioStateAudit) -> str:
    """孤児参照をファイル・名前空間・JSON経路つきで表示する。"""
    return "\n".join(
        f"{path.name}: [{ref.namespace}] {ref.key!r} at {ref.path}"
        for ref in audit.orphans
    )


class TestAllScenarioStateReferencesHaveWriters:
    """全シナリオの状態・フラグ参照が、同じ世界内の書き手に接続されている。"""

    def test_every_reference_has_a_writer_in_the_same_scenario(self) -> None:
        """孤児参照を許すと条件が永久に成立しないため、読み込み前の監査で落とす。"""
        scenarios = _load_raw_scenarios()
        assert scenarios, "監査対象のシナリオJSONが1本も見つかりません"

        violations: list[str] = []
        reference_counts = {namespace: 0 for namespace in NAMESPACES}
        for path, document in scenarios:
            audit = audit_scenario_state_references(document)
            for reference in audit.references:
                reference_counts[reference.namespace] += 1
            if audit.orphans:
                violations.append(_format_orphans(path, audit))

        assert all(reference_counts.values()), (
            "監査が空振りしています: "
            + ", ".join(f"{key}={value}" for key, value in reference_counts.items())
        )
        assert not violations, "\n".join(violations)

    def test_every_interaction_condition_type_is_classified(self) -> None:
        """新しいinteraction条件は、状態参照か非状態条件かを必ず宣言する。"""
        known = {condition.value for condition in InteractionConditionTypeEnum}
        classified = (
            set(_CONDITION_READ_NAMESPACES) & known
        ) | set(_NON_STATE_INTERACTION_CONDITIONS)
        assert classified == known, (
            f"未分類={sorted(known - classified)}, 廃止済み={sorted(classified - known)}"
        )

    def test_every_effect_type_is_classified(self) -> None:
        """新しい効果は、状態の読み書きか非状態効果かを必ず宣言する。"""
        classified = (
            set(_EFFECT_WRITE_NAMESPACES)
            | set(_EFFECT_READ_NAMESPACES)
            | set(_STATE_CLEARING_EFFECTS)
            | set(_NON_STATE_EFFECTS)
        )
        known = set(InteractionEffectTypeEnum)
        assert classified == known, (
            "未分類="
            f"{sorted(effect.value for effect in known - classified)}, "
            "廃止済み="
            f"{sorted(effect.value for effect in classified - known)}"
        )

    def test_every_scenario_condition_type_in_json_is_classified(self) -> None:
        """enum外のscenario event条件も、JSONへ現れた時点で監査上の分類を要求する。"""
        observed: set[str] = set()

        def collect(node: Mapping[str, Any], _path: str) -> None:
            value = node.get("condition_type")
            if isinstance(value, str):
                observed.add(value)

        for _path, document in _load_raw_scenarios():
            _walk(document, collect)

        classified = (
            set(_CONDITION_READ_NAMESPACES)
            | set(_NON_STATE_INTERACTION_CONDITIONS)
            | set(_NON_STATE_SCENARIO_EVENT_CONDITIONS)
        )
        assert observed
        assert not observed - classified, f"監査上未分類の条件: {sorted(observed - classified)}"

    def test_every_state_dictionary_location_is_classified(self) -> None:
        """新しいstate配置がJSONに増えたら、注意力に頼らず名前空間未分類として落とす。"""
        violations: list[str] = []
        classified_count = 0

        for path, document in _load_raw_scenarios():
            classified_ids: set[int] = set()

            for spot in document.get("spots") or ():
                if not isinstance(spot, Mapping):
                    continue
                interior = spot.get("interior")
                if not isinstance(interior, Mapping):
                    continue
                for obj in interior.get("objects") or ():
                    if isinstance(obj, Mapping) and isinstance(obj.get("state"), Mapping):
                        classified_ids.add(id(obj["state"]))

            for player in document.get("players") or ():
                if not isinstance(player, Mapping):
                    continue
                if isinstance(player.get("initial_state"), Mapping):
                    classified_ids.add(id(player["initial_state"]))
                for item in player.get("initial_items") or ():
                    if isinstance(item, Mapping) and isinstance(item.get("state"), Mapping):
                        classified_ids.add(id(item["state"]))

            seen_ids: dict[int, str] = {}

            def collect_state_dicts(node: Mapping[str, Any], node_path: str) -> None:
                for field_name in ("state", "initial_state"):
                    value = node.get(field_name)
                    if isinstance(value, Mapping):
                        seen_ids[id(value)] = f"{node_path}.{field_name}"

            _walk(document, collect_state_dicts)
            classified_count += len(classified_ids)
            for state_id, state_path in seen_ids.items():
                if state_id not in classified_ids:
                    violations.append(f"{path.name}: 未分類のstate辞書 at {state_path}")

        assert classified_count > 0, "state辞書の分類が空振りしています"
        assert not violations, "\n".join(violations)


class TestStateReferenceAuditMutationFixtures:
    """4名前空間の書き手を壊すと、監査helperが孤児として検出する。"""

    def test_object_state_reference_without_writer_is_reported(self) -> None:
        """object stateのtypoは、同じキーの書き手が無ければ孤児になる。"""
        document = {
            "spots": [{"interior": {"objects": [{
                "object_type": "OTHER",
                "state": {"driftwood_stacked": 0},
                "interactions": [{"preconditions": [{
                    "condition_type": "OBJECT_STATE_INT_AT_LEAST",
                    "state_key": "driftwood_stackd",
                }]}],
            }]}}],
        }
        audit = audit_scenario_state_references(document)
        assert [(ref.namespace, ref.key) for ref in audit.orphans] == [
            ("object", "driftwood_stackd")
        ]

    def test_item_state_reference_without_writer_is_reported(self) -> None:
        """item instance stateのtypoは、初期所持品にも更新効果にも無ければ孤児になる。"""
        document = {"condition_type": "ITEM_INSTANCE_STATE", "required_state": {"uesd": False}}
        audit = audit_scenario_state_references(document)
        assert [(ref.namespace, ref.key) for ref in audit.orphans] == [("item", "uesd")]

    def test_player_state_reference_without_writer_is_reported(self) -> None:
        """player stateのtypoは、初期状態にも更新効果にも無ければ孤児になる。"""
        document = {"condition_type": "PLAYER_STATE_IS", "required_state": {"rol": "crew"}}
        audit = audit_scenario_state_references(document)
        assert [(ref.namespace, ref.key) for ref in audit.orphans] == [("player", "rol")]

    def test_comparison_state_reference_without_writer_is_reported(self) -> None:
        """生存人数比較の右辺にある player state の誤記も孤児として報告する。"""
        document = {
            "game_end_conditions": {
                "lose": [
                    {
                        "type": "SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE",
                        "required_state": {"role": "crew"},
                        "comparison_state": {"rol": "keeper"},
                    }
                ]
            },
            "players": [{"initial_state": {"role": "crew"}}],
        }

        audit = audit_scenario_state_references(document)

        assert [(ref.namespace, ref.key) for ref in audit.orphans] == [
            ("player", "rol")
        ]

    def test_world_flag_reference_without_writer_is_reported(self) -> None:
        """world flagのtypoは、初期フラグにもSET_FLAGにも無ければ孤児になる。"""
        document = {"condition_type": "FLAG_SET", "flag_name": "signal_fire_lti"}
        audit = audit_scenario_state_references(document)
        assert [(ref.namespace, ref.key) for ref in audit.orphans] == [
            ("flag", "signal_fire_lti")
        ]

    def test_timed_display_completion_flag_without_writer_is_reported(self) -> None:
        """時限表示を消すフラグの誤記も、警告が永久に残る前に孤児として検出する。"""
        document = {
            "effect_type": "RECORD_OBJECT_STATE_TICK",
            "parameters": {"state_key": "frozen_at_tick"},
            "state_display": [
                {
                    "key": "frozen_at_tick",
                    "within_ticks": 8,
                    "unless_flag_set": "fuel_restroed",
                    "text": "燃料停止まであと少し",
                }
            ],
        }

        audit = audit_scenario_state_references(document)

        assert [(ref.namespace, ref.key) for ref in audit.orphans] == [
            ("flag", "fuel_restroed")
        ]

    def test_initial_item_instance_state_is_a_writer(self) -> None:
        """players[].initial_items[].stateは、効果が無くてもitem stateの書き手になる。"""
        document = {
            "players": [{"initial_items": [{"spec": "match", "state": {"used": False}}]}],
            "condition_type": "ITEM_INSTANCE_STATE",
            "required_state": {"used": False},
        }
        assert audit_scenario_state_references(document).orphans == ()

    def test_initial_object_state_is_a_writer(self) -> None:
        """spots[].interior.objects[].stateは、効果が無くてもobject stateの書き手になる。"""
        document = {
            "spots": [{"interior": {"objects": [{
                "state": {"stock_capacity": 3},
                "interactions": [{"preconditions": [{
                    "condition_type": "OBJECT_STATE_INT_AT_LEAST",
                    "state_key": "stock_capacity",
                }]}],
            }]}}],
        }
        assert audit_scenario_state_references(document).orphans == ()

    def test_initial_player_state_is_a_writer(self) -> None:
        """players[].initial_stateは、効果が無くてもplayer stateの書き手になる。"""
        document = {
            "players": [{"initial_state": {"role": "crew"}}],
            "condition_type": "PLAYER_STATE_IS",
            "required_state": {"role": "crew"},
        }
        assert audit_scenario_state_references(document).orphans == ()

    def test_initial_flag_is_a_writer(self) -> None:
        """initial_flagsは、SET_FLAGが無くてもworld flagの書き手になる。"""
        document = {
            "initial_flags": ["signal_fire_lit"],
            "condition_type": "FLAG_SET",
            "flag_name": "signal_fire_lit",
        }
        assert audit_scenario_state_references(document).orphans == ()

    def test_each_state_writing_effect_contributes_its_declared_key(self) -> None:
        """状態を書く全effectは、実際のparameter規約から対応する書き手を作る。"""
        fixtures = (
            ("CHANGE_OBJECT_STATE", {"state_updates": {"object_changed": True}}, "object", "object_changed"),
            ("INCREMENT_OBJECT_STATE", {"state_key": "object_count"}, "object", "object_count"),
            ("RECORD_OBJECT_STATE_TICK", {"state_key": "object_tick"}, "object", "object_tick"),
            ("DEPOSIT_ITEM_TO_OBJECT", {"state_key": "object_deposit"}, "object", "object_deposit"),
            ("DEPOSIT_GOLD_TO_OBJECT", {"state_key": "object_gold"}, "object", "object_gold"),
            ("CONSUME_OBJECT_STOCK", {}, "object", "stock"),
            ("WRITE_PLAYER_TEXT", {}, "object", SIGN_TEXT_STATE_KEY),
            ("CHANGE_ITEM_INSTANCE_STATE", {"state_updates": {"item_changed": True}}, "item", "item_changed"),
            ("RECORD_ITEM_INSTANCE_STATE_TICK", {"state_key": "item_tick"}, "item", "item_tick"),
            ("CHANGE_TARGET_ITEM_INSTANCE_STATE", {"state_updates": {"target_item_changed": True}}, "item", "target_item_changed"),
            ("RECORD_TARGET_ITEM_INSTANCE_STATE_TICK", {"state_key": "target_item_tick"}, "item", "target_item_tick"),
            ("CHANGE_PLAYER_STATE", {"state_updates": {"player_changed": True}}, "player", "player_changed"),
            ("RECORD_PLAYER_STATE_TICK", {"state_key": "player_tick"}, "player", "player_tick"),
            ("SET_FLAG", {"flag_name": "effect_flag"}, "flag", "effect_flag"),
        )

        assert {effect_type for effect_type, *_rest in fixtures} == {
            effect.value for effect in _EFFECT_WRITE_NAMESPACES
        }
        for effect_type, parameters, namespace, key in fixtures:
            audit = audit_scenario_state_references({
                "effect_type": effect_type,
                "parameters": parameters,
            })
            assert key in audit.written[namespace], effect_type

    def test_distant_cue_state_key_without_writer_is_reported(self) -> None:
        """遠景cueのstate_keyも、interaction条件と同じobject state参照として監査する。"""
        document = {
            "distant_cues": [{
                "source": {"kind": "object_state", "state_key": "signal_fire_lti"},
            }],
        }
        audit = audit_scenario_state_references(document)
        assert [(ref.namespace, ref.key) for ref in audit.orphans] == [
            ("object", "signal_fire_lti")
        ]

    def test_player_outcome_rule_flag_without_writer_is_reported(self) -> None:
        """個人結果規則のFLAG_SETも、SET_FLAGの無いtypoなら孤児として扱う。"""
        document = {
            "player_outcome_rules": [{
                "player_conditions": [{
                    "condition_type": "FLAG_SET",
                    "flag_name": "signal_fire_lti",
                }],
            }],
        }
        audit = audit_scenario_state_references(document)
        assert [(ref.namespace, ref.key) for ref in audit.orphans] == [
            ("flag", "signal_fire_lti")
        ]
