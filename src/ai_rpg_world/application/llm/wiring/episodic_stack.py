"""シナリオ非依存のエピソード記憶パイプライン builder。

# 何のため

第20-23回実験 (Issue #295/#311/#325/#328) で「沈黙の禁書庫」シナリオで
組み上げた episodic memory pipeline を、別シナリオ (survival_island_v2 等)
からも同じ paradigm で使えるように application 層に持ち上げたもの。
詳細な設計は ``docs/episodic_memory_overview.md`` 参照。

# 構成

- ``EpisodicStack``: 組み立てた pipeline をまとめて返す dataclass
- ``build_episodic_stack(...)``: scenario + 共有 IO ストアを受け取り、
  chunk_coordinator / noun_matcher を組む本体
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

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_rpg_world.being.domain.memory_turn_clock import (
        MemoryTurnReader,
    )

from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IShortTermMemory,
)
from ai_rpg_world.application.llm.scheduler import (
    IEpisodicSubjectiveCompletionScheduler,
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
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

# 環境変数名: 1 / true / yes / on (case-insensitive) で有効化
_TRUE_TOKENS = frozenset({"1", "true", "yes", "on"})
_FALSE_TOKENS = frozenset({"0", "false", "no", "off"})


def is_episodic_enabled(env: dict[str, str] | None = None) -> bool:
    """``LLM_EPISODIC_ENABLED`` を読んで episodic pipeline 有効化を判定。

    env を渡せばその dict を見る。None は古い呼び出し経路の取りこぼしとして
    失敗させる。
    未設定 / unknown 値は False (= 完全に off で従来動作)。
    """
    if env is None:
        raise TypeError(
            "env mapping is required; use ResolvedLlmRuntimeConfig.from_mapping()"
        )
    source = env
    raw = source.get("LLM_EPISODIC_ENABLED", "")
    return raw.strip().lower() in _TRUE_TOKENS


def is_episodic_subjective_enabled(env: dict[str, str] | None = None) -> bool:
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
    if env is None:
        raise TypeError(
            "env mapping is required; use ResolvedLlmRuntimeConfig.from_mapping()"
        )
    source = env
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
        chunk_coordinator: ``after_action_recorded(player_id, being_id)`` を呼ぶための
            書き込み側 service
        noun_matcher: observation prose 中の固有名詞を cue 化するマッチャ
        episode_store: 共有 episode store (chunk と主観補完が書く)
        subjective_completion_scheduler: 非同期 LLM 主観文付与のスケジューラ。
            shutdown 時に in-flight ジョブを drain するために保持する。
            未配線時は None。
    """

    chunk_coordinator: EpisodicChunkCoordinator
    noun_matcher: IWorldNounMatcher
    episode_store: EpisodicEpisodeRepository
    subjective_completion_scheduler: IEpisodicSubjectiveCompletionScheduler | None = None
    # memory link graph の store (semantic_enabled のときだけ、snapshot 用に公開)。
    # full 共有 builder (build_episodic_memory_stack) で組む。OFF のときは None。
    memory_link_store: Any | None = None
    # chunk_coordinator が TEMPORAL リンクを書くための link service。
    link_service: Any | None = None


def build_scenario_noun_matcher(
    *,
    scenario: object,
    graph: object,
    spot_interior_repo: Any | None = None,
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
    short_term_memory: IShortTermMemory,
    action_result_store: IActionResultStore,
    trace_recorder_provider: Callable[[], Any] | None = None,
    current_tick_provider: Callable[[], Any] | None = None,
    chunk_subjective_fields_service: EpisodicChunkSubjectiveFieldsService | None = None,
    persona_block_provider: Callable[[PlayerId], str] | None = None,
    subjective_completion_scheduler: IEpisodicSubjectiveCompletionScheduler | None = None,
    episode_store: EpisodicEpisodeRepository | None = None,
    semantic_enabled: bool = False,
    # #526 後続 C1: world_object 名を index するために spot_interior_repo を
    # 任意で受け取る。実 runtime では SpotNode.interior が None で別 repo に
    # 保管されているため、prose から object 名を拾うにはこの経路が必要。
    # 未指定なら従来通り node.interior 経路だけを使う (= test stub 互換)。
    spot_interior_repo: Any | None = None,
    # #526 後続 C2: chunk write 時に player の現在の runtime_context を返す
    # provider。注入時のみ動く (= default None で挙動不変)。
    runtime_context_provider: Callable[..., Any] | None = None,
    # episode store の永続化先 (ResolvedLlmRuntimeConfig.subjective_episode_db_path)。
    # None なら in-memory。semantic 有効時に build_episodic_memory_stack が store を
    # 解決する経路 (episode_store 未指定) でだけ効く。
    subjective_episode_db_path: str | None = None,
) -> EpisodicStack:
    """シナリオ非依存のエピソード記憶パイプラインを組み立てる。

    write 側 (chunk_coordinator) と主観補完の scheduler が 1 つの episode_store を
    共有する。LLM 駆動の reinterpretation や semantic
    promotion は組み込まない (将来必要になったら本家 builders を呼ぶ)。

    # 引数

    - ``scenario`` / ``graph``: 固有名詞 matcher の構築元。``getattr`` で参照する
      ので duck-type (world_runtime / survival_island どちらでも可)
    - ``observation_buffer`` / ``short_term_memory`` / ``action_result_store``:
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
      link の store を組む (default False = 従来の episodic-only)

    # 履歴

    - Issue #283 後続: chunk write / passive recall を ``TraceEventKind`` で
      可視化
    - Issue #295 後続: ``chunk_subjective_fields_service`` (+ persona_provider)
      が両方与えられたときだけ LLM 主観文付与経路を有効化
    - Issue #311 後続 (#310): 非同期 scheduler 経路
    """
    # episode_store を呼び出し側から渡せるようにしているのは、scheduler 経路
    # で「スケジューラと chunk_coordinator が同じ store を共有する必要がある」
    # ため (両者が違う store だと、worker が書き込んだ merged episode が
    # chunk の書いた episode と食い違う)。
    # semantic_enabled のときは full 共有 builder で link の store を組み、
    # chunk_coordinator に link service を渡す。
    link_service: Any | None = None
    memory_link_store: Any | None = None
    if semantic_enabled:
        # 循環 import 回避のため関数内 import。
        from ai_rpg_world.application.llm.wiring._shared_builders import (
            build_episodic_memory_stack,
        )

        mem_stack = build_episodic_memory_stack(
            episode_store,
            subjective_episode_db_path=subjective_episode_db_path,
        )
        # build_episodic_memory_stack が episode_store を解決して返す。以降は
        # 全コンポーネントがこの shared store を共有する (chunk write / recall
        # が同じ store を見る整合性条件)。
        episode_store = mem_stack.shared_episode_store
        link_service = mem_stack.mem_bundle.link_service
        # link graph を snapshot 用に公開する。
        memory_link_store = mem_stack.mem_bundle.link_store
    elif episode_store is None:
        episode_store = InMemorySubjectiveEpisodeStore()

    # #526 後続 Fix A: noun_matcher を chunk_coordinator より先に作り、
    # ChunkEpisodeDraftBuilder に渡す。
    # #526 後続 C1: spot_interior_repo が渡されていれば、各 spot の
    # ``interior.objects`` から world_object 名も index される。
    noun_matcher = build_scenario_noun_matcher(
        scenario=scenario, graph=graph, spot_interior_repo=spot_interior_repo
    )
    chunk_coordinator = EpisodicChunkCoordinator(
        observation_buffer=observation_buffer,
        short_term_memory=short_term_memory,
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
        # semantic OFF なら link service なし (= MVP の従来動作)。ON なら memory
        # link を chunk write 経路に通す。
        episodic_memory_link_service=link_service,
    )

    return EpisodicStack(
        chunk_coordinator=chunk_coordinator,
        noun_matcher=noun_matcher,
        episode_store=episode_store,
        subjective_completion_scheduler=subjective_completion_scheduler,
        memory_link_store=memory_link_store,
        link_service=link_service,
    )


__all__ = [
    "EpisodicStack",
    "build_episodic_stack",
    "build_scenario_noun_matcher",
    "is_episodic_enabled",
    "is_episodic_subjective_enabled",
]
