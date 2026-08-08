"""スポットグラフ系ツールの実行"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.failure_helpers import (
    build_invalid_arg_failure,
    build_sanitized_exception_failure,
    list_object_labels,
)
from ai_rpg_world.application.llm.services.executors.interact_helpers import (
    hidden_object_interaction_failure_reason,
    interact_remediation_for_reason,
    list_object_interactions,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
    InteractionNotFoundException,
)
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    with_inner_thought_empty_warning,
)
from ai_rpg_world.application.llm.services.subjective_args import (
    extract_subjective_action_fields,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    action_history_projection_kwargs,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    TOOL_NAME_SPOT_GRAPH_REPORT_BODY,
    TOOL_NAME_SPOT_GRAPH_VOTE,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.world_graph.prepared_action_registry import PreparedActionRegistry
from ai_rpg_world.application.world_graph.synchronized_action_registry import (
    SynchronizedActionRegistry,
)
from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import SpotGraphWorldServices
from ai_rpg_world.application.speech.services.player_speech_service import (
    PlayerSpeechApplicationService,
)
from ai_rpg_world.application.speech.contracts.commands import SpeakCommand
from ai_rpg_world.application.llm.services.tool_catalog.say_inline import (
    SAY_INLINE_MAX_LENGTH,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
import logging

logger = logging.getLogger(__name__)
from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
    ItemTransferException,
    SpotGraphItemTransferService,
    TargetInventoryFullError,
    TargetIsDeadError,
    TargetIsDownError,
    TargetIsSelfError,
    TargetNotInSameSpotError,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
)
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.value_object.item_effect import (
    CompositeItemEffect,
    ItemEffect,
    SatisfyNeedEffect,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.actionable_target import (
    TargetRequirement,
    validate_actionable_target,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotPlayerPreparedActionEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.domain.world_graph.value_object.synchronized_action_group import (
    SynchronizedActionGroup,
)


# Phase F: 腐敗食を食べた時のダメージ量 (HP)。
# 当面ハードコードで、per-item config 化は将来の PR で行う。
# 10 は base_stats.max_hp=100 (現状の survival demo) に対して 10% 程度で、
# 1 度の事故では致命的にならないが、繰り返せば確実に死ぬバランス。
SPOILED_FOOD_DAMAGE_HP = 10
SPOILED_FOOD_HUNGER_RETENTION_RATIO = 0.5


def _extract_hunger_satisfaction_amount(effect: ItemEffect | None) -> int:
    """consume_effect から HUNGER の satisfy_need 量だけを取り出す。

    腐敗食では HP 回復などは適用しないが、食べ物として腹に入った分だけ
    空腹回復を部分適用する。そのため HUNGER 以外の効果はここで無視する。
    """
    if effect is None:
        return 0
    if isinstance(effect, SatisfyNeedEffect):
        if effect.need_type_name != NeedType.HUNGER.value:
            return 0
        return effect.amount
    if isinstance(effect, CompositeItemEffect):
        return sum(_extract_hunger_satisfaction_amount(sub) for sub in effect.effects)
    return 0


def _use_item_unexpected_exception_result(
    exc: Exception,
    *,
    stage: str,
) -> LlmCommandResultDto:
    """_use_item の想定外例外を LLM には伏せ、trace に原因特定情報だけ残す。"""
    base = exception_result(exc)
    trace_payload = dict(base.trace_payload or {})
    trace_payload.update(
        {
            "tool_exception_location": "_use_item",
            "tool_exception_stage": stage,
            "tool_exception_type": type(exc).__name__,
            "tool_exception_module": type(exc).__module__,
        }
    )
    return LlmCommandResultDto(
        success=base.success,
        message=base.message,
        error_code=base.error_code,
        remediation=base.remediation,
        should_reschedule=base.should_reschedule,
        was_no_op=base.was_no_op,
        omit_result_in_prompt=base.omit_result_in_prompt,
        trace_payload=trace_payload,
    )


#: tend_to_player の拒否理由 → 既存の error_code。
#:
#: 普遍則へ括り出しても、外に見える code は変えない。remediation の対応表と
#: trace の分析がこの値で分岐している。
_TEND_ERROR_CODES = {
    "TARGET_IS_SELF": "INVALID_TARGET_KIND",
    "ACTOR_IS_DOWN": "EXHAUSTED",
}

#: tend_to_player 専用の失敗文。**判定は普遍則、文言はここ。**
#:
#: 負債マップが「共通ヘルパへ載せ替えると専用の失敗文面が汎用に落ちる」と
#: 警告していた点。汎用の「ここには居ない」だと次に何をすればよいかが
#: 消える。載せ替えで実際に落ちかけ、既存テストが捕まえた。
_TEND_MESSAGES = {
    "NOT_IN_SAME_SPOT": (
        "{name} は同じ場所にいない。"
        "介抱するにはまず相手のいる場所へ向かう必要がある。"
    ),
    "TARGET_IS_NOT_DOWN": "{name} は倒れていない。介抱の必要はない。",
    "ACTOR_IS_DOWN": "自分も倒れているので他人を介抱できない。",
    "TARGET_IS_ELIMINATED": "{name} はもう息をしていない。介抱しても戻らない。",
}


class SpotGraphToolExecutor:
    """spot_graph_* ツールのハンドラを提供する。"""

    def __init__(
        self,
        spot_graph_world_services: SpotGraphWorldServices,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        event_publisher: Any = None,
        *,
        sync_action_groups: tuple[SynchronizedActionGroup, ...] = (),
        time_provider: GameTimeProvider | None = None,
        spot_graph_repository: ISpotGraphRepository | None = None,
        sync_action_registry: SynchronizedActionRegistry | None = None,
        monster_repository: Optional[MonsterRepository] = None,
        player_status_repository: Optional[PlayerStatusRepository] = None,
        attack_orchestrator: Optional[SpotAttackOrchestrator] = None,
        item_transfer_service: Optional["SpotGraphItemTransferService"] = None,
        speech_service: Optional["PlayerSpeechApplicationService"] = None,
        # PR-θ1 (経路統合): tool 実装が 2 経路に分裂していた問題の解消。
        # SpotGraphToolExecutor._travel_to を `runtime.do_move` を呼ぶ薄い
        # wrapper 化することで、既に正しく副作用 (start_travel_to_spot +
        # _process_graph_events + 同一 spot 短絡 + _record_action_result
        # の scene_boundary + subjective 記録) が実装されている do_move
        # を単一の真実源として再利用する。
        #
        # 別レイヤーへの依存ではなく application 層内 (WorldRuntime も
        # application 層) の再利用。runtime 未注入時は NOT_WIRED を返す。
        runtime: Optional[Any] = None,
    ) -> None:
        if spot_graph_world_services.movement is None:
            raise TypeError("SpotGraphWorldServices.movement が必要です")
        self._svc = spot_graph_world_services
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._event_publisher = event_publisher
        # 協力ギミック #13 用: 既知の sync group と現在 tick provider。
        # 渡されない場合は sync 関連の追加処理（observation 発火、tick 記録）
        # は行わず、従来の prepare 挙動だけになる。
        self._sync_action_groups = sync_action_groups
        self._time_provider = time_provider
        self._spot_graph_repository = spot_graph_repository
        # resolver stage と同一 instance を共有することで、将来 registry に
        # 状態（キャッシュ等）が増えても乖離しない。渡されない場合は
        # 既定で world_flags を使う独立 instance を生成（後方互換）。
        self._sync_action_registry = (
            sync_action_registry
            or SynchronizedActionRegistry(spot_graph_world_services.world_flags)
        )
        # 戦闘ツール (`spot_graph_attack`) で使用。注入されていない構成では
        # `_attack` が「未対応」エラーを返す（後方互換 + minimal wiring 構成
        # のため）。
        self._monster_repository = monster_repository
        self._player_status_repository = player_status_repository
        # attack_orchestrator が注入されていれば優先利用。注入されない場合は
        # 内部でリポジトリから組み立てる（後方互換: 旧 wiring が orchestrator
        # を渡さず monster/player リポジトリだけ渡してきても動く）。
        self._attack_orchestrator = attack_orchestrator
        # 注入されない構成では drop/pickup ハンドラは「未対応」エラーを返す
        # (後方互換 + minimal wiring 用)。
        self._item_transfer_service = item_transfer_service
        # 実験 #29 後続: travel_to / give_item / drop_item / pickup_item の
        # ``say_inline`` パラメータ用に speech_service を保持。未注入なら
        # say_inline が指定されても silent (= 短発話だけ無視) で本処理は走る。
        self._speech_service = speech_service
        # PR-θ1: travel_to 統合用の WorldRuntime 参照。
        self._runtime = runtime

    # PR β (実験 #29 後続): 疲労 ≥100 (exhausted) で実行を block する重い tool 群。
    # tool list を動的に変えると prefix cache を破壊するため、executor 冒頭で
    # exhausted を検知して EXHAUSTED error を返す形にする (docs/design_decisions.md #1 / #2 参照)。
    # 「動けないが、座ったまま回復行動はできる」モデル: use_item / wait /
    # speech / memo / give_item / drop_item / pickup_item / explore /
    # set_sub_location / listen / prepare_action は通す。
    HEAVY_TOOLS_BLOCKED_AT_EXHAUSTED = frozenset({
        TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
        TOOL_NAME_SPOT_GRAPH_ATTACK,
        TOOL_NAME_SPOT_GRAPH_INTERACT,
    })

    # PR β: 各 heavy action 後に蓄積する疲労量。scenario JSON の
    # interaction.fatigue_cost が将来導入されたらここを上書きする。
    FATIGUE_COST_TRAVEL_LEG = 1
    FATIGUE_COST_ATTACK = 5
    FATIGUE_COST_INTERACT_DEFAULT = 2

    # wait 1 tick あたりの回復量。
    # needs_decay の自然増加 (+1/tick) と相殺すると純減 -9/tick。
    # 疲労 100 → 0 まで ~12 tick (= ~6 hour of game time / 30 min per tick)。
    #
    # 値の変遷:
    # - 旧 2 (= 純減 -1): 100→0 に 100 tick、フィードバック弱で動けない時間が支配的 (Y_after_pr607)
    # - 中間 4 (= 純減 -3): 改善するも Y_after_issue621 で fatigue 100 ロックが多発、
    #   23 wait 前後の平均 Δ が +0.9 (= 効いていない) と観測された
    # - 中間 10 (= 純減 -9): 4 連 wait で 100 → 64 まで戻る。
    #   Y_after_pr634 で「行動が増えた一方 wait 3 連発が頻発」(loop_guard 6 件中 4 件)。
    # - 現行 20 (= 重い行動 attack +5 の 4 回分を一度に回収):
    #   passive decay も同時に 0 にしたので、1 wait で「重い 1 ターン分の蓄積」を
    #   完全に消せる強度。連続待機の必要が消える。
    FATIGUE_RECOVERY_WAIT = 20

    def _find_owned_slot_by_item_spec_id_and_spoilage(
        self,
        player_id: int,
        item_spec_id_raw: Any,
        is_spoiled_raw: Any,
    ):
        """所持中の同種・同腐敗状態アイテムから、その時点で空でない slot を 1 件引く。

        inventory 表示は同種アイテムを 1 行に集約するため、prompt 構築時の
        代表 slot を持ち回ると、batch give の 2 件目以降が空 slot を指して
        しまう。一方、表示側は ``(item_spec_id, is_spoiled)`` で新鮮品と
        腐敗品を分けるので、実行時解決も同じキーに揃える。
        """
        try:
            spec_id = ItemSpecId.create(int(item_spec_id_raw))
        except (TypeError, ValueError):
            return None
        inv = self._player_inventory_repository.find_by_id(PlayerId(player_id))
        if inv is None:
            return None
        return inv.find_slot_by_item_spec_id_and_spoilage(
            spec_id, bool(is_spoiled_raw), self._item_repository,
        )

    def _get_status(self, player_id: int):
        """疲労チェック / 蓄積 / 回復用に PlayerStatusAggregate を取得する。

        repo 未注入 (= minimal wiring) の構成では None を返す。呼び出し側は
        None なら疲労操作を skip する fail-safe。
        """
        if self._player_status_repository is None:
            return None
        try:
            from ai_rpg_world.domain.player.value_object.player_id import PlayerId as _PID
            return self._player_status_repository.find_by_id(_PID(player_id))
        except Exception:
            return None

    def _is_exhausted_and_block(
        self, player_id: int, tool_name: str
    ) -> Optional[LlmCommandResultDto]:
        """exhausted (疲労 100) で重い tool を呼んだ場合の block 判定 (PR β)。

        block 該当なら EXHAUSTED error を返す。それ以外は None。
        """
        if tool_name not in self.HEAVY_TOOLS_BLOCKED_AT_EXHAUSTED:
            return None
        status = self._get_status(player_id)
        if status is None or not status.is_exhausted():
            return None
        return LlmCommandResultDto(
            success=False,
            message=(
                "疲労が限界に達してその場に崩れ落ちている。激しい行動 "
                "(travel_to / attack / interact) は今できない。"
                "wait や食事 (use_item) で回復してから動き直すこと。"
            ),
            error_code="EXHAUSTED",
            remediation=(
                "wait で休む / 食料や寝具系アイテムを use_item する / 仲間に"
                "助けを求める speech で短期的に凌ぐ。回復したら再度試す。"
            ),
        )

    def _apply_fatigue_safe(self, player_id: int, amount: int) -> None:
        """疲労蓄積を best-effort で適用する (PR β)。失敗時は silent。

        action 成功時の post-処理として呼ぶ。repo 未注入や save 失敗で親
        action を倒さないために silent (debug log 程度に留める)。
        """
        if amount <= 0:
            return
        status = self._get_status(player_id)
        if status is None:
            return
        try:
            status.apply_fatigue(amount)
            self._player_status_repository.save(status)
        except Exception:
            pass

    def _recover_fatigue_safe(self, player_id: int, amount: int) -> None:
        """疲労回復を best-effort で適用する (PR β)。"""
        if amount <= 0:
            return
        status = self._get_status(player_id)
        if status is None:
            return
        try:
            status.recover_fatigue(amount)
            self._player_status_repository.save(status)
        except Exception:
            pass

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        return {
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO: self._travel_to,
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION: self._set_sub_location,
            TOOL_NAME_SPOT_GRAPH_EXPLORE: self._explore,
            TOOL_NAME_SPOT_GRAPH_INTERACT: self._interact,
            TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION: self._prepare_action,
            TOOL_NAME_SPOT_GRAPH_USE_ITEM: self._use_item,
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM: self._drop_item,
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM: self._pickup_item,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM: self._give_item,
            TOOL_NAME_SPOT_GRAPH_ATTACK: self._attack,
            TOOL_NAME_SPOT_GRAPH_LISTEN: self._listen,
            TOOL_NAME_SPOT_GRAPH_WAIT: self._wait,
            TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER: self._tend_to_player,
            TOOL_NAME_SPOT_GRAPH_VOTE: self._vote,
            TOOL_NAME_SPOT_GRAPH_REPORT_BODY: self._report_body,
        }

    def _travel_to(self, player_id: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        """``travel_to`` の実行 (PR-θ1: 経路統合後)。

        旧 runtime_manager._handle_travel_to と新 SpotGraphToolExecutor._travel_to
        の 2 経路に分裂していた実装を統合した。**この経路が唯一の travel_to
        実装** で、runtime_manager 側の旧 handler は削除された。

        統合方針 (Option B): 既に正しい副作用を全部持っている ``runtime.do_move``
        (start_travel_to_spot + _process_graph_events + 同一 spot 短絡 +
        _record_action_result の scene_boundary + subjective 記録) を単一の
        真実源として再利用し、新経路が付加した価値 (say_inline / 疲労) だけを
        上乗せする。

        処理順:
        1. 疲労 100 block (新経路の価値)
        2. destination_spot_id validation (resolver 後の canonical int)
        3. runtime.do_move — 移動開始 + graph events + record_action_result
        4. say_inline emit (新経路の価値、旧経路には無かった)
        5. 疲労 +1 蓄積 (新経路の価値)
        6. display_name で成功 message 組立 (旧経路と揃える)
        7. inner_thought 空警告 (旧経路と揃える)
        """
        # PR β: 疲労 limit (100) で重い tool は block。
        blocked = self._is_exhausted_and_block(player_id, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO)
        if blocked is not None:
            return blocked
        raw = args.get("destination_spot_id")
        try:
            dest = int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            return LlmCommandResultDto(
                success=False,
                message="destination_spot_id が不正です（Resolver による解決に失敗した可能性があります）。",
                error_code="INVALID_ARGUMENT",
                remediation=get_remediation("INVALID_ARGUMENT"),
            )
        if dest <= 0:
            return build_invalid_arg_failure(
                arg_name="destination_spot_id",
                detail="正の整数を指定してください",
            )
        # runtime 未注入時 (テスト構成 / minimal wiring) は NOT_WIRED を返す。
        # 実験 / production 経路は必ず runtime を注入するので実害は無い。
        if self._runtime is None:
            return LlmCommandResultDto(
                success=False,
                message="travel_to は本構成で未配線です。",
                error_code="NOT_WIRED",
                remediation=get_remediation("NOT_WIRED"),
            )
        try:
            destination_str_id = self._runtime.id_mapper.get_str("spot", dest)
            subjective = extract_subjective_action_fields(args)
            # do_move が: start_travel_to_spot + _process_graph_events +
            # 同一 spot 短絡 + _record_action_result (scene_boundary=True) を
            # 面倒見る。失敗は例外で返り exception_result で LLM 向け error に。
            self._runtime.do_move(
                PlayerId(player_id),
                destination_str_id,
                **action_history_projection_kwargs(args),
                **subjective,
            )
            # 新経路の付加価値: 行動しながらの一言 (say_inline)。失敗しても
            # travel 結果は変えない (silent fail-safe)。
            self._maybe_emit_say_inline(player_id, args)
            # PR β: travel は 1 leg = 1 fatigue。
            self._apply_fatigue_safe(player_id, self.FATIGUE_COST_TRAVEL_LEG)
            # 出力 message は旧 handler と揃えて display_name を使う (LLM /
            # 観戦者が数字 spot_id より名前で認識できるよう)。runtime.
            # _spot_graph_repo は既に SpotGraphToolExecutor が
            # ``self._spot_graph_repository`` として持っている同一 instance
            # なので、他オブジェクトの private 属性を触らず自分の依存で
            # 参照する (レビュー指摘 HIGH #1)。
            display_name: str
            try:
                if self._spot_graph_repository is not None:
                    graph = self._spot_graph_repository.find_graph()
                    display_name = graph.get_spot(SpotId.create(dest)).name
                else:
                    display_name = f"スポット {dest}"
            except Exception:
                display_name = f"スポット {dest}"
            base = f"{display_name}へ移動しました。"
            return with_inner_thought_empty_warning(
                TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
                args,
                LlmCommandResultDto(
                    success=True,
                    message=base,
                ),
            )
        except Exception as e:
            return exception_result(e)

    def _maybe_emit_say_inline(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> None:
        """``say_inline`` (任意短発話) を SAY channel で発火する。

        実験 #29 後続: 行動ツールに「行動しながらの一言」を
        付けられるようにするためのヘルパ。

        条件:
        - args["say_inline"] が非空 str
        - speech_service が注入されている

        失敗 (例外 / speech_service 未注入 / 空文字) は全部 silent で、
        親アクションの結果には影響させない。
        """
        if self._speech_service is None:
            return
        raw = args.get("say_inline")
        if not isinstance(raw, str):
            return
        content = raw.strip()
        if not content:
            return
        # 文字数上限は tool schema 側で maxLength として宣言済みだが、
        # 防御的にここでも切り詰める (LLM が JSON を雑に返した場合の保険)。
        # レビュー反映 (#422 MEDIUM-1): 定数は module-level import に揃えた。
        # `len()` は Unicode コードポイント基準。サロゲートペア絵文字は
        # 表示上の文字数とズレる可能性があるが、survival シナリオでは実害なし。
        if len(content) > SAY_INLINE_MAX_LENGTH:
            logger.debug(
                "say_inline truncated: player_id=%s len=%d → %d",
                player_id, len(content), SAY_INLINE_MAX_LENGTH,
            )
            content = content[:SAY_INLINE_MAX_LENGTH]
        try:
            self._speech_service.speak(
                SpeakCommand(
                    speaker_player_id=player_id,
                    content=content,
                    channel=SpeechChannel.SAY,
                    target_player_id=None,
                )
            )
        except Exception as e:
            # 親 action は成功扱いを維持する。inline speech 失敗で travel /
            # give が巻き戻ると LLM 体験が壊れる。
            # レビュー反映 (#422 MEDIUM-3): silent ではなく debug ログを残し、
            # デバッグ時に「なぜ say_inline が届かなかったか」を追えるようにする。
            logger.debug(
                "say_inline speak failed: player_id=%s err=%s",
                player_id, str(e),
                exc_info=True,
            )

    def _set_sub_location(self, player_id: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        raw = args.get("sub_location_id")
        sub: SubLocationId | None
        try:
            if raw is None or raw == 0:
                sub = None
            else:
                sub = SubLocationId.create(int(raw))
        except (TypeError, ValueError):
            return build_invalid_arg_failure(
                arg_name="sub_location_id",
                detail="正の整数または 0/None を指定してください",
            )
        try:
            self._svc.movement.move_to_sub_location(PlayerId(player_id), sub)
            return LlmCommandResultDto(
                success=True,
                message="サブロケーションを更新しました。",
            )
        except Exception as e:
            return exception_result(e)

    def _explore(self, player_id: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        """``explore`` の実行 (PR-θ2: 経路統合後)。

        旧 runtime_manager._handle_explore と新 SpotGraphToolExecutor._explore
        の 2 経路を統合。**この経路が唯一の explore 実装** で、旧 handler は
        削除された。

        統合方針 (PR-θ1 と同じ Option B): 既に正しい副作用 (SpotExploredEvent
        発火 + _process_graph_events + _record_action_result + subjective 記録)
        を持つ ``runtime.do_explore`` を単一の真実源として再利用する。

        処理順:
        1. runtime.do_explore — 探索実行 + graph event + action_result 記録
        2. discovery_descriptions を組み立て
        3. 発見なしの場合、可視 object 一覧を併記 (F2: LLM が「部屋に何もない」
           と誤解して interact しなくなる癖の対策)
        4. say_inline emit
        5. inner_thought 空警告 (旧 handler と揃える)
        """
        if self._runtime is None:
            return LlmCommandResultDto(
                success=False,
                message="explore は本構成で未配線です。",
                error_code="NOT_WIRED",
                remediation=get_remediation("NOT_WIRED"),
            )
        try:
            subjective = extract_subjective_action_fields(args)
            result = self._runtime.do_explore(
                PlayerId(player_id),
                **action_history_projection_kwargs(args),
                **subjective,
            )
            if result.discovery_descriptions:
                message = "発見: " + " / ".join(result.discovery_descriptions)
            else:
                # F2: 「新しい発見はなかった」だけだと LLM が「部屋に何もない」と
                # 誤解し interact しなくなる癖がある。runtime_context.targets
                # から可視 object を併記する。
                exhausted_hint = ""
                if not getattr(result, "has_remaining_discoverable_items", False):
                    exhausted_hint = "この場所で新たに探索で見つかるものはもう無い。"
                targets = (
                    getattr(runtime_context, "targets", {}) or {}
                    if runtime_context is not None
                    else {}
                )
                visible_objects = list_object_labels(targets) if targets else ""
                if visible_objects:
                    message = (
                        "新しい発見はなかった。"
                        f"{exhausted_hint}"
                        f"既に見えているオブジェクト: {visible_objects}"
                        " (interact するにはこのオブジェクトの名前を target_label に指定する)"
                    )
                else:
                    message = (
                        "新しい発見はなかった。"
                        f"{exhausted_hint}"
                        "(この場所に interactable なオブジェクトは無い)"
                    )
            self._maybe_emit_say_inline(player_id, args)
            return with_inner_thought_empty_warning(
                TOOL_NAME_SPOT_GRAPH_EXPLORE,
                args,
                LlmCommandResultDto(success=True, message=message),
            )
        except Exception as e:
            return exception_result(e)

    def _interact(self, player_id: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        """``interact`` の実行 (PR-θ3: 経路統合後)。

        旧 runtime_manager._handle_interact と新 SpotGraphToolExecutor._interact
        の 2 経路を統合。**この経路が唯一の interact 実装** で、旧 handler は
        削除された。

        統合方針 (PR-θ1/θ2 と同じ Option B): 既に正しい副作用を持つ
        ``runtime.do_interact`` を単一の真実源として再利用する:
        - `_interaction_service.execute_interaction` の呼び出し
        - `SpotObjectInteractedEvent` の発火
        - `_process_graph_events`
        - `_record_action_result` (subjective 記録)

        処理順:
        1. 疲労 100 block (新経路の価値)
        2. object_id / action_name validation (resolver 済み前提)
        3. runtime.do_interact
        4. `InteractionNotAllowedException` (前提条件失敗) → LLM 向け
           "行動が拒否された: {reason}" + reason 依存の remediation
        5. `InteractionNotFoundException` (action_name typo) → 利用可能操作
           一覧 + LLM 向け remediation
        6. 疲労 +2 蓄積 (新経路の価値)
        7. inner_thought 空警告 (旧 handler と揃える)
        """
        # PR β: 疲労 limit (100) で interact は block。
        blocked = self._is_exhausted_and_block(player_id, TOOL_NAME_SPOT_GRAPH_INTERACT)
        if blocked is not None:
            return blocked
        # resolver は object_id と target_player_id のどちらか一方だけを埋める
        # (排他)。人が対象なら対人経路へ回す。
        if args.get("target_player_id") is not None:
            return self._interact_with_player(player_id, args)
        try:
            oid = int(args.get("object_id", 0))
            action = str(args.get("action_name", "")).strip()
        except (TypeError, ValueError):
            return build_invalid_arg_failure(
                arg_name="object_id / action_name",
                detail="object_id は正の整数、action_name は非空の文字列",
            )
        if oid <= 0 or not action:
            return build_invalid_arg_failure(
                arg_name="object_id / action_name",
                detail="object_id (正の整数) と action_name (非空文字列) を必ず指定してください",
            )
        if self._runtime is None:
            return LlmCommandResultDto(
                success=False,
                message="interact は本構成で未配線です。",
                error_code="NOT_WIRED",
                remediation=get_remediation("NOT_WIRED"),
            )
        try:
            object_str_id = self._runtime.id_mapper.get_str("object", oid)
            subjective = extract_subjective_action_fields(args)
            # 配線切れ修正 (PR-I): interact ツールの自由入力 `parameters`
            # (パズルの暗証番号 / 看板の本文など) が、ここで取り出されず
            # do_interact に渡っていなかった。dict でない値 (None / 型違反)
            # は None として扱い、不正型で落とさない (入口での型ガード)。
            raw_parameters = args.get("parameters")
            interaction_parameters = (
                raw_parameters if isinstance(raw_parameters, dict) else None
            )
            # do_interact が execute_interaction + SpotObjectInteractedEvent +
            # _process_graph_events + _record_action_result を面倒見る。
            result = self._runtime.do_interact(
                PlayerId(player_id),
                object_str_id,
                action,
                interaction_parameters=interaction_parameters,
                **action_history_projection_kwargs(args),
                **subjective,
            )
            # PR-ι: interact しながらの一言 (say_inline)。失敗しても親 action
            # は success 維持 (silent fail-safe)。
            self._maybe_emit_say_inline(player_id, args)
            # PR β: interact は heavy 行動 (default fatigue_cost = 2)。
            self._apply_fatigue_safe(player_id, self.FATIGUE_COST_INTERACT_DEFAULT)
            msg = "; ".join(result.messages) if result.messages else "完了"
            return with_inner_thought_empty_warning(
                TOOL_NAME_SPOT_GRAPH_INTERACT,
                args,
                LlmCommandResultDto(
                    success=True,
                    message=msg,
                ),
            )
        except InteractionNotAllowedException as exc:
            # N2: precondition 失敗 (= scenario JSON の failure_message) を
            # generic "LLM ツール実行に失敗しました" に潰さず、failure_message
            # そのものを surface する。「枯渇」っぽい文言なら retry を抑える
            # remediation を添える (= 同じ object に再度同 action_name を
            # 投げない指示)。
            reason = str(exc) or "前提条件を満たさない"
            return LlmCommandResultDto(
                success=False,
                message=f"行動が拒否された: {reason}",
                error_code="INTERACTION_PRECONDITION_FAILED",
                remediation=interact_remediation_for_reason(reason),
            )
        except InteractionNotFoundException:
            # 実験 #26 で発覚: LLM が表示に無い action_name を
            # 発明して呼んでいた。当該 object で実際に使える一覧を
            # 提示し、現在状況に表示された値だけを選ばせる。
            available = list_object_interactions(
                self._runtime, oid, player_id=player_id
            )
            if not available:
                hidden_reason = hidden_object_interaction_failure_reason(
                    self._runtime, oid, player_id=player_id
                )
                if hidden_reason:
                    return LlmCommandResultDto(
                        success=False,
                        message=f"行動が拒否された: {hidden_reason}",
                        error_code="INTERACTION_PRECONDITION_FAILED",
                        remediation=interact_remediation_for_reason(hidden_reason),
                    )
            avail_str = ", ".join(available) if available else "(なし)"
            return LlmCommandResultDto(
                success=False,
                message=(
                    f"このオブジェクトには '{action}' という操作がありません。"
                    f"利用可能な操作: {avail_str}"
                ),
                error_code="INTERACTION_ACTION_NOT_FOUND",
                remediation=(
                    "action_name には、現在の状況に表示された対象行の"
                    "「使える操作」で ``\"\"`` に囲まれた値を"
                    "そのまま指定してください。表示に無い名前は推測しないでください。"
                ),
            )
        except Exception as e:
            return exception_result(e)

    def _interact_with_player(
        self, player_id: int, args: Dict[str, Any]
    ) -> LlmCommandResultDto:
        """``interact`` の対象がプレイヤーだったときの実行。

        物体経路 (``_interact``) と対になる。失敗コードは物体側と同じものを
        使う — LLM から見れば同じ tool の同じ失敗であり、コードを分けると
        remediation を 2 系統で保守することになる。
        """
        action = str(args.get("action_name", "")).strip()
        if not action:
            return build_invalid_arg_failure(
                arg_name="action_name",
                detail="非空の文字列を指定してください",
            )
        if self._runtime is None or not hasattr(
            self._runtime, "do_interact_with_player"
        ):
            # 対人経路を持たない runtime (テスト double / 旧構成) 向けの
            # 安全網。``create_world_runtime`` は常に service を組み立てるので
            # 本番では通らない。シナリオが player_interactions を宣言して
            # いない場合は available_action_names() が空になり、
            # INTERACTION_ACTION_NOT_FOUND 側で「人に対して使える操作:
            # (なし)」と返る (こちらではない)。
            return LlmCommandResultDto(
                success=False,
                message=(
                    "この世界では人を対象にした操作が定義されていません。"
                    "オブジェクトを対象にしてください。"
                ),
                error_code="NOT_WIRED",
                remediation=get_remediation("NOT_WIRED"),
            )
        try:
            target_player_id = int(args.get("target_player_id"))
        except (TypeError, ValueError):
            return build_invalid_arg_failure(
                arg_name="target_player_id",
                detail="対象プレイヤーの解決に失敗しました",
            )
        raw_parameters = args.get("parameters")
        interaction_parameters = (
            raw_parameters if isinstance(raw_parameters, dict) else None
        )
        try:
            result = self._runtime.do_interact_with_player(
                PlayerId(player_id),
                PlayerId(target_player_id),
                action,
                interaction_parameters=interaction_parameters,
                **action_history_projection_kwargs(args),
                **extract_subjective_action_fields(args),
            )
            self._maybe_emit_say_inline(player_id, args)
            self._apply_fatigue_safe(player_id, self.FATIGUE_COST_INTERACT_DEFAULT)
            msg = "; ".join(result.messages) if result.messages else "完了"
            return with_inner_thought_empty_warning(
                TOOL_NAME_SPOT_GRAPH_INTERACT,
                args,
                LlmCommandResultDto(
                    success=True,
                    message=msg,
                ),
            )
        except InteractionNotAllowedException as exc:
            reason = str(exc) or "前提条件を満たさない"
            return LlmCommandResultDto(
                success=False,
                message=f"行動が拒否された: {reason}",
                error_code="INTERACTION_PRECONDITION_FAILED",
                remediation=interact_remediation_for_reason(reason),
            )
        except InteractionNotFoundException:
            available = ", ".join(
                self._runtime.available_player_action_names(PlayerId(player_id))
            ) or "(なし)"
            return LlmCommandResultDto(
                success=False,
                message=(
                    f"人を対象にした '{action}' という操作はありません。"
                    f"人に対して使える操作: {available}"
                ),
                error_code="INTERACTION_ACTION_NOT_FOUND",
                remediation=(
                    "action_name には、同席しているプレイヤーの行末に表示された"
                    "操作名をそのまま指定してください。物体用の操作名は人には"
                    "使えません。"
                ),
            )
        except Exception as e:
            return exception_result(e)

    def _use_item(self, player_id: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        item_spec_id = args.get("item_spec_id")
        if item_spec_id is None:
            return build_invalid_arg_failure(
                arg_name="item_spec_id",
                detail="使用するアイテムの spec_id (正の整数) を指定してください",
            )
        try:
            item_spec_id_int = int(item_spec_id)
        except (TypeError, ValueError):
            return build_invalid_arg_failure(
                arg_name="item_spec_id",
                detail="正の整数を指定してください",
            )
        try:
            inv = self._player_inventory_repository.find_by_id(PlayerId(player_id))
        except Exception as e:
            return _use_item_unexpected_exception_result(e, stage="inventory_lookup")
        if inv is None:
            return LlmCommandResultDto(
                success=False,
                message="プレイヤー情報が見つかりません。",
                error_code="PLAYER_NOT_FOUND",
                remediation=get_remediation("PLAYER_NOT_FOUND"),
            )
        # インベントリからアイテムインスタンスを探す。
        # 実験 #26 で発覚: 旧コードは `inv.slots` (存在しない属性) を iter して
        # 全 use_item が AttributeError → SYSTEM_ERROR (72 件) で死んでいた。
        # さらに同 spec の新鮮品 / 腐敗品は prompt 上で別ラベルになるため、
        # resolver が渡す is_spoiled も含めて実行時に slot を引く。
        try:
            found = self._find_owned_slot_by_item_spec_id_and_spoilage(
                player_id, item_spec_id_int, args.get("is_spoiled", False),
            )
        except Exception as e:
            return _use_item_unexpected_exception_result(e, stage="slot_resolution")
        if found is None:
            return LlmCommandResultDto(
                success=False,
                message="指定したアイテムは持っていません。",
                error_code="ITEM_NOT_FOUND",
                remediation=get_remediation("ITEM_NOT_FOUND"),
            )
        try:
            matched_slot_id, iid = found
        except (TypeError, ValueError) as e:
            return _use_item_unexpected_exception_result(
                e, stage="slot_resolution_result"
            )
        try:
            item_instance = self._item_repository.find_by_id(iid)
        except Exception as e:
            return _use_item_unexpected_exception_result(e, stage="item_lookup")
        if item_instance is None:
            return LlmCommandResultDto(
                success=False,
                message="指定したアイテムは持っていません。",
                error_code="ITEM_NOT_FOUND",
                remediation=get_remediation("ITEM_NOT_FOUND"),
            )
        from ai_rpg_world.domain.item.enum.item_enum import ItemType
        if item_instance.item_spec.item_type != ItemType.CONSUMABLE:
            return LlmCommandResultDto(
                success=False,
                message="このアイテムは消費できません (CONSUMABLE 種別ではない)。",
                error_code="ITEM_NOT_CONSUMABLE",
                remediation=get_remediation("ITEM_NOT_CONSUMABLE"),
            )
        try:
            # Phase F: 腐敗食を食べたか判定する。use() で quantity が減って
            # state がリセットされる前に読む必要があるのでここで取る。
            # 集約は (spec, spoiled) ベースで slot に分かれて入っているはずなので、
            # 同 slot の instance が「腐敗 / 新鮮」のどちらかに確定している前提。
            is_spoiled = bool(item_instance.state.get("spoiled"))
            item_instance.use()
            # ItemAggregate.use() が aggregate に積んだ event を drain して流す。
            #
            # **drain が要る理由は「観測が落ちるから」ではない。** かつてこの
            # コメントは「publish しないと durability ベースの observation /
            # metrics が silent に落ちる」と書いていたが、その observation も
            # metrics も存在しない。ItemUsedEvent / ItemBrokenEvent には
            # ObservedEventRegistry の登録も handler も無く、publish された値は
            # どこにも届かない (アイテムを使った事実は、新鮮パスで別途 publish
            # される ConsumableUsedEvent が扱う)。
            #
            # それでも drain するのは、集約が event を抱えたまま save されるのを
            # 避けるため。次に同じ instance を find して get_events() すると、
            # 陳腐化した event が別の文脈で流れる (Phase G #3 と同じ罠)。
            # 「積んだら必ず drain して clear する」を例外なく守るほうが、
            # 消費者の有無で扱いを変えるより壊れにくい。
            #
            # ItemBrokenEvent は現状**到達不能**でもある。use() を呼ぶ経路は
            # CONSUMABLE 限定で、かつ scenario_loader は durability を一切
            # パースしないため、どのアイテムも durability=None になる。
            # 装備の破損を実装するときは、ここではなく loader と
            # ObservedEventRegistry の両方に手を入れることになる。
            instance_events = list(item_instance.get_events())
            item_instance.clear_events()
            if instance_events and self._event_publisher is not None:
                self._event_publisher.publish_all(instance_events)
            if item_instance.quantity == 0:
                # 順序が重要: inventory から slot を空ける処理を先に save し、
                # その後に item_repository から物理削除する。これを逆順に
                # すると delete 成功・inventory save 失敗のときに、誰も持って
                # いない slot に存在しない item_instance_id が残り続け、
                # 以降の lookup が全部 None になる silent failure を生む。
                if matched_slot_id is not None:
                    inv.remove_item_for_placement(matched_slot_id)
                self._player_inventory_repository.save(inv)
                self._item_repository.delete(item_instance.item_instance_id)
            else:
                self._item_repository.save(item_instance)
            name = item_instance.item_spec.name
            if is_spoiled:
                # Phase F: 腐敗食 → ConsumableUsedEvent を出さず、直接ダメージを
                # PlayerStatusAggregate に適用する。HP 回復等は捨てるが、食べ物
                # として腹に入った分だけ HUNGER 回復は半分だけ残す。damage 量は
                # 当面ハードコード (10)。per-item config は別 PR で。
                damage = SPOILED_FOOD_DAMAGE_HP
                retained_hunger = int(
                    _extract_hunger_satisfaction_amount(
                        item_instance.item_spec.consume_effect
                    )
                    * SPOILED_FOOD_HUNGER_RETENTION_RATIO
                )
                # 防御: 最小 wiring (テスト等) で _player_status_repository=None
                # でインスタンス化された場合に AttributeError を投げないよう
                # ガード。本ガードに当たるのは構成ミス相当で、damage は適用
                # できないが silent crash よりは LLM に「効果が適用されなかっ
                # た」を返す方が学習可能。
                if self._player_status_repository is None:
                    return LlmCommandResultDto(
                        success=True,
                        message=f"{name}を食べてしまった。腐っていたが体への効果は記録されなかった。",
                    )
                status = self._player_status_repository.find_by_id(PlayerId(player_id))
                if status is not None:
                    status.apply_damage(damage)
                    if retained_hunger > 0:
                        status.satisfy_need(NeedType.HUNGER, retained_hunger)
                    self._player_status_repository.save(status)
                    # Phase G silent-failure fix: apply_damage が HP 0 にした
                    # 場合 aggregate は PlayerDownedEvent を積む。event_publisher
                    # に流さないと PlayerDownedOutcomeHandler が走らず、
                    # 腐敗食で死んでも DEAD outcome が立たない silent 破綻に
                    # なる。new 鮮 path が ConsumableUsedEvent を publish する
                    # のと同様に、spoiled path でも aggregate events を
                    # publish_all で流す。
                    if self._event_publisher is not None:
                        status_events = list(status.get_events())
                        status.clear_events()
                        if status_events:
                            self._event_publisher.publish_all(status_events)
                base = (
                    f"{name}を食べてしまった。腐っていた——胃の奥が灼ける。"
                    f"（{damage} ダメージ。それでも少し空腹は和らいだ）"
                )
                # PR-ι: 使いながらの一言 (silent fail-safe)
                self._maybe_emit_say_inline(player_id, args)
                return LlmCommandResultDto(
                    success=True,
                    message=base,
                )
            # 通常 (新鮮) パス: ConsumableUsedEvent を発行
            # → ConsumableEffectHandler が HP/MP 回復等を適用
            if (
                self._event_publisher is not None
                and item_instance.item_spec.consume_effect is not None
            ):
                from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent
                self._event_publisher.publish(
                    ConsumableUsedEvent.create(
                        aggregate_id=PlayerId(player_id),
                        aggregate_type="PlayerStatusAggregate",
                        item_spec_id=item_instance.item_spec.item_spec_id,
                    )
                )
            # PR β: アイテムの fatigue_recovery を適用 (scenario JSON 由来)。
            # 食料 / 茶 / 薬の類で疲労回復を表現する。0 ならスキップ。
            recovery = getattr(item_instance.item_spec, "fatigue_recovery", 0) or 0
            if recovery > 0:
                self._recover_fatigue_safe(player_id, recovery)
            base = f"{name}を使用した。"
            if item_instance.item_spec.consume_effect is not None:
                base += f"（効果が適用された）"
            # PR-ι: 使いながらの一言 (silent fail-safe)
            self._maybe_emit_say_inline(player_id, args)
            return LlmCommandResultDto(
                success=True,
                message=base,
            )
        except Exception as e:
            return _use_item_unexpected_exception_result(e, stage="effect_application")

    def _prepare_action(self, player_id: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        if not self._sync_action_groups:
            return LlmCommandResultDto(
                success=False,
                message=(
                    "このシナリオでは prepare_action を使う同期アクションが"
                    "定義されていません。利用可能なツール一覧を確認して、"
                    "別の行動を選んでください。"
                ),
                error_code="UNSUPPORTED_TOOL",
                remediation=get_remediation("UNSUPPORTED_TOOL"),
            )
        action_id = str(args.get("action_id", "")).strip()
        if not action_id:
            return build_invalid_arg_failure(
                arg_name="action_id",
                detail="準備するアクションの ID (非空文字列) を指定してください",
            )
        try:
            registry = PreparedActionRegistry(self._svc.world_flags)
            registry.prepare(player_id=player_id, action_id=action_id)
            # 協力ギミック #13: action_id が sync group に属していれば、
            # tick 付きで SynchronizedActionRegistry にも記録し、観測を出す。
            self._maybe_register_sync_prepare(player_id, action_id)
            base = f"アクション「{action_id}」の準備をした。他のプレイヤーが対応する操作を実行できるようになった。"
            return LlmCommandResultDto(
                success=True,
                message=base,
            )
        except ValueError as ve:
            # ValueError は registry の引数検証 (action_id 空など) で起きる想定。
            # str(ve) を LLM に直渡しすると path / 内部 ID を漏らす経路になり得るので、
            # サニタイズ + サーバ側ログを残す (PR #170 と同じ pattern)。
            return build_sanitized_exception_failure(
                exc=ve,
                log_context=(
                    f"spot_graph_prepare_action validation failure "
                    f"player_id={player_id} action_id={action_id!r}"
                ),
                public_message=(
                    f"action_id={action_id!r} の準備に失敗しました。"
                    "シナリオで定義済みの action_id を指定してください。"
                ),
                error_code="INVALID_ARGUMENT",
            )
        except Exception as e:
            return exception_result(e)

    def _maybe_register_sync_prepare(self, player_id: int, action_id: str) -> None:
        """action_id が sync group に属していれば tick 付き登録 + 観測発火。"""
        if not self._sync_action_groups or self._time_provider is None:
            return
        matching = [
            g for g in self._sync_action_groups
            if action_id in g.required_action_ids
        ]
        if not matching:
            return
        current_tick = self._time_provider.get_current_tick()
        sync_registry = self._sync_action_registry
        # MEDIUM-2: 同 player+action_id が既に登録済みなら観測の重複を避ける。
        # （tick だけ更新する形で prepare し直し、観測は出さない。）
        already_prepared_by_same_player = any(
            e.player_id == player_id
            for e in sync_registry.entries_for(action_id)
        )
        sync_registry.prepare(
            action_id=action_id,
            player_id=player_id,
            current_tick=current_tick.value,
        )
        if already_prepared_by_same_player:
            return
        # 観測発火: 各 group の on_prepare_observation_message を持つもののみ
        if self._event_publisher is None or self._spot_graph_repository is None:
            return
        # actor のスポット情報を取得
        try:
            graph = self._spot_graph_repository.find_graph()
            spot_id = graph.get_entity_spot(EntityId.create(player_id))
        except Exception:
            return
        events = []
        for g in matching:
            if not g.on_prepare_observation_message:
                continue
            events.append(
                SpotPlayerPreparedActionEvent.create(
                    aggregate_id=graph.graph_id,
                    aggregate_type="SpotGraphAggregate",
                    entity_id=EntityId.create(player_id),
                    spot_id=spot_id,
                    action_id=action_id,
                    group_id=g.group_id,
                    observation_message=g.on_prepare_observation_message,
                )
            )
        if events:
            self._event_publisher.publish_all(events)

    def _drop_item(self, player_id: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        """`spot_graph_drop_item`: 所持アイテムを現在地の地面に置く。

        resolver は item_spec_id だけを解決する。同名アイテムを複数持つ場合に
        prompt 構築時の代表 slot が古くなるため、slot は実行時に引き直す。
        本ハンドラは SpotGraphItemTransferService に委譲してインベントリから地面
        への転送だけ行う。同室者への観測注入は Phase 19 で event 経由で行う。
        """
        if self._item_transfer_service is None:
            return LlmCommandResultDto(
                success=False,
                message="drop_item は本構成で未配線です。",
                error_code="NOT_WIRED",
                remediation=get_remediation("NOT_WIRED"),
            )
        item_spec_id_raw = args.get("item_spec_id")
        if item_spec_id_raw is None:
            return build_invalid_arg_failure(
                arg_name="item_spec_id",
                detail="resolver が item_spec_id を埋めませんでした (label 解決失敗の可能性)",
            )
        found = self._find_owned_slot_by_item_spec_id_and_spoilage(
            player_id, item_spec_id_raw, args.get("is_spoiled", False),
        )
        if found is None:
            return build_invalid_arg_failure(
                arg_name="item_label",
                detail="指定した名前のアイテムをもう持っていません。所持品欄の名前を確認してください。",
            )
        from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
        slot_id, _item_instance_id = found
        # Phase C: stealth=true なら ACTOR_ONLY、それ以外は従来通り SAME_SPOT
        policy = (
            WitnessPolicy.ACTOR_ONLY if bool(args.get("stealth", False))
            else WitnessPolicy.SAME_SPOT
        )
        try:
            result = self._item_transfer_service.drop_item(
                PlayerId(player_id), slot_id,
                witness_policy=policy,
            )
            self._maybe_emit_say_inline(player_id, args)
            msg = "; ".join(result.messages) if result.messages else "地面に置いた。"
            return LlmCommandResultDto(
                success=True, message=msg
            )
        except ItemTransferException as e:
            # PR-ε: subclass (SlotIsEmptyError 等) の error_code / message を
            # そのまま LLM に返す。base の ItemTransferException では従来通り
            # ITEM_TRANSFER_FAILED に落ちる。
            error_code = getattr(e, "error_code", "ITEM_TRANSFER_FAILED")
            return LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code=error_code,
                remediation=get_remediation(error_code),
            )
        except Exception as e:
            return exception_result(e)

    def _pickup_item(self, player_id: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        """`spot_graph_pickup_item`: 現在地の地面アイテムを拾う。

        resolver で item_instance_id / target_display_name まで解決済み。
        """
        if self._item_transfer_service is None:
            return LlmCommandResultDto(
                success=False,
                message="pickup_item は本構成で未配線です。",
                error_code="NOT_WIRED",
                remediation=get_remediation("NOT_WIRED"),
            )
        iid_raw = args.get("item_instance_id")
        if iid_raw is None:
            return build_invalid_arg_failure(
                arg_name="item_instance_id",
                detail="resolver が item_instance_id を埋めませんでした",
            )
        try:
            iid_int = int(iid_raw)
        except (TypeError, ValueError):
            return build_invalid_arg_failure(
                arg_name="item_instance_id",
                detail="item_instance_id は整数で指定してください",
            )
        from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
        from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
        policy = (
            WitnessPolicy.ACTOR_ONLY if bool(args.get("stealth", False))
            else WitnessPolicy.SAME_SPOT
        )
        try:
            result = self._item_transfer_service.pickup_item(
                PlayerId(player_id), ItemInstanceId.create(iid_int),
                witness_policy=policy,
            )
            self._maybe_emit_say_inline(player_id, args)
            msg = "; ".join(result.messages) if result.messages else "拾い上げた。"
            return LlmCommandResultDto(
                success=True, message=msg
            )
        except ItemTransferException as e:
            # PR-ε: subclass (GroundItemGoneError / PickupSelfInventoryFullError)
            # の error_code / message をそのまま LLM に返す。domain 側で
            # 「先取り可能性」「drop で空き作成」等の次アクションを message
            # に含めているので prefix は不要。
            error_code = getattr(e, "error_code", "ITEM_TRANSFER_FAILED")
            return LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code=error_code,
                remediation=get_remediation(error_code),
            )
        except Exception as e:
            return exception_result(e)

    def _give_item(self, player_id: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        """``give_item`` (batch-always): 同 tick に複数 give を集約実行する。

        PR-α (Y_after_pr639_640 後続): 旧 give_item (単発) と旧 give_items
        (batch) を統合。resolver は常に ``gives_resolved: [...]`` を埋めて
        渡してくる (単発でも length=1 の配列)。

        ``gives_resolved`` の各 entry を順に処理し、結果を 1 行 1 entry の
        サマリ message に集約する。**partial success**: 一部失敗しても残りは
        進行し、success フラグは「1 件でも成功したか」で立つ。

        say_inline は **全 give が終わった後** に 1 度だけ発火する
        (もし一部成功なら整合性のため発火する)。

        エラー処理は domain-specific exception ごとに error_code を分けて
        LLM が次アクションを取れる形にする (PR-α):
        - ``TargetIsSelfError`` → GIVE_ITEM_TARGET_IS_SELF
        - ``TargetNotInSameSpotError`` → GIVE_ITEM_TARGET_NOT_IN_SAME_SPOT
          (executor 側で相手名 / 現在地名を埋め直す)
        - ``TargetInventoryFullError`` → GIVE_ITEM_TARGET_INVENTORY_FULL
        - ``TargetIsDeadError`` / ``TargetIsDownError`` → 対象が受け取れない
        - その他 ``ItemTransferException`` → ITEM_TRANSFER_FAILED
        バッチのため各 entry の失敗は個別に message に集約する。
        """
        if self._item_transfer_service is None:
            return LlmCommandResultDto(
                success=False,
                message="give_item は本構成で未配線です。",
                error_code="NOT_WIRED",
                remediation=get_remediation("NOT_WIRED"),
            )
        gives_resolved = args.get("gives_resolved")
        if not isinstance(gives_resolved, list) or not gives_resolved:
            return build_invalid_arg_failure(
                arg_name="gives",
                detail="resolver が gives_resolved を埋めませんでした "
                "(gives 配列が空 / 不正?)。1 件だけの場合も "
                "gives=[{item_label:..., target_player_label:...}] のように "
                "配列で渡してください。",
            )

        ok_lines: list[str] = []
        ng_lines: list[str] = []
        # partial success で最も深刻な (LLM に伝えたい) 失敗 error_code を残す。
        # 全失敗のとき、success=False の DTO に立てる error_code に使う。
        first_ng_code: str | None = None

        for entry in gives_resolved:
            item_disp = entry.get("item_display_name") or entry.get("item_label") or "?"
            target_disp = (
                entry.get("target_display_name")
                or entry.get("target_player_label")
                or "?"
            )
            # resolve 段階で失敗していた entry は error_code が埋まっている
            if entry.get("error_code"):
                ng_lines.append(
                    f"{item_disp} → {target_disp}: NG "
                    f"({entry.get('message', '解決失敗')})"
                )
                if first_ng_code is None:
                    first_ng_code = str(entry.get("error_code"))
                continue
            try:
                item_spec_id = entry["item_spec_id"]
                is_spoiled = bool(entry.get("is_spoiled", False))
                to_int = int(entry["target_player_id"])
            except (KeyError, TypeError, ValueError):
                ng_lines.append(
                    f"{item_disp} → {target_disp}: NG (resolver 出力が不正)"
                )
                if first_ng_code is None:
                    first_ng_code = "INVALID_ARGUMENT"
                continue
            found = self._find_owned_slot_by_item_spec_id_and_spoilage(
                player_id, item_spec_id, is_spoiled,
            )
            if found is None:
                msg = (
                    f"{item_disp} をもう持っていません。"
                    "所持品欄に表示されているアイテム名を確認してください。"
                )
                ng_lines.append(f"{item_disp} → {target_disp}: NG ({msg})")
                if first_ng_code is None:
                    first_ng_code = "ITEM_TRANSFER_SLOT_IS_EMPTY"
                continue
            slot_id, _item_instance_id = found
            try:
                self._item_transfer_service.give_item(
                    PlayerId(player_id), PlayerId(to_int), slot_id,
                )
                ok_lines.append(f"{item_disp} → {target_disp}: OK")
            except TargetIsSelfError as e:
                ng_lines.append(
                    f"{item_disp} → {target_disp}: NG ({e})"
                )
                if first_ng_code is None:
                    first_ng_code = e.error_code
            except TargetNotInSameSpotError:
                # domain 層は relative 名前を持たないので、ここで target_disp
                # を差し込んだ message を組み立て直す (現在地名は wiring 未設定
                # なので相手名だけ具体化)。
                msg = (
                    f"{target_disp} は同じ場所にいません。"
                    f"travel_to で移動してから再度渡してください。"
                )
                ng_lines.append(f"{item_disp} → {target_disp}: NG ({msg})")
                if first_ng_code is None:
                    first_ng_code = "GIVE_ITEM_TARGET_NOT_IN_SAME_SPOT"
            except TargetInventoryFullError:
                msg = (
                    f"{target_disp} のインベントリが満杯で {item_disp} を"
                    f"受け取れません。{target_disp} が別のアイテムを drop する"
                    f"のを待つか、別の相手に渡してください。"
                )
                ng_lines.append(f"{item_disp} → {target_disp}: NG ({msg})")
                if first_ng_code is None:
                    first_ng_code = "GIVE_ITEM_TARGET_INVENTORY_FULL"
            except TargetIsDeadError:
                msg = f"{target_disp}は死亡しており受け取れない。"
                ng_lines.append(f"{item_disp} → {target_disp}: NG ({msg})")
                if first_ng_code is None:
                    first_ng_code = "GIVE_ITEM_TARGET_DEAD"
            except TargetIsDownError:
                msg = f"{target_disp}は倒れていて受け取れない。"
                ng_lines.append(f"{item_disp} → {target_disp}: NG ({msg})")
                if first_ng_code is None:
                    first_ng_code = "GIVE_ITEM_TARGET_DOWN"
            except ItemTransferException as e:
                # PR-ε: SlotIsEmptyError などの新設 subclass は
                # error_code class attribute を持つので、それを LLM に返す。
                # base の ItemTransferException (稀な整合性違反) は
                # ITEM_TRANSFER_FAILED にフォールバック。
                ng_lines.append(f"{item_disp} → {target_disp}: NG ({e})")
                if first_ng_code is None:
                    first_ng_code = getattr(
                        e, "error_code", "ITEM_TRANSFER_FAILED"
                    )
            except Exception as e:  # noqa: BLE001
                ng_lines.append(f"{item_disp} → {target_disp}: NG (内部例外: {e})")
                if first_ng_code is None:
                    first_ng_code = "ITEM_TRANSFER_FAILED"

        # 全失敗の場合は success=False で返し、LLM に「何 1 つ渡せなかった」を明示
        trace_payload = {
            "give_item_total_count": len(gives_resolved),
            "give_item_success_count": len(ok_lines),
            "give_item_failure_count": len(ng_lines),
            "give_item_partial_failure": bool(ok_lines and ng_lines),
        }
        if not ok_lines:
            code = first_ng_code or "ITEM_TRANSFER_FAILED"
            return LlmCommandResultDto(
                success=False,
                message="give_item: 全て失敗\n" + "\n".join(ng_lines),
                error_code=code,
                remediation=get_remediation(code),
                trace_payload=trace_payload,
            )

        # 1 件でも成功したら success=True とし、say_inline を発火する
        # (受け渡しが少なくとも 1 件成立したので、行動しながらの一言は自然)
        self._maybe_emit_say_inline(player_id, args)
        parts = ok_lines + ng_lines
        msg = "give_item 結果:\n" + "\n".join(parts)
        return LlmCommandResultDto(
            success=True,
            message=msg,
            trace_payload=trace_payload,
        )

    def _attack(self, player_id: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        """`spot_graph_attack`: 同スポットのモンスターを攻撃する。

        resolver で `monster_id` / `target_display_name` まで解決済み。
        実際の attack 処理は `SpotAttackOrchestrator` に委譲し、本ハンドラは:
        1. 必要なリポジトリ + orchestrator + tick provider が揃っているか確認
        2. attacker / target aggregate をロード
        3. orchestrator.execute_player_attack に loaded aggregate を渡す
        4. 戻ってきた `AttackOutcome` を LlmCommandResultDto に変換

        save / event 発火は orchestrator が責任を持つ。失敗系
        （cooldown / target_dead / damage=0 / wiring 不足）は
        `success=False` で返す。
        """
        # PR β: 疲労 limit (100) で attack は block。
        blocked = self._is_exhausted_and_block(player_id, TOOL_NAME_SPOT_GRAPH_ATTACK)
        if blocked is not None:
            return blocked
        orchestrator = self._resolve_attack_orchestrator()
        if (
            orchestrator is None
            or self._monster_repository is None
            or self._player_status_repository is None
            or self._spot_graph_repository is None
            or self._time_provider is None
        ):
            return LlmCommandResultDto(
                success=False,
                message="attack は現在のワイヤリングでは未対応です。",
                error_code="UNSUPPORTED_TOOL",
                remediation=get_remediation("UNSUPPORTED_TOOL"),
            )

        monster_id_int = args.get("monster_id")
        if not isinstance(monster_id_int, int):
            return LlmCommandResultDto(
                success=False,
                message="monster_id が解決されていません。",
                error_code="INVALID_TARGET_LABEL",
            )
        display_name = str(args.get("target_display_name", "")).strip() or "モンスター"

        monster_id = MonsterId.create(monster_id_int)
        try:
            monster = self._monster_repository.find_by_id(monster_id)
            if monster is None:
                return LlmCommandResultDto(
                    success=False,
                    message=f"対象のモンスターが見つかりません: {display_name}",
                    error_code="TARGET_NOT_FOUND",
                )
            attacker = self._player_status_repository.find_by_id(PlayerId(player_id))
            if attacker is None:
                return LlmCommandResultDto(
                    success=False,
                    message="プレイヤー情報が見つかりません。",
                    error_code="PLAYER_NOT_FOUND",
                )

            graph = self._spot_graph_repository.find_graph()
            current_tick = self._time_provider.get_current_tick()
            outcome = orchestrator.execute_player_attack(
                attacker_player=attacker,
                target_monster=monster,
                graph=graph,
                current_tick=current_tick,
            )
            if not outcome.executed:
                return LlmCommandResultDto(
                    success=False,
                    message=f"{display_name}を攻撃できなかった ({outcome.reason})。",
                    error_code="ATTACK_FAILED",
                )

            base = f"{display_name}に {outcome.damage} のダメージを与えた。"
            if outcome.target_incapacitated:
                base += " 致命傷で倒した。"
            # PR-ι: 戦闘中の一言 (silent fail-safe)。「離れろ！」等を仲間に伝える。
            self._maybe_emit_say_inline(player_id, args)
            # PR β: 戦闘は激しい消耗。executed のみ蓄積 (空振り cooldown は除外)。
            self._apply_fatigue_safe(player_id, self.FATIGUE_COST_ATTACK)
            return LlmCommandResultDto(
                success=True,
                message=base,
            )
        except Exception as e:
            return exception_result(e)

    def _resolve_attack_orchestrator(self) -> Optional[SpotAttackOrchestrator]:
        """attack_orchestrator が注入されていればそれを使い、無ければ
        repository から動的に組み立てる（後方互換）。

        将来、wiring が必ず orchestrator を渡すようになったら本メソッドと
        その下の組み立てロジックは削除して `self._attack_orchestrator` を
        直接使えば良い。
        """
        if self._attack_orchestrator is not None:
            return self._attack_orchestrator
        if (
            self._monster_repository is None
            or self._player_status_repository is None
            or self._spot_graph_repository is None
        ):
            return None
        return SpotAttackOrchestrator(
            spot_graph_repository=self._spot_graph_repository,
            monster_repository=self._monster_repository,
            player_status_repository=self._player_status_repository,
        )

    def _listen(self, player_id: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        """`spot_graph_listen`: 自 spot + 隣接 spot (1 hop 減衰) の環境音観測。

        PR-θ4 (経路統合): 旧 runtime_manager._handle_listen と統合。
        `runtime.do_listen` が `SpotGraphAggregate.emit_listen_carefully` +
        `_process_graph_events` (= observation pipeline への投入) を面倒見るので、
        executor 側は LLM 向けの実行確認を組み立てるだけの薄い wrapper。
        環境音と人の気配は
        別々の observation として届くため、環境音の件数だけから「何も
        聞こえなかった」とは断定しない。

        state 変更なし。observation は formatter が prose を構築し本人にだけ
        配信される (recipient strategy で filter)。
        """
        if self._runtime is None:
            return LlmCommandResultDto(
                success=False,
                message="listen は本構成で未配線です。",
                error_code="NOT_WIRED",
                remediation=get_remediation("NOT_WIRED"),
            )
        try:
            self._runtime.do_listen(PlayerId(player_id))
        except Exception as e:
            return exception_result(e)
        base = "耳を澄まし、周囲の音や人の気配を確かめた。"
        return with_inner_thought_empty_warning(
            TOOL_NAME_SPOT_GRAPH_LISTEN,
            args,
            LlmCommandResultDto(
                success=True,
                message=base,
            ),
        )

    def _wait(self, player_id: int, args: Dict[str, Any], runtime_context: Any = None) -> LlmCommandResultDto:
        """``wait`` の実行 (PR-θ5: 経路統合後)。

        旧 runtime_manager._handle_wait と統合。**この経路が唯一の wait 実装**。

        統合方針 (Option B): ``runtime.do_wait`` を呼ぶ薄い wrapper 化。
        do_wait が `_record_action_result` (subjective 含む) を面倒見る。
        疲労回復は新経路の付加価値として wrapper 側で残す。

        wait は exhausted でも実行可 (= 回復の主経路)、疲労 block しない。
        #471 fix: 旧経路が誤って world tick を進めていた再帰カスケード bug は
        do_wait 実装で解消済み。
        """
        if self._runtime is None:
            return LlmCommandResultDto(
                success=False,
                message="wait は本構成で未配線です。",
                error_code="NOT_WIRED",
                remediation=get_remediation("NOT_WIRED"),
            )
        reason = str(args.get("reason", "")).strip()
        try:
            subjective = extract_subjective_action_fields(args)
            tick = self._runtime.do_wait(
                PlayerId(player_id), reason=reason, **subjective
            )
            # PR β: wait は微回復 (専用 rest tool は作らない設計)。
            self._recover_fatigue_safe(player_id, self.FATIGUE_RECOVERY_WAIT)
            self._maybe_emit_say_inline(player_id, args)
            suffix = f"（理由: {reason}）" if reason else ""
            base = f"今ターンは行動を控えた: tick={tick}{suffix}"
            return with_inner_thought_empty_warning(
                TOOL_NAME_SPOT_GRAPH_WAIT,
                args,
                LlmCommandResultDto(
                    success=True,
                    message=base,
                ),
            )
        except Exception as e:
            return exception_result(e)

    # Issue #621 Phase 3b: 同 spot に倒れた仲間を介抱して revive する。
    # アイテム (= first_aid) を持っていなくても物理的に起こす経路。
    #
    # PR-κ (Y_after_pr651_652 分析後続): 旧値 0.4 (= HP 40/100) だと野犬
    # 15 ダメ x 3 発で確実に再ダウンし、実 trace で「復帰 → 2 tick 後に再
    # ダウン」のループが観測された (エイダの t=180-192 で 4 回連続の
    # revive→再down)。復帰 → LLM の action turn (travel_to など) が挟まる
    # 前に攻撃で潰される設計不良。
    #
    # 対処: HP 回復率を 0.4 → 0.6 に引き上げ。60 HP なら野犬 4 発耐えられ
    # るので、LLM が 2 tick 以内に travel_to 判断できれば逃げ切れる。加え
    # て post_hoc observation の prose を強化 (下記 handler 参照) して
    # 「travel_to で退避せよ」を LLM に届ける。無敵時間 (grace period) の
    # 本格実装 (StatusEffect 経由の monster attack skip) は別 PR で行う。
    TEND_REVIVE_HP_RATE = 0.6

    def _vote(
        self, player_id: int, args: Dict[str, Any], runtime_context: Any = None
    ) -> LlmCommandResultDto:
        """`spot_graph_vote` の handler。

        resolver が ``target_player_id`` まで解決済み。None は棄権。
        会議中かどうかは runtime が判定する。toolset から外すだけでは悪性
        クライアントや provider の変換崩れで届きうるので、実行側でも弾く
        (設計 doc H-6)。
        """
        raw = args.get("target_player_id")
        target = PlayerId(int(raw)) if raw is not None else None
        return self._runtime.cast_vote(PlayerId(player_id), target)

    def _report_body(
        self, player_id: int, args: Dict[str, Any], runtime_context: Any = None
    ) -> LlmCommandResultDto:
        """`spot_graph_report_body` の handler。

        resolver が ``target_player_id`` まで解決済み。同席しているか、相手が
        本当に倒れているか、同じ相手を二度報告していないかは runtime が見る。

        自由時間かどうかも runtime が判定する。toolset から外すだけでは悪性
        クライアントや provider の変換崩れで届きうるので、実行側でも弾く
        (設計 doc H-6)。vote と同じ形。
        """
        raw = args.get("target_player_id")
        if raw is None:
            return LlmCommandResultDto(
                success=False,
                message="誰を見つけたのかが分からない。",
                error_code="INVALID_TARGET_LABEL",
            )
        return self._runtime.report_body(PlayerId(player_id), PlayerId(int(raw)))

    def _tend_to_player(
        self, player_id: int, args: Dict[str, Any], runtime_context: Any = None
    ) -> LlmCommandResultDto:
        """`spot_graph_tend_to_player` の handler (Issue #621 Phase 3b)。

        resolver で `target_player_id` / `target_display_name` まで解決済み。
        前提条件:
          1. wiring (= player_status_repository) が揃っている
          2. 自分自身を対象にできない (= 倒れている本人は LLM call が
             止まっているはずなので呼ばれないが、防御的に弾く)
          3. 対象が同じ spot にいる (= 物理介抱は隣にいないとできない)
          4. 対象が is_down=True (= 元気な相手を介抱しても意味なし)
          5. 介抱者本人が is_down=False (= 倒れた人は他人を介抱できない)
          ※ DEAD 確定後の player は PlayerDeathGraceTickStage が
             `_is_down=True` のまま outcome=DEAD にするので、is_down=True で
             revive を試行できてしまう。outcome 確定は別レイヤ (registry)
             で持っているので、ここでは is_down だけ見れば足りる
             (= revive が成功しても registry は冪等で DEAD のまま)。
             ただし「もう手遅れだった」感を出すため、別途 outcome registry
             をチェックする設計余地はある (将来 PR)。

        成功時: `target.revive(hp_rate=0.4)` を呼ぶ。PlayerRevivedEvent が
        積まれ、ConsumableEffectHandler 経路と同じく PlayerRevivedOutcomeHandler
        が grace_timer.cancel する。
        """
        if self._player_status_repository is None:
            return LlmCommandResultDto(
                success=False,
                message="tend_to_player は現在のワイヤリングでは未対応です。",
                error_code="UNSUPPORTED_TOOL",
                remediation=get_remediation("UNSUPPORTED_TOOL"),
            )

        target_player_id_raw = args.get("target_player_id")
        if not isinstance(target_player_id_raw, int):
            return LlmCommandResultDto(
                success=False,
                message="target_player_id が解決されていません。",
                error_code="INVALID_TARGET_LABEL",
            )
        if target_player_id_raw == player_id:
            return LlmCommandResultDto(
                success=False,
                message="自分自身を介抱することはできません。",
                error_code="INVALID_TARGET_KIND",
            )
        display_name = (
            str(args.get("target_display_name", "")).strip() or "仲間"
        )

        try:
            attacker_id = PlayerId(player_id)
            target_id = PlayerId(target_player_id_raw)
            actor = self._player_status_repository.find_by_id(attacker_id)
            target = self._player_status_repository.find_by_id(target_id)
            if actor is None or target is None:
                return LlmCommandResultDto(
                    success=False,
                    message=f"対象のプレイヤーが見つかりません: {display_name}",
                    error_code="TARGET_NOT_FOUND",
                )
            # 相手が対象として使えるかは、engine の普遍則に委ねる
            # (負債マップ #2)。ここに書くと、行動を 1 つ足すたびに
            # 「死んだ相手をどう扱うか」を書き直すことになる。
            #
            # **outcome まで見るのは、この載せ替えで足りるようになった点。**
            # 旧実装は is_down しか見ておらず、猶予が切れて死亡が確定した
            # 相手を蘇生できた (この関数の docstring が「将来 PR」として
            # 触れていた穴)。
            registry = getattr(self._runtime, "_player_outcome_registry", None)
            outcome = (
                registry.get_outcome(target_id)
                if registry is not None
                else PlayerOutcomeEnum.UNRESOLVED
            )
            rejection = validate_actionable_target(
                actor_player_id=player_id,
                target_player_id=target_player_id_raw,
                actor_status=actor,
                target_status=target,
                target_outcome=outcome,
                same_spot=(
                    actor.current_spot_id is not None
                    and actor.current_spot_id == target.current_spot_id
                ),
                requirement=TargetRequirement.INCAPACITATED,
                target_display_name=display_name,
            )
            if rejection is not None:
                # 既存の error_code を保つ。呼び出し側 (remediation / 分析) が
                # 種別で分岐しているので、括り出しで変えない。
                template = _TEND_MESSAGES.get(rejection.code)
                return LlmCommandResultDto(
                    success=False,
                    message=(
                        template.format(name=display_name)
                        if template
                        else rejection.message
                    ),
                    error_code=_TEND_ERROR_CODES.get(
                        rejection.code, "INTERACTION_PRECONDITION_FAILED"
                    ),
                )

            # Phase 5: caregiver_player_id を渡すことで PlayerRevivedEvent に
            # 「誰に介抱されたか」を載せる。post hoc observation handler が
            # 「〇〇に介抱されて意識が戻った」を組み立てる。
            target.revive(
                hp_recovery_rate=self.TEND_REVIVE_HP_RATE,
                caregiver_player_id=PlayerId(player_id),
            )
            # イベントは save より先に回収 + clear する (needs_decay /
            # status_effects と同じ「publisher ガード内で clear してから save」)。
            # save→clear の逆順だと PlayerRevivedEvent を持ったまま集約が
            # 永続化され、後続の find→get_events→publish で 1 個の復帰イベントが
            # 毎ターン再放出されて観測を汚染する (実 run v3coop_stagnation_003 で
            # エイダの復帰が 46 tick / 141 観測に増幅)。repo 境界の drain
            # (in_memory_repository_base._clone) と二重の防御。publisher が
            # 無いときは clear せず save する (canonical は _clone が drain する)。
            events: list = []
            if self._event_publisher is not None:
                events = list(target.get_events())
                target.clear_events()
            self._player_status_repository.save(target)
            # PlayerRevivedEvent を pipeline に流す。これにより
            # PlayerRevivedOutcomeHandler が grace_timer.cancel して
            # DEAD 確定を回避する。
            if events:
                self._event_publisher.publish_all(events)
            base = (
                f"{display_name} を介抱して意識を取り戻させた。"
                f"（HP {target.hp.value}/{target.base_stats.max_hp}）"
            )
            # PR-ι: 介抱しながらの一言 (「大丈夫か！」「起きろ！」など)。
            # 同 spot の第三者にも SAY として届くので、他プレイヤーが
            # 「誰かが介抱している」を耳で認識できる (Q3 の直接解消)。
            # silent fail-safe: speak が例外を投げても親 action は success 維持。
            self._maybe_emit_say_inline(player_id, args)
            return LlmCommandResultDto(
                success=True,
                message=base,
            )
        except Exception as e:
            return exception_result(e)
