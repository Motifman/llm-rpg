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
  ``graph._spots`` 等の getattr で取れる属性だけを要求。具体型
  (``ScenarioLoadResult`` 等) には依存しない
- **本家 ``_shared_builders.py`` の重い builder には頼らない**:
  ``EpisodicMemoryLinkApplicationService`` 等の高度機能 (LLM 駆動の
  reinterpretation / semantic cluster promotion) は world_runtime の MVP では
  over-engineering。後で必要になったら本家経路に乗り換える
- **In-memory store がデフォルト**: SQLite store に差し替えるときは
  ``episode_store`` 引数で外側から渡す
- **scenario 構造から固有名詞を抽出**: spot 名は graph から、character 名は
  player_spawns から取る。world_object / item は将来拡張で追加

# 移行履歴

PR #330 で ``demos/world_runtime/world_episodic_wiring.py`` から application
層に持ち上げた。world_runtime 側には後方互換のため re-export shim が残る
(``WorldEpisodicStack`` / ``build_world_episodic_stack`` 名で alias)。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
        EpisodicSemanticClusterPromotionService,
    )
    from ai_rpg_world.application.llm.services.episodic_reinterpretation_coordinator import (
        EpisodicReinterpretationCoordinator,
    )
    from ai_rpg_world.application.llm.ports.episodic_reinterpretation_completion_port import (
        IEpisodicReinterpretationCompletionPort,
    )
    from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
        SemanticPassiveRecallService,
    )
    from ai_rpg_world.domain.memory.episodic.repository.episodic_reinterpretation_journal_repository import (
        EpisodicReinterpretationJournalRepository,
    )
    from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import (
        EpisodicRecallBufferRepository,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
        IEpisodicRecallHabituationStore,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
        IEpisodicRecallSlotStore,
    )
    from ai_rpg_world.application.llm.services.afterglow_store import (
        IAfterglowStore,
    )

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
    # world_runtime でも「学びを作る (promotion) + 学びを出す (passive recall)」が
    # 動くようにする。OFF のときは全て None / 0 で従来の episodic-only 動作。
    #
    #   semantic_passive_recall: prompt の【関連する学び】用 (top_k>0 のとき非 None)
    #   semantic_passive_top_k: prompt に出す semantic 件数 (0 = 出さない)
    #   episodic_semantic_promotion: action 後に on_after_tool_turn を呼ぶ昇格 service
    #   semantic_memory_store: 昇格先 store (snapshot / 検証用に公開)
    #   memory_link_store: 昇格の根拠となる memory link graph (snapshot 用に公開)
    semantic_passive_recall: Optional["SemanticPassiveRecallService"] = None
    semantic_passive_top_k: int = 0
    episodic_semantic_promotion: Optional["EpisodicSemanticClusterPromotionService"] = None
    # store は上流 EpisodicMemoryStack が Any 扱いのため合わせる (repo 実装差を許容)。
    semantic_memory_store: Optional[Any] = None
    memory_link_store: Optional[Any] = None
    # 想起→強化 (recall_count 加算 / CO_RECALL リンク / ヘブ則強化) を担う
    # link service。chunk_coordinator (TEMPORAL リンク) だけでなく prompt builder
    # の passive recall 経路にも同一インスタンスを配線しないと、recall_count が
    # 永遠に 0 のままで昇格ゲート (recall_count>=3) を誰も超えられない
    # (memory_full_002 実験で発覚した静かな失敗)。
    link_service: Optional[Any] = None
    # reinterpretation 拡張 (段1 / default OFF)。``reinterpretation_enabled`` のとき
    # build_episodic_stack が recall_buffer + journal + coordinator を構築する。
    # OFF のときは全て None で、prompt builder の guard で覗かない = 従来動作。
    #
    #   reinterpretation_coordinator: turn 後に after_turn_completed を呼び、
    #       interval 到達時に LLM 再解釈を flush する coordinator
    #   reinterpretation_journal: 再解釈結果 (active recall text) の journal。
    #       prompt builder が想起時に覗いて recall_text を上書きする
    #   recall_buffer_store: prompt 用 recall buffer (completion 有効時のみ非 None)。
    #       想起した episode を pending として積み、coordinator が batch 再解釈する
    reinterpretation_coordinator: Optional["EpisodicReinterpretationCoordinator"] = None
    reinterpretation_journal: Optional["EpisodicReinterpretationJournalRepository"] = None
    recall_buffer_store: Optional["EpisodicRecallBufferRepository"] = None
    # #526 段階 2: 慣化 sidecar (default off)。env で enable 時に in-memory store
    # を構築し、passive_recall service と prompt_builder の両方に渡す。
    recall_habituation_store: Optional[
        "IEpisodicRecallHabituationStore"
    ] = None
    recall_habituation_decay_window_ticks: int = 5
    # #526 段階 3: 想起スロット sidecar (default off)。env で enable 時に
    # in-memory store を構築し、passive_recall と prompt_builder の両方に渡す。
    # 4 パラメータ (capacity / insert_per_tick / max_residence / cooldown_ticks)
    # で運用を調整する。
    recall_slot_store: Optional["IEpisodicRecallSlotStore"] = None
    recall_slot_cooldown_ticks: int = 5
    # PR-D: recall_by_handle ツールが force_insert に渡す capacity を、
    # stack が確定した時点で露出しておく (= world_runtime 側で再計算しない)。
    recall_slot_capacity: int = 4
    # #526 段階 3 PR-C: afterglow index sidecar (= ぼんやり覚えてる 1 行見出し)。
    # default off。slot 退去や score 閾値で slot 入りできなかった弱い hit を
    # heading 付きで保持し、prompt の見出し section と能動想起ツール (別 PR)
    # に使う。
    afterglow_store: Optional["IAfterglowStore"] = None
    afterglow_capacity: int = 10
    afterglow_max_residence: int = 10


def build_scenario_noun_matcher(
    *,
    scenario: object,
    graph: object,
    spot_interior_repo: Optional[Any] = None,
) -> IWorldNounMatcher:
    """scenario の spot 名 + キャラクター名 + world_object 名 から
    ``IWorldNounMatcher`` を構築する。

    - spot: ``graph._spots.values()`` (= SpotNode) の name と spot_id
    - character: ``scenario.player_spawns`` の name と player_id
    - world_object: 各 SpotNode の ``interior.objects`` から
      ``object_id.value`` と ``name`` (#526 後続 C1)

    すべて getattr で参照するため、具体型は world_runtime / survival_island
    の Scenario / SpotGraphAggregate どちらでも動く。

    #526 後続 C1: 観測 prose に「案内板」「覚書」等の world_object 名が
    含まれるケースで、prose 経路から ``object:world_object_{id}`` cue が
    立つようにする。これにより write 側 (Fix A の prose 抽出) でも read 側
    (passive recall 時の prose 抽出) でも object 軸の recall が機能する。

    interior の取得は 2 系統で柔軟に対応する:
    1. ``node.interior`` が直接ある (= test stub やインライン構成)
    2. ``spot_interior_repo`` が与えられている (= 実 runtime。``SpotNode`` に
       は interior が None で、別 repository に保管されている構成)
    両方欠落 / 解決失敗時は world_object 抽出を skip するだけで例外を投げない。
    """
    builder = WorldNounMatcherBuilder()
    # spot 名 — graph aggregate 内の SpotNode を全列挙
    spots = getattr(graph, "_spots", None)
    if spots is not None:
        for node in spots.values():
            spot_id_obj = getattr(node, "spot_id", None)
            spot_id_value = getattr(spot_id_obj, "value", None)
            name = getattr(node, "name", None)
            if spot_id_value is None or not name:
                continue
            builder.add_spot(name=name, spot_id=int(spot_id_value))
            # #526 後続 C1: 各 spot の interior から world_object 名を index。
            # node.interior があればそれを優先 (test stub 経路)、無ければ
            # spot_interior_repo に問い合わせる (実 runtime 経路)。両方無ければ skip。
            interior = getattr(node, "interior", None)
            if interior is None and spot_interior_repo is not None and spot_id_obj is not None:
                try:
                    interior = spot_interior_repo.find_by_spot_id(spot_id_obj)
                except Exception:
                    # repo 経路の失敗で matcher 構築を止めない (degradation)
                    interior = None
            if interior is None:
                continue
            objects = getattr(interior, "objects", None) or ()
            for obj in objects:
                obj_id_value = getattr(getattr(obj, "object_id", None), "value", None)
                obj_name = getattr(obj, "name", None)
                if obj_id_value is None or not obj_name:
                    continue
                builder.add_world_object(
                    name=obj_name, world_object_id=int(obj_id_value)
                )
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
    reinterpretation_enabled: bool = False,
    reinterpretation_completion: Optional[
        "IEpisodicReinterpretationCompletionPort"
    ] = None,
    recall_habituation_enabled: bool = False,
    recall_habituation_decay_window_ticks: int = 5,
    # #526 段階 3 + PR-A: 想起スロット (working memory) 配線。env で enable する。
    # default は「希少資源」化された slot 運用値 (N=4 / K=1 / L=8 / C=5 / 閾値=2)。
    recall_slot_enabled: bool = False,
    recall_slot_capacity: int = 4,
    recall_slot_insert_per_tick: int = 1,
    recall_slot_max_residence: int = 8,
    recall_slot_cooldown_ticks: int = 5,
    recall_slot_insert_score_threshold: int = 2,
    # #526 段階 3 PR-C: afterglow index 配線。env で enable。
    afterglow_enabled: bool = False,
    afterglow_capacity: int = 10,
    afterglow_max_residence: int = 10,
    # #526 後続 C1: world_object 名を index するために spot_interior_repo を
    # 任意で受け取る。実 runtime では SpotNode.interior が None で別 repo に
    # 保管されているため、prose から object 名を拾うにはこの経路が必要。
    # 未指定なら従来通り node.interior 経路だけを使う (= test stub 互換)。
    spot_interior_repo: Optional[Any] = None,
    # #526 後続 C2: chunk write 時に player の現在の runtime_context を返す
    # provider。注入時のみ動く (= default None で挙動不変)。
    runtime_context_provider: Optional[Callable[..., Any]] = None,
) -> EpisodicStack:
    """シナリオ非依存のエピソード記憶パイプラインを組み立てる。

    write 側 (chunk_coordinator) と read 側 (passive_recall + noun_matcher) を
    1 つの episode_store で共有する。LLM 駆動の reinterpretation や semantic
    promotion は組み込まない (将来必要になったら本家 builders を呼ぶ)。

    # 引数

    - ``scenario`` / ``graph``: 固有名詞 matcher の構築元。``getattr`` で参照する
      ので duck-type (world_runtime / survival_island どちらでも可)
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
    - ``semantic_enabled``: True で本家 ``build_episodic_memory_stack`` を再利用し
      link/semantic/promotion を組む (default False = 従来の episodic-only)
    - ``semantic_passive_top_k``: >0 で ``SemanticPassiveRecallService`` を作り
      prompt の【関連する学び】に出す。0 (gist のみ ON) は write-only 構成
    - ``semantic_gist_service`` / ``semantic_persona_resolver``: cluster 昇格時の
      LLM gist と persona。``build_episodic_memory_stack`` にそのまま渡す

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
    # promotion を組み、chunk_coordinator に link service を渡す。world_runtime の
    # 軽量 MVP では従来 semantic を持たなかったが、フラグで本家 builder に委譲する
    # ことで「学びを作る/出す」を実験経路でも動かせるようにする (#526 後続)。
    link_service: Optional[Any] = None
    episodic_semantic_promotion: Optional[Any] = None
    semantic_memory_store: Optional[Any] = None
    memory_link_store: Optional[Any] = None
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
        # promotion の根拠となる link graph も snapshot 用に公開する
        # (semantic entries だけ保存して link graph が空 fallback になるのを防ぐ)。
        memory_link_store = mem_stack.mem_bundle.link_store
    elif episode_store is None:
        episode_store = InMemorySubjectiveEpisodeStore()
    # #526 後続 Fix A: noun_matcher を chunk_coordinator より先に作り、
    # ChunkEpisodeDraftBuilder と passive_recall の両方に同じ matcher を
    # 渡すことで write/read 経路の cue 生成を対称化する。
    # #526 後続 C1: spot_interior_repo が渡されていれば、各 spot の
    # ``interior.objects`` から world_object 名も index される。
    noun_matcher = build_scenario_noun_matcher(
        scenario=scenario, graph=graph, spot_interior_repo=spot_interior_repo
    )
    chunk_coordinator = EpisodicChunkCoordinator(
        observation_buffer=observation_buffer,
        sliding_window_memory=sliding_window_memory,
        action_result_store=action_result_store,
        episodic_episode_store=episode_store,
        chunk_episode_draft_builder=ChunkEpisodeDraftBuilder(
            noun_matcher=noun_matcher,
            # #526 後続 C2: chunk write 時に runtime_context を取得する
            # provider を流す。未指定なら従来通り context 無しで cue を作る。
            runtime_context_provider=runtime_context_provider,
        ),
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
    # #526 段階 2: 慣化 sidecar (default off)。enable 時のみ store を作り、
    # passive_recall に注入する。prompt_builder 側にも同 store を渡して
    # 採用 episode の last_recalled_tick を retrieve 後に書き込む。
    recall_habituation_store: Optional["IEpisodicRecallHabituationStore"] = None
    if recall_habituation_enabled:
        from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
            InMemoryEpisodicRecallHabituationStore,
        )
        recall_habituation_store = InMemoryEpisodicRecallHabituationStore()
    # #526 段階 3: 想起スロット (working memory)。慣化と独立に on/off できる。
    # store + policy が揃ったときだけ passive_recall に注入される。
    recall_slot_store: Optional["IEpisodicRecallSlotStore"] = None
    recall_slot_policy_obj = None
    if recall_slot_enabled:
        from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
            InMemoryEpisodicRecallSlotStore,
            RecallSlotPolicy,
        )
        recall_slot_store = InMemoryEpisodicRecallSlotStore()
        recall_slot_policy_obj = RecallSlotPolicy(
            capacity=recall_slot_capacity,
            insert_per_tick=recall_slot_insert_per_tick,
            max_residence=recall_slot_max_residence,
            cooldown_ticks=recall_slot_cooldown_ticks,
            insert_score_threshold=recall_slot_insert_score_threshold,
        )
    # #526 段階 3 PR-C: afterglow index。slot off のときは afterglow も off に
    # 倒す (= 上層の slot が居ないと「ぼんやり」の階層構造の意味が薄れる)。
    afterglow_store: Optional["IAfterglowStore"] = None
    if afterglow_enabled and recall_slot_enabled:
        from ai_rpg_world.application.llm.services.afterglow_store import (
            InMemoryAfterglowStore,
        )
        afterglow_store = InMemoryAfterglowStore()
    passive_recall = EpisodicPassiveRecallRetrievalService(
        episode_store,
        being_attachment_resolver=being_attachment_resolver,
        default_world_id=default_world_id,
        habituation_store=recall_habituation_store,
        habituation_decay_window_ticks=recall_habituation_decay_window_ticks,
        slot_store=recall_slot_store,
        slot_policy=recall_slot_policy_obj,
        afterglow_store=afterglow_store,
        afterglow_capacity=afterglow_capacity,
        afterglow_max_residence=afterglow_max_residence,
    )
    # noun_matcher は上で chunk_coordinator 用に先に構築済 (Fix A)

    # semantic passive recall は top_k>0 のときだけ作る (= prompt の【関連する学び】)。
    # gist のみ ON (top_k=0) は「学びを作るが prompt には出さない」write-only 構成で、
    # ここで recall=None になるのは意図どおり (promotion は上で配線済)。
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

    # reinterpretation 拡張 (段1 / default OFF)。ON のとき recall_buffer + journal +
    # coordinator を直接構築する。escape は chunk_coordinator を既に上で持つので、
    # chunk_coordinator も束ねる汎用 stack builder は使わず、再解釈に必要な 3 点だけを
    # 組む (semantic とは独立 = mem_bundle 不要)。
    reinterpretation_coordinator: Optional[Any] = None
    reinterpretation_journal: Optional[Any] = None
    prompt_recall_buffer: Optional[Any] = None
    if reinterpretation_enabled:
        from ai_rpg_world.application.llm.services.episodic_reinterpretation_coordinator import (
            EpisodicReinterpretationCoordinator,
        )
        from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
            InMemoryEpisodicRecallBufferStore,
            InMemoryEpisodicReinterpretationJournalStore,
        )

        # escape は in-memory baseline なので具象 in-memory store を直接使う
        # (full wiring の SQLite 永続経路は実験 runtime では使わない)。
        recall_buffer = InMemoryEpisodicRecallBufferStore()
        reinterpretation_journal = InMemoryEpisodicReinterpretationJournalStore()
        reinterpretation_coordinator = EpisodicReinterpretationCoordinator(
            episode_store=episode_store,
            recall_buffer_store=recall_buffer,
            journal_store=reinterpretation_journal,
            completion=reinterpretation_completion,
            being_attachment_resolver=being_attachment_resolver,
            default_world_id=default_world_id,
        )
        # prompt が recall buffer を覗くのは completion が有効なときだけ。completion が
        # None だと再解釈 LLM が走らず buffer が pending を溜め続けるだけなので、
        # prompt builder には None を渡して無駄な query を防ぐ (full wiring と同じ
        # graceful fallback: _shared_builders.py の prompt_recall_buffer None 化)。
        prompt_recall_buffer = (
            recall_buffer if reinterpretation_completion is not None else None
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
        memory_link_store=memory_link_store,
        link_service=link_service,
        reinterpretation_coordinator=reinterpretation_coordinator,
        reinterpretation_journal=reinterpretation_journal,
        recall_buffer_store=prompt_recall_buffer,
        recall_habituation_store=recall_habituation_store,
        recall_habituation_decay_window_ticks=recall_habituation_decay_window_ticks,
        recall_slot_store=recall_slot_store,
        recall_slot_cooldown_ticks=recall_slot_cooldown_ticks,
        recall_slot_capacity=recall_slot_capacity,
        afterglow_store=afterglow_store,
        afterglow_capacity=afterglow_capacity,
        afterglow_max_residence=afterglow_max_residence,
    )


__all__ = [
    "EpisodicStack",
    "build_episodic_stack",
    "build_scenario_noun_matcher",
    "is_episodic_enabled",
    "is_episodic_subjective_enabled",
]
