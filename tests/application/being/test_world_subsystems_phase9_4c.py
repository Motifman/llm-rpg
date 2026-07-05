"""Phase 9-4c codec の単体テスト (sliding_window / obs_buffer / action_result)。"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.application.being.world_subsystems import (
    ActionResultStoreSubsystemCodec,
    ObservationBufferSubsystemCodec,
    SlidingWindowMemorySubsystemCodec,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
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
        expected_result=f"{action} で道が開ける",
        intention=f"{action} で先へ進む",
        emotion_hint="determination",
        occurred_tick=42,
        prediction_context_id="predctx-abc123",
        in_context_belief_ids=("sem-belief-1", "sem-belief-2"),
    )


class TestSlidingWindowCodec:
    def test_capture_restore_round_trip(self) -> None:
        src = DefaultSlidingWindowMemory()
        src.append(PlayerId(1), _obs_entry("first"))
        src.append(PlayerId(1), _obs_entry("second"))
        src.append(PlayerId(2), _obs_entry("p2 only"))
        src_runtime = SimpleNamespace(_sliding_window=src)
        captured = SlidingWindowMemorySubsystemCodec().capture(src_runtime)
        assert len(captured["entries"]) == 2

        dst = DefaultSlidingWindowMemory()
        dst.append(PlayerId(99), _obs_entry("stale"))  # 復元で消える
        dst_runtime = SimpleNamespace(_sliding_window=dst)
        SlidingWindowMemorySubsystemCodec().restore(dst_runtime, captured)

        assert PlayerId(99).value not in dst._store
        p1 = dst.get_recent(PlayerId(1), limit=10)
        assert [e.output.prose for e in p1] == ["first", "second"]

    def test_sliding_window_が_None_でも_no_op(self) -> None:
        runtime = SimpleNamespace(_sliding_window=None)
        captured = SlidingWindowMemorySubsystemCodec().capture(runtime)
        assert captured["entries"] == []
        SlidingWindowMemorySubsystemCodec().restore(runtime, captured)  # no error


class TestObservationBufferCodec:
    def test_capture_restore_round_trip(self) -> None:
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

    def test_obs_buffer_が_None_でも_no_op(self) -> None:
        runtime = SimpleNamespace(_obs_buffer=None)
        captured = ObservationBufferSubsystemCodec().capture(runtime)
        assert captured["entries"] == []


class TestActionResultStoreCodec:
    def test_capture_restore_round_trip(self) -> None:
        src = DefaultActionResultStore()
        # DefaultActionResultStore.append のシグネチャは複雑なので直接 _store
        # に詰める (= test 用)。実本番では append 経由で乗る。
        src._store[1] = [_action_entry("walk"), _action_entry("attack")]
        src_runtime = SimpleNamespace(_action_result_store=src)
        captured = ActionResultStoreSubsystemCodec().capture(src_runtime)
        assert captured["schema_version"] == 5
        assert len(captured["entries"][0]["entries"]) == 2
        first_captured = captured["entries"][0]["entries"][0]
        assert first_captured["expected_result"] == "walk で道が開ける"
        assert first_captured["intention"] == "walk で先へ進む"
        assert first_captured["emotion_hint"] == "determination"
        assert first_captured["prediction_context_id"] == "predctx-abc123"
        assert first_captured["in_context_belief_ids"] == [
            "sem-belief-1",
            "sem-belief-2",
        ]

        dst = DefaultActionResultStore()
        dst_runtime = SimpleNamespace(_action_result_store=dst)
        ActionResultStoreSubsystemCodec().restore(dst_runtime, captured)
        results = dst.get_recent(PlayerId(1), limit=10)
        assert [e.action_summary for e in results] == [
            "walk_summary",
            "attack_summary",
        ]
        assert results[0].expected_result == "walk で道が開ける"
        assert results[0].intention == "walk で先へ進む"
        assert results[0].emotion_hint == "determination"
        assert results[0].occurred_tick == 42
        assert results[0].prediction_context_id == "predctx-abc123"
        assert results[0].in_context_belief_ids == ("sem-belief-1", "sem-belief-2")

    def test_action_result_store_が_None_でも_no_op(self) -> None:
        runtime = SimpleNamespace(_action_result_store=None)
        captured = ActionResultStoreSubsystemCodec().capture(runtime)
        assert captured["entries"] == []

    def test_prediction_context_id_欠損の旧スキーマ相当データは_None_に倒れる(self) -> None:
        """v4 導入前 (= キー自体が無い) payload を decode しても例外にならず None になる。

        schema_version チェック自体は旧 snapshot を弾く仕様 (バージョン不一致で
        ValueError) だが、dict 単体の decode 経路 (_dict_to_action_result_entry)
        は data.get ベースなので、欠損キーに対する robustness を独立に確認する。
        """
        dst = DefaultActionResultStore()
        dst_runtime = SimpleNamespace(_action_result_store=dst)
        payload = {
            "schema_version": 5,
            "entries": [
                {
                    "player_id": 1,
                    "entries": [
                        {
                            "occurred_at": "2026-06-14T12:00:00+00:00",
                            "action_summary": "walk_summary",
                            "result_summary": "ok",
                            # prediction_context_id キー自体を欠落させる
                        }
                    ],
                }
            ],
        }
        ActionResultStoreSubsystemCodec().restore(dst_runtime, payload)
        results = dst.get_recent(PlayerId(1), limit=10)
        assert results[0].prediction_context_id is None

    def test_in_context_belief_ids_欠損の旧スキーマ相当データは空タプルに倒れる(self) -> None:
        """v5 導入前 (= キー自体が無い) payload を decode しても例外にならず空タプルになる。

        U4 で追加した ``in_context_belief_ids`` の後方互換を、
        prediction_context_id と同じ形で独立に確認する。
        """
        dst = DefaultActionResultStore()
        dst_runtime = SimpleNamespace(_action_result_store=dst)
        payload = {
            "schema_version": 5,
            "entries": [
                {
                    "player_id": 1,
                    "entries": [
                        {
                            "occurred_at": "2026-06-14T12:00:00+00:00",
                            "action_summary": "walk_summary",
                            "result_summary": "ok",
                            # in_context_belief_ids キー自体を欠落させる
                        }
                    ],
                }
            ],
        }
        ActionResultStoreSubsystemCodec().restore(dst_runtime, payload)
        results = dst.get_recent(PlayerId(1), limit=10)
        assert results[0].in_context_belief_ids == ()


class TestSlidingWindowCodecRollingSummaryBackend:
    """``MEMORY_KIND=rolling_summary`` (= K run の最適構成) backend での
    capture / restore を検証する (#471 後続)。L4 / L5 が失われると agent の
    self_image / world_view が空に戻るため、永続化は実験再現性に必須。"""

    def _make_rolling(self) -> Any:
        from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
            RollingSummaryShortTermMemory,
        )

        return RollingSummaryShortTermMemory(
            l1_soft_cap=15, l1_hard_cap=25, l4_keep_generations=3
        )

    def test_L1_raw_と_L4_と_L5_が_全部_往復する(self) -> None:
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

        src_runtime = SimpleNamespace(_sliding_window=src)
        captured = SlidingWindowMemorySubsystemCodec().capture(src_runtime)
        assert captured["mode"] == "rolling_summary"
        assert captured["schema_version"] == 2
        assert len(captured["raw_entries"]) == 2  # player 1, 2
        assert len(captured["mid_summaries"][0]["summaries"]) == 1
        assert captured["long_summaries"][0]["summary"]["self_image"] == "探索者カイ"
        assert captured["long_gen_indices"][0]["index"] == 2

        # 別 instance に restore
        dst = self._make_rolling()
        dst.append(PlayerId(99), _obs_entry("stale"))  # 復元で消える
        dst_runtime = SimpleNamespace(_sliding_window=dst)
        SlidingWindowMemorySubsystemCodec().restore(dst_runtime, captured)

        assert 99 not in dst._raw
        p1_recent = dst.get_recent(PlayerId(1), limit=10)
        assert [e.output.prose for e in p1_recent] == ["raw-2", "raw-1"]  # 新しい順
        assert dst._mid_generations(1)[0].compressed_activity == "3 時間山を登った"
        l5 = dst._long_summary(1)
        assert l5 is not None
        assert l5.self_image == "探索者カイ"
        assert dst._long_gen_index[1] == 2

    def test_sliding_v1_snapshot_を_rolling_backend_に_load_できる(self) -> None:
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
        runtime = SimpleNamespace(_sliding_window=dst)
        SlidingWindowMemorySubsystemCodec().restore(runtime, v1_data)
        recent = dst.get_recent(PlayerId(1), limit=5)
        assert [e.output.prose for e in recent] == ["migrated"]
        assert dst._long_summary(1) is None  # v1 には L5 が無い

    def test_rolling_snapshot_を_sliding_backend_に_load_は_raw_のみ移送(self) -> None:
        """cross-backend (rolling → sliding): L4 / L5 は捨てて raw だけ復元。"""
        src = self._make_rolling()
        src.append(PlayerId(1), _obs_entry("raw-only"))
        captured = SlidingWindowMemorySubsystemCodec().capture(
            SimpleNamespace(_sliding_window=src)
        )
        dst = DefaultSlidingWindowMemory()
        runtime = SimpleNamespace(_sliding_window=dst)
        SlidingWindowMemorySubsystemCodec().restore(runtime, captured)
        recent = dst.get_recent(PlayerId(1), limit=5)
        assert [e.output.prose for e in recent] == ["raw-only"]


class TestUnsupportedSchemaVersion:
    @pytest.mark.parametrize(
        "codec_cls",
        [
            SlidingWindowMemorySubsystemCodec,
            ObservationBufferSubsystemCodec,
            ActionResultStoreSubsystemCodec,
        ],
    )
    def test_未サポート_schema_version_は_例外(self, codec_cls) -> None:
        codec = codec_cls()
        with pytest.raises(ValueError, match="schema_version"):
            codec.restore(SimpleNamespace(), {"schema_version": 999})
