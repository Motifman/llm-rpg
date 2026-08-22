"""Tool dispatch / wire / speech / busy interrupt。"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Collection
from dataclasses import replace as dataclass_replace
from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    is_reschedulable_error_code,
    should_reschedule_for_next_tick,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    ACTION_HISTORY_PROJECTION_KEY,
    project_action_arguments_for_history,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.llm.services.failure_helpers import (
    list_destination_labels,
    list_object_labels,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_BUY_ITEM,
    TOOL_NAME_SPOT_GRAPH_MARKET_BID,
    TOOL_NAME_SPOT_GRAPH_MARKET_BUY,
    TOOL_NAME_SPOT_GRAPH_MARKET_CANCEL,
    TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM,
    TOOL_NAME_SPOT_GRAPH_MARKET_REPRICE,
    TOOL_NAME_SPOT_GRAPH_MARKET_SELL,
    TOOL_NAME_SPOT_GRAPH_MARKET_VIEW,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
    TOOL_NAME_SPOT_GRAPH_REPORT_BODY,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    TOOL_NAME_SPOT_GRAPH_TRADE_ACCEPT,
    TOOL_NAME_SPOT_GRAPH_TRADE_DECLINE,
    TOOL_NAME_SPOT_GRAPH_TRADE_OFFER,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_VOTE,
    TOOL_NAME_SPOT_GRAPH_WAIT,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)

from ai_rpg_world.application.llm.services.world_llm_turn.escape_tools import (
    filter_definitions_for_escape_llm,
    validate_tool_handler_consistency,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_name_rescue import (
    build_unsupported_tool_message,
)
from ai_rpg_world.application.llm.services.world_llm_turn.gold_change_trace import (
    build_gold_reader,
    build_roster_reader,
    wrap_with_gold_change,
)

logger = logging.getLogger(__name__)

BUSY_FREE_TOOLS: frozenset[str] = frozenset({
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_WAIT,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_LIST,
    TOOL_NAME_TODO_COMPLETE,
})

def wire_missing_spot_graph_tools(wiring) -> None:
    """#344: spot_graph_use_item / attack / give_item / pickup_item /
    drop_item / prepare_action を experiment runtime から呼べるよう、
    SpotGraphToolExecutor を runtime のリポジトリ群で組み立てて handler を
    merge する。

    runtime に必要なリポジトリ / orchestrator が揃っていない (= テストや
    minimal wiring) 場合は silent に skip する (該当ツールは旧来通り
    UNSUPPORTED_TOOL のままになるが、本来の experiment 経路では届く前提)。
    """
    runtime = wiring.runtime
    # 必須リポジトリ群。どれかが欠けたら executor の構築は諦める。
    needed = (
        "_player_inventory_repo",
        "_item_repo",
        "_player_status_repo",
        "_item_transfer_service",
        "_interaction_service",
        "_movement_service",
        "_exploration_service",
        "_world_flag_state",
        "_exploration_progress",
    )
    for attr in needed:
        if not hasattr(runtime, attr) or getattr(runtime, attr) is None:
            # PR-θ1 (経路統合) レビュー HIGH #2: travel_to は本来
            # runtime.do_move + runtime.id_mapper + runtime._spot_graph_repo
            # しか要らないが、経路統合で他 tool と同じ needed check の下に
            # 組み込まれた。従って interaction_service / exploration_service
            # 等が欠けた test wiring では travel_to まで UNSUPPORTED_TOOL に
            # 化ける。production wiring (world_runtime.py) では needed が
            # 必ず全部揃うので顕在化しないが、将来的な軽量 wiring / mock
            # 構成で travel_to だけが理由不明に消える silent failure リスク
            # がある。travel_to 独立 wire は経路が再び分裂するので却下、
            # 本コメントで risk を明示するに留める。
            logger.warning(
                "_wire_missing_spot_graph_tools: runtime is missing %s; "
                "use_item / attack / give_item / pickup_item / drop_item / "
                "prepare_action / tend_to_player / travel_to will remain "
                "UNSUPPORTED_TOOL.",
                attr,
            )
            return


    services = SpotGraphWorldServices(
        interaction=runtime._interaction_service,
        exploration=runtime._exploration_service,
        world_flags=runtime._world_flag_state,
        game_end_evaluator=GameEndConditionEvaluator(),
        exploration_progress=runtime._exploration_progress,
        movement=runtime._movement_service,
    )
    # monster_repository / attack_orchestrator は monster placements を
    # 持つシナリオのみ runtime に存在する。spot_graph_attack は両方無いと
    # 「未対応」を返すよう executor 側で実装済み。
    # ConsumableUsedEvent を ConsumableEffectHandler に届けるため
    # pipeline_event_publisher を渡す。これがないと use_item が
    # 「使用した」success を返しつつ HP / hunger が変化しない silent
    # failure になる (#344 の隠れた半分)。
    event_publisher = getattr(runtime, "_speech_event_publisher", None)
    executor = SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=runtime._player_inventory_repo,
        item_repository=runtime._item_repo,
        event_publisher=event_publisher,
        spot_graph_repository=runtime._spot_graph_repo,
        monster_repository=getattr(runtime, "_monster_repo", None),
        player_status_repository=runtime._player_status_repo,
        attack_orchestrator=getattr(runtime, "_attack_orchestrator", None),
        item_transfer_service=runtime._item_transfer_service,
        # テスト用の代役 runtime には無いことがあるので getattr で読む。
        # 未注入なら executor が NOT_WIRED を返す (黙って成功しない)。
        merchant_trade_service=getattr(runtime, "_merchant_trade_service", None),
        player_trade_service=getattr(runtime, "_player_trade_service", None),
        market_service=getattr(runtime, "_market_service", None),
        time_provider=getattr(runtime, "_time_provider", None),
        sync_action_groups=getattr(
            getattr(runtime, "scenario", None),
            "synchronized_action_groups",
            (),
        ),
        # #380: 前提条件の失敗を「待てば戻る / もう変わらない」に区分する
        # 材料。渡さないと「時間で回復」が判別できず、251 件 (実測) に
        # 「別の対象へ」という逆の助言が出る。配線されていることは
        # tests/demos/test_precondition_failure_kind_is_wired.py が見張る。
        reactive_object_state_bindings=getattr(
            getattr(runtime, "scenario", None),
            "reactive_object_state_bindings",
            (),
        ),
        # 実験 #29 後続: travel/give/drop/pickup の say_inline 短発話用。
        speech_service=getattr(runtime, "_speech_service", None),
        # PR-θ1 (経路統合): travel_to を旧 _handle_travel_to から新経路
        # SpotGraphToolExecutor._travel_to に統合するため runtime を注入。
        # _travel_to 内部で runtime.do_move を呼んで単一の副作用実装を
        # 共有する。runtime.do_move は既に start_travel_to_spot +
        # _process_graph_events + 同一 spot 短絡 + _record_action_result
        # (scene_boundary + subjective) を面倒見ている。
        runtime=runtime,
    )
    wiring._spot_graph_executor = executor
    raw_handlers = executor.get_handlers()
    # executor は (player_id_int, args) -> result の signature。
    # _tool_handlers は (PlayerId, args, runtime_context) -> result なので
    # ラップして adapt する。runtime_context は executor 側で使わない。
    # PR-α (Y_after_pr639_640 後続): 旧 give_items は削除、give_item に
    # batch-always で統合された。旧 PR-E のコメントで触れていた
    # 「give_items が漏れる silent failure」問題は本 refactor で不要になった。
    targets = (
        TOOL_NAME_SPOT_GRAPH_USE_ITEM,
        TOOL_NAME_SPOT_GRAPH_ATTACK,
        TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
        TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
        TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
        TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
        TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
        # PR-θ1 (経路統合): travel_to を旧 _handle_travel_to から新経路
        # SpotGraphToolExecutor._travel_to に統合。以前は 2 経路に分裂して
        # おり travel_to の say_inline が 100% silent failure していた。
        TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
        # PR-θ2 (経路統合): explore を旧 _handle_explore から新経路
        # SpotGraphToolExecutor._explore に統合。旧 handler 相当の
        # 「発見なし時に可視 object 併記」も新経路で保持 (runtime_context
        # 経由で targets を参照)。
        TOOL_NAME_SPOT_GRAPH_EXPLORE,
        # PR-θ3 (経路統合): interact を旧 _handle_interact から新経路
        # SpotGraphToolExecutor._interact に統合。旧 handler 相当の
        # InteractionNotAllowedException / InteractionNotFoundException
        # ハンドリング (LLM 向け remediation + 利用可能操作列挙) も新経路で
        # 保持。resolver エラー時の invalid_label_failure_builder も設定。
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        # PR-θ4 (経路統合): listen を旧 _handle_listen から新経路
        # SpotGraphToolExecutor._listen に統合。runtime.do_listen 経由で
        # 副作用 (_process_graph_events / event 差分カウント) は保持。
        TOOL_NAME_SPOT_GRAPH_LISTEN,
        # PR-θ5 (経路統合): wait を旧 _handle_wait から新経路
        # SpotGraphToolExecutor._wait に統合。runtime.do_wait 経由で
        # 副作用 (_record_action_result + subjective 記録) を保持しつつ、
        # 新経路の付加価値 (疲労回復 = FATIGUE_RECOVERY_WAIT) も引き継ぐ。
        TOOL_NAME_SPOT_GRAPH_WAIT,
        # 会議と投票 PR 6 / PR 8。**どちらも露出だけ足して dispatch を
        # 忘れていた。** vote は会議中にしか出ないので、現在フェーズ
        # だけを見る起動時検査を素通りしていた (検査自体もこの PR で
        # 両フェーズを見るように直した)。
        TOOL_NAME_SPOT_GRAPH_VOTE,
        TOOL_NAME_SPOT_GRAPH_REPORT_BODY,
        # 経済統合 Phase 1: 商人との売買。露出だけ足して dispatch を
        # 忘れると UNSUPPORTED_TOOL に化ける (#589 / #590 と同じ形)。
        TOOL_NAME_SPOT_GRAPH_BUY_ITEM,
        TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
        # 経済統合 Phase 3: 市場の掲示板。ここも露出だけ足して dispatch を
        # 忘れると UNSUPPORTED_TOOL に化ける。起動時検査
        # (ToolHandlerConsistencyError) が実際に落ちて教えてくれた。
        TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM,
        TOOL_NAME_SPOT_GRAPH_MARKET_BUY,
        TOOL_NAME_SPOT_GRAPH_MARKET_REPRICE,
        TOOL_NAME_SPOT_GRAPH_MARKET_CANCEL,
        TOOL_NAME_SPOT_GRAPH_MARKET_BID,
        TOOL_NAME_SPOT_GRAPH_MARKET_SELL,
        TOOL_NAME_SPOT_GRAPH_MARKET_VIEW,
        # 経済統合 Phase 2: 人同士の取引。露出だけ足して dispatch を
        # 忘れると UNSUPPORTED_TOOL に化ける。
        TOOL_NAME_SPOT_GRAPH_TRADE_OFFER,
        TOOL_NAME_SPOT_GRAPH_TRADE_ACCEPT,
        TOOL_NAME_SPOT_GRAPH_TRADE_DECLINE,
    )
    # #356 実験 #25 OFF で発覚: use_item / drop_item / give_item /
    # pickup_item は tool catalog 上 ``item_label`` (= I1, I2 など) を
    # 受け取るが、executor は post-resolver の ``item_spec_id`` /
    # ``slot_id`` / ``item_instance_id`` を読む。それらの間を埋める
    # ``SpotGraphArgumentResolver`` の呼び出しが experiment 用 wiring
    # に無く、164 件すべて INVALID_ARGUMENT で落ちていた。
    # 解決後 args を executor に渡すように adapter で resolver を噛ませる。
    resolver_targets = frozenset({
        TOOL_NAME_SPOT_GRAPH_USE_ITEM,
        TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
        TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
        TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
        # attack も resolver 経由で `target_label='大型カニ'` を
        # `monster_id` に解決する必要がある。Issue #618 で発覚した
        # silent failure: resolver に hook されていなかったため、
        # agent が attack を呼ぶと毎回 `INVALID_TARGET_LABEL: monster_id
        # が解決されていません` で reject されていた (= scenario で
        # モンスターと戦えない致命的 bug)。
        TOOL_NAME_SPOT_GRAPH_ATTACK,
        # Issue #621 Phase 3b: 新 tool `tend_to_player`。
        # `target_player_label='エイダ'` を `target_player_id` に解決して
        # executor に渡す必要があるため resolver hook が必須。
        TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
        # PR-θ1 (経路統合): travel_to も resolver 経由で
        # `destination_label='森の広場'` を `destination_spot_id` に解決
        # する。旧 handler は handler 内で resolve していたが、新経路は
        # resolver stage で SpotGraphArgumentResolver._resolve_travel_to
        # (`resolve_destination_target` 同一関数を再利用) が変換する。
        TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
        # PR-θ3 (経路統合): interact も resolver 経由で
        # `target_label='OBJ1'` を `object_id` に解決する。旧 handler と
        # 同じく resolver 例外時の「有効な target_label 一覧」 message は
        # invalid_label_failure_builder で構築する。
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        # vote / report_body はどちらも `target_player_label='アオイ'`
        # を `target_player_id` に解決してから executor に渡す。
        # resolver を挟まないと executor が None を読んで必ず失敗する
        # (#618 の attack と同じ形)。
        TOOL_NAME_SPOT_GRAPH_VOTE,
        TOOL_NAME_SPOT_GRAPH_REPORT_BODY,
        # 売買も resolver 経由で `item_label='パン'` を「どの商人の
        # どの品か」へ解決する。挟まないと executor が merchant_id を
        # 読めず必ず失敗する。
        TOOL_NAME_SPOT_GRAPH_BUY_ITEM,
        TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
        # 取引も resolver 経由で相手と差し出す品を解決する。
        TOOL_NAME_SPOT_GRAPH_TRADE_OFFER,
        TOOL_NAME_SPOT_GRAPH_TRADE_ACCEPT,
        TOOL_NAME_SPOT_GRAPH_TRADE_DECLINE,
    })
    argument_resolver = SpotGraphArgumentResolver()
    for tool_name in targets:
        raw = raw_handlers.get(tool_name)
        if raw is None:
            continue
        if tool_name in resolver_targets:
            # PR-θ1/θ3 (経路統合): travel_to / interact は resolver 例外時に
            # 「有効な label 一覧 + should_reschedule」を含む tool-specific
            # 失敗を組み立てる (旧 handler 相当)。他 tool は従来通り generic
            # message で処理。
            tool_specific_builder = (
                build_travel_to_invalid_label_failure
                if tool_name == TOOL_NAME_SPOT_GRAPH_TRAVEL_TO
                else build_interact_invalid_label_failure
                if tool_name == TOOL_NAME_SPOT_GRAPH_INTERACT
                else None
            )
            adapted = adapt_executor_handler_with_resolver(
                raw, tool_name, argument_resolver,
                invalid_label_failure_builder=tool_specific_builder,
            )
        else:
            adapted = adapt_executor_handler(raw)
        wiring._tool_handlers[tool_name] = adapted
    _wrap_every_handler_with_gold_change(wiring, runtime)
    # Step 1 並列化 review HIGH 1: build_full_prompt が内部で lazy-init する
    # _todo_tool_executor / _cached_default_prompt_builder は check-then-act
    # で 2 スレッドが同時に初回呼び出しすると double-init になる。並列実行
    # の前に単一スレッドで pre-warm して race を構造的に消す。
    try:
        if hasattr(runtime, "_wire_auxiliary_tool_stack"):
            runtime._wire_auxiliary_tool_stack()
        if hasattr(runtime, "_get_or_build_default_prompt_builder"):
            runtime._get_or_build_default_prompt_builder()
    except Exception:
        # pre-warm に失敗しても通常パスはあくまで lazy で動く。安全側 fallback。
        logger.exception(
            "Pre-warming auxiliary tool stack / default prompt builder failed; "
            "lazy initialization will fall back, but Phase A 並列化時に race の "
            "可能性が残る"
        )
    # PR-E: tool spec (= LLM に見せる) と _tool_handlers (= dispatch SSOT) の
    # 不整合は起動時に止める。pre-warm が aux executor を完成させた直後に
    # 一度だけ実行するため、ここに置く。get_tool_definitions に失敗しても
    # それ自体は通常運用で起きるべきでないが、検証ロジックの破綻で実験を
    # 止めるのは過剰なので例外なら警告だけ残す。
    wiring._validate_tool_handler_consistency()

def definitions_across_phases(wiring) -> list:
    """**どのフェーズでも**露出しうる tool 定義をまとめて返す。

    現在フェーズだけを見ると、会議中にしか出ない tool (vote) が検査を
    素通りする。実際 vote は handler 未登録のまま起動時検査を通っていて、
    会議が始まって初めて UNSUPPORTED_TOOL になる状態だった。PR #589 /
    #590 で潰したはずの silent failure が、フェーズという新しい軸で
    戻ってきた形になる。

    フェーズを問わない tool は両方に出るので、名前で重複を除く。
    """
    seen: dict = {}
    for as_meeting in (False, True):
        try:
            definitions = wiring.runtime.get_tool_definitions(
                as_meeting_phase=as_meeting,
                for_every_player=True,
            )
        except TypeError:
            # フェーズ機構を持たない runtime (= 引数を知らない) は
            # 現在フェーズだけで検査する。
            definitions = wiring.runtime.get_tool_definitions()
        for definition in definitions:
            seen.setdefault(definition.name, definition)
    return list(seen.values())

def validate_tool_handler_consistency_for_wiring(wiring) -> None:
    """runtime が expose する tool 定義集合と _tool_handlers のキー集合が
    矛盾していないか確認する。expose されているのに handler 未登録の tool
    があれば ``ToolHandlerConsistencyError`` を投げて起動を止める。

    過去 PR #589 / #590 で「LLM には tool を見せているのに dispatch 側で
    UNSUPPORTED_TOOL になる」silent failure を 30 tick 走らせてから気付いた
    ことが直接の動機。
    """
    try:
        definitions = definitions_across_phases(wiring)
    except Exception as exc:
        if exc.__class__.__name__ == "ToolExposureConfigurationError":
            raise
        logger.warning(
            "_validate_tool_handler_consistency: get_tool_definitions が "
            "失敗したため整合性検証をスキップする",
            exc_info=True,
        )
        return
    # PR-A: LLM に実際に expose する tool 集合と handler 集合を突合する。
    # 脱出ランタイムで永続的に UNSUPPORTED_TOOL になる tool は除外して比較
    # (= 「expose されているのに handler が無い」検出だけは引き続き機能する)。
    definitions = filter_definitions_for_escape_llm(definitions)
    exposed_names = [d.name for d in definitions]
    validate_tool_handler_consistency(
        exposed_tool_names=exposed_names,
        handler_keys=wiring._tool_handlers.keys(),
    )

def build_interact_invalid_label_failure(
    runtime_context: Any,
    arguments: Dict[str, Any],
    exc: Exception,
) -> LlmCommandResultDto:
    """PR-θ3 (経路統合): interact の resolver 例外を旧 _handle_interact
    相当の tool-specific 失敗 dto に変換する。

    旧 handler は resolver 例外時に「有効な target_label 一覧を含む
    message + target_label 用の remediation」を組み立てていた。
    """
    targets = getattr(runtime_context, "targets", {}) or {}
    label = str(arguments.get("target_label", ""))
    valid_objects = list_object_labels(targets)
    error_code = getattr(exc, "error_code", "INVALID_TARGET_LABEL")
    if error_code == "INVALID_ARGUMENT":
        return LlmCommandResultDto(
            success=False,
            message=str(exc),
            error_code=error_code,
            remediation=(
                "action_name には、target_label で指定したオブジェクト行の "
                "[] 内に表示されている操作名を 1 つ指定してください。"
                "日本語の説明文ではなく、表示された action_name をそのまま使ってください。"
            ),
            should_reschedule=is_reschedulable_error_code(error_code),
        )
    # 暗さでプロンプトから伏せた物体は resolver の候補には入れない。
    # ただし、記憶や目的文から正しい名前を指定した場合に「存在しない」と
    # 返すのも嘘になる。今回の snapshot が内部に保持した名前との完全一致
    # のときだけ、物体名を列挙せず視界の理由を返す。
    normalized_label = label.strip().strip('"\'「」')
    dark_hidden_names = tuple(
        getattr(runtime_context, "dark_hidden_object_names", ()) or ()
    )
    if normalized_label and normalized_label in dark_hidden_names:
        return LlmCommandResultDto(
            success=False,
            message=(
                f"暗くて見えないため、{normalized_label}を対象にできない。"
                "灯りを確保してから確かめる必要がある。"
            ),
            error_code=error_code,
            remediation=(
                "灯りを持つか、灯りを持つ人物と同席してから"
                "同じ対象を確認してください。"
            ),
            should_reschedule=is_reschedulable_error_code(error_code),
        )
    # 旧引数名 ``object_label`` で呼ばれたときに「見つかりません: (空文字)」
    # という無意味な文面を返さない。名前を変えた以上、LLM が旧名を書くのは
    # 起こりうる誤りであり、何が悪かったのかを明示できないと同じ失敗を
    # 繰り返す (failure_helpers の設計動機と同じ)。
    if not label.strip() and "object_label" in arguments:
        return LlmCommandResultDto(
            success=False,
            message=(
                "引数名が違います: この tool の対象は object_label ではなく "
                f"target_label で指定します。有効な target_label: "
                f"{valid_objects or '(この場所に interactable なオブジェクトなし)'}"
            ),
            error_code=error_code,
            remediation=(
                "object_label に書いた値をそのまま target_label に移して"
                "呼び直してください。"
            ),
            should_reschedule=is_reschedulable_error_code(error_code),
        )
    return LlmCommandResultDto(
        success=False,
        message=(
            f"対象の名前が見つかりません: {label}。"
            f"有効な target_label: "
            f"{valid_objects or '(この場所に interactable なオブジェクトなし)'}"
        ),
        error_code=error_code,
        remediation=(
            "target_label には「現在の状況」のオブジェクト欄で "
            "\"\" に囲まれているオブジェクト名を指定してください。"
            "action_name は同じ行の [] 内に表示された操作名から選んでください。"
        ),
        should_reschedule=is_reschedulable_error_code(error_code),
    )

def build_travel_to_invalid_label_failure(
    runtime_context: Any,
    arguments: Dict[str, Any],
    exc: Exception,
) -> LlmCommandResultDto:
    """PR-θ1 (経路統合): travel_to の resolver 例外を旧 _handle_travel_to
    相当の tool-specific 失敗 dto に変換する。

    旧 handler は resolver 例外時に:
    1. 有効な destination_label 一覧 (S1, S2, ...) を含む message
    2. destination_label 用の remediation
    3. INVALID_DESTINATION_LABEL 用の reschedule policy を尊重

    の 3 点をやっていた。新経路の resolver adapter は generic message を
    返すため、これらを再現するために tool-specific builder を用意する。
    """
    targets = getattr(runtime_context, "targets", {}) or {}
    label = str(arguments.get("destination_label", ""))
    valid_destinations = list_destination_labels(targets)
    error_code = getattr(exc, "error_code", "INVALID_DESTINATION_LABEL")
    return LlmCommandResultDto(
        success=False,
        message=(
            f"移動先が見つかりません: {label}。"
            f"有効な destination_label: "
            f"{valid_destinations or '(この場所からの移動先なし)'}"
        ),
        error_code=error_code,
        remediation=(
            "destination_label には「現在の状況」の接続先で "
            "\"\" に囲まれている行き先スポット名を指定してください。"
            "矢印の左側の道や扉の名前は指定しないでください。"
        ),
        should_reschedule=is_reschedulable_error_code(error_code),
    )

def resolver_failure_remediation(tool_name: str, error_code: str) -> str:
    """resolver 失敗時に、現在プロンプトと同じ名前指定規約で復帰ヒントを返す。"""
    if error_code == "INVALID_ARGUMENT":
        if tool_name == TOOL_NAME_SPOT_GRAPH_GIVE_ITEM:
            return (
                "gives には {item_label: アイテム名, target_player_label: 相手の名前} "
                "の object を 1 件以上入れてください。item_label は所持アイテム欄の "
                "\"\" 内、target_player_label は同じ場所にいるプレイヤー名を使います。"
            )
        return "ツール説明にある必須引数と型を確認し、足りない引数を指定してください。"
    if tool_name == TOOL_NAME_SPOT_GRAPH_USE_ITEM:
        return (
            "item_label には「現在の状況」の所持アイテム欄で \"\" に囲まれている"
            "アイテム名を指定してください。食べ物以外を使うと別の失敗になります。"
        )
    if tool_name == TOOL_NAME_SPOT_GRAPH_DROP_ITEM:
        return (
            "item_label には「現在の状況」の所持アイテム欄で \"\" に囲まれている"
            "アイテム名を指定してください。地面に落ちているものの名前は drop_item には使えません。"
        )
    if tool_name == TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM:
        return (
            "ground_item_label には「現在の状況」の地面に落ちているもの欄で "
            "\"\" に囲まれているアイテム名を指定してください。所持アイテム名は pickup_item には使えません。"
        )
    if tool_name == TOOL_NAME_SPOT_GRAPH_GIVE_ITEM:
        return (
            "gives の item_label には所持アイテム欄の \"\" 内のアイテム名を、"
            "target_player_label には同じ場所にいる相手の名前を指定してください。"
        )
    if tool_name == TOOL_NAME_SPOT_GRAPH_ATTACK:
        return (
            "target_label には「現在の状況」に表示されているモンスター名を指定してください。"
            "アイテム名・プレイヤー名・オブジェクト名は attack の対象には使えません。"
        )
    if tool_name == TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER:
        return (
            "target_player_label には同じ場所で倒れているプレイヤーの名前を指定してください。"
            "相手が別の場所にいるなら travel_to で移動し、倒れていない相手には speech_speak などを使ってください。"
        )
    if tool_name == TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION:
        return (
            "sub_location_label には「現在の状況」に表示されているサブロケーション名を指定してください。"
        )
    return (
        "ツール説明と「現在の状況」を確認し、そのツールが要求する種類の名前を指定してください。"
    )

def _wrap_every_handler_with_gold_change(wiring, runtime) -> None:
    """登録済みの**全ツール**を、所持金の変化を測る包みで囲む。

    所持金が動いたのに記録が出ないツールがあると、分析側は「どのツールが
    gold を動かすか」を知っていないと台帳を組めない。**知識が分析器の側へ
    漏れる**形で、ツールを 1 つ足すたびに分析器が壊れる。

    ツールの種類で選り分けず全部に掛けるのは、選り分けた瞬間に「選び忘れ」が
    生まれるから。動かなければ何も足さないので、掛けても trace は太らない。
    将来クエスト報酬や戦利品で gold が動いても、同じ経路を通る限り自動で残る。
    """
    statuses = getattr(runtime, "_player_status_repo", None)
    gold_reader = build_gold_reader(statuses)
    # **その場の全員を測る。** 呼んだ人だけだと、二者間の取引で受け取った側が
    # 記録に残らない (実 run で台帳を差額から逆算する羽目になった)。
    roster_reader = build_roster_reader(statuses)
    for tool_name, handler in list(wiring._tool_handlers.items()):
        if getattr(handler, "records_gold_change", False):
            continue  # 二重に包まない (再配線されても 1 枚)
        wiring._tool_handlers[tool_name] = wrap_with_gold_change(
            handler, gold_reader, tool_name=tool_name,
            roster_reader=roster_reader,
        )


def adapt_executor_handler(
    raw_handler: Callable[..., LlmCommandResultDto],
) -> Callable[[PlayerId, Dict[str, Any], Any], LlmCommandResultDto]:
    """executor signature (int, args[, runtime_context]) →  signature
    (PlayerId, args, ctx)。

    PR-θ2 (経路統合): executor が runtime_context を必要とする tool (explore
    の可視 object 併記など、旧 handler が targets を参照していたもの) に
    対応するため、raw_handler 呼び出し時に位置引数として runtime_context
    を渡すよう拡張した。executor 側では第3引数を optional (default None)
    で受ければ、runtime_context を使わない handler は従来と同じシグネチャ
    で動く。
    """
    def _handler(
        player_id: PlayerId,
        arguments: Dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        return raw_handler(int(player_id.value), arguments, runtime_context)
    return _handler

def adapt_executor_handler_with_resolver(
    raw_handler: Callable[[int, Dict[str, Any]], LlmCommandResultDto],
    tool_name: str,
    argument_resolver: Any,
    *,
    # PR-θ1 (経路統合): travel_to の resolver エラー時に旧 handler と同じ
    # 「有効な destination_label 一覧を含む」 message を組み立てるための
    # optional builder。渡されない場合は従来通り generic message を使う。
    # 他 tool (interact / attack 等) 統合時も同じ pattern を再利用できる。
    invalid_label_failure_builder: Optional[
        Callable[[Any, Dict[str, Any], Exception], LlmCommandResultDto]
    ] = None,
) -> Callable[[PlayerId, Dict[str, Any], Any], LlmCommandResultDto]:
    """resolver を噛ませた adapter (#356 fix)。

    LLM が送ってくる ``item_label`` (I1/I2) を、executor が読む
    ``item_spec_id`` / ``slot_id`` / ``item_instance_id`` に変換する。
    resolver が例外 (label 見つからない 等) を投げたら ``LlmCommandResultDto``
    に変換して返す (= LLM に「このラベルは存在しない」と surface する)。

    PR-θ1: ``invalid_label_failure_builder`` が渡された場合、resolver 例外
    時にそちらを呼び出して tool-specific な失敗 dto を作れる (旧
    ``_handle_travel_to`` が「有効候補列挙 + should_reschedule」を組み立て
    ていた挙動を新経路でも再現するための拡張点)。
    """

    def _handler(
        player_id: PlayerId,
        arguments: Dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        try:
            resolved = argument_resolver.resolve_args(
                tool_name, arguments, runtime_context,
            )
        except ToolArgumentResolutionException as e:
            if invalid_label_failure_builder is not None:
                return invalid_label_failure_builder(
                    runtime_context, arguments, e,
                )
            return LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code=getattr(e, "error_code", "INVALID_TARGET_LABEL"),
                remediation=resolver_failure_remediation(
                    tool_name,
                    getattr(e, "error_code", "INVALID_TARGET_LABEL"),
                ),
            )
        if resolved is None:
            # resolver dispatch table に tool_name が登録されていない =
            # 設計違反。raw 渡しで executor に押し付けるとエラー発生源が
            # 分かりにくくなる (executor 内 KeyError or INVALID_ARGUMENT
            # に化ける)。明示的な error_code で即 surface する。
            logger.error(
                "argument resolver returned None for tool_name=%s; "
                "dispatch table is missing this tool (design violation)",
                tool_name,
            )
            return LlmCommandResultDto(
                success=False,
                message=(
                    f"ツール '{tool_name}' の引数解決が実装されていません "
                    "(設計バグ)。"
                ),
                error_code="RESOLVER_DISPATCH_MISSING",
                remediation=(
                    "別のツールを試してください。同じツールを連打しても "
                    "解決しません (フレームワーク側の修正が必要)。"
                ),
            )
        # resolver は公開 label を内部 ID に置き換える。履歴には LLM が
        # 実際に送った値を残すため、raw arguments の射影を成功経路へ運ぶ。
        resolved[ACTION_HISTORY_PROJECTION_KEY] = (
            project_action_arguments_for_history(arguments)
        )
        return raw_handler(int(player_id.value), resolved, runtime_context)

    return _handler

def maybe_interrupt_busy(
    wiring, player_id: PlayerId, tool_name: str
) -> tuple[bool, Optional[PlayerSpotNavigationState]]:
    """重い tool が来たら travel をキャンセルして agent を現在地に着地させる。

    Review HIGH 1 対応: 中断前の nav_state を snapshot として返す。
    tool が失敗した場合に呼び出し側が `_restore_nav_state` で元に戻せる。

    Returns:
        (was_interrupted, nav_state_snapshot)。
        was_interrupted=False のとき snapshot は None。
    """
    if not tool_name or tool_name in BUSY_FREE_TOOLS:
        return False, None
    repo = getattr(wiring.runtime, "_player_status_repo", None)
    if repo is None:
        return False, None
    status = repo.find_by_id(player_id)
    if status is None or status.spot_navigation_state is None:
        return False, None
    nav = status.spot_navigation_state
    if not nav.is_traveling:
        return False, None
    # 本番runtimeは移動専用commandで中断し、status保存失敗時に
    # 中途半端なat_restを残さない。軽量wiringは後方互換経路を使う。
    movement_service = getattr(wiring.runtime, "_movement_service", None)
    if movement_service is not None:
        nav_snapshot = movement_service.cancel_spot_travel(player_id)
        if nav_snapshot is None:
            return False, None
    else:
        nav_snapshot = nav
        status.set_spot_navigation_state(
            PlayerSpotNavigationState.at_rest(nav.current_spot_id)
        )
        repo.save(status)
    logger.info(
        "Travel interrupted for player_id=%s by tool=%s (was at leg %d of %d)",
        int(player_id.value),
        tool_name,
        nav.leg_index,
        len(nav.leg_connection_ids),
    )
    return True, nav_snapshot

def restore_nav_state(
    wiring,
    player_id: PlayerId,
    nav_snapshot: PlayerSpotNavigationState,
) -> None:
    """Review HIGH 1 対応: tool が失敗したら nav_state を snapshot に戻す。

    「中断 → tool 失敗 → 移動が消える」を避けるためのロールバック。
    """
    movement_service = getattr(wiring.runtime, "_movement_service", None)
    if movement_service is not None:
        movement_service.restore_spot_travel_state(player_id, nav_snapshot)
        return
    repo = getattr(wiring.runtime, "_player_status_repo", None)
    if repo is None:
        return
    status = repo.find_by_id(player_id)
    if status is None:
        return
    status.set_spot_navigation_state(nav_snapshot)
    repo.save(status)
    logger.info(
        "Travel restored for player_id=%s (tool failed, nav_state rolled back)",
        int(player_id.value),
    )

def coerce_arguments(raw_arguments: Any) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if isinstance(raw_arguments, str) and raw_arguments:
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}

def reason_tool_is_not_offered(
    wiring,
    name: str,
    player_id: PlayerId,
    *,
    offered_tool_names_at_prompt: Collection[str],
):
    """いま出していないツールなら、その理由を返す。出していれば None。

    **UNSUPPORTED_TOOL とは区別する。** あちらは「そんなツールは無い」で、
    こちらは「あるが、いまは使えない」。同じ文言にすると、会議が終われば
    使えることが伝わらず、二度と試さなくなる。

    現在の利用可否判定は ``get_tool_definitions`` を通す。フェーズもシナリオの無効化
    宣言も、あちらが唯一の出口なので、ここで条件を書き直さない
    (書き直すと必ずずれる)。

    一方、「選んだ時点で一覧に載っていたか」は Phase A で実際に送った
    ``tools_payload`` だけを根拠にする。現在の条件から引き直すと、位相変更前の
    一覧を再現できず、本人の正しい選択を誤りとして扱ってしまう。

    定義を組めないときは通す。**塞ぐ側に倒すと、組み立てが壊れた世界で
    誰も何もできなくなり、原因が見えなくなる。**
    """
    try:
        offered = {
            d.name
            for d in wiring.runtime.get_tool_definitions(player_id=player_id)
        }
    except Exception:
        logger.warning(
            "get_tool_definitions に失敗したため %s の露出判定を省略する",
            name,
            exc_info=True,
        )
        return None
    if name in offered:
        return None
    if name in offered_tool_names_at_prompt:
        return LlmCommandResultDto(
            success=False,
            message=(
                f"状況が変わったため、選んだ時点では可能だった {name} を"
                "いまは実行できない。"
            ),
            error_code="TOOL_BECAME_UNAVAILABLE",
            should_reschedule=is_reschedulable_error_code(
                "TOOL_BECAME_UNAVAILABLE"
            ),
        )
    return LlmCommandResultDto(
        success=False,
        message=(
            f"いまは {name} を選べない。"
            "「利用可能な tool」に出ているものから選ぶこと。"
        ),
        error_code="TOOL_NOT_OFFERED_NOW",
        should_reschedule=True,
    )

def execute_tool(
    wiring,
    player_id: PlayerId,
    name: str,
    arguments: dict[str, Any],
    runtime_context: Any,
    *,
    offered_tool_names_at_prompt: Collection[str],
) -> LlmCommandResultDto:
    """ツール名から対応するハンドラを選んで実行する。

    PR 7 (#227): 旧コードは 240 行の if/elif ディスパッチだった。本家経路
    ``ToolCommandMapper.execute`` と構造を合わせるため、ツール名→ハンドラ
    メソッドの ``_tool_handlers`` テーブル経由のディスパッチに改めた。
    各ハンドラは ``(player_id, arguments, runtime_context) -> LlmCommandResultDto``。
    未登録のツールは UNSUPPORTED_TOOL を返す。

    経路統一 (R2c) で full wiring (LlmAgentOrchestrator) は退役し、本 escape 経路が
    唯一の turn 実行経路になった。本テーブルが tool ディスパッチの SSOT である。
    """
    # 出し分けは助言でしかなかった。ハンドラ表は tool 名しか見ないので、
    # 会議中に隠したはずの ``interact`` を LLM が書けばそのまま動いていた。
    # 実 run 009 で、アオイが会議の最中に棚卸しを 2 段進めている
    # (t=10 count_supplies / t=11 count_supplies_2 がどちらも成功)。
    # 本人の思考にも「話し合い中だけど、私の担当の棚卸しをまず進めたい」
    # と出ていた。
    #
    # 前提条件で弾く形にすると、全 interaction に「会議中は不可」を書いて
    # 回ることになる (#860 で潰した形)。**出していないなら実行もできない**、
    # を 1 か所で守る。
    handler = wiring._tool_handlers.get(name)

    # ハンドラがあるのに、いま出していないなら実行させない。
    #
    # **順序が要点。** ハンドラごと無いものまでここで弾くと、綴り間違いの
    # 救済 (近い候補の提示) に届かなくなる。「存在しない」と「あるが今は
    # 使えない」は別の失敗で、返す文言も変える必要がある。
    if handler is not None:
        not_offered = reason_tool_is_not_offered(
            wiring, name,
            player_id,
            offered_tool_names_at_prompt=offered_tool_names_at_prompt,
        )
        if not_offered is not None:
            return not_offered

    if handler is None:
        # PR-J: LLM の tool 名 typo を救済する 3 層:
        # 1. fuzzy suggestion で近い候補を message に追記
        # 2. valid tool 一覧を併記 (想像由来 typo の救済)
        # 3. should_reschedule=True で次 tick の起床を確保 (= 配信)
        # 1/2 が無くても 3 (= message を agent に届ける) が無いと意味が
        # ないので、3 が最重要。
        message = build_unsupported_tool_message(
            requested=name,
            valid_tools=wiring._tool_handlers.keys(),
        )
        # PR-J: should_reschedule は _RESCHEDULE_ERROR_CODES SSOT 経由で
        # 決定する。ハードコードすると将来 policy を変えた時に乖離する。
        return LlmCommandResultDto(
            success=False,
            message=message,
            error_code="UNSUPPORTED_TOOL",
            should_reschedule=is_reschedulable_error_code("UNSUPPORTED_TOOL"),
        )
    result = handler(player_id, arguments, runtime_context)
    # 個別 handler が should_reschedule を立て忘れても、error_code の
    # 共通方針を実行結果へ反映する。ActionFailedObservationEmitter はこの
    # field を schedules_turn に写すため、ここが既存の本人向け失敗観測と
    # wiring-reschedule streak をつなぐ共通出口になる。
    if (
        not result.should_reschedule
        and should_reschedule_for_next_tick(result)
    ):
        return dataclass_replace(result, should_reschedule=True)
    return result

# ── per-tool handlers (PR 7) ──

# PR-θ1/θ2 (経路統合): _handle_travel_to / _handle_explore は削除。
# SpotGraphToolExecutor._travel_to / _explore に統合され、それぞれ
# runtime.do_move / runtime.do_explore を呼ぶ薄い wrapper として単一の
# 実装になった。旧 handler の副作用 (scene_boundary / subjective /
# _process_graph_events / display_name / 発見なし時の可視 object 併記 /
# inner_thought 空警告) は全部保持している。
#
# 可視 object 併記は executor が runtime_context.targets を受け取れる
# よう SpotGraphToolExecutor handlers の signature を
# ``(int, args, runtime_context=None)`` に拡張して対応した。
# travel_to は SpotGraphArgumentResolver._resolve_travel_to が
# resolver stage で destination_label → destination_spot_id に解決する
# (resolver_targets に含まれる)。

# PR-θ3 (経路統合): _handle_interact は削除。SpotGraphToolExecutor._interact
# に統合され、runtime.do_interact を呼ぶ薄い wrapper として単一の
# interact 実装になった。旧 handler の副作用 (label→object_id resolve /
# SpotObjectInteractedEvent / _process_graph_events / _record_action_result /
# InteractionNotAllowedException 用の reason-based remediation /
# InteractionNotFoundException 用の 利用可能操作列挙 / inner_thought
# 空警告) は全部保持している。
#
# label→object_id resolve は SpotGraphArgumentResolver._resolve_interact
# が resolver stage で行い、新経路には object_id (int) が届く。
# resolver_targets に TOOL_NAME_SPOT_GRAPH_INTERACT を含めた。resolver
# 例外時の「有効な target_label 一覧」message は
# _build_interact_invalid_label_failure が組み立てる。
# LLM 向け remediation helper (interact_remediation_for_reason /
# list_object_interactions) は application 層 (interact_helpers.py) に
# 移動した。

# PR-θ4 (経路統合): _handle_listen は削除。SpotGraphToolExecutor._listen
# に統合され、runtime.do_listen を呼ぶ薄い wrapper として単一の実装に
# なった。旧 handler の副作用 (event 差分カウント / _process_graph_events /
# inner_thought 空警告) は保持している。

# PR-θ5 (経路統合): _handle_wait は削除。SpotGraphToolExecutor._wait
# に統合され、runtime.do_wait を呼ぶ薄い wrapper として単一の実装に
# なった。旧 handler の副作用 (_record_action_result / subjective 記録 /
# inner_thought 空警告) は保持し、新経路の付加価値 (疲労回復) も引き継ぐ。



# PR-θ6 (経路統合): _handle_set_sub_location は削除。脱出ランタイムでは
# set_sub_location は意図的に未対応 (ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS
# で LLM 露出も除外されている)。SpotGraphToolExecutor._set_sub_location
# は完全実装を持つが、脱出ランタイムでは wire されない (将来の別ランタイム用)。
# 仮に LLM が set_sub_location を呼んだ場合 (エッジケース) は
# `_execute_tool` の default 経路が UNSUPPORTED_TOOL を返す。旧 handler は
# 防御 UNSUPPORTED_TOOL を返すだけの dead code だったので削除する。

def make_auxiliary_tool_handler(
    wiring, tool_name: str
) -> Callable[[PlayerId, dict[str, Any], Any], LlmCommandResultDto]:
    """TODO/memo ツール用のハンドラを tool_name 固定で返す。

    NOTE: pure_spot_graph mode (B-4 / Issue #155) では TODO/memo ツールは
    LLM の tools リストに含まれないため、通常到達しない。安全側のフォール
    バックとして残し、デフォルト構成で memo を使う際の経路を維持する。
    """

    def handler(
        player_id: PlayerId,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        del runtime_context
        return wiring.runtime.run_llm_auxiliary_tool(
            player_id, tool_name, arguments
        )

    return handler
