"""強リンククラスタ検出とセマンティック記憶への昇格。

Phase 1b (#356 後続): LLM gist 生成 (``SemanticGistService``) を optional に
注入できるようにした。注入されていれば LLM 抽象化を試み、失敗時は
``_deterministic_gist`` (cluster 内 episode 本文の concat) にフォールバック
する。デフォルトは未注入 = 決定論 gist のみ (検証中の挙動保持)。
"""

from __future__ import annotations

import logging
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Sequence, Set
from uuid import uuid4

from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import EpisodicEpisodeRepository
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    effective_link_strength,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import MemoryLinkRepository
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry
from ai_rpg_world.domain.memory.semantic.repository.semantic_memory_repository import SemanticMemoryRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.episodic_promotion_frontier import EpisodicPromotionFrontier
from ai_rpg_world.application.llm.services.semantic_gist_service import (
    SemanticGistResult,
    SemanticGistService,
)


_logger = logging.getLogger(__name__)

MIN_CLUSTER_SIZE = 3
MIN_RECALL_COUNT = 3
MIN_EFFECTIVE_STRENGTH = 0.5


def _env_force_full_scan() -> bool:
    v = (os.environ.get("EPISODIC_PROMOTION_FORCE_FULL_SCAN") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _default_expansion_hops() -> int:
    raw = (os.environ.get("EPISODIC_PROMOTION_EXPANSION_HOPS") or "").strip()
    if not raw:
        return 4
    try:
        return max(0, int(raw))
    except ValueError:
        return 4


def _evidence_signature(episode_ids: Set[str]) -> str:
    return ",".join(sorted(episode_ids))


def _build_strong_adjacency(
    player_id: int,
    link_store: MemoryLinkRepository,
    now: datetime,
    *,
    being_id: Optional[BeingId] = None,
) -> Dict[str, Set[str]]:
    """実効強度 >= 閾値の無向辺を隣接リスト化する。

    Phase 3 Step 3c-2: dual-path。``being_id`` 指定時は
    ``list_all_links_for_being`` を使い、未指定なら legacy
    ``list_all_links_for_player`` を使う。Step 3c-3 で legacy 経路撤去予定。
    """
    adj: Dict[str, Set[str]] = {}
    if being_id is not None:
        all_links = link_store.list_all_links_for_being(being_id)
    else:
        all_links = link_store.list_all_links_for_player(player_id)
    for ln in all_links:
        eff = effective_link_strength(ln, now)
        if eff < MIN_EFFECTIVE_STRENGTH:
            continue
        a = ln.episode_id_a
        b = ln.episode_id_b
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def _incident_links_dual_path(
    link_store: MemoryLinkRepository,
    player_id: int,
    episode_id: str,
    *,
    now: datetime,
    being_id: Optional[BeingId],
) -> list[MemoryLink]:
    """dual-path: being_id があれば by_being、なければ legacy。"""
    if being_id is not None:
        return link_store.list_all_incident_links_by_being(
            being_id, episode_id, now=now
        )
    return link_store.list_all_incident_links(player_id, episode_id, now=now)


def _expand_frontier_nodes(
    player_id: int,
    link_store: MemoryLinkRepository,
    seeds: Set[str],
    now: datetime,
    max_hops: int,
    *,
    being_id: Optional[BeingId] = None,
) -> Set[str]:
    """強リンクのみを辿り、シードから最大 max_hops ホップで到達するノード集合。

    Phase 3 Step 3c-2: dual-path。``being_id`` 指定時は ``*_by_being`` API。
    """
    seeds_clean = {s.strip() for s in seeds if s.strip()}
    if not seeds_clean:
        return set()
    nodes = set(seeds_clean)
    frontier = set(seeds_clean)
    for _ in range(max(0, max_hops)):
        nxt: Set[str] = set()
        for n in frontier:
            for ln in _incident_links_dual_path(
                link_store, player_id, n, now=now, being_id=being_id
            ):
                if effective_link_strength(ln, now) < MIN_EFFECTIVE_STRENGTH:
                    continue
                other = ln.episode_id_b if ln.episode_id_a == n else ln.episode_id_a
                if other not in nodes:
                    nxt.add(other)
        if not nxt:
            break
        nodes |= nxt
        frontier = nxt
    return nodes


def _build_strong_adjacency_for_nodes(
    player_id: int,
    link_store: MemoryLinkRepository,
    nodes: Set[str],
    now: datetime,
    *,
    being_id: Optional[BeingId] = None,
) -> Dict[str, Set[str]]:
    """nodes に含まれる頂点のみを対象に、強リンクで誘導する無向グラフの隣接リスト。

    Phase 3 Step 3c-2: dual-path。``being_id`` 指定時は ``*_by_being`` API。
    """
    adj: Dict[str, Set[str]] = {}
    for n in nodes:
        for ln in _incident_links_dual_path(
            link_store, player_id, n, now=now, being_id=being_id
        ):
            if effective_link_strength(ln, now) < MIN_EFFECTIVE_STRENGTH:
                continue
            other = ln.episode_id_b if ln.episode_id_a == n else ln.episode_id_a
            if other in nodes:
                adj.setdefault(n, set()).add(other)
                adj.setdefault(other, set()).add(n)
    return adj


def _connected_components(adj: Dict[str, Set[str]]) -> list[Set[str]]:
    seen: Set[str] = set()
    out: list[Set[str]] = []
    for start in adj:
        if start in seen:
            continue
        comp: Set[str] = set()
        q: deque[str] = deque([start])
        while q:
            n = q.popleft()
            if n in seen:
                continue
            seen.add(n)
            comp.add(n)
            for nb in adj.get(n, ()):
                if nb not in seen:
                    q.append(nb)
        if comp:
            out.append(comp)
    return out


def _deterministic_gist(episodes: list[SubjectiveEpisode]) -> str:
    parts: list[str] = []
    for ep in episodes:
        body = (ep.interpreted or ep.recall_text or ep.what or "").strip()
        if body:
            parts.append(body)
    if not parts:
        return "（要約不能: 解釈文が空）"
    joined = " / ".join(parts)
    return joined[:1200]


@dataclass
class EpisodicSemanticClusterPromotionService:
    """
    プレイヤーのリンクグラフから閾値以上のクラスタを探し、セマンティックストアへ書き込む。

    Phase 1b: ``gist_service`` を optional に注入すると LLM 抽象化を行う。
    未注入なら従来の決定論 gist (cluster body concat) を使う。

    LLM 利用時の失敗 (API 例外 / JSON パース失敗 / 空応答) は warning ログを
    出した上で決定論 gist にフォールバックする (silent failure 防止)。

    ``persona_resolver`` は player_id → (player_name, persona_block) を返す
    callable。LLM gist の prompt 構築に必要。未指定なら ("Player {id}", "")。
    """

    episode_store: EpisodicEpisodeRepository
    link_store: MemoryLinkRepository
    semantic_store: SemanticMemoryRepository
    promotion_frontier: EpisodicPromotionFrontier | None = None
    expansion_hops: int = field(default_factory=_default_expansion_hops)
    # Phase 1b: LLM gist (optional)。注入時のみ LLM 抽象化を試みる。
    gist_service: Optional[SemanticGistService] = None
    persona_resolver: Optional[Callable[[int], tuple[str, str]]] = None
    # Phase 3 Step 3b-3: legacy player_id 経路は撤去済。Resolver + WorldId が
    # 未注入 / Being 未 provision の場合は silent no-op (= promotion は turn の
    # 副作用なので止めない。次回 turn で再試行される)。
    being_attachment_resolver: Optional[BeingAttachmentResolver] = None
    default_world_id: Optional[WorldId] = None

    def __post_init__(self) -> None:
        """SemanticPassiveRecallService と同じ型ガードを dataclass にも適用する
        (= caller 間の一貫性確保)。"""
        if self.being_attachment_resolver is not None and not isinstance(
            self.being_attachment_resolver, BeingAttachmentResolver
        ):
            raise TypeError(
                "being_attachment_resolver must be BeingAttachmentResolver"
            )
        if self.default_world_id is not None and not isinstance(
            self.default_world_id, WorldId
        ):
            raise TypeError("default_world_id must be WorldId")

    def _resolve_being_id(self, player_id: int) -> Optional[BeingId]:
        """Resolver + WorldId が両方揃っていれば being_id を引く。未注入 or
        Being 未 provision なら None (= 本 service の operation は silent no-op)。

        Phase 3 Step 3b-3: legacy player_id 経路は撤去。promotion は turn の
        副作用なので、解決できなければ「何もしない」 (= 次回 turn で再試行) が
        正しい挙動。
        """
        if self.being_attachment_resolver is None or self.default_world_id is None:
            return None
        return self.being_attachment_resolver.resolve_being_id(
            self.default_world_id, PlayerId(player_id)
        )

    def _register_signature(self, player_id: int, sig: str) -> bool:
        """being_id 経路で signature 登録。Being 未解決なら ``False`` (= 既存扱い
        で skip)。promotion を進ませないので結果として no-op になる。"""
        being_id = self._resolve_being_id(player_id)
        if being_id is None:
            return False
        return self.semantic_store.register_cluster_signature_if_new_by_being(
            being_id, sig
        )

    def _add_entry(self, player_id: int, entry: SemanticMemoryEntry) -> None:
        """being_id 経路で entry 追加。Being 未解決なら silent no-op。"""
        being_id = self._resolve_being_id(player_id)
        if being_id is None:
            return
        self.semantic_store.add_by_being(being_id, entry)

    def on_after_tool_turn(self, player_id: int, *, now: datetime | None = None) -> None:
        """LLM ツール実行 1 回成功後に呼び、昇格候補があればストアへ追加する。"""
        now = now or datetime.now(timezone.utc)
        force_full = _env_force_full_scan()
        # Phase 3 Step 3c-2: link 走査も dual-path 化。being_id が引ければ
        # ``*_by_being`` 経路、欠ければ legacy player_id 経路。
        being_id = self._resolve_being_id(player_id)
        if force_full or self.promotion_frontier is None:
            adj = _build_strong_adjacency(
                player_id, self.link_store, now, being_id=being_id
            )
        else:
            seeds = self.promotion_frontier.drain(player_id)
            if not seeds:
                adj = _build_strong_adjacency(
                    player_id, self.link_store, now, being_id=being_id
                )
            else:
                nodes = _expand_frontier_nodes(
                    player_id,
                    self.link_store,
                    seeds,
                    now,
                    self.expansion_hops,
                    being_id=being_id,
                )
                adj = _build_strong_adjacency_for_nodes(
                    player_id,
                    self.link_store,
                    nodes,
                    now,
                    being_id=being_id,
                )
        if not adj:
            return
        for comp in _connected_components(adj):
            if len(comp) < MIN_CLUSTER_SIZE:
                continue
            eps: list[SubjectiveEpisode] = []
            cluster_ok = True
            for eid in comp:
                ep = self.episode_store.get(player_id, eid)
                if ep is None or ep.recall_count < MIN_RECALL_COUNT:
                    cluster_ok = False
                    break
                eps.append(ep)
            if not cluster_ok or len(eps) < MIN_CLUSTER_SIZE:
                continue
            sig = _evidence_signature(comp)
            if not self._register_signature(player_id, sig):
                continue
            confidence = min(1.0, 0.4 + 0.1 * len(eps))
            gist_result = self._build_gist(player_id, eps)
            entry = SemanticMemoryEntry(
                entry_id=f"sem-{uuid4().hex}",
                player_id=player_id,
                text=gist_result.gist_text,
                evidence_episode_ids=tuple(sorted(comp)),
                confidence=confidence,
                created_at=now,
                importance_score=gist_result.importance_score,
                tags=gist_result.tags,
            )
            self._add_entry(player_id, entry)

    def _build_gist(
        self,
        player_id: int,
        cluster_episodes: Sequence[SubjectiveEpisode],
    ) -> SemanticGistResult:
        """LLM gist を試みる。注入無し / 失敗時は決定論 gist にフォールバック。

        どのパスを通っても呼び出し元は同じ ``SemanticGistResult`` を受け取る
        (importance_score / tags は決定論パスでは default)。
        """
        ordered = sorted(cluster_episodes, key=lambda e: e.occurred_at)
        if self.gist_service is None:
            return _deterministic_gist_result(ordered)

        player_name, persona_block = self._resolve_persona(player_id)
        try:
            return self.gist_service.generate(
                player_name=player_name,
                persona_block=persona_block,
                cluster_episodes=list(ordered),
                existing_related_semantic=None,
            )
        except (LlmApiCallException, ValueError) as e:
            _logger.warning(
                "Semantic gist LLM failed for player_id=%s; falling back to deterministic gist: %s",
                player_id,
                e,
            )
            return _deterministic_gist_result(ordered)
        except Exception as e:  # pragma: no cover - 想定外を一応握って fallback
            _logger.exception(
                "Unexpected error in semantic gist LLM (player_id=%s); falling back: %s",
                player_id,
                e,
            )
            return _deterministic_gist_result(ordered)

    def _resolve_persona(self, player_id: int) -> tuple[str, str]:
        if self.persona_resolver is None:
            return (f"Player {player_id}", "")
        try:
            name, persona = self.persona_resolver(player_id)
            return (name or f"Player {player_id}", persona or "")
        except Exception as e:
            _logger.warning(
                "persona_resolver failed for player_id=%s: %s",
                player_id,
                e,
            )
            return (f"Player {player_id}", "")


def _deterministic_gist_result(
    cluster_episodes: Sequence[SubjectiveEpisode],
) -> SemanticGistResult:
    """LLM 経路の戻り値形状に合わせて決定論 gist を SemanticGistResult に包む。

    importance_score / tags は default (5 / 空) のまま。
    """
    return SemanticGistResult(
        gist_text=_deterministic_gist(list(cluster_episodes)),
        importance_score=5,
        tags=(),
    )
