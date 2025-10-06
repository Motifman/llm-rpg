from src.domain.battle.events.battle_events import (
    BattleStartedEvent,
    PlayerJoinedBattleEvent,
    TurnStartedEvent,
    TurnExecutedEvent,
    BattleEndedEvent,
    MonsterDefeatedEvent,
    PlayerDefeatedEvent,
    StatusEffectAppliedEvent,
    BuffAppliedEvent,
)
from src.domain.common.event_handler import EventHandler
from src.domain.common.notifier import Notifier
from src.domain.spot.area_repository import AreaRepository
from src.domain.player.player_repository import PlayerRepository


class BattleStartedNotificationHandler(EventHandler[BattleStartedEvent]):
    """戦闘開始時の通知ハンドラー"""

    def __init__(
        self,
        notifier: Notifier,
        area_repository: AreaRepository,
        player_repository: PlayerRepository
    ):
        self._notifier = notifier
        self._area_repository = area_repository
        self._player_repository = player_repository

    def handle(self, event: BattleStartedEvent):
        """戦闘開始イベントを処理"""
        spot_id = event.spot_id
        area = self._area_repository.find_by_spot_id(spot_id)

        if area:
            # 同じスポットの全プレイヤーに通知
            spot_players = self._player_repository.find_by_spot_id(spot_id)
            player_ids = [p.player_id for p in spot_players]

            message = f"戦闘が開始されました！{area.name}でモンスターが出現しました。"
            self._notifier.send_notification_to_all(player_ids, message)


class PlayerJoinedBattleNotificationHandler(EventHandler[PlayerJoinedBattleEvent]):
    """プレイヤー参加時の通知ハンドラー"""

    def __init__(
        self,
        notifier: Notifier,
        player_repository: PlayerRepository
    ):
        self._notifier = notifier
        self._player_repository = player_repository

    def handle(self, event: PlayerJoinedBattleEvent):
        """プレイヤー参加イベントを処理"""
        battle_players = self._player_repository.find_by_battle_id(event.battle_id)
        player_ids = [p.player_id for p in battle_players]

        player = self._player_repository.find_by_id(event.player_id)
        if player:
            message = f"{player.name}が戦闘に参加しました。"
            self._notifier.send_notification_to_all(player_ids, message)


class TurnStartedNotificationHandler(EventHandler[TurnStartedEvent]):
    """ターン開始時の通知ハンドラー"""

    def __init__(
        self,
        notifier: Notifier,
        player_repository: PlayerRepository
    ):
        self._notifier = notifier
        self._player_repository = player_repository

    def handle(self, event: TurnStartedEvent):
        """ターン開始イベントを処理"""
        battle_players = self._player_repository.find_by_battle_id(event.battle_id)
        player_ids = [p.player_id for p in battle_players]

        if event.participant_type.value == "PLAYER":
            player = self._player_repository.find_by_id(event.actor_id)
            if player:
                if event.can_act:
                    message = f"{player.name}のターンです。行動を選択してください。"
                else:
                    message = f"{player.name}は行動不能です。ターンをスキップします。"
                self._notifier.send_notification_to_all(player_ids, message)
        else:
            # モンスターのターン開始
            if event.can_act:
                message = f"モンスターのターンです。"
            else:
                message = f"モンスターは行動不能です。ターンをスキップします。"
            self._notifier.send_notification_to_all(player_ids, message)


class TurnExecutedNotificationHandler(EventHandler[TurnExecutedEvent]):
    """ターン実行時の通知ハンドラー"""

    def __init__(
        self,
        notifier: Notifier,
        player_repository: PlayerRepository
    ):
        self._notifier = notifier
        self._player_repository = player_repository

    def handle(self, event: TurnExecutedEvent):
        """ターン実行イベントを処理"""
        battle_players = self._player_repository.find_by_battle_id(event.battle_id)
        player_ids = [p.player_id for p in battle_players]

        # 行動結果のメッセージを通知
        for message in event.messages:
            self._notifier.send_notification_to_all(player_ids, message)

        # 成功/失敗の情報を追加で通知
        action_name = event.action_info.name if event.action_info else "アクション"
        if event.success:
            action_msg = f"{action_name}が成功しました。"
        else:
            action_msg = f"{action_name}が失敗しました。理由: {event.failure_reason}"

        self._notifier.send_notification_to_all(player_ids, action_msg)


class BattleEndedNotificationHandler(EventHandler[BattleEndedEvent]):
    """戦闘終了時の通知ハンドラー"""

    def __init__(
        self,
        notifier: Notifier,
        player_repository: PlayerRepository
    ):
        self._notifier = notifier
        self._player_repository = player_repository

    def handle(self, event: BattleEndedEvent):
        """戦闘終了イベントを処理"""
        battle_players = self._player_repository.find_by_battle_id(event.battle_id)
        player_ids = [p.player_id for p in battle_players]

        if event.result_type.value == "VICTORY":
            message = "戦闘に勝利しました！"
        elif event.result_type.value == "DEFEAT":
            message = "戦闘に敗北しました..."
        else:
            message = "戦闘が引き分けになりました。"

        self._notifier.send_notification_to_all(player_ids, message)


class MonsterDefeatedNotificationHandler(EventHandler[MonsterDefeatedEvent]):
    """モンスター撃破時の通知ハンドラー"""

    def __init__(
        self,
        notifier: Notifier,
        player_repository: PlayerRepository
    ):
        self._notifier = notifier
        self._player_repository = player_repository

    def handle(self, event: MonsterDefeatedEvent):
        """モンスター撃破イベントを処理"""
        battle_players = self._player_repository.find_by_battle_id(event.battle_id)
        player_ids = [p.player_id for p in battle_players]

        message = f"モンスターを撃破しました！経験値{event.final_monster_stats.get('exp', 0)}を獲得しました。"
        self._notifier.send_notification_to_all(player_ids, message)


class PlayerDefeatedNotificationHandler(EventHandler[PlayerDefeatedEvent]):
    """プレイヤー撃破時の通知ハンドラー"""

    def __init__(
        self,
        notifier: Notifier,
        player_repository: PlayerRepository
    ):
        self._notifier = notifier
        self._player_repository = player_repository

    def handle(self, event: PlayerDefeatedEvent):
        """プレイヤー撃破イベントを処理"""
        battle_players = self._player_repository.find_by_battle_id(event.battle_id)
        player_ids = [p.player_id for p in battle_players]

        player = self._player_repository.find_by_id(event.player_id)
        if player:
            message = f"{player.name}が戦闘不能になりました。"
            self._notifier.send_notification_to_all(player_ids, message)


class StatusEffectAppliedNotificationHandler(EventHandler[StatusEffectAppliedEvent]):
    """状態異常適用時の通知ハンドラー"""

    def __init__(
        self,
        notifier: Notifier,
        player_repository: PlayerRepository
    ):
        self._notifier = notifier
        self._player_repository = player_repository

    def handle(self, event: StatusEffectAppliedEvent):
        """状態異常適用イベントを処理"""
        battle_players = self._player_repository.find_by_battle_id(event.battle_id)
        player_ids = [p.player_id for p in battle_players]

        if event.participant_type.value == "PLAYER":
            player = self._player_repository.find_by_id(event.target_id)
            if player:
                message = f"{player.name}は{event.status_effect_type.value}の状態異常を受けました。"
        else:
            message = f"モンスターは{event.status_effect_type.value}の状態異常を受けました。"

        self._notifier.send_notification_to_all(player_ids, message)


class BuffAppliedNotificationHandler(EventHandler[BuffAppliedEvent]):
    """バフ適用時の通知ハンドラー"""

    def __init__(
        self,
        notifier: Notifier,
        player_repository: PlayerRepository
    ):
        self._notifier = notifier
        self._player_repository = player_repository

    def handle(self, event: BuffAppliedEvent):
        """バフ適用イベントを処理"""
        battle_players = self._player_repository.find_by_battle_id(event.battle_id)
        player_ids = [p.player_id for p in battle_players]

        if event.participant_type.value == "PLAYER":
            player = self._player_repository.find_by_id(event.target_id)
            if player:
                message = f"{player.name}は{event.buff_type.value}のバフを受けました。"
        else:
            message = f"モンスターは{event.buff_type.value}のバフを受けました。"

        self._notifier.send_notification_to_all(player_ids, message)
