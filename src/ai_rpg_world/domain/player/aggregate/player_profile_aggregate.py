from typing import Optional

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.enum.player_enum import Role
from ai_rpg_world.domain.battle.battle_enum import Race, Element
from ai_rpg_world.domain.player.event.profile_events import PlayerProfileChangedEvent


class PlayerProfileAggregate(AggregateRoot):
    """プレイヤープロフィール集約"""

    def __init__(
        self,
        player_id: PlayerId,
        name: PlayerName,
        role: Role,
        race: Race = Race.HUMAN,
        element: Element = Element.NEUTRAL,
    ):
        super().__init__()
        self._player_id = player_id
        self._name = name
        self._role = role
        self._race = race
        self._element = element

    @classmethod
    def create(
        cls,
        player_id: PlayerId,
        name: PlayerName,
        role: Role = Role.CITIZEN,
        race: Race = Race.HUMAN,
        element: Element = Element.NEUTRAL,
    ) -> "PlayerProfileAggregate":
        """新しいプロフィール集約を作成"""
        return cls(player_id, name, role, race, element)

    @property
    def player_id(self) -> PlayerId:
        """プレイヤーID"""
        return self._player_id

    @property
    def name(self) -> PlayerName:
        """プレイヤー名"""
        return self._name

    @property
    def role(self) -> Role:
        """ロール"""
        return self._role

    @property
    def race(self) -> Race:
        """種族"""
        return self._race

    @property
    def element(self) -> Element:
        """属性"""
        return self._element

    def change_name(self, new_name: PlayerName) -> None:
        """名前を変更する"""
        if self._name == new_name:
            return  # 変更なし

        old_name = self._name
        self._name = new_name

        self.add_event(PlayerProfileChangedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerProfileAggregate",
            old_name=old_name,
            new_name=new_name,
            old_role=None,
            new_role=None,
            old_race=None,
            new_race=None,
            old_element=None,
            new_element=None
        ))

    def change_role(self, new_role: Role) -> None:
        """ロールを変更する"""
        if self._role == new_role:
            return  # 変更なし

        old_role = self._role
        self._role = new_role

        self.add_event(PlayerProfileChangedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerProfileAggregate",
            old_name=None,
            new_name=None,
            old_role=old_role,
            new_role=new_role,
            old_race=None,
            new_race=None,
            old_element=None,
            new_element=None
        ))

    def change_race(self, new_race: Race) -> None:
        """種族を変更する"""
        if self._race == new_race:
            return  # 変更なし

        old_race = self._race
        self._race = new_race

        self.add_event(PlayerProfileChangedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerProfileAggregate",
            old_name=None,
            new_name=None,
            old_role=None,
            new_role=None,
            old_race=old_race,
            new_race=new_race,
            old_element=None,
            new_element=None
        ))

    def change_element(self, new_element: Element) -> None:
        """属性を変更する"""
        if self._element == new_element:
            return  # 変更なし

        old_element = self._element
        self._element = new_element

        self.add_event(PlayerProfileChangedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerProfileAggregate",
            old_name=None,
            new_name=None,
            old_role=None,
            new_role=None,
            old_race=None,
            new_race=None,
            old_element=old_element,
            new_element=new_element
        ))

    def update_profile(
        self,
        name: Optional[PlayerName] = None,
        role: Optional[Role] = None,
        race: Optional[Race] = None,
        element: Optional[Element] = None
    ) -> None:
        """プロフィールを一括更新する"""
        old_name = self._name if name is not None and self._name != name else None
        old_role = self._role if role is not None and self._role != role else None
        old_race = self._race if race is not None and self._race != race else None
        old_element = self._element if element is not None and self._element != element else None

        # 変更がある場合のみ更新
        has_changes = any([old_name is not None, old_role is not None, old_race is not None, old_element is not None])

        if not has_changes:
            return  # 変更なし

        # 更新
        if name is not None:
            self._name = name
        if role is not None:
            self._role = role
        if race is not None:
            self._race = race
        if element is not None:
            self._element = element

        self.add_event(PlayerProfileChangedEvent.create(
            aggregate_id=self._player_id,
            aggregate_type="PlayerProfileAggregate",
            old_name=old_name,
            new_name=name if old_name is not None else None,
            old_role=old_role,
            new_role=role if old_role is not None else None,
            old_race=old_race,
            new_race=race if old_race is not None else None,
            old_element=old_element,
            new_element=element if old_element is not None else None
        ))


    def can_change_name(self, new_name: PlayerName) -> bool:
        """名前変更可能かどうかをチェック"""
        return self._name != new_name

    def is_role(self, role: Role) -> bool:
        """指定したロールかどうかをチェック"""
        return self._role == role

    def is_race(self, race: Race) -> bool:
        """指定した種族かどうかをチェック"""
        return self._race == race

    def is_element(self, element: Element) -> bool:
        """指定した属性かどうかをチェック"""
        return self._element == element
