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
)
from ai_rpg_world.domain.memory.memo.value_object.memo_fulfillment_context import MemoFulfillmentContext
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    ISlidingWindowMemory,
)
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.memo.repository.memo_repository import MemoRepository
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.application.trace import ITraceRecorder, NullTraceRecorder, TraceEventKind
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.memo_id_display import (
    resolve_memo_id_prefix,
    short_memo_id,
)
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
        memo_store: Optional[MemoRepository] = None,
        *,
        sliding_window: Optional[ISlidingWindowMemory] = None,
        action_result_store: Optional[IActionResultStore] = None,
        current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
        todo_store: Optional[MemoRepository] = None,
        trace_recorder: Optional[ITraceRecorder] = None,
        being_attachment_resolver: Optional[BeingAttachmentResolver] = None,
        default_world_id: Optional[WorldId] = None,
    ) -> None:
        # 後方互換: 旧 kwarg ``todo_store`` を受け付ける (Issue #188 リネーム)。
        # 両方指定なら memo_store を優先。
        if memo_store is None and todo_store is not None:
            memo_store = todo_store
        # Phase 3 Step 3a-2: BeingAttachmentResolver + WorldId が両方注入された
        # ときだけ being_id keyed の新 API に切替える (= dual-path)。未注入なら
        # 従来の player_id keyed 経路を使う (= 既存テスト互換)。
        # Step 3a-3 で player_id 経路を撤去し、本 dual-path も解消する。
        if being_attachment_resolver is not None and not isinstance(
            being_attachment_resolver, BeingAttachmentResolver
        ):
            raise TypeError(
                "being_attachment_resolver must be BeingAttachmentResolver"
            )
        if default_world_id is not None and not isinstance(default_world_id, WorldId):
            raise TypeError("default_world_id must be WorldId")
        self._memo_store = memo_store
        self._sliding_window = sliding_window
        self._action_result_store = action_result_store
        self._current_tick_provider = current_tick_provider
        self._trace_recorder: ITraceRecorder = trace_recorder or NullTraceRecorder()
        self._resolver = being_attachment_resolver
        self._default_world_id = default_world_id

    def _resolve_being_id(self, player_id: PlayerId) -> Optional[BeingId]:
        """Resolver + WorldId が両方揃っていれば being_id を引く。

        未注入や解決失敗時は None を返し、呼び出し元は legacy player_id API に
        fallback する。
        """
        if self._resolver is None or self._default_world_id is None:
            return None
        return self._resolver.resolve_being_id(self._default_world_id, player_id)

    # ===== dual-path 内部ヘルパー (Phase 3 Step 3a-2) =====
    # Resolver + WorldId が揃って being_id を引けるなら新 API、そうでなければ
    # 旧 player_id API。Step 3a-3 で旧 API を撤去した時に本ヘルパーは新 API 直叩き
    # にする。

    def _add_memo(self, player_id: PlayerId, content: str) -> str:
        assert self._memo_store is not None
        being_id = self._resolve_being_id(player_id)
        if being_id is not None:
            return self._memo_store.add_by_being(
                being_id, content, current_tick=self._current_tick()
            )
        return self._memo_store.add(
            player_id, content, current_tick=self._current_tick()
        )

    def _list_uncompleted(self, player_id: PlayerId):
        assert self._memo_store is not None
        being_id = self._resolve_being_id(player_id)
        if being_id is not None:
            return self._memo_store.list_uncompleted_by_being(being_id)
        return self._memo_store.list_uncompleted(player_id)

    def _complete_memo(
        self,
        player_id: PlayerId,
        memo_id: str,
        fulfillment_context: Optional[MemoFulfillmentContext],
    ) -> bool:
        assert self._memo_store is not None
        being_id = self._resolve_being_id(player_id)
        if being_id is not None:
            return self._memo_store.complete_by_being(
                being_id, memo_id, fulfillment_context=fulfillment_context
            )
        return self._memo_store.complete(
            player_id, memo_id, fulfillment_context=fulfillment_context
        )

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
            memo_id = self._add_memo(PlayerId(player_id), content)
            self._trace_recorder.record(
                TraceEventKind.MEMO_ADD,
                tick=self._current_tick(),
                player_id=player_id,
                memo_id=memo_id,
                content=content,
            )
            return LlmCommandResultDto(
                success=True,
                message=(
                    f"メモを追加しました（ID: {short_memo_id(memo_id)}）。"
                    "完了したら memo_done でこの ID を指定してください "
                    "(短縮形でも full ID でも受け付けます)。"
                ),
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
            entries = self._list_uncompleted(PlayerId(player_id))
            if not entries:
                return LlmCommandResultDto(
                    success=True,
                    message="未完了のメモはありません。",
                )
            lines = [
                f"- [{short_memo_id(e.id)}] {e.content} (追加: {e.added_at.strftime('%Y-%m-%d %H:%M')})"
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
            # Issue #276: memo_id は short prefix (例: "a3b9f1") でも full UUID
            # でも受け付ける。uncompleted memo の ID 集合に対して prefix match で
            # 解決し、ambiguous なら個別に失敗扱いにする。
            uncompleted_ids = [e.id for e in self._list_uncompleted(pid)]
            completed: list[str] = []  # full UUID
            not_found: list[str] = []  # 入力のまま (短縮形 or 入力 ID)
            ambiguous: list[tuple[str, list[str]]] = []  # (入力, candidates)
            for raw_id in memo_ids:
                resolved, ambiguous_matches = resolve_memo_id_prefix(
                    raw_id, uncompleted_ids
                )
                if resolved is None:
                    if ambiguous_matches:
                        ambiguous.append((raw_id, ambiguous_matches))
                    else:
                        not_found.append(raw_id)
                    continue
                # fulfillment_context は memo ごとに snapshot する (完了タイミングごとに
                # 周辺 context が違うことに意味がある)。
                fulfillment_context = self._build_fulfillment_context(pid)
                ok = self._complete_memo(
                    pid, resolved, fulfillment_context=fulfillment_context
                )
                if ok:
                    completed.append(resolved)
                    # resolved 後に同じ ID を別の raw_id が指してくる可能性は
                    # ないが、念のため uncompleted_ids から取り除いて 2 度 match
                    # しないようにする。
                    if resolved in uncompleted_ids:
                        uncompleted_ids.remove(resolved)
                    self._trace_recorder.record(
                        TraceEventKind.MEMO_DONE,
                        tick=self._current_tick(),
                        player_id=player_id,
                        memo_id=resolved,  # trace には full UUID を残す (grep 性)
                    )
                else:
                    not_found.append(raw_id)

            # 表示は short_memo_id で短縮 (LLM へのノイズ低減)
            completed_short = [short_memo_id(c) for c in completed]
            ambiguous_msgs = [
                f"{raw}={'/'.join(short_memo_id(c) for c in cands)}"
                for raw, cands in ambiguous
            ]

            if completed and not not_found and not ambiguous:
                if len(completed) == 1:
                    msg = f"メモ {completed_short[0]} を完了にしました。"
                else:
                    msg = (
                        f"{len(completed)} 件のメモを完了にしました: "
                        + ", ".join(completed_short)
                    )
                return LlmCommandResultDto(success=True, message=msg)
            if completed and (not_found or ambiguous):
                parts = [
                    f"{len(completed)} 件を完了にしました ({', '.join(completed_short)})。",
                ]
                if not_found:
                    parts.append(
                        f"次の memo は見つかりませんでした: {', '.join(not_found)}"
                    )
                if ambiguous_msgs:
                    parts.append(
                        "次の入力は曖昧で複数の memo に一致しました "
                        f"(より長い prefix を指定してください): {', '.join(ambiguous_msgs)}"
                    )
                return LlmCommandResultDto(success=True, message="".join(parts))
            if ambiguous and not completed and not not_found:
                return LlmCommandResultDto(
                    success=False,
                    message=(
                        "指定された prefix が曖昧で複数の memo に一致しました "
                        f"(より長い prefix を指定してください): {', '.join(ambiguous_msgs)}"
                    ),
                    error_code="TODO_ERROR",
                    remediation="memo_list で一覧 + 短縮 ID を確認してください。",
                )
            return LlmCommandResultDto(
                success=False,
                message=f"指定されたメモが見つかりません: {', '.join(not_found)}",
                error_code="TODO_ERROR",
                remediation="正しい memo_id (短縮形可) を指定してください。memo_list で一覧を確認できます。",
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
