"""1 ターン分のプロンプト組み立てのデフォルト実装"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
        ToolCallLoopGuardService,
    )
from ai_rpg_world.application.being.acting_being import ActingBeing
from ai_rpg_world.application.llm.contracts.dtos import SystemPromptPlayerInfoDto
from ai_rpg_world.application.llm.contracts.interfaces import (
    IAvailableToolsProvider,
    IContextFormatStrategy,
    ICurrentStateFormatter,
    ILlmUiContextBuilder,
    IPromptBuilder,
    IRecentEventsFormatter,
    IShortTermMemory,
    ISystemPromptBuilder,
)
from ai_rpg_world.application.llm.exceptions import PlayerProfileNotFoundForPromptException
from ai_rpg_world.application.llm.services.prompt_builder_config import (
    PromptBuilderCoreServices,
    PromptLimits,
    PromptSectionProviders,
)
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
)

# build_pre_turn_failure_section: Issue #227 chore β で廃止 (#241 後続)
# 詳細は build() 内コメント参照
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

DEFAULT_ACTION_INSTRUCTION = "利用可能なツールで次の行動を選んでください。"
MESSAGE_WHEN_PLAYER_NOT_PLACED = "現在地: 未配置。ゲームに参加するまで待機しています。"


class DefaultPromptBuilder(IPromptBuilder):
    """
    観測バッファの drain → スライディングウィンドウへの append と、
    現在状態・直近の出来事・システムプロンプトの組み立てを行う。
    """

    def __init__(
        self,
        core: PromptBuilderCoreServices,
        *,
        sections: PromptSectionProviders | None = None,
        limits: PromptLimits | None = None,
        ui_context_builder: ILlmUiContextBuilder,
        current_tick_provider: Callable[[], int | None] | None = None,
        trace_recorder: Optional["ITraceRecorder"] = None,
        trace_recorder_provider: Callable[[], Optional["ITraceRecorder"]] | None = None,
        tool_call_loop_guard: Optional["ToolCallLoopGuardService"] = None,
    ) -> None:
        """Config dataclass ベースの API (Issue #227 後続 HIGH-1)。

        - ``core``: 必須インフラ群 (observation_buffer / world_query_service 等)
        - ``sections``: 任意 provider 群 (persona / objective / inventory / memo)
        - ``limits``: action_instruction の設定

        sections / limits は省略可能で、それぞれ「全フィールドが
        default」のインスタンスが使われる (= optional 機能はすべて無効)。
        """
        sections = sections or PromptSectionProviders()
        limits = limits or PromptLimits()

        # core は dataclass 自体が型 + non-Optional で表現するため、
        # 個別 isinstance 検証は最小限に絞る (Protocol 系のみ)
        if not isinstance(core, PromptBuilderCoreServices):
            raise TypeError("core must be PromptBuilderCoreServices")
        if not isinstance(sections, PromptSectionProviders):
            raise TypeError("sections must be PromptSectionProviders")
        if not isinstance(limits, PromptLimits):
            raise TypeError("limits must be PromptLimits")

        # Issue #227 HIGH-3 Part 2: world_query_service / player_profile_repository は
        # 「DefaultPromptBuilder が呼ぶ 1〜2 メソッドを満たせばよい」duck-type 契約に
        # ゆるめる。world_runtime runtime のような独自経路から adapter を差し込めるよう、
        # isinstance ではなく hasattr で構造チェックする。
        if not hasattr(core.world_query_service, "get_player_current_state"):
            raise TypeError("core.world_query_service must have get_player_current_state method")
        if not hasattr(core.player_profile_repository, "find_by_id"):
            raise TypeError("core.player_profile_repository must have find_by_id method")

        observation_buffer = core.observation_buffer
        short_term_memory = core.short_term_memory
        recent_event_store = core.recent_event_store
        world_query_service = core.world_query_service
        player_profile_repository = core.player_profile_repository
        current_state_formatter = core.current_state_formatter
        recent_events_formatter = core.recent_events_formatter
        context_format_strategy = core.context_format_strategy
        system_prompt_builder = core.system_prompt_builder
        available_tools_provider = core.available_tools_provider

        persona_block_provider = sections.persona_block_provider
        objective_text_provider = sections.objective_text_provider
        known_people_text_provider = sections.known_people_text_provider
        episode_index_text_provider = sections.episode_index_text_provider
        being_memo_text_provider = sections.being_memo_text_provider
        inventory_text_provider = sections.inventory_text_provider

        default_action_instruction = limits.default_action_instruction
        if not isinstance(observation_buffer, IObservationContextBuffer):
            raise TypeError("observation_buffer must be IObservationContextBuffer")
        if not isinstance(short_term_memory, IShortTermMemory):
            raise TypeError("short_term_memory must be IShortTermMemory")
        if not isinstance(recent_event_store, UnifiedRecentEventStore):
            raise TypeError("recent_event_store must be UnifiedRecentEventStore")
        # world_query_service / player_profile_repository は __init__ 冒頭で
        # hasattr 構造チェック済み (Issue #227 HIGH-3 Part 2: duck-type 契約)
        if not isinstance(current_state_formatter, ICurrentStateFormatter):
            raise TypeError("current_state_formatter must be ICurrentStateFormatter")
        if not isinstance(recent_events_formatter, IRecentEventsFormatter):
            raise TypeError("recent_events_formatter must be IRecentEventsFormatter")
        if not isinstance(context_format_strategy, IContextFormatStrategy):
            raise TypeError("context_format_strategy must be IContextFormatStrategy")
        if not isinstance(system_prompt_builder, ISystemPromptBuilder):
            raise TypeError("system_prompt_builder must be ISystemPromptBuilder")
        if not isinstance(available_tools_provider, IAvailableToolsProvider):
            raise TypeError("available_tools_provider must be IAvailableToolsProvider")
        if not isinstance(ui_context_builder, ILlmUiContextBuilder):
            raise TypeError("ui_context_builder must be ILlmUiContextBuilder")
        if persona_block_provider is not None and not callable(persona_block_provider):
            raise TypeError("persona_block_provider must be callable or None")
        if not isinstance(default_action_instruction, str):
            raise TypeError("default_action_instruction must be str")
        if current_tick_provider is not None and not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable or None")
        if objective_text_provider is not None and not callable(objective_text_provider):
            raise TypeError("objective_text_provider must be callable or None")
        if known_people_text_provider is not None and not callable(known_people_text_provider):
            raise TypeError("known_people_text_provider must be callable or None")
        if episode_index_text_provider is not None and not callable(episode_index_text_provider):
            raise TypeError("episode_index_text_provider must be callable or None")
        if being_memo_text_provider is not None and not callable(being_memo_text_provider):
            raise TypeError("being_memo_text_provider must be callable or None")
        if inventory_text_provider is not None and not callable(inventory_text_provider):
            raise TypeError("inventory_text_provider must be callable or None")
        if trace_recorder is not None and not isinstance(trace_recorder, ITraceRecorder):
            raise TypeError("trace_recorder must be ITraceRecorder or None")
        if trace_recorder_provider is not None and not callable(trace_recorder_provider):
            raise TypeError("trace_recorder_provider must be callable or None")

        # 直前ターンで同じ tool + 同じ引数を選ぼうとしているとき、その状態を
        # peek して instruction の先頭に専用警告を挟む (= attention 補強)。
        # loop_guard 本体の observation 注入は recent_events に並ぶので
        # 埋もれやすい。recency bias が効きやすい instruction の冒頭に
        # prepend して、LLM が「直前と同じ手」を選ぶ直前にもう一度気付く
        # きっかけを作る。None なら警告 prefix は出ない (= 既存挙動)。
        if tool_call_loop_guard is not None:
            from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
                ToolCallLoopGuardService,
            )

            if not isinstance(tool_call_loop_guard, ToolCallLoopGuardService):
                raise TypeError("tool_call_loop_guard must be ToolCallLoopGuardService or None")
        self._tool_call_loop_guard = tool_call_loop_guard
        self._objective_text_provider = objective_text_provider
        self._known_people_text_provider = known_people_text_provider
        self._episode_index_text_provider = episode_index_text_provider
        self._being_memo_text_provider = being_memo_text_provider
        self._inventory_text_provider = inventory_text_provider
        self._current_tick_provider = current_tick_provider

        self._observation_buffer = observation_buffer
        self._short_term_memory = short_term_memory
        self._recent_event_store = recent_event_store
        self._world_query_service = world_query_service
        self._profile_repository = player_profile_repository
        self._current_state_formatter = current_state_formatter
        self._recent_events_projection = core.recent_events_projection
        self._recent_events_shadow = core.recent_events_shadow
        self._recent_events_formatter = recent_events_formatter
        self._context_format_strategy = context_format_strategy
        self._system_prompt_builder = system_prompt_builder
        self._available_tools_provider = available_tools_provider
        self._ui_context_builder = ui_context_builder
        self._persona_block_provider = persona_block_provider
        self._default_action_instruction = default_action_instruction
        self._trace_recorder = trace_recorder
        self._trace_recorder_provider = trace_recorder_provider
        self._logger = logging.getLogger(self.__class__.__name__)

    def _resolve_trace_recorder(self) -> ITraceRecorder | None:
        """trace の recorder を runtime 時点で取得する。

        ``trace_recorder_provider`` があれば毎回 lookup (= 後付け差し込み
        対応)、なければ構築時固定値。provider 例外は None フォールバック
        (= prompt は普段通り組まれ、trace 行だけ落ちる)。
        """
        if self._trace_recorder_provider is not None:
            try:
                return self._trace_recorder_provider()
            except Exception:
                # 通常 provider は単純な lambda なので例外は希。DI 化や
                # 動的解決を加えたときに silent に消えるのを防ぐため DEBUG
                # 級で痕跡を残す。
                self._logger.debug(
                    "trace_recorder_provider raised; skipping trace",
                    exc_info=True,
                )
                return None
        return self._trace_recorder

    def _emit_prompt_section_breakdown_trace(
        self,
        *,
        player_id: PlayerId,
        system_content: str,
        objective_text: str,
        current_state_text: str,
        memos_text: str,
        recent_events_text: str,
        inventory_text: str,
        instruction: str,
        tools: list[dict[str, Any]],
        user_content: str,
        known_people_text: str = "",
        episode_index_text: str = "",
    ) -> None:
        """``PROMPT_SECTION_BREAKDOWN`` を 1 件記録する (失敗は握りつぶす)。

        prompt_builder.build() の末尾で 1 ターン 1 件呼ぶ。各 section の文字数を
        独立に計測することで、後続の prefix cache / token 分析で「どの section
        が prompt_tokens を支配しているか」が post-hoc に分かる。

        tools 配列は ``json.dumps`` でシリアライズした長さを使う。これは LLM
        API に送られる payload サイズの近似で、tool が動的に増減する効果を
        測れる。
        """
        recorder = self._resolve_trace_recorder()
        if recorder is None:
            return
        tick: int | None = None
        if self._current_tick_provider is not None:
            try:
                tick = self._current_tick_provider()
            except Exception:
                tick = None
        try:
            import json as _json

            tools_chars = len(_json.dumps(tools, ensure_ascii=False))
        except Exception:
            tools_chars = 0
        try:
            recorder.record(
                TraceEventKind.PROMPT_SECTION_BREAKDOWN,
                tick=tick,
                player_id=int(player_id.value),
                system_chars=len(system_content),
                objective_chars=len(objective_text),
                known_people_chars=len(known_people_text),
                episode_index_chars=len(episode_index_text),
                current_state_chars=len(current_state_text),
                memos_chars=len(memos_text),
                recent_events_chars=len(recent_events_text),
                inventory_chars=len(inventory_text),
                instruction_chars=len(instruction),
                tools_chars=tools_chars,
                user_content_chars=len(user_content),
                messages_total_chars=len(system_content) + len(user_content),
                tools_count=len(tools),
            )
        except Exception:
            self._logger.debug(
                "trace recorder.record raised for PROMPT_SECTION_BREAKDOWN; skipping",
                exc_info=True,
            )

    def _build_loop_warning_prefix(self, player_id: PlayerId) -> str:
        """instruction の前に挟む「同じ手の繰り返し」警告 prefix を返す。

        ``tool_call_loop_guard.peek_streak`` が連続 2 回以上を返したときだけ
        prefix を作る。それ以外は空文字。文面は recent_events に流れる
        loop_guard 警告と意図的に重ねて、両方の attention 経路を踏む。
        """
        if self._tool_call_loop_guard is None:
            return ""
        try:
            streak = self._tool_call_loop_guard.peek_streak(player_id)
        except Exception:
            return ""
        if streak is None:
            return ""
        tool_name, count = streak
        return (
            f"⚠ 直前のあなたは `{tool_name}` を同じ引数で {count} ターン連続"
            f"実行しました。同じ手を取れば同じ結果しか返りません。"
            f"「直近の出来事」のエラーメッセージや状況のヒントを読み返し、"
            f"別の選択肢 (引数を変える / 別のツールを使う / 周囲に尋ねる等) "
            f"を選んでください。"
        )

    def build(
        self,
        acting: ActingBeing,
        action_instruction: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(acting, ActingBeing):
            raise TypeError("acting must be ActingBeing")
        if action_instruction is not None and not isinstance(action_instruction, str):
            raise TypeError("action_instruction must be str or None")
        player_id = acting.player_id

        # 1. プロフィール取得（システムプロンプト用。必須）
        profile = self._profile_repository.find_by_id(player_id)
        if profile is None:
            raise PlayerProfileNotFoundForPromptException(player_id.value)
        player_info = SystemPromptPlayerInfoDto(
            player_name=profile.name.value,
            role=profile.role.value,
            race=profile.race.value,
            element=profile.element.value,
            game_description="",
            persona_block=(self._persona_block_provider(player_id) if self._persona_block_provider is not None else ""),
        )

        # 2. drain して短期記憶に append
        drained = self._observation_buffer.drain(player_id)
        if drained:
            self._short_term_memory.append_all(player_id, drained)

        # 3. 現在状態取得（None の場合はプレースホルダ）
        current_state_dto = self._world_query_service.get_player_current_state(
            GetPlayerCurrentStateQuery(
                player_id=player_id.value,
            )
        )
        if current_state_dto is not None:
            base_current_state_text = self._current_state_formatter.format(current_state_dto)
        else:
            base_current_state_text = MESSAGE_WHEN_PLAYER_NOT_PLACED
        ui_context = self._ui_context_builder.build(
            base_current_state_text,
            current_state_dto,
        )
        current_state_text = ui_context.current_state_text

        # 4. 直近の出来事（観測＋行動結果をマージ）
        recent_entries = self._recent_event_store.get_active_timeline(player_id)
        projected_entries = recent_entries
        shown_notification_ids: tuple[str, ...] = ()
        if self._recent_events_projection is not None:
            projected_entries, shown_notification_ids = self._recent_events_projection(player_id, recent_entries)
        recent_events_text = self._recent_events_formatter.format_unified_entries(projected_entries)
        if self._recent_events_shadow is not None:
            self._recent_events_shadow(player_id, recent_events_text)

        # 5. 利用可能ツール取得
        tools = self._available_tools_provider.get_available_tools(current_state_dto)

        # Issue #227 chore β: 実行ランタイム固有の固定目的文 + 所持物証テキスト
        # を provider 経由で取得 (world_runtime format への統一)。
        # provider が落ちた場合は ERROR で記録した上で空文字に degrade する。
        # WARNING ではなく ERROR にする理由: provider 実装バグはサイレントに
        # 黙過すべきでなく、ログ集約側で必ず可視化したい (silent failure 防止)。
        # 一方で prompt 構築全体を中断するのは過剰なので degrade で続行する。
        objective_text = self._call_text_provider(self._objective_text_provider, player_id, "objective_text_provider")
        inventory_text = self._call_text_provider(self._inventory_text_provider, player_id, "inventory_text_provider")
        known_people_text = self._call_text_provider(
            self._known_people_text_provider, player_id, "known_people_text_provider"
        )
        episode_index_text = self._call_text_provider(
            self._episode_index_text_provider, player_id, "episode_index_text_provider"
        )
        being_memo_text = self._call_text_provider(
            self._being_memo_text_provider, player_id, "being_memo_text_provider"
        )

        # Phase 2: 短期記憶の L4 mid summary (rolling 実装のみが値を返す)。
        # 失敗しても prompt 構築を止めない。
        try:
            raw_mid = self._short_term_memory.get_mid_summary_text(player_id)
            mid_summary_text = raw_mid if isinstance(raw_mid, str) else ""
        except Exception as e:
            self._logger.warning(
                "get_mid_summary_text failed for player_id=%s: %s",
                player_id.value,
                e,
                exc_info=True,
            )
            mid_summary_text = ""

        context = self._context_format_strategy.format(
            current_state_text=current_state_text,
            recent_events_text=recent_events_text,
            objective_text=objective_text,
            inventory_text=inventory_text,
            mid_summary_text=mid_summary_text,
            known_people_text=known_people_text,
            episode_index_text=episode_index_text,
            being_memo_text=being_memo_text,
        )

        # Issue #227 chore β: failure_block (直前ターン失敗時の補正セクション)
        # を廃止した。理由:
        #   1. 同じ失敗情報は ``recent_events_text`` (## 直近の出来事) に既に
        #      含まれている。重複表示で LLM の attention が拡散する。
        #   2. 「連続同一ツール失敗」の警告は PR #230 で導入した
        #      ``tool_call_loop_guard`` がより一般化して扱う (success / fail
        #      両方 / threshold 可変)。失敗専用のセクションは loop_guard で
        #      代替可能。
        # build_pre_turn_failure_section() を呼んでいた箇所はこの commit で削除。
        user_context_body = context.rstrip()

        # 7. システムプロンプト・ユーザーメッセージ
        system_content = self._system_prompt_builder.build(player_info)
        instruction = action_instruction or self._default_action_instruction
        # 7b. loop_guard 警告 prefix:
        # 直前ターンで同じ (tool, 引数) を選んでいた場合、instruction の
        # 直前に短い警告を挟む。recent_events に埋もれる loop_guard 観測と
        # 違い、instruction 末尾は LLM の attention が乗りやすい位置のため、
        # 「同じ手をもう一度選ぼうとしている」瞬間に気付かせやすい。
        loop_warning = self._build_loop_warning_prefix(player_id)
        if loop_warning:
            instruction = loop_warning + "\n\n" + instruction
        user_content = user_context_body + "\n\n" + instruction

        result: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            "tools": tools,
            "tool_choice": "required",
        }
        result["sns_shown_notification_ids"] = shown_notification_ids
        result["tool_runtime_context"] = ui_context.tool_runtime_context
        # Phase A が、実際に API へ出す tool 集合から動的引数候補表を作り、
        # この指示の直前へ安全に差し込むための境界を明示する。
        result["action_instruction"] = instruction
        result["current_state_snapshot"] = current_state_text
        result["persona_snapshot"] = player_info.persona_block

        # 実験 #356 後続: prefix cache 分析用の section 別 char 内訳を trace に
        # 1 件記録する。token ではなく char で吐く理由はモジュール docstring 参照。
        self._emit_prompt_section_breakdown_trace(
            player_id=player_id,
            system_content=system_content,
            objective_text=objective_text,
            known_people_text=known_people_text,
            episode_index_text=episode_index_text,
            current_state_text=current_state_text,
            memos_text=being_memo_text,
            recent_events_text=recent_events_text,
            inventory_text=inventory_text,
            instruction=instruction,
            tools=tools,
            user_content=user_content,
        )
        return result

    def _call_text_provider(
        self,
        provider: Callable[[PlayerId], str] | None,
        player_id: PlayerId,
        provider_name: str,
    ) -> str:
        """provider を呼んで text を返す。落ちたら ERROR ログ + 空文字 degrade。

        provider バグを silent に握り潰すと debug が極めて困難になるため、
        ERROR レベル + exc_info=True でログ集約側に必ず可視化させる。
        prompt 構築自体は止めず degrade で続行する (provider は補助的な
        section なので、欠けても LLM ターン自体は成立する)。
        """
        if provider is None:
            return ""
        try:
            return provider(player_id) or ""
        except Exception:
            self._logger.error(
                "%s raised; degrading to empty text. Fix provider implementation.",
                provider_name,
                exc_info=True,
            )
            return ""
