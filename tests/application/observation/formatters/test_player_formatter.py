"""PlayerObservationFormatter の単体テスト。"""

from dataclasses import replace

import pytest
from unittest.mock import MagicMock

# observation.contracts.interfaces と prompt_builder_config の循環 import を避けるため、
# observation formatter を直接 import する単体テストでは prompt_builder を先に初期化する。
from ai_rpg_world.application.llm.services import prompt_builder as _prompt_builder  # noqa: F401
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.player_formatter import (
    PlayerObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerLocationChangedEvent,
    PlayerLevelUpEvent,
    PlayerRevivedEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
)
from ai_rpg_world.domain.player.event.inventory_events import (
    ItemAddedToInventoryEvent,
    ItemDroppedFromInventoryEvent,
    ItemEquippedEvent,
    ItemUnequippedEvent,
    InventorySlotOverflowEvent,
)
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.skill.event.skill_events import SkillEquippedEvent
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier


def _make_context(
    spot_repository=None,
    player_profile_repository=None,
    item_repository=None,
) -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    name_resolver = ObservationNameResolver(
        spot_repository=spot_repository,
        player_profile_repository=player_profile_repository,
        item_spec_repository=None,
        item_repository=item_repository,
        shop_repository=None,
        guild_repository=None,
        monster_repository=None,
        skill_spec_repository=None,
        sns_user_repository=None,
    )
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=item_repository,
    )


class TestPlayerObservationFormatterCreation:
    """PlayerObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる（parent 不要）。"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self):
        """format(event, recipient_player_id) が呼び出し可能。"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestPlayerObservationFormatterPlayerLocationChanged:
    """PlayerLocationChangedEvent のフォーマットテスト"""

    def test_self_returns_current_location_prose(self):
        """本人向けは「現在地: 〇〇」を返す。"""
        spot_repo = MagicMock()
        spot = MagicMock()
        spot.name = "町の広場"
        spot_repo.find_by_id.return_value = spot
        ctx = _make_context(spot_repository=spot_repo)
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(1, 1, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "現在地" in out.prose
        assert "町の広場" in out.prose
        assert out.structured.get("type") == "current_location"
        assert out.observation_category == "self_only"

    def test_other_player_returns_entered_spot_prose(self):
        """他プレイヤー向けは「〇〇がこのスポットにやってきました。」"""
        spot_repo = MagicMock()
        spot = MagicMock()
        spot.name = "洞窟入口"
        spot_repo.find_by_id.return_value = spot
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Bob"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(
            spot_repository=spot_repo,
            player_profile_repository=profile_repo,
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(2),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(1, 1, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Bob" in out.prose
        assert "やってきました" in out.prose
        assert out.structured.get("type") == "player_entered_spot"
        assert out.observation_category == "social"


class TestPlayerObservationFormatterPlayerDowned:
    """PlayerDownedEvent のフォーマットテスト"""

    def test_self_without_killer_returns_downed_prose(self):
        """本人・killer なしは戦闘に限定せず、常体で倒れた事実を伝える。"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.prose == "倒れて動けなくなった。"
        assert "戦闘不能" not in out.prose
        assert out.breaks_movement is True
        assert out.schedules_turn is True

    def test_self_with_killer_includes_killer_name(self):
        """本人・killer ありは、加害者を主語にした能動態で伝える。"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Alice"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(player_profile_repository=profile_repo)
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.prose == "Aliceがあなたを倒した。"


class TestPlayerObservationFormatterPlayerDownedKillerVisibility:
    """Issue #185: 第三者観測の killer 視認チェック。

    別 spot に killer がいるケースで killer 名を prose に出すと、観測者が
    本来知り得ない「誰が倒したか」を漏らす経路になる。同 spot のときだけ
    killer 名を出す。位置不明 fallback は安全側 (killer 名を出さない)。
    """

    def _make_ctx_with_positions(
        self,
        recipient_spot,
        killer_spot,
        victim_spot=None,
        killer_name: str = "Alice",
        victim_name: str = "Victor",
        lighting=LightingEnum.BRIGHT,
    ):
        """recipient と killer の位置を任意に設定できる context。

        victim (PlayerId=1) と killer (PlayerId=2) で別名を返すよう
        profile_repo.find_by_id を id 別に振り分ける。
        """
        from ai_rpg_world.application.observation.services.formatters._formatter_context import (
            ObservationFormatterContext,
        )

        profile_repo = MagicMock()

        def _find_profile(pid):
            p = MagicMock()
            if pid.value == 1:
                p.name.value = victim_name
            elif pid.value == 2:
                p.name.value = killer_name
            else:
                p.name.value = f"Player{pid.value}"
            return p

        profile_repo.find_by_id.side_effect = _find_profile
        name_resolver = ObservationNameResolver(
            spot_repository=None,
            player_profile_repository=profile_repo,
            item_spec_repository=None,
            item_repository=None,
            shop_repository=None,
            guild_repository=None,
            monster_repository=None,
            skill_spec_repository=None,
            sns_user_repository=None,
        )

        # spot_graph_repository.find_graph().get_entity_spot を player_id 別に返す
        graph = MagicMock()

        def _get_entity_spot(entity_id):
            v = entity_id.value
            if v == 100:  # recipient
                return recipient_spot
            if v == 2:  # killer
                return killer_spot
            if v == 1:  # victim
                return victim_spot
            return None

        graph.get_entity_spot.side_effect = _get_entity_spot
        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        lighting_resolver = MagicMock()
        lighting_resolver.resolve.return_value = lighting

        return ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=None,
            spot_graph_repository=spot_repo,
            effective_lighting_resolver=lighting_resolver,
        )

    @pytest.mark.parametrize(
        ("lighting", "reveals_killer"),
        (
            (LightingEnum.BRIGHT, True),
            (LightingEnum.DIM, True),
            (LightingEnum.DARK, False),
            (LightingEnum.PITCH_BLACK, False),
            (None, False),
        ),
    )
    def test_third_party_identity_follows_effective_lighting(
        self, lighting, reveals_killer
    ):
        """同室でも身元を出すのは BRIGHT / DIM だけで、不明を含む残りは伏せる。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=SpotId(5),
            killer_spot=SpotId(5),
            victim_spot=SpotId(5),
            lighting=lighting,
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),
        )

        out = formatter.format(event, PlayerId(100))

        assert out is not None
        assert out.structured["killer_visible_to_recipient"] is reveals_killer
        assert ("Alice" in out.prose) is reveals_killer
        if reveals_killer:
            assert out.structured["killer_player_id"] == 2
        else:
            assert "killer_player_id" not in out.structured

    def test_lighting_resolution_failure_hides_the_killer(self):
        """実効照明の解決に失敗しても、例外を漏らさず加害者の身元を伏せる。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=SpotId(5), killer_spot=SpotId(5), victim_spot=SpotId(5)
        )
        ctx.effective_lighting_resolver.resolve.side_effect = RuntimeError("broken")
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),
        )

        out = formatter.format(event, PlayerId(100))

        assert out is not None
        assert out.prose == "Victorが倒れて動かなくなった。"
        assert out.structured["killer_visible_to_recipient"] is False
        assert "killer_player_id" not in out.structured

    def test_missing_lighting_resolver_hides_the_killer(self):
        """実効照明 resolver が未注入でも、同室の加害者の身元を伏せる。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=SpotId(5), killer_spot=SpotId(5), victim_spot=SpotId(5)
        )
        ctx = replace(ctx, effective_lighting_resolver=None)
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),
        )

        out = formatter.format(event, PlayerId(100))

        assert out is not None
        assert out.prose == "Victorが倒れて動かなくなった。"
        assert out.structured["killer_visible_to_recipient"] is False
        assert "killer_player_id" not in out.structured

    def test_third_party_same_spot_as_killer_includes_killer_name(self):
        """observer が killer と同 spot なら、加害者を主語にした能動態で伝える。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=SpotId(5), killer_spot=SpotId(5), victim_spot=SpotId(5)
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),  # victim
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),  # killer
        )
        out = formatter.format(event, PlayerId(100))  # third-party observer
        assert out is not None
        assert out.prose == "AliceがVictorを倒した。"
        assert out.structured["killer_visible_to_recipient"] is True
        assert out.schedules_turn is True

    def test_third_party_different_spot_from_killer_hides_killer_name(self):
        """observer が killer と別 spot なら killer 名は prose に出ない。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=SpotId(5), killer_spot=SpotId(99), victim_spot=SpotId(5)
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),
        )
        out = formatter.format(event, PlayerId(100))
        assert out is not None
        # victim の事実 prose は戦闘に限定しない。
        assert out.prose == "Victorが倒れて動かなくなった。"
        assert "戦闘不能" not in out.prose
        # killer 名は秘匿
        assert "Alice" not in out.prose
        assert out.structured["killer_visible_to_recipient"] is False
        assert "killer_player_id" not in out.structured
        assert out.schedules_turn is True

    def test_third_party_position_unknown_hides_killer_name(self):
        """位置不明 (graph 未注入 等) は安全側に倒し、詳細でなく気配文にする。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=None, killer_spot=None
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),
        )
        out = formatter.format(event, PlayerId(100))
        assert out is not None
        assert "遠くで誰かが倒れた気配" in out.prose
        assert "Alice" not in out.prose
        assert out.structured["killer_visible_to_recipient"] is False
        assert "killer_player_id" not in out.structured
        assert out.schedules_turn is True

    def test_remote_player_downed_uses_distant_prose_without_actor_name(self):
        """別 spot の down 観測は詳細目撃でなく、名前を伏せた遠隔の気配文になる。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=SpotId(9), killer_spot=None, victim_spot=SpotId(5)
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=None,
        )

        out = formatter.format(event, PlayerId(100))

        assert out is not None
        assert "遠くで誰かが倒れた気配" in out.prose
        assert "Victor" not in out.prose
        assert out.schedules_turn is True
        assert out.breaks_movement is False
        assert out.structured["proximity"] == "remote_or_unknown"

    def test_third_party_killer_still_outputs_victim_prose(self):
        """killer 不明 (event.killer_player_id=None) は victim 名のみで prose 出す。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=SpotId(5), killer_spot=SpotId(5), victim_spot=SpotId(5)
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            # killer_player_id 未指定
        )
        out = formatter.format(event, PlayerId(100))
        assert out is not None
        assert out.prose == "Victorが倒れて動かなくなった。"
        assert "戦闘不能" not in out.prose
        assert out.structured["killer_visible_to_recipient"] is False

    def test_death_without_a_declared_witness_message_keeps_engine_prose(self):
        """宣言文を伴わない死では、同室の第三者へ engine の説明を残す。"""
        ctx = self._make_ctx_with_positions(
            recipient_spot=SpotId(5), killer_spot=SpotId(5), victim_spot=SpotId(5)
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=PlayerId(2),
        )

        out = formatter.format(event, PlayerId(100))

        assert out is not None
        assert out.prose == "AliceがVictorを倒した。"
        assert out.structured["type"] == "player_downed"


class TestPlayerObservationFormatterPlayerRevived:
    """PlayerRevivedEvent のフォーマットテスト"""

    def test_self_returns_revived_prose(self):
        """本人向けは「復帰しました。」"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerRevivedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            hp_recovered=50,
            total_hp=100,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "復帰" in out.prose
        assert out.structured.get("type") == "player_revived"

    def test_other_same_spot_returns_actor_revived_prose_and_schedules_turn(self):
        """同 spot の他者復帰は actor 名付きで届き、反応のため起床する。"""
        ctx = TestPlayerObservationFormatterPlayerDownedKillerVisibility()._make_ctx_with_positions(
            recipient_spot=SpotId(5), killer_spot=None, victim_spot=SpotId(5)
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerRevivedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            hp_recovered=50,
            total_hp=100,
        )

        out = formatter.format(event, PlayerId(100))

        assert out is not None
        assert "Victorが復帰しました" in out.prose
        assert out.schedules_turn is True
        assert out.structured["proximity"] == "same_spot"

    def test_other_remote_revived_uses_distant_prose_and_schedules_turn(self):
        """別 spot の復帰観測は名前を伏せた遠隔の気配文で届き、反応のため起床する。"""
        ctx = TestPlayerObservationFormatterPlayerDownedKillerVisibility()._make_ctx_with_positions(
            recipient_spot=SpotId(9), killer_spot=None, victim_spot=SpotId(5)
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerRevivedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            hp_recovered=50,
            total_hp=100,
        )

        out = formatter.format(event, PlayerId(100))

        assert out is not None
        assert "遠くで誰かが動けるようになった気配" in out.prose
        assert "Victor" not in out.prose
        assert out.schedules_turn is True
        assert out.structured["proximity"] == "remote_or_unknown"

    def test_other_unknown_position_revived_uses_distant_prose(self):
        """位置不明の復帰観測も、名前を断定せず遠隔の気配文に倒す。"""
        ctx = TestPlayerObservationFormatterPlayerDownedKillerVisibility()._make_ctx_with_positions(
            recipient_spot=None, killer_spot=None, victim_spot=None
        )
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerRevivedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            hp_recovered=50,
            total_hp=100,
        )

        out = formatter.format(event, PlayerId(100))

        assert out is not None
        assert "遠くで誰かが動けるようになった気配" in out.prose
        assert "Victor" not in out.prose
        assert out.schedules_turn is True
        assert out.structured["proximity"] == "remote_or_unknown"


class TestPlayerObservationFormatterPlayerLevelUp:
    """PlayerLevelUpEvent のフォーマットテスト"""

    def test_includes_old_and_new_level(self):
        """old_level と new_level を prose に含む。"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "レベル" in out.prose
        assert "1" in out.prose
        assert "2" in out.prose
        assert out.schedules_turn is True


class TestPlayerObservationFormatterItemAddedToInventory:
    """ItemAddedToInventoryEvent のフォーマットテスト"""

    def test_uses_item_repository_for_quantity(self):
        """item_repository で数量を解決。"""
        item_repo = MagicMock()
        agg = MagicMock()
        agg.item_spec.name = "銅の剣"
        agg.item_spec.item_spec_id.value = 501
        agg.quantity = 3
        item_repo.find_by_id.return_value = agg
        ctx = _make_context(item_repository=item_repo)
        formatter = PlayerObservationFormatter(ctx)
        event = ItemAddedToInventoryEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId.create(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "銅の剣" in out.prose
        assert "3個" in out.prose
        assert out.structured.get("item_spec_id_value") == 501

    def test_event_item_spec_id_value_takes_precedence_over_repository(self):
        """イベントの item_spec_id_value があればリポジトリの spec より優先する。"""
        item_repo = MagicMock()
        agg = MagicMock()
        agg.item_spec.name = "銅の剣"
        agg.item_spec.item_spec_id.value = 501
        agg.quantity = 1
        item_repo.find_by_id.return_value = agg
        ctx = _make_context(item_repository=item_repo)
        formatter = PlayerObservationFormatter(ctx)
        event = ItemAddedToInventoryEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId.create(1),
            item_spec_id_value=888,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert out.structured.get("item_spec_id_value") == 888

    def test_fallback_when_repository_None(self):
        """item_repository なしのとき「何かのアイテムを入手」"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        event = ItemAddedToInventoryEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerInventoryAggregate",
            item_instance_id=ItemInstanceId.create(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "何かのアイテム" in out.prose
        assert "入手" in out.prose


class TestPlayerObservationFormatterPlayerSpoke:
    """PlayerSpokeEvent のフォーマットテスト"""

    def test_uses_say_channel(self):
        """SAY チャンネルは「言った」"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Bob"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(player_profile_repository=profile_repo)
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(2),
            aggregate_type="PlayerStatusAggregate",
            content="こんにちは",
            channel=SpeechChannel.SAY,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Bob" in out.prose
        assert "言った" in out.prose
        assert "こんにちは" in out.prose
        assert out.structured.get("type") == "player_spoke"


class TestPlayerObservationFormatterPlayerSpokeSelfSuppression:
    """Issue #188: 話者本人への speech observation は suppress する。

    第 5 回 LLM 実験で「自分が言った内容を三人称 prose で受け取り、自己同
    一性を見失う」現象 (Bさん 自己三人称ループ) が観測された。formatter が
    本人へは ``None`` を返すことで回避する。
    """

    def _make_speaker_ctx(self, speaker_name: str = "探索者B"):
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = speaker_name
        profile_repo.find_by_id.return_value = profile
        return _make_context(player_profile_repository=profile_repo)

    def test_self_say_returns_None(self):
        """SAY を自分自身に対しては formatter が None を返す。"""
        ctx = self._make_speaker_ctx()
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(2),
            aggregate_type="PlayerStatusAggregate",
            content="私は廊下で待機する",
            channel=SpeechChannel.SAY,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
        )
        out = formatter.format(event, PlayerId(2))  # 話者本人
        assert out is None

    def test_self_shout_returns_None(self):
        """SHOUT も同様に話者本人には届けない。"""
        ctx = self._make_speaker_ctx()
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(2),
            aggregate_type="PlayerStatusAggregate",
            content="助けて！",
            channel=SpeechChannel.SHOUT,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
        )
        out = formatter.format(event, PlayerId(2))
        assert out is None

    def test_self_whisper_returns_None(self):
        """WHISPER も話者本人には届けない (action_result_store で十分)。"""
        ctx = self._make_speaker_ctx()
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(2),
            aggregate_type="PlayerStatusAggregate",
            content="内緒だよ",
            channel=SpeechChannel.WHISPER,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=PlayerId(3),
        )
        out = formatter.format(event, PlayerId(2))
        assert out is None

    def test_other_recipient_still_receives_prose(self):
        """他者 (話者ではない recipient) には引き続き prose が届く。"""
        ctx = self._make_speaker_ctx("Bob")
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(2),
            aggregate_type="PlayerStatusAggregate",
            content="こんにちは",
            channel=SpeechChannel.SAY,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
        )
        out = formatter.format(event, PlayerId(1))  # 別人 recipient
        assert out is not None
        assert "Bob" in out.prose
        assert "こんにちは" in out.prose
        assert out.observation_category == "social"
        assert out.structured.get("role") == "other"


class TestPlayerObservationFormatterUnknownEvent:
    """対象外イベントのテスト"""

    @pytest.fixture
    def formatter(self):
        return PlayerObservationFormatter(_make_context())

    def test_returns_None_for_skill_event(self, formatter):
        """Skill イベントは None。"""
        event = SkillEquippedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=SkillId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestPlayerObservationFormatterRecipientIndependence:
    """recipient_player_id への依存テスト"""

    def test_level_up_does_depend_on_recipient(self):
        """PlayerLevelUp は recipient に依存しない（出力は常に本人向け）。"""
        ctx = _make_context()
        formatter = PlayerObservationFormatter(ctx)
        event = PlayerLevelUpEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_level=1,
            new_level=2,
            stat_growth=BaseStats(0, 0, 0, 0, 0, 0.0, 0.0),
        )
        out1 = formatter.format(event, PlayerId(1))
        out2 = formatter.format(event, PlayerId(999))
        assert out1 is not None
        assert out2 is not None
        assert out1.prose == out2.prose
        assert out1.structured == out2.structured
