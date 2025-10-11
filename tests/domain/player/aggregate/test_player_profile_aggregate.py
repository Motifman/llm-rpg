import pytest
from src.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from src.domain.player.value_object.player_id import PlayerId
from src.domain.player.value_object.player_name import PlayerName
from src.domain.player.enum.player_enum import Role
from src.domain.battle.battle_enum import Race, Element
from src.domain.player.event.profile_events import PlayerProfileChangedEvent


# テスト用のプロフィール作成ヘルパー関数
def create_test_profile(
    player_id: int = 1,
    name: str = "TestPlayer",
    role: Role = Role.CITIZEN,
    race: Race = Race.HUMAN,
    element: Element = Element.NEUTRAL
) -> PlayerProfileAggregate:
    """テスト用のPlayerProfileAggregateを作成"""
    return PlayerProfileAggregate(
        player_id=PlayerId(player_id),
        name=PlayerName(name),
        role=role,
        race=race,
        element=element
    )


class TestPlayerProfileAggregate:
    """PlayerProfileAggregateのテスト"""

    def test_create_profile(self):
        """プロフィールが正しく作成されること"""
        profile = create_test_profile()

        assert profile.player_id.value == 1
        assert profile.name.value == "TestPlayer"
        assert profile.role == Role.CITIZEN
        assert profile.race == Race.HUMAN
        assert profile.element == Element.NEUTRAL

    def test_change_name(self):
        """名前が正しく変更されること"""
        profile = create_test_profile(name="OldName")
        new_name = PlayerName("NewName")

        profile.change_name(new_name)

        assert profile.name == new_name

    def test_change_name_no_change(self):
        """同じ名前の場合は変更されないこと"""
        profile = create_test_profile(name="SameName")
        same_name = PlayerName("SameName")

        profile.change_name(same_name)

        assert profile.name.value == "SameName"
        # イベントは発行されないはず
        events = profile.get_events()
        assert len(events) == 0

    def test_change_name_emits_event(self):
        """名前変更時にイベントが発行されること"""
        profile = create_test_profile(name="OldName")
        new_name = PlayerName("NewName")

        profile.change_name(new_name)

        events = profile.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, PlayerProfileChangedEvent)
        assert event.old_name.value == "OldName"
        assert event.new_name.value == "NewName"
        assert event.old_role is None
        assert event.new_role is None
        assert event.aggregate_id.value == 1

    def test_change_role(self):
        """ロールが正しく変更されること"""
        profile = create_test_profile(role=Role.CITIZEN)

        profile.change_role(Role.ADVENTURER)

        assert profile.role == Role.ADVENTURER

    def test_change_role_no_change(self):
        """同じロールの場合は変更されないこと"""
        profile = create_test_profile(role=Role.CITIZEN)

        profile.change_role(Role.CITIZEN)

        assert profile.role == Role.CITIZEN
        # イベントは発行されないはず
        events = profile.get_events()
        assert len(events) == 0

    def test_change_role_emits_event(self):
        """ロール変更時にイベントが発行されること"""
        profile = create_test_profile(role=Role.CITIZEN)

        profile.change_role(Role.ADVENTURER)

        events = profile.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, PlayerProfileChangedEvent)
        assert event.old_role == Role.CITIZEN
        assert event.new_role == Role.ADVENTURER
        assert event.old_name is None
        assert event.new_name is None

    def test_change_race(self):
        """種族が正しく変更されること"""
        profile = create_test_profile(race=Race.HUMAN)

        profile.change_race(Race.GOBLIN)

        assert profile.race == Race.GOBLIN

    def test_change_race_no_change(self):
        """同じ種族の場合は変更されないこと"""
        profile = create_test_profile(race=Race.HUMAN)

        profile.change_race(Race.HUMAN)

        assert profile.race == Race.HUMAN
        events = profile.get_events()
        assert len(events) == 0

    def test_change_race_emits_event(self):
        """種族変更時にイベントが発行されること"""
        profile = create_test_profile(race=Race.HUMAN)

        profile.change_race(Race.GOBLIN)

        events = profile.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, PlayerProfileChangedEvent)
        assert event.old_race == Race.HUMAN
        assert event.new_race == Race.GOBLIN

    def test_change_element(self):
        """属性が正しく変更されること"""
        profile = create_test_profile(element=Element.NEUTRAL)

        profile.change_element(Element.FIRE)

        assert profile.element == Element.FIRE

    def test_change_element_no_change(self):
        """同じ属性の場合は変更されないこと"""
        profile = create_test_profile(element=Element.NEUTRAL)

        profile.change_element(Element.NEUTRAL)

        assert profile.element == Element.NEUTRAL
        events = profile.get_events()
        assert len(events) == 0

    def test_change_element_emits_event(self):
        """属性変更時にイベントが発行されること"""
        profile = create_test_profile(element=Element.NEUTRAL)

        profile.change_element(Element.FIRE)

        events = profile.get_events()
        assert len(events) == 1

        event = events[0]
        assert isinstance(event, PlayerProfileChangedEvent)
        assert event.old_element == Element.NEUTRAL
        assert event.new_element == Element.FIRE

    def test_update_profile_single_field(self):
        """単一フィールドの更新が正しく動作すること"""
        profile = create_test_profile(name="OldName")

        profile.update_profile(name=PlayerName("NewName"))

        assert profile.name.value == "NewName"
        assert profile.role == Role.CITIZEN  # 変更なし

        events = profile.get_events()
        assert len(events) == 1

    def test_update_profile_multiple_fields(self):
        """複数フィールドの一括更新が正しく動作すること"""
        profile = create_test_profile(
            name="OldName",
            role=Role.CITIZEN,
            race=Race.HUMAN,
            element=Element.NEUTRAL
        )

        profile.update_profile(
            name=PlayerName("NewName"),
            role=Role.ADVENTURER,
            race=Race.GOBLIN,
            element=Element.FIRE
        )

        assert profile.name.value == "NewName"
        assert profile.role == Role.ADVENTURER
        assert profile.race == Race.GOBLIN
        assert profile.element == Element.FIRE

        events = profile.get_events()
        assert len(events) == 1

        event = events[0]
        assert event.old_name.value == "OldName"
        assert event.new_name.value == "NewName"
        assert event.old_role == Role.CITIZEN
        assert event.new_role == Role.ADVENTURER
        assert event.old_race == Race.HUMAN
        assert event.new_race == Race.GOBLIN
        assert event.old_element == Element.NEUTRAL
        assert event.new_element == Element.FIRE

    def test_update_profile_no_changes(self):
        """変更がない場合はイベントが発行されないこと"""
        profile = create_test_profile()

        profile.update_profile(
            name=PlayerName("TestPlayer"),  # 同じ値
            role=Role.CITIZEN,  # 同じ値
            race=Race.HUMAN,  # 同じ値
            element=Element.NEUTRAL  # 同じ値
        )

        events = profile.get_events()
        assert len(events) == 0

    def test_update_profile_partial_changes(self):
        """一部フィールドのみ変更した場合のイベント発行"""
        profile = create_test_profile(
            name="OldName",
            role=Role.CITIZEN
        )

        profile.update_profile(
            name=PlayerName("NewName"),
            # roleは変更なし
            race=Race.GOBLIN  # raceのみ変更
        )

        events = profile.get_events()
        assert len(events) == 1

        event = events[0]
        assert event.old_name.value == "OldName"
        assert event.new_name.value == "NewName"
        assert event.old_race == Race.HUMAN
        assert event.new_race == Race.GOBLIN
        assert event.old_role is None  # roleは変更なし
        assert event.new_role is None


    def test_can_change_name_true(self):
        """名前変更可能チェックが正しく動作すること（変更可能）"""
        profile = create_test_profile(name="OldName")

        assert profile.can_change_name(PlayerName("NewName")) == True

    def test_can_change_name_false(self):
        """名前変更可能チェックが正しく動作すること（変更不可）"""
        profile = create_test_profile(name="SameName")

        assert profile.can_change_name(PlayerName("SameName")) == False

    def test_is_role_true(self):
        """ロール一致チェックが正しく動作すること（一致）"""
        profile = create_test_profile(role=Role.CITIZEN)

        assert profile.is_role(Role.CITIZEN) == True

    def test_is_role_false(self):
        """ロール一致チェックが正しく動作すること（不一致）"""
        profile = create_test_profile(role=Role.CITIZEN)

        assert profile.is_role(Role.ADVENTURER) == False

    def test_is_race_true(self):
        """種族一致チェックが正しく動作すること（一致）"""
        profile = create_test_profile(race=Race.HUMAN)

        assert profile.is_race(Race.HUMAN) == True

    def test_is_race_false(self):
        """種族一致チェックが正しく動作すること（不一致）"""
        profile = create_test_profile(race=Race.HUMAN)

        assert profile.is_race(Race.GOBLIN) == False

    def test_is_element_true(self):
        """属性一致チェックが正しく動作すること（一致）"""
        profile = create_test_profile(element=Element.NEUTRAL)

        assert profile.is_element(Element.NEUTRAL) == True

    def test_is_element_false(self):
        """属性一致チェックが正しく動作すること（不一致）"""
        profile = create_test_profile(element=Element.NEUTRAL)

        assert profile.is_element(Element.FIRE) == False

    def test_events_are_cleared_after_getting(self):
        """イベントを取得した後にクリアできること"""
        profile = create_test_profile()

        profile.change_name(PlayerName("NewName"))

        # イベントを取得
        events = profile.get_events()
        assert len(events) == 1

        # イベントをクリア
        profile.clear_events()

        # 再度取得すると空になる
        events_after = profile.get_events()
        assert len(events_after) == 0
