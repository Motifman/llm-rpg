"""escape_game runtime に最小限の episodic memory pipeline を組み込む補助。

# 何のため

第19回実験 (Issue #283) の議論で出した「未接続スポット問題」を、
ハードコードな pathfinding ではなく **記憶からの emergent な route 想起**
で解こうとしている。pipeline 自体は本家 ``application/llm`` に揃って
いるが、escape_game demo は独自経路 (``_EscapeGameLlmWiring.run_turn``) を
通っていて wire されていない。

このモジュールは「scenario から最小限の episodic stack + 固有名詞 matcher を
組み立て、escape_game runtime に on/off で挿せる」薄い builder を提供する。
本家 ``application/llm/wiring/_shared_builders.py`` の重い builder (LLM 駆動
の reinterpretation や semantic promotion を含む) は使わず、**書き込み =
chunk coordinator** と **読み出し = passive recall + noun matcher** に
絞る。

# 構成

- ``EscapeEpisodicStack``: enable 時にまとめて返す dataclass
- ``build_escape_episodic_stack``: scenario + 共有 IO ストアを受け取り、
  chunk_coordinator / passive_recall / noun_matcher を組む
- ``is_episodic_enabled``: ``LLM_EPISODIC_ENABLED`` 環境変数のパース

# 設計判断

- **本家 builders に頼らない**: ``EpisodicMemoryLinkApplicationService`` や
  ``EpisodicSemanticClusterPromotionService`` は LLM 駆動の高度機能で
  escape_game の初期統合では over-engineering。後で必要になったら本家
  builders に乗り換える
- **In-memory のみ**: SQLite store 等は使わない。1 run 内で書き込み→読み
  出しが繋がれば十分
- **scenario 構造から固有名詞を抽出**: spot 名は graph から、character 名は
  player_spawns から取る。world_object / item は将来拡張で追加
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ai_rpg_world.application.llm.contracts.episodic_subjective_scheduler_port import (
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
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
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


# 環境変数名: 1 / true / yes / on (case-insensitive) で有効化
_TRUE_TOKENS = frozenset({"1", "true", "yes", "on"})


def is_episodic_enabled(env: Optional[dict[str, str]] = None) -> bool:
    """``LLM_EPISODIC_ENABLED`` を読んで episodic pipeline 有効化を判定。

    env を渡せばその dict を見る (テスト用)、None なら ``os.environ``。
    未設定 / unknown 値は False (= 完全に off で従来動作)。
    """
    source = env if env is not None else os.environ
    raw = source.get("LLM_EPISODIC_ENABLED", "")
    return raw.strip().lower() in _TRUE_TOKENS


_FALSE_TOKENS = frozenset({"0", "false", "no", "off"})


def is_episodic_subjective_enabled(env: Optional[dict[str, str]] = None) -> bool:
    """``LLM_EPISODIC_SUBJECTIVE_ENABLED`` を読んで LLM 主観文付与の有効化を判定。

    ``is_episodic_enabled`` が True のときに更にこの判定が True なら、
    ``EpisodicChunkSubjectiveFieldsService`` を chunk_coordinator に配線する。

    **既定値は True (= LLM 補完を有効化)**。第21回実験以降「エピソード記憶を
    使うときは LLM 補完も既定で走らせたい」という方針になったため、明示的に
    OFF にしたいときだけ ``LLM_EPISODIC_SUBJECTIVE_ENABLED=0`` (もしくは
    ``false`` / ``no`` / ``off``) を指定する。

    env を渡せばその dict を見る (テスト用)、None なら ``os.environ``。

    判定ルール:
    - 未設定 (key 自体が無い): True (既定 on)
    - True 表現 (1/true/yes/on): True
    - False 表現 (0/false/no/off): False
    - 不明な値: True (壊さず on 側に倒す)。``info`` レベルでは特に warn しない。
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
class EscapeEpisodicStack:
    """build_escape_episodic_stack の戻り値。on のときだけ作られる。

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


def build_scenario_noun_matcher(*, scenario: object, graph: object) -> IWorldNounMatcher:
    """scenario の spot 名 + キャラクター名 から ``IWorldNounMatcher`` を構築する。

    - spot: ``graph._spots.values()`` (= SpotNode) の name と spot_id
    - character: ``scenario.player_spawns`` の name と player_id

    将来 world_object / item の名前も追加可能だが、初期統合では spot と
    キャラクターだけで実害は出ない。
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


def build_escape_episodic_stack(
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
) -> EscapeEpisodicStack:
    """escape_game 用の最小限 episodic pipeline を組み立てる。

    write 側 (chunk_coordinator) と read 側 (passive_recall + noun_matcher) を
    1 つの episode_store で共有する。LLM 駆動の reinterpretation や semantic
    promotion は組み込まない (将来必要になったら本家 builders を呼ぶ)。

    Issue #283 後続: chunk write / passive recall を ``TraceEventKind`` で
    可視化するため、recorder の provider を chunk_coordinator に渡す。
    recall 側の trace は prompt_builder に直接 wire するので別経路。

    Issue #295 後続: ``chunk_subjective_fields_service`` (+ ``persona_block_provider``)
    が両方与えられたときだけ LLM 主観文付与経路を有効化する。draft が完成して
    store に書き込む直前に LLM で ``interpreted`` / ``recall_text`` を上書き
    する。LLM 失敗時はテンプレ既定値 (#305 で draft に既に入っている) のまま
    上書きされず流れる。
    """
    # episode_store を呼び出し側から渡せるようにしているのは、scheduler 経路
    # で「スケジューラと chunk_coordinator が同じ store を共有する必要がある」
    # ため (両者が違う store だと、worker が書き込んだ merged episode を
    # passive_recall が読めない)。
    if episode_store is None:
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
        # memory link service は未注入のまま (= リンクなし)。MVP 構成として最小。
    )
    passive_recall = EpisodicPassiveRecallRetrievalService(episode_store)
    noun_matcher = build_scenario_noun_matcher(scenario=scenario, graph=graph)
    return EscapeEpisodicStack(
        chunk_coordinator=chunk_coordinator,
        passive_recall=passive_recall,
        noun_matcher=noun_matcher,
        episode_store=episode_store,
        subjective_completion_scheduler=subjective_completion_scheduler,
    )


__all__ = [
    "EscapeEpisodicStack",
    "build_escape_episodic_stack",
    "build_scenario_noun_matcher",
    "is_episodic_enabled",
    "is_episodic_subjective_enabled",
]
