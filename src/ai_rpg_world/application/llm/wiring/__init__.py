"""LLM ランタイム配線の submodule を束ねる package (経路統一 R2c-2 後)。

# 経緯

かつて本 ``__init__.py`` は full wiring (``create_llm_agent_wiring`` /
``LlmAgentWiringResult`` + 多数の ``_build_*`` helper) を抱えていたが、本番
(spot_graph_game サーバ) と全実験は escape runtime
(``application/world_runtime/world_runtime.py`` の
``create_world_runtime`` → ``presentation/spot_graph_game/runtime_manager.py``
の ``_WorldLlmWiring``) 一本で動いており、full wiring はどの本番経路からも
到達しない死蔵だった (調査: 経路統一アーク)。

R2c-2 で ``create_llm_agent_wiring`` / ``LlmAgentOrchestrator`` /
``LlmAgentTurnRunner`` / ``DefaultLlmTurnTrigger`` と full wiring 専用 helper を
退役した。escape runtime が turn 実行の単一経路となる。

# 残った submodule (個別 import して使う)

本 package には configuration / builder の submodule が残っており、escape runtime や
共有コードはそれらを **直接** import する (本 ``__init__`` は何も re-export しない):

- ``resolved_runtime_config`` — env から解決した LLM runtime 設定の単一窓口
- ``feature_flags`` — short-term memory / semantic 等の env flag resolver
- ``_llm_client_factory`` — LLM クライアント生成
- ``episodic_stack`` — escape も使うエピソード記憶 stack builder
- ``optional_llm_services`` — LiteLLM 有無で optional な LLM サービス/ポート解決 (R2c-1)
- ``_shared_builders`` — エピソード/リンク/セマンティック構築の共有 builder
- ``episodic_memory_link_bundle`` / ``_default_episodic_episode_store`` 等
"""
