"""実行時候補から、再実験可能な動的引数候補表を組み立てる。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    MonsterToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    WorldObjectToolRuntimeTargetDto,
)


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


def _entry(tool: str, argument: str, values: list[str], **extra: str) -> dict[str, Any]:
    return {"tool": tool, "argument": argument, **extra, "values": values}


def build_dynamic_argument_candidate_snapshot(
    runtime_context: ToolRuntimeContextDto,
    exposed_tools: set[str],
) -> dict[str, Any]:
    """同じ ``tool_runtime_context`` からツール・引数別の候補を作る。

    空の候補は「指定できる値がある」と誤読させないため載せない。候補表をまだ
    モデルへ見せない基準 run でも、この snapshot は保存して再実験に使う。
    """
    targets = list(runtime_context.targets.values())
    objects = [target for target in targets if isinstance(target, WorldObjectToolRuntimeTargetDto)]
    destinations = [target for target in targets if isinstance(target, DestinationToolRuntimeTargetDto)]
    inventory = [
        target
        for target in targets
        if isinstance(target, InventoryToolRuntimeTargetDto) and target.kind == "inventory_item"
    ]
    ground_items = [
        target
        for target in targets
        if isinstance(target, InventoryToolRuntimeTargetDto) and target.kind == "ground_item"
    ]
    players = [target for target in targets if isinstance(target, PlayerToolRuntimeTargetDto)]
    monsters = [target for target in targets if isinstance(target, MonsterToolRuntimeTargetDto)]
    entries: list[dict[str, Any]] = []

    if "interact" in exposed_tools:
        interactive = [target for target in (*objects, *players, *inventory) if target.available_interactions]
        values = _names(interactive)
        if values:
            entries.append(_entry("interact", "target_label", values))
        for target in interactive:
            actions = list(dict.fromkeys(target.available_interactions))
            if actions:
                entries.append(
                    _entry(
                        "interact",
                        "action_name",
                        actions,
                        target=target.display_name,
                    )
                )

    simple_groups = (
        ("travel_to", "destination_label", destinations),
        ("use_item", "item_label", inventory),
        ("drop_item", "item_label", inventory),
        ("pickup_item", "ground_item_label", ground_items),
        ("attack", "target_label", monsters),
        ("tend_to_player", "target_label", players),
    )
    for tool, argument, candidates in simple_groups:
        values = _names(candidates)
        if tool in exposed_tools and values:
            entries.append(_entry(tool, argument, values))

    if "give_item" in exposed_tools:
        item_names = _names(inventory)
        player_names = _names(players)
        if item_names:
            entries.append(_entry("give_item", "gives[].item_label", item_names))
        if player_names:
            entries.append(_entry("give_item", "gives[].target_player_label", player_names))

    return {
        "schema_version": 1,
        "entries": entries,
        "rendered": render_dynamic_argument_candidate_table(entries),
    }


def render_dynamic_argument_candidate_table(
    entries: Iterable[Mapping[str, Any]],
) -> str:
    """保存用の構造化候補を、本番介入で使う日本語表へ変換する。"""
    lines = ["【現在指定できる引数】"]
    count = 0
    for entry in entries:
        values = [str(value) for value in entry.get("values", []) if str(value)]
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
        return {"status": "not_applicable", "violations": []}

    violations: list[dict[str, Any]] = []

    def check(argument: str, value: Any, allowed: list[str]) -> None:
        if not isinstance(value, str) or not value.strip():
            violations.append(
                {
                    "argument": argument,
                    "value": value,
                    "allowed": allowed,
                    "reason": "missing_or_not_string",
                }
            )
        elif value not in allowed:
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
            check("target_label", target, list(target_entry.get("values", [])))
        action_entry = next(
            (entry for entry in entries if entry.get("argument") == "action_name" and entry.get("target") == target),
            None,
        )
        check(
            "action_name",
            arguments.get("action_name"),
            list(action_entry.get("values", [])) if action_entry else [],
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
                    check(
                        f"gives[{index}].{name}",
                        give.get(name),
                        allowed_by_argument.get(f"gives[].{name}", []),
                    )
    else:
        for entry in entries:
            argument = str(entry["argument"])
            check(argument, arguments.get(argument), list(entry.get("values", [])))
    return {
        "status": "invalid" if violations else "valid",
        "violations": violations,
    }


__all__ = [
    "build_dynamic_argument_candidate_snapshot",
    "evaluate_dynamic_argument_choice",
    "render_dynamic_argument_candidate_table",
]
