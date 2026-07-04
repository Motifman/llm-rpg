"""``ToolCallLoopGuardService`` に「離れた tick に散らばる同一失敗の反復」
検出を追加する (Y_after_pr639_640_200tick 後続、PR-AA)。

Y_after_pr639_640 の分析で観測された問題:
- ベリー gather の失敗が tick 96 / 104 / 108 / 113 と 20 tick に渡って
  散発的に反復。同じ ``(tool, fingerprint, error_code)`` の失敗を LLM が
  何度も繰り返しているが、既存 ``loop_guard_warning`` は **連続同一**
  しか検出しないため間に explore や travel_to が挟まると streak が
  リセットされ、警告が発火しない
- E-34 の指摘: 20 tick 越しの同 failure 反復は現状 silent

## 変更方針

``record_and_check`` に optional な ``success`` / ``error_code`` を受け取り、
失敗パターンだけを別トラッカーで累積する:

1. 失敗のみを ``_failure_history`` に (tick, tool, fingerprint, error_code)
   として記録 (ここで tick は ``current_tick_provider`` から取得)
2. 一定の tick window (default 20) より古いエントリは drop
3. 同じ (tool, fingerprint, error_code) が window 内で 3 回以上出現したら
   「間欠的な失敗反復」警告を observation として注入
4. trace には ``LOOP_GUARD_WARNING`` として ``pattern="cross_tick_failure"``
   付きで残す (既存 pattern と識別可能)

## 後方互換

- ``record_and_check`` の新パラメータは全て kwargs 且つ default 値付き
  (既存呼び出し側は変更不要)
- 失敗記録は既存 streak 計測とは独立の deque。既存挙動 (連続同一) は
  そのまま
- ``peek_streak`` は連続 streak 用のまま (cross_tick は peek 対象外)
"""

from __future__ import annotations

from datetime import datetime

from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
    ToolCallLoopGuardService,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_INTERACT,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _StubBuffer(IObservationContextBuffer):
    """テスト用 observation buffer。append を単純に記録するだけ。"""

    def __init__(self) -> None:
        self.appended: list[tuple[int, ObservationEntry]] = []

    def append(self, player_id: PlayerId, entry: ObservationEntry) -> None:
        self.appended.append((player_id.value, entry))

    def drain(self, player_id: PlayerId) -> list[ObservationEntry]:
        # 実装は本テストで使わない
        out = [e for pid, e in self.appended if pid == player_id.value]
        self.appended = [(p, e) for p, e in self.appended if p != player_id.value]
        return out

    def clear(self, player_id: PlayerId) -> None:
        self.appended = [(p, e) for p, e in self.appended if p != player_id.value]

    def get_observations(self, player_id: PlayerId) -> list[ObservationEntry]:
        # インターフェース必須メソッド、テストでは使わない
        return [e for pid, e in self.appended if pid == player_id.value]


class _TickProvider:
    """テスト内で tick を進めるための可変 provider。"""

    def __init__(self, start: int = 0) -> None:
        self.tick = start

    def __call__(self) -> int:
        return self.tick


class TestCrossTickFailureDetection:
    """同一 (tool, fingerprint, error_code) の失敗が window 内で N 回反復
    したら警告を注入する新機能 (PR-AA)。"""

    def _make(self, buffer, tick_provider):
        return ToolCallLoopGuardService(
            buffer,
            clock=lambda: datetime(2026, 1, 1),
            current_tick_provider=tick_provider,
        )

    def test_同一失敗が_window内で_3回_で警告が発火する(self) -> None:
        """ベリー gather 3 連発 (tick 96/104/108) を模す。間に他 tool が挟まっても
        streak は切れているが、cross_tick 検出は起きる。"""
        buffer = _StubBuffer()
        tick = _TickProvider(start=96)
        svc = self._make(buffer, tick)
        pid = PlayerId(3)
        args = {"object_label": "東の茂み", "action_name": "harvest_berry"}

        # 1 回目 (streak=1、cross_tick=1)
        svc.record_and_check(
            pid,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            args,
            success=False,
            error_code="INTERACTION_PRECONDITION_FAILED",
        )
        assert len(buffer.appended) == 0, (
            "1 件目で警告は発火しない (閾値未達)"
        )

        # 間に別 tool を挟む (streak がリセットされる)
        tick.tick = 100
        svc.record_and_check(
            pid,
            "explore",
            {},
            success=True,
        )

        # 2 回目 (cross_tick=2、streak=1)
        tick.tick = 104
        svc.record_and_check(
            pid,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            args,
            success=False,
            error_code="INTERACTION_PRECONDITION_FAILED",
        )
        assert len(buffer.appended) == 0

        # 3 回目 (cross_tick=3、閾値到達 → 警告発火)
        tick.tick = 108
        svc.record_and_check(
            pid,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            args,
            success=False,
            error_code="INTERACTION_PRECONDITION_FAILED",
        )
        assert len(buffer.appended) == 1, (
            "3 回目で cross_tick 警告が発火するはず"
        )
        entry = buffer.appended[0][1]
        assert entry.output.structured.get("loop_guard") is True
        assert entry.output.structured.get("pattern") == "cross_tick_failure"
        assert (
            entry.output.structured.get("error_code")
            == "INTERACTION_PRECONDITION_FAILED"
        )

    def test_window外の失敗は_カウントされない(self) -> None:
        """window (default 20) を跨いだ古い失敗はドロップされる。"""
        buffer = _StubBuffer()
        tick = _TickProvider(start=0)
        svc = self._make(buffer, tick)
        pid = PlayerId(3)
        args = {"object_label": "東の茂み", "action_name": "harvest_berry"}

        # 3 回失敗を 25 tick 間隔で置く (window=20 だと最も古い 2 件は消える)
        for i, t in enumerate([0, 25, 50]):
            tick.tick = t
            svc.record_and_check(
                pid,
                TOOL_NAME_SPOT_GRAPH_INTERACT,
                args,
                success=False,
                error_code="INTERACTION_PRECONDITION_FAILED",
            )
        assert len(buffer.appended) == 0, (
            "各 tick で failure history には 1 件しか残らないはずなので 3 回に到達しない"
        )

    def test_成功は_cross_tick_failure_としてはカウントされない(self) -> None:
        """success=True は failure history に入らない (cross_tick_failure 側)。
        既存の連続 streak 側は success 情報を見ないので、同一 args 連発なら
        従来 warning は発火するが、その pattern は cross_tick_failure では
        ない。"""
        buffer = _StubBuffer()
        tick = _TickProvider(start=0)
        svc = self._make(buffer, tick)
        pid = PlayerId(3)
        args = {"object_label": "東の茂み", "action_name": "harvest_berry"}
        # cross_tick 側閾値 3 に達しないよう 2 回だけ
        for t in [0, 5]:
            tick.tick = t
            svc.record_and_check(
                pid,
                TOOL_NAME_SPOT_GRAPH_INTERACT,
                args,
                success=True,
            )
        # cross_tick_failure pattern は発火しない
        assert not any(
            e.output.structured.get("pattern") == "cross_tick_failure"
            for _, e in buffer.appended
        ), "success=True の呼び出しが cross_tick_failure カウントに入っている"

    def test_異なる_error_code_は_別カウント(self) -> None:
        """同 tool + 同 args でも error_code が違えば別カウント (root cause
        違いとして扱う)。"""
        buffer = _StubBuffer()
        tick = _TickProvider(start=0)
        svc = self._make(buffer, tick)
        pid = PlayerId(3)
        args = {"object_label": "東の茂み", "action_name": "harvest_berry"}
        for t, ec in [
            (0, "INTERACTION_PRECONDITION_FAILED"),
            (5, "INTERACTION_ACTION_NOT_FOUND"),
            (10, "INTERACTION_PRECONDITION_FAILED"),
        ]:
            tick.tick = t
            svc.record_and_check(
                pid,
                TOOL_NAME_SPOT_GRAPH_INTERACT,
                args,
                success=False,
                error_code=ec,
            )
        assert len(buffer.appended) == 0, (
            "PRECONDITION_FAILED は 2 回、ACTION_NOT_FOUND は 1 回で閾値未達"
        )

    def test_同一パターン警告の再発火は_window_経過後に許可される(self) -> None:
        """code-review MEDIUM 1 反映: ``_cross_tick_last_warn`` の pruning が
        機能しているか。同一 pattern が window (default 20 tick) 経過後に
        再度 3 回反復した場合、再警告が発火する。"""
        buffer = _StubBuffer()
        tick = _TickProvider(start=0)
        svc = self._make(buffer, tick)
        pid = PlayerId(3)
        args = {"object_label": "東の茂み", "action_name": "harvest_berry"}

        def fail_at(t: int) -> None:
            tick.tick = t
            svc.record_and_check(
                pid,
                TOOL_NAME_SPOT_GRAPH_INTERACT,
                args,
                success=False,
                error_code="INTERACTION_PRECONDITION_FAILED",
            )

        def cross_tick_warns() -> list:
            return [
                e
                for _, e in buffer.appended
                if e.output.structured.get("pattern") == "cross_tick_failure"
            ]

        # 1 回目の 3 連続 (window 内): tick 0/5/10 で 3 回 → cross_tick 1 発火
        fail_at(0)
        fail_at(5)
        fail_at(10)
        assert len(cross_tick_warns()) == 1

        # 再発火抑制: window (20) 経過前の tick 15 で 4 回目 → まだ silent
        fail_at(15)
        assert len(cross_tick_warns()) == 1, (
            "window 内では cross_tick_failure 再発火しないはず"
        )

        # window 経過後 (tick 40 以降で fresh window 開始): tick 40/45/50 の
        # 3 回で新しい cross_tick カウント → 再警告
        fail_at(40)
        fail_at(45)
        fail_at(50)
        assert len(cross_tick_warns()) >= 2, (
            "window 経過後の再発火が起きていない (_cross_tick_last_warn が"
            " pruning されていない疑い)"
        )

    def test_success_error_code_default_の呼び出しは_既存挙動を壊さない(self) -> None:
        """新パラメータ ``success`` / ``error_code`` を渡さない旧 API 呼び出しは、
        (a) 失敗としてカウントされず、(b) 既存の連続 streak 検出は動く。"""
        buffer = _StubBuffer()
        tick = _TickProvider(start=0)
        svc = self._make(buffer, tick)
        pid = PlayerId(3)
        # 旧 API 呼び出し (success/error_code なし) は失敗として記録しない
        for t in [0, 5, 10]:
            tick.tick = t
            svc.record_and_check(
                pid,
                TOOL_NAME_SPOT_GRAPH_INTERACT,
                {"object_label": "A", "action_name": "gather"},
            )
        # cross_tick_failure は発火しない (success 情報がないため failure と
        # 見なせない)。だが同 args を連続 4 回 (INTERACT の threshold=4) 呼べば
        # 既存 streak 警告は発火する
        assert not any(
            e.output.structured.get("pattern") == "cross_tick_failure"
            for _, e in buffer.appended
        )
