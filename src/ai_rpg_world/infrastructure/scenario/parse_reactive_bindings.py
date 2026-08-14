"""reactive passage / object bindings の読み取り。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.reactive_object_state_binding import ReactiveObjectStateBinding
from ai_rpg_world.domain.world_graph.value_object.reactive_passage_binding import ReactivePassageBinding
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.parse_helpers import parse_bool
from ai_rpg_world.infrastructure.scenario.parse_scenario_events import (
    parse_scenario_event_condition,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper
from ai_rpg_world.infrastructure.scenario.validate_features import (
    SILENT_REACTIVE_OBJECT_BINDING_WARNING,
)

def parse_reactive_passage_bindings( raw: Dict[str, Any], mapper: ScenarioIdMapper,
) -> Tuple[ReactivePassageBinding, ...]:
    """`reactive_bindings.passages` を Passage 用 binding にパースする。

    スキーマ:
      "reactive_bindings": {
        "passages": [
          {
            "target": "<connection_string_id>",
            "predicate": <ScenarioEventCondition tree>,
            "on_true_state": "OPEN",
            "on_false_state": "LOCKED"
          }
        ]
      }
    """
    if not isinstance(raw, dict):
        return ()
    passages_raw = raw.get("passages", [])
    if not isinstance(passages_raw, list):
        raise ScenarioLoadError(
            f"reactive_bindings.passages must be a list "
            f"(got {type(passages_raw).__name__})"
        )
    bindings: list[ReactivePassageBinding] = []
    for i, b in enumerate(passages_raw):
        target = b.get("target")
        if not target:
            raise ScenarioLoadError(
                f"reactive_bindings.passages[{i}].target is required"
            )
        cid = mapper.get_int("connection", target)
        predicate_raw = b.get("predicate")
        if not isinstance(predicate_raw, dict):
            raise ScenarioLoadError(
                f"reactive_bindings.passages[{i}].predicate must be an object"
            )
        predicate = parse_scenario_event_condition(
            predicate_raw, mapper,
            path=f"reactive_bindings.passages[{i}].predicate",
        )
        on_true = b.get("on_true_state")
        on_false = b.get("on_false_state")
        if not on_true:
            raise ScenarioLoadError(
                f"reactive_bindings.passages[{i}].on_true_state is required"
            )
        if not on_false:
            raise ScenarioLoadError(
                f"reactive_bindings.passages[{i}].on_false_state is required"
            )
        apply_to_reverse = parse_bool(
            b.get("apply_to_reverse", True),
            path=f"reactive_bindings.passages[{i}].apply_to_reverse",
        )
        bindings.append(
            ReactivePassageBinding(
                target_connection_id=ConnectionId.create(cid),
                predicate=predicate,
                on_true_state=str(on_true),
                on_false_state=str(on_false),
            )
        )
        # bidirectional 接続には自動で逆方向 binding を生やす（既定）。
        # 一方通行で良い場合は apply_to_reverse=false を明示する。
        reverse_str = f"{target}__reverse"
        if apply_to_reverse and mapper.contains("connection", reverse_str):
            rev_cid = mapper.get_int("connection", reverse_str)
            bindings.append(
                ReactivePassageBinding(
                    target_connection_id=ConnectionId.create(rev_cid),
                    predicate=predicate,
                    on_true_state=str(on_true),
                    on_false_state=str(on_false),
                )
            )
    return tuple(bindings)

def parse_reactive_object_state_bindings( raw: Dict[str, Any], mapper: ScenarioIdMapper,
) -> Tuple[ReactiveObjectStateBinding, ...]:
    """`reactive_bindings.objects` を ReactiveObjectStateBinding にパース。

    スキーマ:
      "reactive_bindings": {
        "objects": [
          {
            "target": "<object_string_id>",
            "predicate": <ScenarioEventCondition tree>,
            "on_true_state_updates": {"k": v, ...},
            "on_false_state_updates": {"k": v, ...}
          }
        ]
      }
    """
    if not isinstance(raw, dict):
        return ()
    objects_raw = raw.get("objects", [])
    if not isinstance(objects_raw, list):
        raise ScenarioLoadError(
            f"reactive_bindings.objects must be a list "
            f"(got {type(objects_raw).__name__})"
        )
    out: list[ReactiveObjectStateBinding] = []
    for i, b in enumerate(objects_raw):
        target = b.get("target")
        if not target:
            raise ScenarioLoadError(
                f"reactive_bindings.objects[{i}].target is required"
            )
        oid = mapper.get_int("object", target)
        predicate_raw = b.get("predicate")
        if not isinstance(predicate_raw, dict):
            raise ScenarioLoadError(
                f"reactive_bindings.objects[{i}].predicate must be an object"
            )
        predicate = parse_scenario_event_condition(
            predicate_raw, mapper,
            path=f"reactive_bindings.objects[{i}].predicate",
        )
        on_true = b.get("on_true_state_updates", {})
        on_false = b.get("on_false_state_updates", {})
        if not isinstance(on_true, dict) or not isinstance(on_false, dict):
            raise ScenarioLoadError(
                f"reactive_bindings.objects[{i}].on_true/false_state_updates must be objects"
            )
        # 著者が宣言した観測 narrative (オプショナル)。flip 方向ごとに別文。
        # 例: 採取資源 cooldown reset (false→true) には narrative_on_true=
        # "ベリーの茂みに新しい実が生っている" を渡す。
        narrative_on_true = b.get("narrative_on_true")
        narrative_on_false = b.get("narrative_on_false")
        if narrative_on_true is not None and not isinstance(narrative_on_true, str):
            raise ScenarioLoadError(
                f"reactive_bindings.objects[{i}].narrative_on_true must be a string"
            )
        if narrative_on_false is not None and not isinstance(narrative_on_false, str):
            raise ScenarioLoadError(
                f"reactive_bindings.objects[{i}].narrative_on_false must be a string"
            )
        # #383: どちらの向きにも narrative が無い binding は、状態だけ静かに
        # 変わって誰にも観測されない。formatter は narrative 無しなら観測を
        # 出さない (#372) ので、**著者の書き忘れと意図的な無音が区別できない**。
        #
        # 「向きごとに無ければ警告」にはしない。実測するとその形は 59 件警告し、
        # うち 48 件が survival_island_v2 / v2_short / v3_coop / v4_coop から出る。
        # それらは全部 on_false (= 自分の採取で資源が枯れた) で、interact の
        # 結果として本人に伝わっているので narrative を書かないのが正しい。
        # ノイズを出すと人が警告を無視するようになり、検出器が死ぬ。
        #
        # 片方でも書いてあれば著者はこの仕組みを知っていて、もう片方を意図的に
        # 省いたと読める。**書き忘れの信号は「どこにも観測が無い」。**
        #
        # 空文字は「意図的な無音」の明示とみなして警告しない (`is None` で
        # 判定する)。formatter 上の挙動は narrative 無しと同じ。
        #
        # 状態更新の有無は見ない。ReactiveObjectStateBinding が「どちらかの
        # 向きに状態更新がある」ことを不変条件として持つので、ここに来る
        # binding は必ず何かを変える (テストでこの前提を固定している)。
        if narrative_on_true is None and narrative_on_false is None:
            logging.getLogger(__name__).warning(
                "[%s] reactive_bindings.objects[%d] target=%s は状態を変えるが "
                "narrative_on_true / narrative_on_false のどちらも無いため、"
                "変化が誰にも観測されない。意図的な無音なら "
                'narrative_on_true="" を明示してください。',
                SILENT_REACTIVE_OBJECT_BINDING_WARNING, i, target,
            )
        out.append(
            ReactiveObjectStateBinding(
                target_object_id=SpotObjectId.create(oid),
                predicate=predicate,
                on_true_state_updates=tuple((k, v) for k, v in on_true.items()),
                on_false_state_updates=tuple((k, v) for k, v in on_false.items()),
                narrative_on_true=narrative_on_true,
                narrative_on_false=narrative_on_false,
            )
        )
    return tuple(out)
