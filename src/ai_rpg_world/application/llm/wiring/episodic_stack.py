"""シナリオ非依存のエピソード記憶パイプライン builder。

# 何のため

第20-23回実験 (Issue #295/#311/#325/#328) で「沈黙の禁書庫」シナリオで
組み上げた episodic memory pipeline を、別シナリオ (survival_island_v2 等)
からも同じ paradigm で使えるように application 層に持ち上げたもの。
詳細な設計は ``docs/episodic_memory_overview.md`` 参照。

# 構成

- ``EpisodicStack``: 組み立てた pipeline をまとめて返す dataclass
- ``build_episodic_stack(...)``: scenario + 共有 IO ストアを受け取り、
  chunk_coordinator / passive_recall / noun_matcher を組む本体
- ``build_scenario_noun_matcher(...)``: scenario の spot 名 / キャラクター名から
  ``IWorldNounMatcher`` を構築
- ``is_episodic_enabled`` / ``is_episodic_subjective_enabled``: 環境変数の
  パース (シナリオ非依存)

# 設計判断

- **シナリオは duck-type で受ける**: ``scenario.player_spawns`` /
  ``graph._spots`` 等の getattr で取れる属性だけを要求。具体型 (escape の
  ``EscapeScenario`` 等) には依存しない
- **本家 ``_shared_builders.py`` の重い builder には頼らない**:
  ``EpisodicMemoryLinkApplicationService`` 等の高度機能 (LLM 駆動の
  reinterpretation / semantic cluster promotion) は escape_game の MVP では
  over-engineering。後で必要になったら本家経路に乗り換える
- **In-memory store がデフォルト**: SQLite store に差し替えるときは
  ``episode_store`` 引数で外側から渡す
- **scenario 構造から固有名詞を抽出**: spot 名は graph から、character 名は
  player_spawns から取る。world_object / item は将来拡張で追加

# 移行履歴

PR #330 で ``demos/escape_game/escape_episodic_wiring.py`` から application
層に持ち上げた。escape_game 側には後方互換のため re-export shim が残る
(``EscapeEpisodicStack`` / ``build_escape_episodic_stack`` 名で alias)。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ai_rpg_world.application.llm.scheduler import (
    IEpisodicSubjectiveCompletionScheduler,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    ISlidingWindowMemory,
)
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_coordinator import (
    EpisodicChunkCoordinator,
)
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    EpisodicChunkSubjectiveFieldsService,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.world_noun_matcher import (
    IWorldNounMatcher,
    WorldNounMatcherBuilder,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


# 環境変数名: 1 / true / yes / on (case-insensitive) で有効化
_TRUE_TOKENS = frozenset({"1", "true", "yes", "on"})
_FALSE_TOKENS = frozenset({"0", "false", "no", "off"})


def is_episodic_enabled(env: Optional[dict[str, str]] = None) -> bool:
    """``LLM_EPISODIC_ENABLED`` を読んで episodic pipeline 有効化を判定。

    env を渡せばその dict を見る (テスト用)、None なら ``os.environ``。
    未設定 / unknown 値は False (= 完全に off で従来動作)。
    """
    source = env if env is not None else os.environ
    raw = source.get("LLM_EPISODIC_ENABLED", "")
    return raw.strip().lower() in _TRUE_TOKENS


def is_episodic_subjective_enabled(env: Optional[dict[str, str]] = None) -> bool:
    """``LLM_EPISODIC_SUBJECTIVE_ENABLED`` を読んで LLM 主観文付与の有効化を判定。

    ``is_episodic_enabled`` が True のときに更にこの判定が True なら、
    ``EpisodicChunkSubjectiveFieldsService`` を chunk_coordinator に配線する。

    **既定値は True (= LLM 補完を有効化)** (#308)。明示的に OFF にしたいときだけ
    ``LLM_EPISODIC_SUBJECTIVE_ENABLED=0`` (もしくは ``false`` / ``no`` / ``off``)
    を指定する。

    判定ルール:
    - 未設定 (key 自体が無い): True (既定 on)
    - True 表現 (1/true/yes/on): True
    - False 表現 (0/false/no/off): False
    - 不明な値: True (壊さず on 側に倒す)
    """
    source = env if env is not None else os.environ
    raw = source.get("LLM_EPISODIC_SUBJECTIVE_ENABLED")
    if raw is None:
        return True
    normalized = raw.strip().lower()
    if not normalized:
        return True
    if normalized in _FALSE_TOKENS:
        return False
    return True


@dataclass(frozen=True)
class EpisodicStack:
    """build_episodic_stack の戻り値。on のときだけ作られる。

    Attributes:
        chunk_coordinator: ``after_action_recorded(player_id)`` を呼ぶための
            書き込み側 service
        passive_recall: prompt builder に渡す読み出し側 service
        noun_matcher: observation prose 中の固有名詞を cue 化するマッチャ
        episode_store: 共有 episode store (chunk が書き、passive_recall が読む)
        subjective_completion_scheduler: 非同期 LLM 主観文付与のスケジューラ。
            shutdown 時に in-flight ジョブを drain するために保持する。
            未配線時は None。
    """

    chunk_coordinator: EpisodicChunkCoordinator
    passive_recall: EpisodicPassiveRecallRetrievalService
    noun_matcher: IWorldNounMatcher
    episode_store: InMemorySubjectiveEpisodeStore
    subjective_completion_scheduler: Optional[IEpisodicSubjectiveCompletionScheduler] = None
    # semantic 拡張 (default OFF)。``semantic_passive_top_k > 0`` または LLM gist
    # 有効時に full 共有 builder (build_episodic_memory_stack) で組み、
    # escape_game でも「学びを作る (promotion) + 学びを出す (passive recall)」が
    # 動くようにする。OFF のときは全て None / 0 で従来の episodic-only 動作。
    #
    #   semantic_passive_recall: prompt の【関連する学び】用 (top_k>0 のとき非 None)
    #   semantic_passive_top_k: prompt に出す semantic 件数 (0 = 出さない)
    #   episodic_semantic_promotion: action 後に on_after_tool_turn を呼ぶ昇格 service
    #   semantic_memory_store: 昇格先 store (snapshot / 検証用に公開)
    semantic_passive_recall: Optional[Any] = None
    semantic_passive_top_k: int = 0
    episodic_semantic_promotion: Optional[Any] = None
    semantic_memory_store: Optional[Any] = None


def build_scenario_noun_matcher(*, scenario: object, graph: object) -> IWorldNounMatcher:
    """scenario の spot 名 + キャラクター名 から ``IWorldNounMatcher`` を構築する。

    - spot: ``graph._spots.values()`` (= SpotNode) の name と spot_id
    - character: ``scenario.player_spawns`` の name と player_id

    両方とも getattr で参照するため、具体型は escape_game / survival_island
    の Scenario / SpotGraphAggregate どちらでも動く。将来 world_object /
    item の名前も追加可能だが、初期統合では spot とキャラクターだけで実害は出ない。
    """
    builder = WorldNounMatcherBuilder()
    # spot 名 — graph aggregate 内の SpotNode を全列挙
    spots = getattr(graph, "_spots", None)
    if spots is not None:
        for node in spots.values():
            spot_id_value = getattr(getattr(node, "spot_id", None), "value", None)
            name = getattr(node, "name", None)
            if spot_id_value is None or not name:
                continue
            builder.add_spot(name=name, spot_id=int(spot_id_value))
    # キャラクター名 — scenario の player_spawns
    spawns = getattr(scenario, "player_spawns", None) or ()
    for spawn in spawns:
        name = getattr(spawn, "name", None)
        pid = getattr(spawn, "player_id", None)
        if not name or pid is None:
            continue
        builder.add_character(name=name, player_id=int(pid))
    return builder.build()


def build_episodic_stack(
    *,
    scenario: object,
    graph: object,
    observation_buffer: IObservationContextBuffer,
    sliding_window_memory: ISlidingWindowMemory,
    action_result_store: IActionResultStore,
    trace_recorder_provider: Optional[Callable[[], Any]] = None,
    current_tick_provider: Optional[Callable[[], Any]] = None,
    chunk_subjective_fields_service: Optional[EpisodicChunkSubjectiveFieldsService] = None,
    persona_block_provider: Optional[Callable[[PlayerId], str]] = None,
    subjective_completion_scheduler: Optional[IEpisodicSubjectiveCompletionScheduler] = None,
    episode_store: Optional[InMemorySubjectiveEpisodeStore] = None,
    being_attachment_resolver: Optional[Any] = None,
    default_world_id: Optional[Any] = None,
    semantic_enabled: bool = False,
    semantic_passive_top_k: int = 0,
    semantic_gist_service: Optional[Any] = None,
    semantic_persona_resolver: Optional[Any] = None,
) -> EpisodicStack:
    """シナリオ非依存のエピソード記憶パイプラインを組み立てる。

    write 側 (chunk_coordinator) と read 側 (passive_recall + noun_matcher) を
    1 つの episode_store で共有する。LLM 駆動の reinterpretation や semantic
    promotion は組み込まない (将来必要になったら本家 builders を呼ぶ)。

    # 引数

    - ``scenario`` / ``graph``: 固有名詞 matcher の構築元。``getattr`` で参照する
      ので duck-type (escape_game / survival_island どちらでも可)
    - ``observation_buffer`` / ``sliding_window_memory`` / ``action_result_store``:
      呼び出し側の runtime が保持する I/O 群を共有する
    - ``trace_recorder_provider`` / ``current_tick_provider``: trace 配線
      (provider 経由なので runtime 完成後に set_trace_recorder で差し込まれる
      経路にも対応)
    - ``chunk_subjective_fields_service``: 同期 LLM 補完経路 (旧来)。
      ``subjective_completion_scheduler`` と排他
    - ``persona_block_provider``: player_id → persona text の dict 引き
    - ``subjective_completion_scheduler``: 非同期 LLM 補完経路 (#310 推奨)。
      scheduler と stack で同じ ``episode_store`` を共有することが整合性条件
    - ``episode_store``: 呼び出し側が事前に scheduler と共有する store を渡せる。
      None なら新規作成

    # 履歴

    - Issue #283 後続: chunk write / passive recall を ``TraceEventKind`` で
      可視化
    - Issue #295 後続: ``chunk_subjective_fields_service`` (+ persona_provider)
      が両方与えられたときだけ LLM 主観文付与経路を有効化
    - Issue #311 後続 (#310): 非同期 scheduler 経路
    """
    # episode_store を呼び出し側から渡せるようにしているのは、scheduler 経路
    # で「スケジューラと chunk_coordinator が同じ store を共有する必要がある」
    # ため (両者が違う store だと、worker が書き込んだ merged episode を
    # passive_recall が読めない)。
    # semantic 拡張 (default OFF)。ON のときは full 共有 builder で link/semantic/
    # promotion を組み、chunk_coordinator に link service を渡す。escape_game の
    # 軽量 MVP では従来 semantic を持たなかったが、フラグで本家 builder に委譲する
    # ことで「学びを作る/出す」を実験経路でも動かせるようにする (#526 後続)。
    link_service: Optional[Any] = None
    episodic_semantic_promotion: Optional[Any] = None
    semantic_memory_store: Optional[Any] = None
    if semantic_enabled:
        # 循環 import 回避のため関数内 import。
        from ai_rpg_world.application.llm.wiring._shared_builders import (
            build_episodic_memory_stack,
        )

        mem_stack = build_episodic_memory_stack(
            episode_store,
            semantic_gist_service=semantic_gist_service,
            semantic_persona_resolver=semantic_persona_resolver,
            being_attachment_resolver=being_attachment_resolver,
            default_world_id=default_world_id,
        )
        # build_episodic_memory_stack が episode_store を解決して返す。以降は
        # 全コンポーネントがこの shared store を共有する (chunk write / recall /
        # promotion が同じ store を見る整合性条件)。
        episode_store = mem_stack.shared_episode_store
        link_service = mem_stack.mem_bundle.link_service
        episodic_semantic_promotion = mem_stack.episodic_semantic_promotion
        semantic_memory_store = mem_stack.semantic_memory_store
    elif episode_store is None:
        episode_store = InMemorySubjectiveEpisodeStore()
    chunk_coordinator = EpisodicChunkCoordinator(
        observation_buffer=observation_buffer,
        sliding_window_memory=sliding_window_memory,
        action_result_store=action_result_store,
        episodic_episode_store=episode_store,
        chunk_episode_draft_builder=ChunkEpisodeDraftBuilder(),
        trace_recorder_provider=trace_recorder_provider,
        current_tick_provider=current_tick_provider,
        chunk_subjective_fields_service=chunk_subjective_fields_service,
        subjective_completion_scheduler=subjective_completion_scheduler,
        persona_block_provider=persona_block_provider,
        # semantic OFF なら link service なし (= MVP の従来動作)。ON なら昇格に
        # 必要な memory link を chunk write 経路に通す。
        episodic_memory_link_service=link_service,
        being_attachment_resolver=being_attachment_resolver,
        default_world_id=default_world_id,
    )
    passive_recall = EpisodicPassiveRecallRetrievalService(
        episode_store,
        being_attachment_resolver=being_attachment_resolver,
        default_world_id=default_world_id,
    )
    noun_matcher = build_scenario_noun_matcher(scenario=scenario, graph=graph)

    # semantic passive recall は top_k>0 のときだけ作る (= prompt の【関連する学び】)。
    semantic_passive_recall: Optional[Any] = None
    if semantic_enabled and semantic_passive_top_k > 0:
        from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
            SemanticPassiveRecallService,
        )

        semantic_passive_recall = SemanticPassiveRecallService(
            semantic_memory_store,
            being_attachment_resolver=being_attachment_resolver,
            default_world_id=default_world_id,
        )

    return EpisodicStack(
        chunk_coordinator=chunk_coordinator,
        passive_recall=passive_recall,
        noun_matcher=noun_matcher,
        episode_store=episode_store,
        subjective_completion_scheduler=subjective_completion_scheduler,
        semantic_passive_recall=semantic_passive_recall,
        semantic_passive_top_k=semantic_passive_top_k if semantic_enabled else 0,
        episodic_semantic_promotion=episodic_semantic_promotion,
        semantic_memory_store=semantic_memory_store,
    )


__all__ = [
    "EpisodicStack",
    "build_episodic_stack",
    "build_scenario_noun_matcher",
    "is_episodic_enabled",
    "is_episodic_subjective_enabled",
]
