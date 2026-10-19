"""Phase 9-4c codec の単体テスト (sliding_window / obs_buffer / action_result)。"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    ActionResultStoreSubsystemCodec,
    ObservationBufferSubsystemCodec,
    ShortTermMemorySubsystemCodec,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _obs_entry(prose: str = "saw a wolf") -> ObservationEntry:
    return ObservationEntry(
        occurred_at=_NOW,
        output=ObservationOutput(
            prose=prose,
            structured={"event_kind": "encounter"},
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        ),
        game_time_label="Day 1 12:00",
    )


def _action_entry(action: str = "walk") -> ActionResultEntry:
    return ActionResultEntry(
        occurred_at=_NOW,
        action_summary=f"{action}_summary",
        result_summary="ok",
        success=True,
        tool_name=action,
        game_time_label="Day 1",
        inner_thought=f"{action} の前に状況を整理する",
        intention=f"{action} で先へ進む",
        emotion_hint="determination",
        occurred_tick=42,
    )


class TestSlidingWindowCodec:
    def test_sliding_window_none_op(self) -> None:
        """sliding window が None でも no op。"""
        runtime = SimpleNamespace(_short_term_memory=None)
        captured = ShortTermMemorySubsystemCodec().capture(runtime)
        assert captured["entries"] == []
        ShortTermMemorySubsystemCodec().restore(runtime, captured)  # no error


class TestObservationBufferCodec:
    def test_capture_restore_round_trip_2(self) -> None:
        src = DefaultObservationContextBuffer()
        src.append(PlayerId(1), _obs_entry("pending obs"))
        src_runtime = SimpleNamespace(_obs_buffer=src)
        captured = ObservationBufferSubsystemCodec().capture(src_runtime)

        dst = DefaultObservationContextBuffer()
        dst_runtime = SimpleNamespace(_obs_buffer=dst)
        ObservationBufferSubsystemCodec().restore(dst_runtime, captured)
        observations = dst.get_observations(PlayerId(1))
        assert len(observations) == 1
        assert observations[0].output.prose == "pending obs"

    def test_obs_buffer_none_op(self) -> None:
        """obs buffer が None でも no op。"""
        runtime = SimpleNamespace(_obs_buffer=None)
        captured = ObservationBufferSubsystemCodec().capture(runtime)
        assert captured["entries"] == []


class TestActionResultStoreCodec:
    def test_capture_restore_round_trip_3(self) -> None:
        src = DefaultActionResultStore()
        src._event_store.replace_action_results(
            PlayerId(1), [_action_entry("walk"), _action_entry("attack")]
        )
        src_runtime = SimpleNamespace(_action_result_store=src)
        captured = ActionResultStoreSubsystemCodec().capture(src_runtime)
        assert captured["schema_version"] == 5
        assert len(captured["entries"][0]["entries"]) == 2
        first_captured = captured["entries"][0]["entries"][0]
        assert first_captured["inner_thought"] == "walk の前に状況を整理する"
        assert "expected_result" not in first_captured
        assert first_captured["intention"] == "walk で先へ進む"
        assert first_captured["emotion_hint"] == "determination"
        assert "prediction_context_id" not in first_captured
        assert "in_context_belief_ids" not in first_captured
        assert "scene_boundary" not in first_captured

        dst = DefaultActionResultStore()
        dst_runtime = SimpleNamespace(_action_result_store=dst)
        ActionResultStoreSubsystemCodec().restore(dst_runtime, captured)
        results = dst.get_recent(PlayerId(1), limit=10)
        assert [e.action_summary for e in results] == [
            "walk_summary",
            "attack_summary",
        ]
        assert results[0].inner_thought == "walk の前に状況を整理する"
        assert results[0].intention == "walk で先へ進む"
        assert results[0].emotion_hint == "determination"
        assert results[0].occurred_tick == 42

    def test_restore_ignores_keys_of_snapshots_saved_before_removal(self) -> None:
        """expected_result / prediction_context_id / in_context_belief_ids / scene_boundary を書いていたころの v5 の snapshot も読め、ほかの欄はそのまま戻る (#1631)。"""
        src = DefaultActionResultStore()
        src._event_store.replace_action_results(PlayerId(1), [_action_entry("walk")])
        captured = ActionResultStoreSubsystemCodec().capture(SimpleNamespace(_action_result_store=src))
        old_entry = captured["entries"][0]["entries"][0]
        old_entry["expected_result"] = "walk で道が開ける"
        old_entry["prediction_context_id"] = "predctx-abc123"
        old_entry["in_context_belief_ids"] = ["sem-belief-1"]
        old_entry["scene_boundary"] = True
        dst = DefaultActionResultStore()

        ActionResultStoreSubsystemCodec().restore(SimpleNamespace(_action_result_store=dst), captured)

        (restored,) = dst.get_recent(PlayerId(1), limit=10)
        assert not hasattr(restored, "expected_result")
        assert not hasattr(restored, "prediction_context_id")
        assert not hasattr(restored, "in_context_belief_ids")
        assert not hasattr(restored, "scene_boundary")
        assert restored.inner_thought == "walk の前に状況を整理する"
        assert restored.intention == "walk で先へ進む"

    def test_action_result_store_none_op(self) -> None:
        """action result store が None でも no op。"""
        runtime = SimpleNamespace(_action_result_store=None)
        captured = ActionResultStoreSubsystemCodec().capture(runtime)
        assert captured["entries"] == []

class TestSlidingWindowCodecRollingSummaryBackend:
    """``SummarizingShortTermMemory`` backend での
    capture / restore を検証する (#471 後続)。L4 / L5 が失われると agent の
    self_image / world_view が空に戻るため、永続化は実験再現性に必須。"""

    def _make_rolling(self) -> Any:
        from ai_rpg_world.application.llm.services.summarizing_short_term_memory import (
            SummarizingShortTermMemory,
        )

        return SummarizingShortTermMemory(l4_keep_generations=3)

    def test_includes_all_l_one_raw_l4_l_five(self) -> None:
        """L1raw と L4 と L5 が全部往復する。"""
        from ai_rpg_world.domain.memory.short_term.value_object.l4_mid_summary import (
            L4MidSummary,
        )
        from ai_rpg_world.domain.memory.short_term.value_object.l5_long_summary import (
            L5LongSummary,
        )

        src = self._make_rolling()
        # L1 raw に 3 件 (= soft_cap 未満なので畳まれない)
        src.append(PlayerId(1), _obs_entry("raw-1"))
        src.append(PlayerId(1), _obs_entry("raw-2"))
        src.append(PlayerId(2), _obs_entry("p2-raw"))
        # L4 を手で 1 世代 install
        src._install_l4(
            L4MidSummary(
                summary_id="l4-test",
                player_id=1,
                raw_count=15,
                generated_at=_NOW,
                compressed_activity="3 時間山を登った",
                emotional_summary="達成感がある",
                unresolved=("狼煙の燃料",),
                is_fallback=False,
            )
        )
        # L5 も書き込む (= _install_l4 は L4 evict 時のみ L5 trigger なので直接書く)
        with src._long_lock:
            src._long[1] = L5LongSummary(
                summary_id="l5-test",
                player_id=1,
                generation_index=2,
                generated_at=_NOW,
                self_image="探索者カイ",
                world_view="火を絶やしてはならない島",
                is_fallback=False,
            )
            src._long_gen_index[1] = 2

        src_runtime = SimpleNamespace(_short_term_memory=src)
        captured = ShortTermMemorySubsystemCodec().capture(src_runtime)
        assert captured["mode"] == "rolling_summary"
        assert captured["schema_version"] == 2
        assert len(captured["raw_entries"]) == 2  # player 1, 2
        assert len(captured["mid_summaries"][0]["summaries"]) == 1
        assert captured["long_summaries"][0]["summary"]["self_image"] == "探索者カイ"
        assert captured["long_gen_indices"][0]["index"] == 2

        # 別 instance に restore
        dst = self._make_rolling()
        dst.append(PlayerId(99), _obs_entry("stale"))  # 復元で消える
        dst_runtime = SimpleNamespace(_short_term_memory=dst)
        ShortTermMemorySubsystemCodec().restore(dst_runtime, captured)

        assert dst.get_recent(PlayerId(99), limit=10) == []
        p1_recent = dst.get_recent(PlayerId(1), limit=10)
        assert [e.output.prose for e in p1_recent] == ["raw-2", "raw-1"]  # 新しい順
        assert dst._mid_generations(1)[0].compressed_activity == "3 時間山を登った"
        l5 = dst._long_summary(1)
        assert l5 is not None
        assert l5.self_image == "探索者カイ"
        assert dst._long_gen_index[1] == 2

    def test_sliding_v1_snapshot_rolling_backend_load(self) -> None:
        """v1 (sliding 専用) フォーマットを rolling backend が読めるか (= マイグレーション互換)。"""
        v1_data = {
            "schema_version": 1,
            "entries": [
                {
                    "player_id": 1,
                    "entries": [
                        {
                            "occurred_at": _NOW.isoformat(),
                            "game_time_label": "Day 1",
                            "output": {
                                "prose": "migrated",
                                "structured": {},
                                "observation_category": "self_only",
                                "schedules_turn": False,
                                "breaks_movement": False,
                            },
                        }
                    ],
                }
            ],
        }
        dst = self._make_rolling()
        runtime = SimpleNamespace(_short_term_memory=dst)
        ShortTermMemorySubsystemCodec().restore(runtime, v1_data)
        recent = dst.get_recent(PlayerId(1), limit=5)
        assert [e.output.prose for e in recent] == ["migrated"]
        assert dst._long_summary(1) is None  # v1 には L5 が無い

    def test_sliding_v2_snapshot_replaces_observations_and_clears_summaries(self) -> None:
        """固定容量の短期記憶で保存した v2 の mode: sliding_window を読むと、観測は保存されたものに置き換わり、L4 / L5 は空になる。"""
        from ai_rpg_world.domain.memory.short_term.value_object.l5_long_summary import (
            L5LongSummary,
        )

        v2_data = {
            "schema_version": 2,
            "mode": "sliding_window",
            "entries": [
                {
                    "player_id": 1,
                    "entries": [
                        {
                            "occurred_at": _NOW.isoformat(),
                            "game_time_label": "Day 1",
                            "output": {
                                "prose": "sliding で保存した観測",
                                "structured": {},
                                "observation_category": "self_only",
                                "schedules_turn": False,
                                "breaks_movement": False,
                            },
                        }
                    ],
                }
            ],
        }
        dst = self._make_rolling()
        dst.append(PlayerId(99), _obs_entry("stale"))
        with dst._long_lock:
            dst._long[1] = L5LongSummary(
                summary_id="l5-stale",
                player_id=1,
                generation_index=1,
                generated_at=_NOW,
                self_image="復元前の自己像",
                world_view="復元前の世界観",
                is_fallback=False,
            )
            dst._long_gen_index[1] = 1

        ShortTermMemorySubsystemCodec().restore(
            SimpleNamespace(_short_term_memory=dst), v2_data
        )

        assert dst.get_recent(PlayerId(99), limit=10) == []
        recent = dst.get_recent(PlayerId(1), limit=5)
        assert [e.output.prose for e in recent] == ["sliding で保存した観測"]
        assert dst._mid_generations(1) == []
        assert dst._long_summary(1) is None
        assert dst._long_gen_index == {}

    def test_unknown_mode_raises_exception(self) -> None:
        """mode が rolling_summary でも sliding_window でもない payload は ValueError で拒む。"""
        dst = self._make_rolling()

        with pytest.raises(ValueError, match="mode"):
            ShortTermMemorySubsystemCodec().restore(
                SimpleNamespace(_short_term_memory=dst),
                {"schema_version": 2, "mode": "unknown", "entries": []},
            )


class TestUnsupportedSchemaVersion:
    @pytest.mark.parametrize(
        "codec_cls",
        [
            ShortTermMemorySubsystemCodec,
            ObservationBufferSubsystemCodec,
            ActionResultStoreSubsystemCodec,
        ],
    )
    def test_unsupported_schema_version_raises_exception(self, codec_cls) -> None:
        """未サポート schemaversion は例外。"""
        codec = codec_cls()
        with pytest.raises(ValueError, match="schema_version"):
            codec.restore(SimpleNamespace(), {"schema_version": 999})
