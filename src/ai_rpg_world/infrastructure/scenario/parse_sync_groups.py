"""synchronized action groups の読み取り。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
)
from ai_rpg_world.domain.world_graph.value_object.synchronized_action_group import SynchronizedActionGroup
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError
from ai_rpg_world.infrastructure.scenario.parse_helpers import declared_action_names
from ai_rpg_world.infrastructure.scenario.parse_interaction_effects import (
    parse_interaction_effect,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper

def reject_unreachable_synchronized_action_names(
    groups: Tuple[SynchronizedActionGroup, ...],
    raw: Dict[str, Any],
) -> None:
    """`required_action_names` が到達可能な名前を指していることを確かめる。

    ## なぜ読み込み時に落とすか (#853)

    改称前、`sync_levers_demo` は `required_action_ids` に
    `["pull_lever_left", "pull_lever_right"]` と書いていたのに、レバーの
    `interactions` は**両方とも空配列**だった。つまり **その名前はプロンプトの
    どこにも現れない**。エージェントは表示されていないものを指定するしかなく、
    推測した名前は (改称前の handler では) `success=True` で返っていた。

    「宣言はあるが到達できない」は実行時には静かに失敗する。#843 で終了条件の
    必須フィールド欠落を読み込み時に落としたのと同じ発想で、**宣言した時点で**
    落とす。

    ## 何を到達可能とみなすか

    - spot の `interior.objects[].interactions[].action_name`
    - connection の `interactions[].action_name`
    - シナリオ直下の `player_interactions[].action_name`

    いずれもプロンプトの「使える操作」に出る経路を持つ。前提条件で出ない場合は
    あるが、**宣言が存在しないことと、条件で今出ていないことは別**なので、ここでは
    宣言の有無だけを見る。
    """
    if not groups:
        return
    declared = declared_action_names(raw)
    unreachable: List[str] = []
    for group in groups:
        for name in group.required_action_names:
            if name not in declared:
                unreachable.append(f"{group.group_id}.{name}")
    if unreachable:
        raise ScenarioLoadError(
            "synchronized_action_groups の required_action_names に、"
            "どこにも宣言されていない操作名があります: "
            f"{unreachable}。"
            " interactions[].action_name として宣言しないと、"
            "プロンプトに表示されずエージェントが指定できません。"
            f" 宣言済みの名前: {sorted(declared)}"
        )

def parse_synchronized_action_groups(
    raw: Any,
    mapper: ScenarioIdMapper,
    *,
    player_attribute_specs: PlayerAttributeSpecs,
) -> Tuple[SynchronizedActionGroup, ...]:
    """`synchronized_action_groups` を SynchronizedActionGroup 値オブジェクト
    の tuple にパースする。

    スキーマ:
      [
        {
          "id": "vault_unlock",
          "required_action_names": ["pull_lever_left", "pull_lever_right"],
          "window_ticks": 2,
          "on_complete": [<InteractionEffect>...],
          "on_timeout": [<InteractionEffect>...],
          "on_prepare_observation_message": "..."
        }
      ]
    """
    if not isinstance(raw, list):
        return ()
    out: list[SynchronizedActionGroup] = []
    for i, g in enumerate(raw):
        if not isinstance(g, dict):
            raise ScenarioLoadError(
                f"synchronized_action_groups[{i}] must be an object"
            )
        gid = g.get("id")
        if not gid:
            raise ScenarioLoadError(
                f"synchronized_action_groups[{i}].id is required"
            )
        # #853: 旧キー `required_action_ids` を黙って無視しない。
        #
        # 名前で指す方針 (design_decisions #3) に寄せて改称した。知らないキーを
        # 無視すると「書いたのに効かない」= 静かな失敗になるので、明示的に落とす。
        if "required_action_ids" in g:
            raise ScenarioLoadError(
                f"synchronized_action_groups[{i}].required_action_ids は"
                f" required_action_names へ改称されました。値は"
                f" interactions[].action_name として宣言済みの名前を書きます"
                f" (内部 ID ではありません)。"
            )
        req = g.get("required_action_names", [])
        if not isinstance(req, list):
            raise ScenarioLoadError(
                f"synchronized_action_groups[{i}].required_action_names must be a list"
            )
        on_complete = tuple(
            parse_interaction_effect(
                e,
                mapper,
                actor_context="synchronized_action_group",
                player_attribute_specs=player_attribute_specs,
            )
            for e in g.get("on_complete", [])
        )
        on_timeout = tuple(
            parse_interaction_effect(
                e,
                mapper,
                actor_context="synchronized_action_group",
                player_attribute_specs=player_attribute_specs,
            )
            for e in g.get("on_timeout", [])
        )
        out.append(
            SynchronizedActionGroup(
                group_id=str(gid),
                required_action_names=tuple(str(x) for x in req),
                window_ticks=int(g.get("window_ticks", 1)),
                on_complete=on_complete,
                on_timeout=on_timeout,
                on_prepare_observation_message=g.get("on_prepare_observation_message"),
            )
        )
    return tuple(out)
