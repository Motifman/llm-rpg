"""Short-term memory subsystem codec 群 (Phase 9-4c / #471 後続)。

LLM agent の prompt context に乗る短期記憶を 3 subsystem 分 save / restore する:

| Codec | 対象 | 内容 |
|---|---|---|
| ``SlidingWindowMemorySubsystemCodec`` | ``_sliding_window`` | sliding/rolling 両 backend 対応の短期記憶 |
| ``ObservationBufferSubsystemCodec`` | ``_obs_buffer`` | player_id → pending ObservationEntry list (= LLM turn で drain される) |
| ``ActionResultStoreSubsystemCodec`` | ``_action_result_store`` | player_id → recent ActionResultEntry list (= 直近の tool 実行結果) |

resume 時にこれらが空だと agent は **「直前の出来事を覚えていない」** 状態で
再開する (= 前 run の最終 tick で何が起きたかが prompt に乗らない)。

``SlidingWindowMemorySubsystemCodec`` は 2 つの backend に対応する:

- ``DefaultSlidingWindowMemory`` (``MEMORY_KIND=sliding_window``): 単一 L1
  raw store のみ
- ``RollingSummaryShortTermMemory`` (``MEMORY_KIND=rolling_summary``):
  L1 raw + L4 mid summary (3 generations) + L5 long summary (1 per player)
  の 3 階層

K run の最適構成 (= ``rolling_summary``) で snapshot resume するためには
L4 / L5 の永続化が必須 (= LLM 生成済の要約が失われると agent の
self_image / world_view が空に戻る)。``schema_version`` を 1 → 2 に上げ、
``mode`` field で backend を識別する forward-compatible なフォーマットに拡張。

すべて dataclass を JSON 化する共通ヘルパを使う。datetime → ISO 8601 文字列で正規化。
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldSubsystemCodec,
)
from ai_rpg_world.domain.memory.short_term.value_object.l4_mid_summary import (
    L4MidSummary,
)
from ai_rpg_world.domain.memory.short_term.value_object.l5_long_summary import (
    L5LongSummary,
)


# ----------------------------------------------------------------------------
# 共通 serializer / deserializer
# ----------------------------------------------------------------------------

def _dt_to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


def _iso_to_dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _observation_entry_to_dict(entry: Any) -> dict[str, Any]:
    out = entry.output
    return {
        "occurred_at": _dt_to_iso(entry.occurred_at),
        "game_time_label": entry.game_time_label,
        "output": {
            "prose": out.prose,
            "structured": dict(out.structured),
            "observation_category": out.observation_category,
            "schedules_turn": bool(out.schedules_turn),
            "breaks_movement": bool(out.breaks_movement),
        },
    }


def _dict_to_observation_entry(data: dict[str, Any]) -> Any:
    from ai_rpg_world.application.observation.contracts.dtos import (
        ObservationEntry,
        ObservationOutput,
    )

    out_d = data["output"]
    output = ObservationOutput(
        prose=str(out_d["prose"]),
        structured=dict(out_d.get("structured", {})),
        observation_category=str(out_d.get("observation_category", "self_only")),
        schedules_turn=bool(out_d.get("schedules_turn", False)),
        breaks_movement=bool(out_d.get("breaks_movement", False)),
    )
    return ObservationEntry(
        occurred_at=_iso_to_dt(str(data["occurred_at"])),
        output=output,
        game_time_label=data.get("game_time_label"),
    )


def _action_result_entry_to_dict(entry: Any) -> dict[str, Any]:
    return {
        "occurred_at": _dt_to_iso(entry.occurred_at),
        "action_summary": entry.action_summary,
        "result_summary": entry.result_summary,
        "success": bool(entry.success),
        "error_code": entry.error_code,
        "tool_name": entry.tool_name,
        "argument_fingerprint": entry.argument_fingerprint,
        "should_reschedule": bool(entry.should_reschedule),
        "game_time_label": entry.game_time_label,
        "omit_result_in_prompt": bool(entry.omit_result_in_prompt),
        "expected_result": entry.expected_result,
        "intention": entry.intention,
        "emotion_hint": entry.emotion_hint,
        "scene_boundary": bool(entry.scene_boundary),
        "occurred_tick": entry.occurred_tick,
    }


def _dict_to_action_result_entry(data: dict[str, Any]) -> Any:
    from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry

    return ActionResultEntry(
        occurred_at=_iso_to_dt(str(data["occurred_at"])),
        action_summary=str(data["action_summary"]),
        result_summary=str(data["result_summary"]),
        success=bool(data.get("success", True)),
        error_code=data.get("error_code"),
        tool_name=data.get("tool_name"),
        argument_fingerprint=data.get("argument_fingerprint"),
        should_reschedule=bool(data.get("should_reschedule", False)),
        game_time_label=data.get("game_time_label"),
        omit_result_in_prompt=bool(data.get("omit_result_in_prompt", False)),
        expected_result=data.get("expected_result"),
        intention=data.get("intention"),
        emotion_hint=data.get("emotion_hint"),
        scene_boundary=bool(data.get("scene_boundary", False)),
        occurred_tick=data.get("occurred_tick"),
    )


def _check_version(data: dict[str, Any], key: str, expected: int) -> None:
    version = data.get("schema_version")
    if version != expected:
        raise ValueError(
            f"{key} schema_version={version!r} unsupported (expected {expected})"
        )


def _capture_dict_store(
    store_dict: dict[int, list[Any]],
    entry_to_dict,
) -> list[dict[str, Any]]:
    """共通 capture: ``{player_id: [Entry, ...]}`` を JSON-serializable に。"""
    return sorted(
        (
            {
                "player_id": int(pid),
                "entries": [entry_to_dict(e) for e in entries],
            }
            for pid, entries in store_dict.items()
        ),
        key=lambda d: d["player_id"],
    )


def _restore_dict_store(
    store_dict: dict[int, list[Any]],
    entries_data: list[dict[str, Any]],
    dict_to_entry,
) -> None:
    """共通 restore: store_dict を clear + repopulate。"""
    store_dict.clear()
    for entry in entries_data:
        pid = int(entry["player_id"])
        store_dict[pid] = [dict_to_entry(d) for d in entry.get("entries", [])]


# ----------------------------------------------------------------------------
# L4 / L5 summary serializer (rolling_summary backend 専用)
# ----------------------------------------------------------------------------

def _l4_mid_summary_to_dict(s: L4MidSummary) -> dict[str, Any]:
    return {
        "summary_id": s.summary_id,
        "player_id": int(s.player_id),
        "raw_count": int(s.raw_count),
        "generated_at": _dt_to_iso(s.generated_at),
        "compressed_activity": s.compressed_activity,
        "emotional_summary": s.emotional_summary,
        "unresolved": list(s.unresolved),
        "is_fallback": bool(s.is_fallback),
    }


def _dict_to_l4_mid_summary(d: dict[str, Any]) -> L4MidSummary:
    return L4MidSummary(
        summary_id=str(d["summary_id"]),
        player_id=int(d["player_id"]),
        raw_count=int(d["raw_count"]),
        generated_at=_iso_to_dt(str(d["generated_at"])),
        compressed_activity=str(d["compressed_activity"]),
        emotional_summary=str(d["emotional_summary"]),
        unresolved=tuple(str(u) for u in d.get("unresolved", [])),
        is_fallback=bool(d.get("is_fallback", False)),
    )


def _l5_long_summary_to_dict(s: L5LongSummary) -> dict[str, Any]:
    return {
        "summary_id": s.summary_id,
        "player_id": int(s.player_id),
        "generation_index": int(s.generation_index),
        "generated_at": _dt_to_iso(s.generated_at),
        "self_image": s.self_image,
        "world_view": s.world_view,
        "is_fallback": bool(s.is_fallback),
    }


def _dict_to_l5_long_summary(d: dict[str, Any]) -> L5LongSummary:
    return L5LongSummary(
        summary_id=str(d["summary_id"]),
        player_id=int(d["player_id"]),
        generation_index=int(d["generation_index"]),
        generated_at=_iso_to_dt(str(d["generated_at"])),
        self_image=str(d["self_image"]),
        world_view=str(d["world_view"]),
        is_fallback=bool(d.get("is_fallback", False)),
    )


# ----------------------------------------------------------------------------
# 1. Sliding window (= 2 backend に対応: sliding_window / rolling_summary)
# ----------------------------------------------------------------------------
_SW_SUBSYSTEM_KEY = "sliding_window"
# v1: {schema_version: 1, entries: [...]}                     ← sliding 専用
# v2: {schema_version: 2, mode: "sliding_window", entries: [...]}
#     {schema_version: 2, mode: "rolling_summary",
#      raw_entries: [...], mid_summaries: [...], long_summaries: [...],
#      long_gen_indices: [...]}
_SW_SCHEMA_VERSION = 2
_SW_MODE_SLIDING = "sliding_window"
_SW_MODE_ROLLING = "rolling_summary"


def _is_rolling_backend(sw: Any) -> bool:
    """duck typing で rolling_summary backend を識別する。

    循環 import (RollingSummaryShortTermMemory) を避けるため、内部 attribute
    の有無で判定する。``_raw`` (L1 raw queue) と ``_mid`` (L4 mid summary
    deque) の両方を持つのは現状 ``RollingSummaryShortTermMemory`` のみ。
    """
    return hasattr(sw, "_raw") and hasattr(sw, "_mid") and hasattr(sw, "_long")


class SlidingWindowMemorySubsystemCodec(WorldSubsystemCodec):
    """``_sliding_window`` の短期記憶を JSON 化。

    backend の種別 (``DefaultSlidingWindowMemory`` / ``RollingSummaryShortTermMemory``)
    を duck typing で識別し、それぞれの内部構造を保存する。schema_version=2
    で ``mode`` field を導入し、旧 v1 (sliding 専用) との後方互換も維持。
    """

    @property
    def subsystem_key(self) -> str:
        return _SW_SUBSYSTEM_KEY

    # -------- capture --------

    def capture(self, runtime: Any) -> dict[str, Any]:
        sw = getattr(runtime, "_sliding_window", None)
        if sw is None:
            return {
                "schema_version": _SW_SCHEMA_VERSION,
                "mode": _SW_MODE_SLIDING,
                "entries": [],
            }
        if _is_rolling_backend(sw):
            return self._capture_rolling(sw)
        return self._capture_sliding(sw)

    def _capture_sliding(self, sw: Any) -> dict[str, Any]:
        return {
            "schema_version": _SW_SCHEMA_VERSION,
            "mode": _SW_MODE_SLIDING,
            "entries": _capture_dict_store(sw._store, _observation_entry_to_dict),
        }

    def _capture_rolling(self, sw: Any) -> dict[str, Any]:
        # L4 / L5 は worker thread からも書かれる: 必ず lock 内で snapshot を取る。
        # L1 (_raw) は main thread 専用なので lock 不要 (RollingSummaryShortTermMemory
        # の自己ドキュメント済の不変条件)。
        with sw._mid_lock:
            mid_snapshot: dict[int, list[L4MidSummary]] = {
                int(pid): list(dq) for pid, dq in sw._mid.items()
            }
        with sw._long_lock:
            long_snapshot: dict[int, L5LongSummary] = dict(sw._long)
            gen_snapshot: dict[int, int] = dict(sw._long_gen_index)
        raw_entries = sorted(
            (
                {
                    "player_id": int(pid),
                    "entries": [
                        _observation_entry_to_dict(e) for e in list(dq)
                    ],
                }
                for pid, dq in sw._raw.items()
            ),
            key=lambda d: d["player_id"],
        )
        mid_summaries = sorted(
            (
                {
                    "player_id": int(pid),
                    "summaries": [
                        _l4_mid_summary_to_dict(s) for s in summaries
                    ],
                }
                for pid, summaries in mid_snapshot.items()
            ),
            key=lambda d: d["player_id"],
        )
        long_summaries = sorted(
            (
                {
                    "player_id": int(pid),
                    "summary": _l5_long_summary_to_dict(l5),
                }
                for pid, l5 in long_snapshot.items()
            ),
            key=lambda d: d["player_id"],
        )
        long_gen_indices = sorted(
            (
                {"player_id": int(pid), "index": int(idx)}
                for pid, idx in gen_snapshot.items()
            ),
            key=lambda d: d["player_id"],
        )
        return {
            "schema_version": _SW_SCHEMA_VERSION,
            "mode": _SW_MODE_ROLLING,
            "raw_entries": raw_entries,
            "mid_summaries": mid_summaries,
            "long_summaries": long_summaries,
            "long_gen_indices": long_gen_indices,
        }

    # -------- restore --------

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        version = data.get("schema_version")
        if version not in (1, _SW_SCHEMA_VERSION):
            raise ValueError(
                f"{_SW_SUBSYSTEM_KEY} schema_version={version!r} unsupported "
                f"(expected 1 or {_SW_SCHEMA_VERSION})"
            )
        sw = getattr(runtime, "_sliding_window", None)
        if sw is None:
            return
        # v1 は sliding_window 暗黙
        mode = data.get("mode", _SW_MODE_SLIDING)
        is_rolling = _is_rolling_backend(sw)

        if mode == _SW_MODE_ROLLING and is_rolling:
            self._restore_rolling_to_rolling(sw, data)
        elif mode == _SW_MODE_SLIDING and not is_rolling:
            _restore_dict_store(
                sw._store, data.get("entries", []), _dict_to_observation_entry
            )
        elif mode == _SW_MODE_SLIDING and is_rolling:
            # sliding snapshot を rolling backend に流す: entries は L1 raw に積む。
            # L4 / L5 は空のまま (= 初回 run と同じ立ち上がり)。
            self._restore_sliding_to_rolling(sw, data.get("entries", []))
        else:  # mode == ROLLING and not is_rolling
            # rolling snapshot を sliding backend に流す: raw_entries だけを
            # L1 (sliding) に展開。L4 / L5 は捨てる (= sliding には居場所なし)。
            self._restore_rolling_to_sliding(sw, data.get("raw_entries", []))

    def _restore_rolling_to_rolling(self, sw: Any, data: dict[str, Any]) -> None:
        # L1 raw queue を clear + repopulate
        sw._raw.clear()
        for player_entry in data.get("raw_entries", []):
            pid = int(player_entry["player_id"])
            entries = [
                _dict_to_observation_entry(d)
                for d in player_entry.get("entries", [])
            ]
            sw._raw[pid] = deque(entries)
        # L4 / L5 / generation index は lock 内で書き戻す (worker thread と race)
        with sw._mid_lock:
            sw._mid.clear()
            for player_entry in data.get("mid_summaries", []):
                pid = int(player_entry["player_id"])
                summaries = [
                    _dict_to_l4_mid_summary(d)
                    for d in player_entry.get("summaries", [])
                ]
                sw._mid[pid] = deque(summaries)
            # _raw に居て _mid に居ない player も _mid に空 deque を確保
            # (_ensure_player の不変条件と一致させる)
            for pid in sw._raw.keys():
                if pid not in sw._mid:
                    sw._mid[pid] = deque()
        with sw._long_lock:
            sw._long.clear()
            for player_entry in data.get("long_summaries", []):
                pid = int(player_entry["player_id"])
                sw._long[pid] = _dict_to_l5_long_summary(player_entry["summary"])
            sw._long_gen_index.clear()
            for player_entry in data.get("long_gen_indices", []):
                sw._long_gen_index[int(player_entry["player_id"])] = int(
                    player_entry["index"]
                )

    def _restore_sliding_to_rolling(
        self, sw: Any, entries_data: list[dict[str, Any]]
    ) -> None:
        sw._raw.clear()
        for player_entry in entries_data:
            pid = int(player_entry["player_id"])
            entries = [
                _dict_to_observation_entry(d)
                for d in player_entry.get("entries", [])
            ]
            sw._raw[pid] = deque(entries)
        with sw._mid_lock:
            sw._mid.clear()
            for pid in sw._raw.keys():
                sw._mid[pid] = deque()
        with sw._long_lock:
            sw._long.clear()
            sw._long_gen_index.clear()

    def _restore_rolling_to_sliding(
        self, sw: Any, raw_entries_data: list[dict[str, Any]]
    ) -> None:
        # L4 / L5 は sliding backend に居場所がないため捨てる
        _restore_dict_store(
            sw._store, raw_entries_data, _dict_to_observation_entry
        )


# ----------------------------------------------------------------------------
# 2. Observation buffer
# ----------------------------------------------------------------------------
_OB_SUBSYSTEM_KEY = "observation_buffer"
_OB_SCHEMA_VERSION = 1


class ObservationBufferSubsystemCodec(WorldSubsystemCodec):
    """``_obs_buffer._buffer`` (= pending ObservationEntry list per player)。"""

    @property
    def subsystem_key(self) -> str:
        return _OB_SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        ob = getattr(runtime, "_obs_buffer", None)
        if ob is None:
            return {"schema_version": _OB_SCHEMA_VERSION, "entries": []}
        return {
            "schema_version": _OB_SCHEMA_VERSION,
            "entries": _capture_dict_store(
                ob._buffer, _observation_entry_to_dict
            ),
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        _check_version(data, _OB_SUBSYSTEM_KEY, _OB_SCHEMA_VERSION)
        ob = getattr(runtime, "_obs_buffer", None)
        if ob is None:
            return
        _restore_dict_store(
            ob._buffer, data.get("entries", []), _dict_to_observation_entry
        )


# ----------------------------------------------------------------------------
# 3. Action result store
# ----------------------------------------------------------------------------
_AR_SUBSYSTEM_KEY = "action_result_store"
# v2: expected_result 追加 (PR1)。v3: intention / emotion_hint 追加 (PR2a)。
# 旧 snapshot 互換は不要 (ユーザー判断)。restore は data.get で欠損を None に倒すため
# 実害は出ないが、schema の意味変更を明示するため version を上げる。
_AR_SCHEMA_VERSION = 3


class ActionResultStoreSubsystemCodec(WorldSubsystemCodec):
    """``_action_result_store._store`` (= ActionResultEntry list per player)。"""

    @property
    def subsystem_key(self) -> str:
        return _AR_SUBSYSTEM_KEY

    def capture(self, runtime: Any) -> dict[str, Any]:
        ar = getattr(runtime, "_action_result_store", None)
        if ar is None:
            return {"schema_version": _AR_SCHEMA_VERSION, "entries": []}
        return {
            "schema_version": _AR_SCHEMA_VERSION,
            "entries": _capture_dict_store(
                ar._store, _action_result_entry_to_dict
            ),
        }

    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        _check_version(data, _AR_SUBSYSTEM_KEY, _AR_SCHEMA_VERSION)
        ar = getattr(runtime, "_action_result_store", None)
        if ar is None:
            return
        _restore_dict_store(
            ar._store, data.get("entries", []), _dict_to_action_result_entry
        )


__all__ = [
    "SlidingWindowMemorySubsystemCodec",
    "ObservationBufferSubsystemCodec",
    "ActionResultStoreSubsystemCodec",
]
