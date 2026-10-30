"""SNS通知の本文は全体予算・優先順・表示確定の規則に従う。"""

from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.chunk_encoding import UnifiedRecentEventEntry
from ai_rpg_world.application.llm.services.recent_events_formatter import DefaultRecentEventsFormatter
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.social.public_sns.contracts import PublicSnsNotificationDto
from ai_rpg_world.application.social.public_sns.prompt_projection import (
    PublicSnsPromptProjection,
    notification_observation,
)
from ai_rpg_world.application.social.public_sns.retained_screen import PublicSnsScreenStore


def test_reply_body_precedes_newer_likes_under_total_budget():
    """古い返信本文を新しい大量いいねより優先し、保存した原文は変えない。"""
    projection = PublicSnsPromptProjection(PublicSnsScreenStore(), budget_chars=800)
    entries = []
    for index, kind in enumerate(["reply", *(["like"] * 10)]):
        dto = PublicSnsNotificationDto(
            kind,
            "相手",
            datetime.now(timezone.utc),
            f"notice-{index}",
            "actor-id",
            "target-id",
            "直接答える本文" if kind == "reply" else None,
        )
        output = notification_observation(dto, None)
        entries.append(UnifiedRecentEventEntry.from_observation(ObservationEntry(datetime.now(timezone.utc), output)))
        projection.note_incoming(1, dto.notification_id)
    rendered_entries, ids = projection.project(1, entries)
    rendered = DefaultRecentEventsFormatter().format_unified_entries(rendered_entries)
    assert len(rendered) <= 800
    assert "直接答える本文" in rendered
    assert "notice-0" in ids
    assert projection.pending_count(1) == 11
    assert "直接答える本文" in entries[0].payload.output.prose
    projection.confirm_shown(1, ids)
    assert "直接答える本文" not in DefaultRecentEventsFormatter().format_unified_entries(
        projection.project(1, entries)[0]
    )


def test_large_name_and_source_metadata_do_not_expand_prompt_budget():
    """長い表示名は短縮し、出典の内部情報は描画予算へ漏らさない。"""
    projection = PublicSnsPromptProjection(PublicSnsScreenStore(), budget_chars=800)
    dto = PublicSnsNotificationDto(
        "reply", "名" * 9000, datetime.now(timezone.utc), "notice", "actor-id", "target-id", "全文"
    )
    output = notification_observation(dto, None)
    output.structured["extra_source_metadata"] = "内部情報" * 9000
    entry = UnifiedRecentEventEntry.from_observation(ObservationEntry(datetime.now(timezone.utc), output))
    projection.note_incoming(1, "notice")
    rendered = DefaultRecentEventsFormatter().format_unified_entries(projection.project(1, [entry])[0])
    assert len(rendered) <= 800
    assert "内部情報" not in rendered
    assert "全文" in rendered
