"""SlidingWindow 以外の記憶システム削除を固定する回帰テスト。"""

import importlib

import pytest

from ai_rpg_world.application.llm.contracts.dtos import SystemPromptPlayerInfoDto
from ai_rpg_world.application.llm.services.game_tool_registry import DefaultGameToolRegistry
from ai_rpg_world.application.llm.services.system_prompt_builder import DefaultSystemPromptBuilder
from ai_rpg_world.application.llm.services.tool_catalog import register_default_tools


def test_system_prompt_does_not_advertise_memory_tools() -> None:
    """system prompt に想起・長期記憶・作業メモの案内を戻さない。"""
    prompt = DefaultSystemPromptBuilder().build(
        SystemPromptPlayerInfoDto(
            player_name="Alice",
            role="冒険者",
            race="人間",
            element="火",
            game_description="",
        )
    )

    assert "memory_query" not in prompt
    assert "working_memory" not in prompt
    assert "episodic" not in prompt
    assert "facts" not in prompt
    assert "laws" not in prompt
    assert "todo_add" in prompt


def test_default_tools_register_todo_without_memory_tools() -> None:
    """ツールカタログは TODO を残し、記憶検索・想起ツールを登録しない。"""
    registry = DefaultGameToolRegistry()

    register_default_tools(registry, todo_enabled=True, include_movement_tools=False)
    names = {
        definition.name
        for definition, resolver in registry.get_definitions_with_resolvers()
        if resolver.is_available(None)
    }

    assert {"todo_add", "todo_list", "todo_complete"} <= names
    assert "memory_query" not in names
    assert "memory_recall_subjective" not in names
    assert "memory_working_memory_append" not in names
    assert "memory_subagent" not in names


@pytest.mark.parametrize(
    "module_name",
    [
        "ai_rpg_world.application.llm.services.predictive_memory_retriever",
        "ai_rpg_world.application.llm.services.memory_query_executor",
        "ai_rpg_world.application.llm.services.passive_subjective_recall_composer",
        "ai_rpg_world.application.llm.services.in_memory_long_term_memory_store",
        "ai_rpg_world.infrastructure.llm.sqlite_subjective_episode_store",
    ],
)
def test_deleted_memory_modules_are_not_importable(module_name: str) -> None:
    """削除済みの旧記憶実装を import 可能な状態で残さない。"""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)
