"""実行時候補から、再実験可能な動的引数候補表を組み立てる。"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from ai_rpg_world.application.llm.contracts.dtos import (
    InventoryToolRuntimeTargetDto,
    MerchantToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    normalize_action_name_candidates,
)
from ai_rpg_world.application.llm.services._argument_resolvers.target_lookup import (
    label_forms,
)

# runtime_context のラベルを require_target_type で直接引くツール。値には
# display_name ではなく、実際に resolver が受理する label を載せる。
_EXACT_LABEL_SPECS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "world_inspect_item": (("inventory_item_label", ("inventory_item",)),),
    "world_inspect_target": (("target_label", ("npc", "monster", "chest", "door", "resource", "object")),),
    "world_interact": (("target_label", ("npc", "chest", "door", "object")),),
    "harvest_start": (("target_label", ("resource",)),),
    "harvest_cancel": (("target_label", ("active_harvest", "resource")),),
    "world_change_attention": (("level_label", ("attention_level",)),),
    "conversation_advance": (
        ("target_label", ("npc",)),
        ("choice_label", ("conversation_choice",)),
    ),
    "world_place_object": (("inventory_item_label", ("inventory_item",)),),
    "world_drop_item": (("inventory_item_label", ("inventory_item",)),),
    "world_chest_store": (
        ("target_label", ("chest",)),
        ("inventory_item_label", ("inventory_item",)),
    ),
    "world_chest_take": (
        ("target_label", ("chest",)),
        ("chest_item_label", ("chest_item",)),
    ),
    "move_to_destination": (("destination_label", ("destination",)),),
    "world_pursue_target": (("target_label", ("player", "npc", "monster")),),
    "combat_use_skill": (
        ("skill_label", ("skill",)),
        ("target_label", ("player", "npc", "monster")),
    ),
    "skill_equip": (
        ("skill_label", ("skill_equip_candidate",)),
        ("slot_label", ("skill_equip_slot",)),
    ),
    "skill_accept_proposal": (("proposal_label", ("skill_proposal",)),),
    "skill_reject_proposal": (("proposal_label", ("skill_proposal",)),),
    "skill_activate_awakened_mode": (("awakened_action_label", ("awakened_action",)),),
    "quest_accept": (("quest_label", ("quest",)),),
    "quest_cancel": (("quest_label", ("quest",)),),
    "quest_approve": (("quest_label", ("quest",)),),
    "quest_issue": (("guild_label", ("guild",)),),
    "guild_add_member": (
        ("guild_label", ("guild",)),
        ("target_player_label", ("player", "spot_graph_player")),
    ),
    "guild_change_role": (
        ("guild_label", ("guild",)),
        ("target_member_label", ("player", "spot_graph_player")),
    ),
    "guild_disband": (("guild_label", ("guild",)),),
    "guild_leave": (("guild_label", ("guild",)),),
    "guild_deposit_bank": (("guild_label", ("guild",)),),
    "guild_withdraw_bank": (("guild_label", ("guild",)),),
    "shop_purchase": (
        ("shop_label", ("shop",)),
        ("listing_label", ("shop_listing",)),
    ),
    "shop_list_item": (
        ("shop_label", ("shop",)),
        ("inventory_item_label", ("inventory_item",)),
    ),
    "shop_unlist_item": (
        ("shop_label", ("shop",)),
        ("listing_label", ("shop_listing",)),
    ),
    "speak": (("target_label", ("player",)),),
}


# TargetIndex が display_name と内部 label の両方を受理するツール。
_DISPLAY_NAME_SPECS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "travel_to": (("destination_label", ("spot_graph_destination",)),),
    "set_sub_location": (("sub_location_label", ("spot_graph_sub_location",)),),
    "use_item": (("item_label", ("inventory_item",)),),
    "drop_item": (("item_label", ("inventory_item",)),),
    "pickup_item": (("ground_item_label", ("ground_item",)),),
    "attack": (("target_label", ("spot_graph_monster",)),),
    "tend_to_player": (("target_player_label", ("spot_graph_player",)),),
    "vote": (("target_player_label", ("spot_graph_player",)),),
    "report_body": (("target_player_label", ("spot_graph_player",)),),
    "trade_offer": (("target_player_label", ("spot_graph_player",)),),
    "trade_accept": (("offerer_player_label", ("spot_graph_player",)),),
    "trade_decline": (("offerer_player_label", ("spot_graph_player",)),),
    "speak": (("target_label", ("spot_graph_player",)),),
}


_OPTIONAL_ARGUMENTS = {
    ("combat_use_skill", "target_label"),
    ("conversation_advance", "choice_label"),
    ("quest_issue", "guild_label"),
    ("speak", "target_label"),
    ("trade_accept", "offerer_player_label"),
    ("trade_decline", "offerer_player_label"),
    ("trade_offer", "gives.items[].item_label"),
    ("vote", "target_player_label"),
    ("buy_item", "merchant_label"),
    ("sell_item", "merchant_label"),
}


def _requirement_metadata(tool: str, argument: str) -> dict[str, Any]:
    """保存データだけで任意・条件付き・代替引数を識別できるようにする。"""
    if (tool, argument) == ("speak", "target_label"):
        return {"required": False, "required_when": "channel=whisper"}
    if tool in {"shop_purchase", "shop_unlist_item"} and argument == "listing_label":
        return {"required": False, "alternative": "listing_id"}
    if tool in {"shop_purchase", "shop_unlist_item"} and argument == "shop_label":
        return {"required": False, "required_when": "listing_id is specified"}
    return {"required": (tool, argument) not in _OPTIONAL_ARGUMENTS}


def _names(targets: Iterable[Any]) -> list[str]:
    """内部 shadow を除き、重複しない表示名を出現順で返す。"""
    result: list[str] = []
    for target in targets:
        label = str(getattr(target, "label", ""))
        name = str(getattr(target, "display_name", "")).strip()
        if label.startswith("__") or not name or name in result:
            continue
        result.append(name)
    return result


def _entry(tool: str, argument: str, values: list[str], **extra: Any) -> dict[str, Any]:
    return {"tool": tool, "argument": argument, **extra, "values": values}


def _target_entry(
    tool: str,
    argument: str,
    candidates: list[Any],
    *,
    use_display_names: bool,
) -> dict[str, Any] | None:
    visible = [target for target in candidates if not str(target.label).startswith("__")]
    if not visible:
        return None
    if not use_display_names:
        values = [str(target.label) for target in visible]
        return _entry(
            tool,
            argument,
            list(dict.fromkeys(values)),
            match="exact",
            **_requirement_metadata(tool, argument),
        )

    name_counts: dict[str, int] = {}
    for target in visible:
        name = str(target.display_name).strip()
        if name:
            name_counts[name] = name_counts.get(name, 0) + 1
    values = []
    accepted: list[str] = []
    for target in visible:
        label = str(target.label)
        name = str(target.display_name).strip()
        canonical = name if name and name_counts[name] == 1 else label
        if canonical and canonical not in values:
            values.append(canonical)
        for form in (label, name if name_counts.get(name) == 1 else ""):
            if form and form not in accepted:
                accepted.append(form)
    return _entry(
        tool,
        argument,
        values,
        match="label",
        accepted_values=accepted,
        **_requirement_metadata(tool, argument),
    )


def build_dynamic_argument_candidate_snapshot(
    runtime_context: ToolRuntimeContextDto,
    exposed_tools: set[str],
) -> dict[str, Any]:
    """同じ ``tool_runtime_context`` からツール・引数別の候補を作る。

    空の候補は「指定できる値がある」と誤読させないため載せない。候補表をまだ
    モデルへ見せない基準 run でも、この snapshot は保存して再実験に使う。
    """
    targets = list(runtime_context.targets.values())
    inventory = [
        target
        for target in targets
        if isinstance(target, InventoryToolRuntimeTargetDto) and target.kind == "inventory_item"
    ]
    players = [target for target in targets if isinstance(target, PlayerToolRuntimeTargetDto)]
    entries: list[dict[str, Any]] = []

    if "interact" in exposed_tools:
        # interact の解決条件そのものを使う。spot graph の物体は、行為者に
        # 伏せた操作を持てる都合で専用 subclass ではなく基底 DTO として登録
        # される経路がある。型の列挙で絞ると、実行できる偽装作業・襲撃・
        # 通気口などが候補表から静かに消える。
        interactive = [target for target in targets if target.available_interactions]
        if _names(interactive):
            target_entry = _target_entry("interact", "target_label", interactive, use_display_names=True)
            if target_entry is not None:
                entries.append(target_entry)
        interactive_name_counts: dict[str, int] = {}
        for interactive_target in interactive:
            name = str(interactive_target.display_name).strip()
            if name:
                interactive_name_counts[name] = interactive_name_counts.get(name, 0) + 1
        for target in interactive:
            actions = list(dict.fromkeys(target.available_interactions))
            if actions:
                display_name = str(target.display_name).strip()
                target_values = [str(target.label)]
                if display_name and interactive_name_counts.get(display_name) == 1:
                    target_values.append(display_name)
                entries.append(
                    _entry(
                        "interact",
                        "action_name",
                        actions,
                        target=(display_name if interactive_name_counts.get(display_name) == 1 else str(target.label)),
                        target_accepted_values=target_values,
                        match="action_name",
                        required=True,
                    )
                )

    by_kind: dict[str, list[Any]] = {}
    for target in targets:
        by_kind.setdefault(str(target.kind), []).append(target)
    for tool, specs in _DISPLAY_NAME_SPECS.items():
        if tool not in exposed_tools:
            continue
        for argument, kinds in specs:
            candidates = [target for kind in kinds for target in by_kind.get(kind, [])]
            entry = _target_entry(tool, argument, candidates, use_display_names=True)
            if tool == "vote" and argument == "target_player_label" and entry is None:
                entry = _entry(
                    tool,
                    argument,
                    [""],
                    match="label",
                    accepted_values=[""],
                    allow_empty=True,
                    **_requirement_metadata(tool, argument),
                )
            if entry is not None:
                if tool == "vote" and argument == "target_player_label":
                    if "" not in entry["values"]:
                        entry["values"].append("")
                    if "" not in entry["accepted_values"]:
                        entry["accepted_values"].append("")
                    entry["allow_empty"] = True
                entries.append(entry)

    for tool, specs in _EXACT_LABEL_SPECS.items():
        if tool not in exposed_tools:
            continue
        for argument, kinds in specs:
            candidates = [target for kind in kinds for target in by_kind.get(kind, [])]
            entry = _target_entry(tool, argument, candidates, use_display_names=False)
            if entry is not None:
                entries.append(entry)

    if "give_item" in exposed_tools:
        if _names(inventory):
            item_entry = _target_entry("give_item", "gives[].item_label", inventory, use_display_names=True)
            if item_entry is not None:
                entries.append(item_entry)
        if _names(players):
            player_entry = _target_entry("give_item", "gives[].target_player_label", players, use_display_names=True)
            if player_entry is not None:
                entries.append(player_entry)

    if "trade_offer" in exposed_tools and inventory:
        item_entry = _target_entry(
            "trade_offer",
            "gives.items[].item_label",
            inventory,
            use_display_names=True,
        )
        if item_entry is not None:
            entries.append(item_entry)

    merchants = [target for target in targets if isinstance(target, MerchantToolRuntimeTargetDto)]
    for tool, offer_attr in (("buy_item", "sells"), ("sell_item", "buys")):
        if tool not in exposed_tools or not merchants:
            continue
        item_names = list(
            dict.fromkeys(offer.item_name for merchant in merchants for offer in getattr(merchant, offer_attr))
        )
        if item_names:
            entries.append(
                _entry(
                    tool,
                    "item_label",
                    item_names,
                    match="label",
                    accepted_values=item_names,
                    **_requirement_metadata(tool, "item_label"),
                )
            )
        merchant_names = _names(merchants)
        if merchant_names:
            entries.append(
                _entry(
                    tool,
                    "merchant_label",
                    merchant_names,
                    match="label",
                    accepted_values=merchant_names,
                    **_requirement_metadata(tool, "merchant_label"),
                )
            )

    return {
        "schema_version": 2,
        "entries": entries,
        "rendered": render_dynamic_argument_candidate_table(entries),
    }


def render_dynamic_argument_candidate_table(
    entries: Iterable[Mapping[str, Any]],
) -> str:
    """保存用の構造化候補を、本番介入で使う日本語表へ変換する。"""
    lines = ["【現在選べる対象引数】"]
    count = 0
    for entry in entries:
        values = [str(value) for value in entry.get("values", []) if value is not None]
        if not values:
            continue
        rendered = ", ".join(json.dumps(value, ensure_ascii=False) for value in values)
        target = entry.get("target")
        suffix = f" ({json.dumps(str(target), ensure_ascii=False)})" if target else ""
        lines.append(f"- {entry['tool']}.{entry['argument']}{suffix}: {rendered}")
        count += 1
    if count == 0:
        return ""
    lines.append("※ 一覧にあることは操作の成功を保証しない。現在の状態や前提条件によって失敗する場合がある。")
    return "\n".join(lines)


_CANDIDATE_TABLE_HEADING = "【現在選べる対象引数】"
_CANDIDATE_LINE = re.compile(
    r'^- (?P<tool>[A-Za-z0-9_]+)\.(?P<argument>[^\s(:]+)'
    r'(?: \((?P<target>"(?:[^"\\]|\\.)*")\))?: (?P<values>.+)$'
)


def parse_dynamic_argument_candidate_table(text: str) -> list[dict[str, Any]]:
    """プロンプト本文から候補表を読み戻し、``tool`` / ``argument`` / ``target`` / ``values`` の列にする。

    でたらめに行動するスタブが、エージェントに見えている候補だけから選ぶために使う。
    表が無ければ空の列を返す。読めない行に当たったら、そこまでで止める。
    """
    lines = text.splitlines()
    try:
        start = lines.index(_CANDIDATE_TABLE_HEADING)
    except ValueError:
        return []
    entries: list[dict[str, Any]] = []
    for line in lines[start + 1 :]:
        match = _CANDIDATE_LINE.match(line)
        if match is None:
            break
        target = match.group("target")
        try:
            values = json.loads(f"[{match.group('values')}]")
            parsed_target = json.loads(target) if target else None
        except json.JSONDecodeError:
            break
        entries.append(
            {
                "tool": match.group("tool"),
                "argument": match.group("argument"),
                "target": parsed_target,
                "values": values,
            }
        )
    return entries


def inject_dynamic_argument_candidate_table(
    prompt: Mapping[str, Any],
    exposed_tools: set[str],
) -> dict[str, Any]:
    """実送信するユーザープロンプトの行動指示直前へ動的候補表を置く。

    ``prompt`` 自体は変更しない。候補が空なら本文を byte 単位で保ちつつ、
    保存・評価用の snapshot だけを返り値へ載せる。
    """
    result = copy.deepcopy(dict(prompt))
    runtime_context = result.get("tool_runtime_context")
    if not isinstance(runtime_context, ToolRuntimeContextDto):
        raise TypeError("prompt.tool_runtime_context must be ToolRuntimeContextDto")
    snapshot = build_dynamic_argument_candidate_snapshot(runtime_context, exposed_tools)
    result["dynamic_argument_candidates"] = snapshot
    table = str(snapshot.get("rendered") or "")
    if not table:
        return result

    instruction = str(result.get("action_instruction") or "")
    if not instruction:
        raise ValueError("candidate table injection requires prompt.action_instruction")
    messages = result.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("candidate table injection requires prompt.messages")
    user_message = messages[-1]
    if not isinstance(user_message, dict) or user_message.get("role") != "user":
        raise ValueError("candidate table injection requires the last message to be user")
    content = str(user_message.get("content") or "")
    if not content.endswith(instruction):
        raise ValueError("candidate table injection requires action instruction at prompt tail")
    body = content[: -len(instruction)].rstrip()
    user_message["content"] = f"{body}\n\n{table}\n\n{instruction}"
    return result


def _argument_values(arguments: Mapping[str, Any], argument: str) -> list[tuple[str, Any]]:
    """``gives.items[].item_label`` を含む候補引数の実値を取り出す。"""
    nodes: list[tuple[str, Any]] = [("", arguments)]
    for part in argument.split("."):
        is_array = part.endswith("[]")
        key = part[:-2] if is_array else part
        next_nodes: list[tuple[str, Any]] = []
        for path, node in nodes:
            if not isinstance(node, Mapping) or key not in node:
                continue
            value = node[key]
            current_path = f"{path}.{key}" if path else key
            if is_array:
                if not isinstance(value, list):
                    next_nodes.append((current_path, value))
                    continue
                next_nodes.extend((f"{current_path}[{index}]", item) for index, item in enumerate(value))
            else:
                next_nodes.append((current_path, value))
        nodes = next_nodes
    return nodes


def _argument_is_required(
    tool_name: str,
    argument: str,
    arguments: Mapping[str, Any],
    entry: Mapping[str, Any],
) -> bool:
    """resolverの条件付き・代替引数契約に合わせて欠落を判定する。"""
    if (tool_name, argument) == ("speak", "target_label"):
        return arguments.get("channel") == "whisper"
    if tool_name in {"shop_purchase", "shop_unlist_item"} and argument == "listing_label":
        return arguments.get("listing_id") is None
    if tool_name in {"shop_purchase", "shop_unlist_item"} and argument == "shop_label":
        return arguments.get("listing_label") is None and arguments.get("listing_id") is not None
    return bool(entry.get("required", True))


def evaluate_dynamic_argument_choice(
    tool_name: str,
    arguments: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """モデル出力を保存時点の候補へ照合し、実行せず形式上の拒否を判定する。"""
    entries = [
        entry for entry in snapshot.get("entries", []) if isinstance(entry, Mapping) and entry.get("tool") == tool_name
    ]
    if not entries:
        return {
            "status": "not_applicable",
            "violations": [],
            "candidate_table_status": "not_applicable",
            "candidate_table_violations": [],
        }

    violations: list[dict[str, Any]] = []
    candidate_table_violations: list[dict[str, Any]] = []

    def check(
        argument: str,
        value: Any,
        allowed: list[str],
        *,
        match: str = "exact",
        accepted_values: list[str] | None = None,
        allow_empty: bool = False,
    ) -> None:
        missing = not isinstance(value, str) or (not value.strip() and not (allow_empty and value == ""))
        if missing:
            violation = {
                "argument": argument,
                "value": value,
                "allowed": allowed,
                "reason": "missing_or_not_string",
            }
            violations.append(violation)
            candidate_table_violations.append(dict(violation))
        elif value not in allowed:
            candidate_table_violations.append(
                {
                    "argument": argument,
                    "value": value,
                    "allowed": allowed,
                    "reason": "not_exactly_in_candidate_table",
                }
            )
        if missing:
            return
        if match == "label" and not any(form in (accepted_values or allowed) for form in label_forms(value)):
            violations.append(
                {
                    "argument": argument,
                    "value": value,
                    "allowed": allowed,
                    "reason": "not_in_candidates",
                }
            )
        elif match == "action_name" and not any(
            candidate in allowed for candidate in normalize_action_name_candidates(value)
        ):
            violations.append(
                {
                    "argument": argument,
                    "value": value,
                    "allowed": allowed,
                    "reason": "not_in_candidates",
                }
            )
        elif match == "exact" and value not in allowed:
            violations.append(
                {
                    "argument": argument,
                    "value": value,
                    "allowed": allowed,
                    "reason": "not_in_candidates",
                }
            )

    if tool_name == "interact":
        target = arguments.get("target_label")
        target_entry = next(
            (entry for entry in entries if entry.get("argument") == "target_label"),
            None,
        )
        if target_entry is not None:
            check(
                "target_label",
                target,
                list(target_entry.get("values", [])),
                match=str(target_entry.get("match", "exact")),
                accepted_values=list(target_entry.get("accepted_values", [])),
                allow_empty=bool(target_entry.get("allow_empty", False)),
            )
        action_entry = next(
            (
                entry
                for entry in entries
                if entry.get("argument") == "action_name"
                and isinstance(target, str)
                and any(
                    form in entry.get("target_accepted_values", [entry.get("target")]) for form in label_forms(target)
                )
            ),
            None,
        )
        check(
            "action_name",
            arguments.get("action_name"),
            list(action_entry.get("values", [])) if action_entry else [],
            match="action_name",
        )
    elif tool_name == "give_item":
        gives = arguments.get("gives")
        if not isinstance(gives, list) or not gives:
            violations.append(
                {
                    "argument": "gives",
                    "value": gives,
                    "allowed": [],
                    "reason": "missing_or_not_array",
                }
            )
        else:
            allowed_by_argument = {str(entry["argument"]): list(entry.get("values", [])) for entry in entries}
            for index, give in enumerate(gives):
                if not isinstance(give, Mapping):
                    violations.append(
                        {
                            "argument": f"gives[{index}]",
                            "value": give,
                            "allowed": [],
                            "reason": "not_object",
                        }
                    )
                    continue
                for name in ("item_label", "target_player_label"):
                    entry = next(
                        (candidate for candidate in entries if candidate.get("argument") == f"gives[].{name}"),
                        {},
                    )
                    check(
                        f"gives[{index}].{name}",
                        give.get(name),
                        allowed_by_argument.get(f"gives[].{name}", []),
                        match=str(entry.get("match", "exact")),
                        accepted_values=list(entry.get("accepted_values", [])),
                        allow_empty=bool(entry.get("allow_empty", False)),
                    )
    else:
        for entry in entries:
            argument = str(entry["argument"])
            values = _argument_values(arguments, argument)
            if not values:
                if not _argument_is_required(tool_name, argument, arguments, entry):
                    continue
                values = [(argument, None)]
            for actual_argument, value in values:
                check(
                    actual_argument,
                    value,
                    list(entry.get("values", [])),
                    match=str(entry.get("match", "exact")),
                    accepted_values=list(entry.get("accepted_values", [])),
                    allow_empty=bool(entry.get("allow_empty", False)),
                )
    return {
        "status": "invalid" if violations else "valid",
        "violations": violations,
        "candidate_table_status": ("invalid" if candidate_table_violations else "valid"),
        "candidate_table_violations": candidate_table_violations,
    }


__all__ = [
    "build_dynamic_argument_candidate_snapshot",
    "evaluate_dynamic_argument_choice",
    "inject_dynamic_argument_candidate_table",
    "render_dynamic_argument_candidate_table",
]
