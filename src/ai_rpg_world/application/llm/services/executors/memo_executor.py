"""Memo ツール (memo_add / memo_list / memo_done) の実行。

Issue #188 Phase 1a で ``TodoToolExecutor`` から改名・拡張。

設計:
- LLM が context に固定したい情報 (タスク / 目標 / 戦略メモ / 観察など) を扱う
- ``memo_done`` 呼び出し時に **周辺コンテキストを snapshot** し、後で
  episodic cue 経由で recall できる材料にする
- 旧 ``TodoToolExecutor`` は本クラスのエイリアスとして残す (後方互換)
"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    MemoFulfillmentContext,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IMemoStore,
    ISlidingWindowMemory,
)
from ai_rpg_world.application.trace import ITraceRecorder, NullTraceRecorder, TraceEventKind
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    unknown_tool,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_MEMO_DONE,
    TOOL_NAME_MEMO_LIST,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from datetime import datetime


# memo_done の fulfillment_context に格納する直近観測 / 行動結果の件数。
# 多すぎると entry が肥大化し episodic cue で扱いにくいので少数で抑える。
_FULFILLMENT_RECENT_OBSERVATIONS_LIMIT = 5
_FULFILLMENT_RECENT_ACTIONS_LIMIT = 5


class MemoToolExecutor:
    """Memo ツールの実行を担当するサブマッパー。

    ``get_handlers()`` でツール名→ハンドラの辞書を返し、
    ``ToolCommandMapper`` が ``_executor_map`` にマージする。

    ``memo_done`` 時に周辺コンテキストを snapshot するため、
    ``sliding_window`` と ``action_result_store`` を inject 可能 (Optional)。
    また ``current_tick_provider`` で完了時 tick も snapshot する。
    """

    def __init__(
        self,
        memo_store: Optional[IMemoStore] = None,
        *,
        sliding_window: Optional[ISlidingWindowMemory] = None,
        action_result_store: Optional[IActionResultStore] = None,
        current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
        todo_store: Optional[IMemoStore] = None,
        trace_recorder: Optional[ITraceRecorder] = None,
    ) -> None:
        # 後方互換: 旧 kwarg ``todo_store`` を受け付ける (Issue #188 リネーム)。
        # 両方指定なら memo_store を優先。
        if memo_store is None and todo_store is not None:
            memo_store = todo_store
        self._memo_store = memo_store
        self._sliding_window = sliding_window
        self._action_result_store = action_result_store
        self._current_tick_provider = current_tick_provider
        self._trace_recorder: ITraceRecorder = trace_recorder or NullTraceRecorder()

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。memo_store が None の場合は空辞書。"""
        if self._memo_store is None:
            return {}
        return {
            TOOL_NAME_MEMO_ADD: self._execute_memo_add,
            TOOL_NAME_MEMO_LIST: self._execute_memo_list,
            TOOL_NAME_MEMO_DONE: self._execute_memo_done,
        }

    def _current_tick(self) -> Optional[int]:
        if self._current_tick_provider is None:
            return None
        try:
            return self._current_tick_provider()
        except Exception:
            return None

    def _execute_memo_add(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        if self._memo_store is None:
            return unknown_tool("memo ツールはまだ利用できません。")
        try:
            content = (args.get("content") or "").strip()
            if not content:
                return LlmCommandResultDto(
                    success=False,
                    message="content が指定されていません。",
                    error_code="TODO_ERROR",
                    remediation=get_remediation("TODO_ERROR"),
                )
            memo_id = self._memo_store.add(
                PlayerId(player_id), content, current_tick=self._current_tick()
            )
            self._trace_recorder.record(
                TraceEventKind.MEMO_ADD,
                tick=self._current_tick(),
                player_id=player_id,
                memo_id=memo_id,
                content=content,
            )
            return LlmCommandResultDto(
                success=True,
                message=f"メモを追加しました（ID: {memo_id}）。完了したら memo_done で記録してください。",
            )
        except Exception as e:
            return exception_result(e)

    def _execute_memo_list(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        del args  # unused
        if self._memo_store is None:
            return unknown_tool("memo ツールはまだ利用できません。")
        try:
            entries = self._memo_store.list_uncompleted(PlayerId(player_id))
            if not entries:
                return LlmCommandResultDto(
                    success=True,
                    message="未完了のメモはありません。",
                )
            lines = [
                f"- [{e.id}] {e.content} (追加: {e.added_at.strftime('%Y-%m-%d %H:%M')})"
                for e in entries
            ]
            return LlmCommandResultDto(
                success=True,
                message="未完了のメモ:\n" + "\n".join(lines),
            )
        except Exception as e:
            return exception_result(e)

    def _execute_memo_done(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        """指定 ID 群の memo を一括完了する。常に配列を受け取り、1 件だけでも
        ``["..."]`` の単一要素配列として渡す。部分失敗を許容し、存在しない ID
        は ``not_found`` として individual に報告する。
        """
        if self._memo_store is None:
            return unknown_tool("memo ツールはまだ利用できません。")
        try:
            raw_ids = args.get("memo_ids")
            if not isinstance(raw_ids, list):
                return LlmCommandResultDto(
                    success=False,
                    message="memo_ids は配列で指定してください。1 件のみ完了する場合も ['id'] のように単一要素配列にしてください。",
                    error_code="TODO_ERROR",
                    remediation=get_remediation("TODO_ERROR"),
                )
            memo_ids: list[str] = []
            for x in raw_ids:
                if not isinstance(x, str):
                    return LlmCommandResultDto(
                        success=False,
                        message="memo_ids の各要素は string でなければなりません。",
                        error_code="TODO_ERROR",
                        remediation=get_remediation("TODO_ERROR"),
                    )
                trimmed = x.strip()
                if trimmed:
                    memo_ids.append(trimmed)
            if not memo_ids:
                return LlmCommandResultDto(
                    success=False,
                    message="memo_ids が空です。少なくとも 1 件の memo_id を含めてください。",
                    error_code="TODO_ERROR",
                    remediation=get_remediation("TODO_ERROR"),
                )

            pid = PlayerId(player_id)
            completed: list[str] = []
            not_found: list[str] = []
            for memo_id in memo_ids:
                # fulfillment_context は memo ごとに snapshot する (完了タイミングごとに
                # 周辺 context が違うことに意味がある)。
                fulfillment_context = self._build_fulfillment_context(pid)
                ok = self._memo_store.complete(
                    pid, memo_id, fulfillment_context=fulfillment_context
                )
                if ok:
                    completed.append(memo_id)
                    self._trace_recorder.record(
                        TraceEventKind.MEMO_DONE,
                        tick=self._current_tick(),
                        player_id=player_id,
                        memo_id=memo_id,
                    )
                else:
                    not_found.append(memo_id)

            if completed and not not_found:
                if len(completed) == 1:
                    msg = f"メモ {completed[0]} を完了にしました。"
                else:
                    msg = (
                        f"{len(completed)} 件のメモを完了にしました: "
                        + ", ".join(completed)
                    )
                return LlmCommandResultDto(success=True, message=msg)
            if completed and not_found:
                msg = (
                    f"{len(completed)} 件を完了にしました ({', '.join(completed)})。"
                    f"次の memo は見つかりませんでした: {', '.join(not_found)}"
                )
                return LlmCommandResultDto(
                    success=True,
                    message=msg,
                )
            return LlmCommandResultDto(
                success=False,
                message=f"指定されたメモが見つかりません: {', '.join(not_found)}",
                error_code="TODO_ERROR",
                remediation="正しい memo_id を指定してください。memo_list で一覧を確認できます。",
            )
        except Exception as e:
            return exception_result(e)

    def _build_fulfillment_context(
        self, player_id: PlayerId
    ) -> Optional[MemoFulfillmentContext]:
        """memo_done 呼び出し時点の周辺 context を snapshot する。

        sliding_window と action_result_store が両方注入されていれば、
        それぞれから直近 N 件を取って凍結保存する。注入されていない場合は
        None (= snapshot なし、completed_at だけ記録) を返す。
        """
        if self._sliding_window is None and self._action_result_store is None:
            return None
        observations: tuple = ()
        actions: tuple = ()
        if self._sliding_window is not None:
            try:
                recent_obs = self._sliding_window.get_recent(
                    player_id, _FULFILLMENT_RECENT_OBSERVATIONS_LIMIT
                )
                observations = tuple(
                    entry.output.prose for entry in recent_obs if entry.output.prose
                )
            except Exception:
                observations = ()
        if self._action_result_store is not None:
            try:
                recent_actions = self._action_result_store.get_recent(
                    player_id, _FULFILLMENT_RECENT_ACTIONS_LIMIT
                )
                actions = tuple(
                    entry.action_summary
                    for entry in recent_actions
                    if entry.action_summary
                )
            except Exception:
                actions = ()
        if not observations and not actions:
            # snapshot 対象が無い場合は context 自体を作らない (None)
            return None
        return MemoFulfillmentContext(
            completed_at=datetime.now(),
            completed_at_tick=self._current_tick(),
            recent_observation_proses=observations,
            recent_action_summaries=actions,
        )


# 後方互換: 旧名 ``TodoToolExecutor`` は本クラスのエイリアス。
# 新規コードは MemoToolExecutor を使うこと。
TodoToolExecutor = MemoToolExecutor
