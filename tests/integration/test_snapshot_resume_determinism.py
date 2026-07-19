"""Snapshot capture → restore の決定性テスト (Phase 8 / Issue #470)。

LLM 出力自体は非決定論的なので「同じ run を 2 回回せば同じ trace になる」と
いう strong determinism は担保できない。代わりに **LLM への入力が同じである
ことを保証する** ための property:

  P1. snapshot を capture → 別の clean stack で restore すると、再度 capture
      した payload は元と **bit-identical** (= JSON-level equality)
  P2. snapshot を 2 回 restore しても結果は同じ (= idempotent restore)
  P3. capture → JSON 文字列に直 → JSON dict 化 → 構築した BeingSnapshot は
      元の BeingSnapshot と等価 (= 経路の対称性)
  P4. cross-scenario transfer で別 scenario に読み込んでも、Being の
      aggregate 状態 + memory store 内容は変わらない (= scenario 名の違いが
      restore 内容に影響しない)

これらが成立する限り、「同じ LLM model + temperature + prompt 構成」を使えば
原理的に決定論的になる (= LLM 側の非決定性しか残らない)。

prompt ordering / cache 議論との関係:
- snapshot は **memory store の中身だけ** を保存する
- ``PROMPT_SECTION_ORDER`` / ``SHORT_TERM_MEMORY_KIND`` / ``LLM_MODEL`` 等の
  env-var は snapshot に含まれない (= 別レイヤーの設定)
- したがって snapshot の決定性は prompt config と直交する。test も
  memory store 内容に focus する
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.being.experiment_snapshot_session import (
    ExperimentSnapshotSession,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
    InMemoryMemoryLinkStore,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
    InMemoryEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.application.llm.services.in_memory_memo_store import (
    InMemoryMemoStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import (
    EpisodeAction,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import (
    EpisodeLocation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import (
    EpisodeSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
    EpisodicReinterpretationEntry,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_status import (
    EpisodicReinterpretationStatus,
)
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import (
    DEFAULT_SINGLE_WORLD_ID,
)
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


_FIXED_TIME = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _make_stack():
    """新規 in-memory store stack + wiring stub を返す。"""
    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    provisioning = BeingProvisioningService(repo)
    wiring = SimpleNamespace(
        memo_store=InMemoryMemoStore(),
        semantic_memory_store=InMemorySemanticMemoryStore(),
        memory_link_store=InMemoryMemoryLinkStore(),
        episodic_recall_buffer_store=InMemoryEpisodicRecallBufferStore(),
        episodic_reinterpretation_journal_store=InMemoryEpisodicReinterpretationJournalStore(),
        episodic_episode_store=InMemorySubjectiveEpisodeStore(),
        being_repository=repo,
        being_attachment_resolver=resolver,
    )
    return wiring, provisioning


def _populate_all_stores(wiring: SimpleNamespace, being_id: BeingId) -> None:
    """全 5 memory store に決定論的データを投入する。

    決定論性のため、すべての datetime は ``_FIXED_TIME`` 固定。これにより
    capture → restore → recapture で payload が bit-identical になる。
    """
    # memo: 完了済 + 未完了の混在
    m1 = wiring.memo_store.add_by_being(being_id, "active task")
    m2 = wiring.memo_store.add_by_being(being_id, "done task")
    wiring.memo_store.complete_by_being(being_id, m2)

    # semantic: entries + cluster signatures
    wiring.semantic_memory_store.add_by_being(
        being_id,
        SemanticMemoryEntry(
            entry_id="se-1",
            player_id=1,
            text="森は東に位置する",
            evidence_episode_ids=("ep-1", "ep-2"),
            confidence=0.85,
            created_at=_FIXED_TIME,
            importance_score=7,
            tags=("location", "forest"),
        ),
    )
    wiring.semantic_memory_store.register_cluster_signature_if_new_by_being(
        being_id, "sig-forest"
    )
    wiring.semantic_memory_store.register_cluster_signature_if_new_by_being(
        being_id, "sig-village"
    )

    # memory_link
    wiring.memory_link_store.upsert_link_by_being(
        being_id,
        MemoryLink(
            link_id="mlk-1",
            player_id=1,
            episode_id_a="ep-1",
            episode_id_b="ep-2",
            link_type=MemoryLinkType.CO_RECALL,
            strength=0.7,
            co_activation_count=3,
            created_at=_FIXED_TIME,
            last_activated_at=_FIXED_TIME,
            decay_rate=0.001,
        ),
    )

    # recall_buffer
    wiring.episodic_recall_buffer_store.append_by_being(
        being_id,
        EpisodicRecallObservation(
            recall_id="r-1",
            player_id=1,
            episode_id="ep-1",
            recalled_at=_FIXED_TIME,
            source_axes=("temporal", "spatial"),
            current_state_snapshot="state-snap",
            recent_events_snapshot="events-snap",
            persona_snapshot="persona-snap",
            situation_cues=("cue-a", "cue-b"),
            turn_index=5,
        ),
    )

    # reinterpretation_journal
    wiring.episodic_reinterpretation_journal_store.put_active_by_being(
        being_id,
        EpisodicReinterpretationEntry(
            entry_id="je-1",
            player_id=1,
            episode_id="ep-1",
            created_at=_FIXED_TIME,
            turn_index=5,
            current_interpretation="interp",
            current_recall_text="recall text",
            source_recall_ids=("r-1",),
            status=EpisodicReinterpretationStatus.ACTIVE,
        ),
    )

    # episodic_episode
    wiring.episodic_episode_store.put_by_being(
        being_id,
        SubjectiveEpisode(
            episode_id="ep-1",
            player_id=1,
            occurred_at=_FIXED_TIME,
            game_time_label="day 1",
            source=EpisodeSource(event_ids=("e1", "e2")),
            location=EpisodeLocation(spot_id=42, tile_area_ids=(1, 2)),
            action=EpisodeAction(tool_name="walk"),
            who=("ada", "ben"),
            what="explored forest",
            why="curious",
            observed="trees and birds",
            expected="silence",
            outcome="encountered wolf",
            prediction_error="surprise",
            felt="afraid",
            interpreted="dangerous area",
            cues=(
                EpisodicCue(
                    axis="place_spot",
                    value="42",
                    source=EpisodicCueSource.RUNTIME_CONTEXT,
                ),
            ),
            recall_text="recall body",
            recall_count=2,
            last_recalled_at=_FIXED_TIME,
        ),
    )


def _strip_volatile_metadata(payload_dict: dict) -> dict:
    """``captured_at`` は capture 時刻なので毎回変わる。比較前に取り除く。

    Phase 7 で追加した ``_metadata.captured_at`` は雑談用情報なので、
    determinism 比較からは外す (= 内容の bit-identical 性だけ見る)。
    """
    out = dict(payload_dict)
    meta = out.get("_metadata")
    if isinstance(meta, dict):
        cleaned = {k: v for k, v in meta.items() if k != "captured_at"}
        out["_metadata"] = cleaned
    return out


class TestSnapshotRoundTripDeterminism:
    """P1: capture → restore → recapture で payload が bit-identical。"""

    def test_all_five_store_capture_restore_recapture_matches(
        self, tmp_path: Path
    ) -> None:
        """全 5 store を埋めた capture restore recapture で一致。"""
        src_wiring, src_prov = _make_stack()
        src_prov.ensure_attached(PlayerId(1))
        being_id = src_wiring.being_attachment_resolver.resolve_being_id(
            DEFAULT_SINGLE_WORLD_ID, PlayerId(1)
        )
        assert being_id is not None
        _populate_all_stores(src_wiring, being_id)

        src_session = ExperimentSnapshotSession(
            wiring_result=src_wiring, snapshot_dir=tmp_path / "src"
        )
        src_session.capture_all([PlayerId(1)], source_scenario="test_scenario")
        src_payload = _strip_volatile_metadata(
            json.loads((tmp_path / "src" / f"{being_id.value}.json").read_text())
        )

        # clean stack に restore → recapture
        dst_wiring, _ = _make_stack()
        dst_session = ExperimentSnapshotSession(
            wiring_result=dst_wiring, snapshot_dir=tmp_path / "dst"
        )
        dst_session.restore_all_from_dir(
            tmp_path / "src", current_scenario="test_scenario"
        )
        dst_session.capture_all([PlayerId(1)], source_scenario="test_scenario")
        dst_payload = _strip_volatile_metadata(
            json.loads((tmp_path / "dst" / f"{being_id.value}.json").read_text())
        )

        assert src_payload == dst_payload, (
            "capture → restore → recapture で payload が一致しない。"
            "snapshot codec の決定性が壊れている可能性がある。"
        )


class TestRestoreIdempotency:
    """P2: 同じ snapshot を 2 回 restore しても結果は同じ。"""

    def test_two_restore_capture_same(self, tmp_path: Path) -> None:
        """2回 restore しても capture 結果が同じ。"""
        src_wiring, src_prov = _make_stack()
        src_prov.ensure_attached(PlayerId(1))
        being_id = src_wiring.being_attachment_resolver.resolve_being_id(
            DEFAULT_SINGLE_WORLD_ID, PlayerId(1)
        )
        assert being_id is not None
        _populate_all_stores(src_wiring, being_id)

        ExperimentSnapshotSession(
            wiring_result=src_wiring, snapshot_dir=tmp_path / "src"
        ).capture_all([PlayerId(1)])

        # 1 回目 restore + recapture
        dst1_wiring, _ = _make_stack()
        dst1_session = ExperimentSnapshotSession(
            wiring_result=dst1_wiring, snapshot_dir=tmp_path / "dst1"
        )
        dst1_session.restore_all_from_dir(tmp_path / "src")
        dst1_session.capture_all([PlayerId(1)])
        payload_1 = _strip_volatile_metadata(
            json.loads(
                (tmp_path / "dst1" / f"{being_id.value}.json").read_text()
            )
        )

        # 2 回目: 同じ snapshot を再度 restore (= dst1 に上書き)
        dst1_session.restore_all_from_dir(tmp_path / "src")
        dst1_session.capture_all([PlayerId(1)])
        payload_2 = _strip_volatile_metadata(
            json.loads(
                (tmp_path / "dst1" / f"{being_id.value}.json").read_text()
            )
        )

        assert payload_1 == payload_2, "restore が冪等でない"


class TestRestoreInsensitivityToScenarioName:
    """P4: cross-scenario でも Being aggregate + memory 内容は変わらない。"""

    def test_different_scenario_restore_payload_same(
        self, tmp_path: Path
    ) -> None:
        """別 scenario で restore しても payload 内容は同一。"""
        src_wiring, src_prov = _make_stack()
        src_prov.ensure_attached(PlayerId(1))
        being_id = src_wiring.being_attachment_resolver.resolve_being_id(
            DEFAULT_SINGLE_WORLD_ID, PlayerId(1)
        )
        assert being_id is not None
        _populate_all_stores(src_wiring, being_id)

        ExperimentSnapshotSession(
            wiring_result=src_wiring, snapshot_dir=tmp_path / "src"
        ).capture_all([PlayerId(1)], source_scenario="forest_world")

        # 別 scenario に restore
        dst_wiring, _ = _make_stack()
        dst_session = ExperimentSnapshotSession(
            wiring_result=dst_wiring, snapshot_dir=tmp_path / "dst"
        )
        dst_session.restore_all_from_dir(
            tmp_path / "src", current_scenario="desert_world"
        )
        # recapture with NEW scenario name
        dst_session.capture_all([PlayerId(1)], source_scenario="desert_world")

        # 比較: source_scenario は変わるはず (= forest → desert)、それ以外は同一。
        src_payload = json.loads(
            (tmp_path / "src" / f"{being_id.value}.json").read_text()
        )
        dst_payload = json.loads(
            (tmp_path / "dst" / f"{being_id.value}.json").read_text()
        )

        # source_scenario 以外を 一致確認
        src_clean = _strip_volatile_metadata(src_payload)
        dst_clean = _strip_volatile_metadata(dst_payload)
        src_clean["_metadata"]["source_scenario"] = "X"
        dst_clean["_metadata"]["source_scenario"] = "X"
        assert src_clean == dst_clean, (
            "cross-scenario restore で Being aggregate / memory 内容が変わった "
            "= scenario 名が data に影響している (= determinism 違反)"
        )


class TestSchemaStrictness:
    """P5 (schema 進化 (a) 厳格モード): 未知 schema_version は load 失敗。"""

    def test_being_snapshot_unknown_snapshot_version_raises_exception(
        self, tmp_path: Path
    ) -> None:
        """JSON ファイルの ``snapshot_version`` が SUPPORTED_VERSIONS 外なら例外。"""
        from ai_rpg_world.domain.being.exception.being_exceptions import (
            BeingSnapshotVersionException,
        )

        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        (bad_dir / "being_w1_p1.json").write_text(
            json.dumps(
                {
                    "being_id_value": "being_w1_p1",
                    "identity_name": "agent",
                    "identity_first_person": "わたし",
                    "attachment_world_id": 1,
                    "attachment_player_id": 1,
                    "declared_memory_kinds": [],
                    "snapshot_version": 999,
                    "memory_payload_json": None,
                }
            ),
            encoding="utf-8",
        )
        wiring, _ = _make_stack()
        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "x"
        )
        with pytest.raises(BeingSnapshotVersionException):
            session.restore_all_from_dir(bad_dir)

    def test_memory_payload_unknown_schema_version_raises_exception(
        self, tmp_path: Path
    ) -> None:
        """payload JSON の ``schema_version`` が SUPPORTED_PAYLOAD_SCHEMA_VERSIONS 外なら例外。"""
        from ai_rpg_world.application.being.being_memory_snapshot_service import (
            BeingMemoryPayloadSchemaError,
        )

        bad_payload = json.dumps(
            {"schema_version": 999, "memo": []}, ensure_ascii=False
        )
        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        (bad_dir / "being_w1_p1.json").write_text(
            json.dumps(
                {
                    "being_id_value": "being_w1_p1",
                    "identity_name": "agent",
                    "identity_first_person": "わたし",
                    "attachment_world_id": 1,
                    "attachment_player_id": 1,
                    "declared_memory_kinds": [],
                    "snapshot_version": 2,
                    "memory_payload_json": bad_payload,
                }
            ),
            encoding="utf-8",
        )
        wiring, _ = _make_stack()
        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "x"
        )
        with pytest.raises(BeingMemoryPayloadSchemaError):
            session.restore_all_from_dir(bad_dir)
