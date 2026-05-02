"""Episode Encoder と Passive Recall の goals ヒントに共通するコンテキストを組み立てる。"""

from __future__ import annotations

from typing import Callable, Optional

from ai_rpg_world.application.llm.contracts.dtos import EpisodeEncodingContextDto
from ai_rpg_world.application.llm.contracts.interfaces import (
    IIdentityMemoryStore,
    ILongTermMemoryStore,
    IWorkingMemoryStore,
)
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def build_episode_encoding_context_provider(
    *,
    player_profile_repository: PlayerProfileRepository,
    long_term_memory_store: ILongTermMemoryStore,
    working_memory_store: IWorkingMemoryStore,
    persona_block_provider: Optional[Callable[[PlayerId], str]] = None,
    identity_memory_store: Optional[IIdentityMemoryStore] = None,
    beliefs_fact_limit: int = 12,
    working_memory_limit: int = 8,
    max_chars_per_field: int = 2000,
    identity_statement_limit: int = 12,
) -> Callable[[PlayerId], EpisodeEncodingContextDto]:
    """プロフィール・作業メモ・長期事実・ペルソナ断片から `EpisodeEncodingContextDto` を返す。"""
    if not isinstance(player_profile_repository, PlayerProfileRepository):
        raise TypeError("player_profile_repository must be PlayerProfileRepository")
    if not isinstance(long_term_memory_store, ILongTermMemoryStore):
        raise TypeError("long_term_memory_store must be ILongTermMemoryStore")
    if not isinstance(working_memory_store, IWorkingMemoryStore):
        raise TypeError("working_memory_store must be IWorkingMemoryStore")
    if persona_block_provider is not None and not callable(persona_block_provider):
        raise TypeError("persona_block_provider must be callable or None")
    if identity_memory_store is not None and not isinstance(
        identity_memory_store, IIdentityMemoryStore
    ):
        raise TypeError("identity_memory_store must be IIdentityMemoryStore or None")
    if beliefs_fact_limit < 0:
        raise ValueError("beliefs_fact_limit must be 0 or greater")
    if working_memory_limit < 0:
        raise ValueError("working_memory_limit must be 0 or greater")
    if max_chars_per_field < 1:
        raise ValueError("max_chars_per_field must be 1 or greater")
    if identity_statement_limit < 0:
        raise ValueError("identity_statement_limit must be 0 or greater")

    def _truncate(s: str) -> str:
        s = s.strip()
        if len(s) <= max_chars_per_field:
            return s
        return s[: max_chars_per_field - 1] + "…"

    def _provide(player_id: PlayerId) -> EpisodeEncodingContextDto:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        profile = player_profile_repository.find_by_id(player_id)
        if profile is None:
            identity_only = ""
            if identity_memory_store is not None and identity_statement_limit > 0:
                ist = identity_memory_store.list_statements(
                    player_id, identity_statement_limit
                )
                if ist:
                    identity_only = _truncate(
                        "Identity（追記のみ）:\n" + "\n".join(reversed(ist))
                    )
            return EpisodeEncodingContextDto(
                persona_summary="（プレイヤープロフィール未取得）",
                current_goals="",
                current_beliefs="",
                identity_summary=identity_only,
            )
        role = profile.role.value
        race = profile.race.value
        element = profile.element.value
        name = profile.name.value
        base_persona = (
            f"名前: {name}。ロール: {role}。種族: {race}。属性: {element}。"
        )
        persona_extra = ""
        if persona_block_provider is not None:
            fragment = persona_block_provider(player_id)
            if isinstance(fragment, str) and fragment.strip():
                persona_extra = "\n" + fragment.strip()
        persona_summary = _truncate(base_persona + persona_extra)
        identity_summary = _truncate(
            f"自己位置づけ（プロフィール要約）: {role} の {race}。属性は {element}。"
        )
        if identity_memory_store is not None and identity_statement_limit > 0:
            ist = identity_memory_store.list_statements(
                player_id, identity_statement_limit
            )
            if ist:
                extra = "\n".join(reversed(ist))
                identity_summary = _truncate(
                    f"{identity_summary}\nIdentity（追記）:\n{extra}"
                )
        wm_lines = working_memory_store.get_recent(player_id, working_memory_limit)
        current_goals = _truncate(" / ".join(wm_lines)) if wm_lines else ""
        facts = long_term_memory_store.search_facts(
            player_id, keywords=None, limit=beliefs_fact_limit
        )
        if facts:
            belief_lines = [f.content.strip() for f in facts if f.content.strip()]
            current_beliefs = _truncate("\n".join(belief_lines))
        else:
            current_beliefs = ""
        return EpisodeEncodingContextDto(
            persona_summary=persona_summary,
            current_goals=current_goals,
            current_beliefs=current_beliefs,
            identity_summary=identity_summary,
        )

    return _provide
