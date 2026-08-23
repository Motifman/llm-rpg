"""#1244の旧確定経路一覧が製品コードとずれないことを保証する。"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_ROOT = _REPO_ROOT / "src/ai_rpg_world"
_APPLICATION_ROOT = _PACKAGE_ROOT / "application"
_SCOPE_FIELD_PATTERN = re.compile(r"self\._[a-z_]*command_scope_factory")
_LEGACY_UOW_MODULE = "ai_rpg_world.domain.common.unit_of_work"
_LEGACY_UOW_FACTORY_MODULE = "ai_rpg_world.domain.common.unit_of_work_factory"

_RESIDUAL_OPTIONAL_SCOPE_PATHS = {
    "application/monster/services/spot_monster_behavior_tick_service.py",
    "application/trade/services/market_service.py",
    "application/trade/services/player_trade_service.py",
    "application/trade/services/trade_offer_expiry_stage.py",
    "application/world_graph/food_spoilage_stage_service.py",
    "application/world_graph/player_interaction_application_service.py",
    "application/world_graph/reactive_object_state_binding_stage_service.py",
    "application/world_graph/spot_graph_day_night_stage_service.py",
    "application/world_graph/spot_graph_environment_stage_service.py",
    "application/world_graph/spot_graph_merchant_trade_service.py",
    "application/world_graph/spot_graph_needs_decay_stage_service.py",
    "application/world_graph/spot_interaction_application_service.py",
    "application/world_graph/status_effects_tick_stage_service.py",
    "application/world_graph/synchronized_action_resolver_stage_service.py",
}

_MANDATORY_SCOPE_PATHS = {
    "application/llm/services/executors/spot_graph_tool_executor.py",
    "application/player/services/player_death_grace_tick_stage.py",
    "application/trade/services/market_order_expiry_stage.py",
    "application/trade/services/trade_command_service.py",
    "application/world_graph/meeting_command_service.py",
    "application/world_graph/player_outcome_rule_stage_service.py",
    "application/world_graph/reactive_passage_binding_stage_service.py",
    "application/world_graph/spot_exploration_application_service.py",
    "application/world_graph/spot_graph_item_transfer_service.py",
    "application/world_graph/spot_graph_monster_spawn_stage_service.py",
    "application/world_graph/spot_graph_movement_application_service.py",
    "application/world_graph/spot_graph_scenario_event_stage_service.py",
}

_LEGACY_UNIT_OF_WORK_PATHS = {
    "application/guild/services/guild_command_service.py",
    "application/harvest/services/harvest_command_service.py",
    "application/monster/services/monster_skill_application_service.py",
    "application/monster/services/monster_spawn_application_service.py",
    "application/quest/services/quest_command_service.py",
    "application/shop/services/shop_command_service.py",
    "application/skill/services/skill_command_service.py",
    "application/social/services/notification_command_service.py",
    "application/social/services/notification_event_handler_service.py",
    "application/social/services/post_command_service.py",
    "application/social/services/reply_command_service.py",
    "application/social/services/user_command_service.py",
    "application/world/handlers/combat_aggro_handler.py",
    "application/world/handlers/gateway_handler.py",
    "application/world/handlers/hit_box_damage_handler.py",
    "application/world/handlers/item_stored_in_chest_handler.py",
    "application/world/handlers/item_taken_from_chest_handler.py",
    "application/world/handlers/monster_death_hunger_handler.py",
    "application/world/handlers/monster_death_reward_handler.py",
    "application/world/handlers/monster_died_map_removal_handler.py",
    "application/world/handlers/monster_spawned_map_placement_handler.py",
    "application/world/movement_wiring.py",
    "application/world/services/chest_command_service.py",
    "application/world/services/drop_item_service.py",
    "application/world/services/interaction_command_service.py",
    "application/world/services/monster_behavior_coordinator.py",
    "application/world/services/monster_lifecycle_survival_coordinator.py",
    "application/world/services/monster_spawn_slot_service.py",
    "application/world/services/movement_service.py",
    "application/world/services/movement_step_executor.py",
    "application/world/services/place_object_service.py",
    "application/world/services/pursuit_command_service.py",
    "application/world/services/use_item_service.py",
    "application/world/services/world_simulation_collaborator_factory.py",
    "application/world/services/world_simulation_service.py",
}

_LEGACY_UNIT_OF_WORK_FACTORY_PATHS = {
    "application/observation/handlers/observation_event_handler.py",
    "application/quest/handlers/quest_progress_handler.py",
    "application/shop/handlers/shop_event_handler.py",
    "application/social/services/notification_event_handler_service.py",
    "application/social/services/relationship_event_handler_service.py",
}

_LEGACY_UNIT_OF_WORK_CLIENT_PATHS = (
    _LEGACY_UNIT_OF_WORK_PATHS | _LEGACY_UNIT_OF_WORK_FACTORY_PATHS
)

_LEGACY_LOAD_ONLY_MODULES = {
    "ai_rpg_world.application.skill.services.skill_command_service",
    "ai_rpg_world.application.social.services.notification_event_handler_service",
    "ai_rpg_world.application.social.services.relationship_event_handler_service",
    "ai_rpg_world.application.world.services.movement_service",
    "ai_rpg_world.application.world.services.movement_step_executor",
}


def _relative_source_paths_containing(pattern: re.Pattern[str] | str) -> set[str]:
    result: set[str] = set()
    for path in _APPLICATION_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        matched = pattern.search(source) if hasattr(pattern, "search") else pattern in source
        if matched:
            result.add(str(path.relative_to(_PACKAGE_ROOT)))
    return result


def _module_name(path: Path) -> str:
    relative = path.relative_to(_PACKAGE_ROOT).with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(("ai_rpg_world", *parts))


def _package_module_paths() -> dict[str, Path]:
    return {_module_name(path): path for path in _PACKAGE_ROOT.rglob("*.py")}


def _package_import_graph() -> dict[str, set[str]]:
    module_paths = _package_module_paths()
    graph: dict[str, set[str]] = {}
    for module_name, path in module_paths.items():
        package_name = (
            module_name
            if path.name == "__init__.py"
            else module_name.rpartition(".")[0]
        )
        imports: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
                continue
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.level:
                relative_name = "." * node.level + (node.module or "")
                imported_module = importlib.util.resolve_name(
                    relative_name, package_name
                )
            else:
                imported_module = node.module or ""
            imports.add(imported_module)
            imports.update(
                f"{imported_module}.{alias.name}" for alias in node.names
            )
        expanded_imports = set(imports)
        for imported in tuple(imports):
            parts = imported.split(".")
            expanded_imports.update(
                ".".join(parts[:index]) for index in range(2, len(parts))
            )
        graph[module_name] = {
            name for name in expanded_imports if name in module_paths
        }
    return graph


def _production_reachable_application_modules() -> set[str]:
    graph = _package_import_graph()
    roots = {
        module
        for module in graph
        if module.startswith("ai_rpg_world.application.world_runtime.")
        or module.startswith(
            "ai_rpg_world.application.llm.services.world_llm_turn."
        )
        or module.startswith("ai_rpg_world.presentation.")
    }
    reachable = set(roots)
    pending = list(roots)
    while pending:
        module = pending.pop()
        for imported in graph[module]:
            if imported not in reachable:
                reachable.add(imported)
                pending.append(imported)
    return reachable


def _relative_paths_importing(module: str, symbol: str) -> set[str]:
    paths: set[str] = set()
    for path in _APPLICATION_ROOT.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            imports_module = isinstance(node, ast.Import) and any(
                alias.name == module for alias in node.names
            )
            imports_symbol = (
                isinstance(node, ast.ImportFrom)
                and node.module == module
                and any(alias.name == symbol for alias in node.names)
            )
            if imports_module or imports_symbol:
                paths.add(str(path.relative_to(_PACKAGE_ROOT)))
                break
    return paths


def test_every_command_scope_owner_is_classified() -> None:
    """scope factoryを保持するserviceは、必須経路か残存旧経路へ漏れなく分類される。"""
    actual = _relative_source_paths_containing(_SCOPE_FIELD_PATTERN)

    assert actual == _MANDATORY_SCOPE_PATHS | _RESIDUAL_OPTIONAL_SCOPE_PATHS
    assert _MANDATORY_SCOPE_PATHS.isdisjoint(_RESIDUAL_OPTIONAL_SCOPE_PATHS)


def test_legacy_unit_of_work_imports_match_the_disconnected_allowlist() -> None:
    """旧UnitOfWorkの利用を既知の未接続moduleから増やさず、撤去時は一覧更新を要求する。"""
    actual = _relative_paths_importing(_LEGACY_UOW_MODULE, "UnitOfWork")

    assert actual == _LEGACY_UNIT_OF_WORK_PATHS


def test_legacy_unit_of_work_factory_imports_match_the_disconnected_allowlist() -> None:
    """factory経由で旧UnitOfWorkを生成するhandlerも既知一覧から増やさない。"""
    actual = _relative_paths_importing(
        _LEGACY_UOW_FACTORY_MODULE, "UnitOfWorkFactory"
    )

    assert actual == _LEGACY_UNIT_OF_WORK_FACTORY_PATHS


def test_production_import_graph_has_only_known_load_only_legacy_modules() -> None:
    """現行runtime・LLM・presentationがロードする旧clientを既知5 moduleから増やさない。"""
    legacy_client_modules = {
        "ai_rpg_world." + path.removesuffix(".py").replace("/", ".")
        for path in _LEGACY_UNIT_OF_WORK_CLIENT_PATHS
    }
    reachable = _production_reachable_application_modules()

    assert reachable & legacy_client_modules == _LEGACY_LOAD_ONLY_MODULES


def test_production_import_graph_does_not_construct_legacy_uow_clients() -> None:
    """ロードのみの互換moduleを含め、現行compositionから旧client classを構築しない。"""
    module_paths = _package_module_paths()
    legacy_client_modules = {
        "ai_rpg_world." + path.removesuffix(".py").replace("/", ".")
        for path in _LEGACY_UNIT_OF_WORK_CLIENT_PATHS
    }
    legacy_paths = {
        _PACKAGE_ROOT / path for path in _LEGACY_UNIT_OF_WORK_CLIENT_PATHS
    }
    legacy_class_names = {
        node.name
        for path in legacy_paths
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.ClassDef)
    }
    violations: list[str] = []
    for module in _production_reachable_application_modules():
        if module in legacy_client_modules:
            continue
        path = module_paths[module]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        legacy_constructor_aliases = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
            if alias.name in legacy_class_names
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if (
                called_name in legacy_class_names
                or called_name in legacy_constructor_aliases
            ):
                violations.append(f"{module}:{node.lineno}:{called_name}")

    assert violations == []
