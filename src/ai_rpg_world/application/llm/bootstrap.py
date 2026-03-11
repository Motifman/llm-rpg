"""
LLM ランタイムの低レベルなブートストラップ窓口。

create_llm_agent_wiring の実運用接続先が未確定でも差し込み可能な seam を提供する。
外部ブートストラップは本モジュールの compose_llm_runtime を呼び、
返り値の wiring_result を EventHandlerComposition / WorldSimulationApplicationService に渡す。

memory_db_path または環境変数 LLM_MEMORY_DB_PATH により、
episode / long-term / reflection_state が SQLite に永続化され、再起動後も復元される。

この関数自体は pursuit-capable runtime を保証しない。追跡コマンドと継続処理を
同じ live runtime に束ねる必要がある場合は、より高レベルな composition
entrypoint から両方の pursuit services をまとめて注入すること。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

from ai_rpg_world.application.llm.wiring import (
    create_llm_agent_wiring,
    LlmAgentWiringResult,
)
from ai_rpg_world.infrastructure.events.observation_event_handler_registry import (
    ObservationEventHandlerRegistry,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.contracts.interfaces import (
        IReflectionRunner,
        ILlmTurnTrigger,
    )


def compose_llm_runtime(
    *,
    composition_builder: Optional[
        Callable[[ObservationEventHandlerRegistry], Any]
    ] = None,
    service_builder: Optional[
        Callable[[ILlmTurnTrigger, Optional[IReflectionRunner]], Any]
    ] = None,
    **wiring_kwargs: Any,
) -> "ComposeLlmRuntimeResult":
    """
    LLM ランタイムを組み立てる低レベルなブートストラップ窓口。

    1. create_llm_agent_wiring を呼び observation_registry / llm_turn_trigger / reflection_runner を取得する。
    2. composition_builder が渡されていれば、observation_registry を渡して EventHandlerComposition を生成する。
    3. service_builder が渡されていれば、llm_turn_trigger と reflection_runner を渡して WorldSimulationApplicationService を生成する。

    外部ブートストラップは wiring_kwargs に create_llm_agent_wiring の引数（player_status_repository, physical_map_repository 等）
    を渡し、composition_builder / service_builder で自前の EventHandlerComposition / WorldSimulationApplicationService を生成する。

    オプション機能の組み立て:
    - 意図的ドロップ（world_drop_item）: drop_item_service を wiring_kwargs に渡す（PlayerDropItemApplicationService）。
      EventHandlerComposition に intentional_drop_registry を渡すと、ドロップしたアイテムがマップ上に GROUND_ITEM として配置される。
      （ItemDroppedFromInventoryDropHandler + IntentionalDropEventHandlerRegistry を player_status_repository / physical_map_repository で組み立てる。）

    memory_db_path または LLM_MEMORY_DB_PATH により、episode / long-term / reflection が SQLite に永続化される。

    Args:
        composition_builder: observation_registry を受け取り EventHandlerComposition を返す関数。省略時は None。
        service_builder: (llm_turn_trigger, reflection_runner) を受け取り WorldSimulationApplicationService を返す関数。省略時は None。
        **wiring_kwargs: create_llm_agent_wiring に渡すキーワード引数。

    Returns:
        ComposeLlmRuntimeResult。wiring_result は常に設定され、
        composition / service は builder 指定時のみ設定される。
    """
    wiring_result = create_llm_agent_wiring(**wiring_kwargs)
    composition = None
    service = None
    if composition_builder is not None:
        composition = composition_builder(wiring_result.observation_registry)
    if service_builder is not None:
        service = service_builder(
            wiring_result.llm_turn_trigger,
            wiring_result.reflection_runner,
        )
    return ComposeLlmRuntimeResult(
        wiring_result=wiring_result,
        event_handler_composition=composition,
        world_simulation_service=service,
    )


class ComposeLlmRuntimeResult:
    """compose_llm_runtime の返り値。"""

    def __init__(
        self,
        wiring_result: LlmAgentWiringResult,
        event_handler_composition: Optional[Any] = None,
        world_simulation_service: Optional[Any] = None,
    ) -> None:
        self.wiring_result = wiring_result
        self.event_handler_composition = event_handler_composition
        self.world_simulation_service = world_simulation_service

    @property
    def observation_registry(self) -> ObservationEventHandlerRegistry:
        """wiring_result.observation_registry のショートカット。"""
        return self.wiring_result.observation_registry

    @property
    def llm_turn_trigger(self) -> "ILlmTurnTrigger":
        """wiring_result.llm_turn_trigger のショートカット。"""
        return self.wiring_result.llm_turn_trigger

    @property
    def reflection_runner(self) -> Optional["IReflectionRunner"]:
        """wiring_result.reflection_runner のショートカット。"""
        return self.wiring_result.reflection_runner
