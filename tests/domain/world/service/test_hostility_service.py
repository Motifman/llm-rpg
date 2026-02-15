"""HostilityService（Disposition・関係タイプ）のテスト"""

import pytest
from ai_rpg_world.domain.world.service.hostility_service import ConfigurableHostilityService
from ai_rpg_world.domain.world.enum.world_enum import Disposition
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent, ActorComponent
from ai_rpg_world.domain.world.exception.behavior_exception import (
    ComponentRequiredForDispositionException,
)


def _comp(race: str = "monster", faction: str = "enemy") -> AutonomousBehaviorComponent:
    return AutonomousBehaviorComponent(race=race, faction=faction)


class TestConfigurableHostilityServiceGetDisposition:
    """get_disposition の正常・境界・例外ケース"""

    def test_neutral_when_no_table(self):
        """テーブルが空のとき NEUTRAL を返すこと"""
        service = ConfigurableHostilityService()
        actor = _comp("goblin", "enemy")
        target = _comp("human", "player")
        assert service.get_disposition(actor, target) == Disposition.NEUTRAL

    def test_race_disposition_table_hostile(self):
        """race_disposition_table で HOSTILE が返ること"""
        service = ConfigurableHostilityService(
            race_disposition_table={
                "goblin": {"human": Disposition.HOSTILE},
            }
        )
        actor = _comp("goblin", "enemy")
        target = _comp("human", "player")
        assert service.get_disposition(actor, target) == Disposition.HOSTILE

    def test_race_disposition_table_prey(self):
        """race_disposition_table で PREY が返ること"""
        service = ConfigurableHostilityService(
            race_disposition_table={
                "wolf": {"rabbit": Disposition.PREY},
            }
        )
        actor = _comp("wolf", "beast")
        target = _comp("rabbit", "beast")
        assert service.get_disposition(actor, target) == Disposition.PREY

    def test_race_disposition_table_threat(self):
        """race_disposition_table で THREAT が返ること"""
        service = ConfigurableHostilityService(
            race_disposition_table={
                "goblin": {"dragon": Disposition.THREAT},
            }
        )
        actor = _comp("goblin", "enemy")
        target = _comp("dragon", "boss")
        assert service.get_disposition(actor, target) == Disposition.THREAT

    def test_race_disposition_table_ally(self):
        """race_disposition_table で ALLY が返ること"""
        service = ConfigurableHostilityService(
            race_disposition_table={
                "human": {"elf": Disposition.ALLY},
            }
        )
        actor = _comp("human", "player")
        target = _comp("elf", "player")
        assert service.get_disposition(actor, target) == Disposition.ALLY

    def test_race_disposition_table_actor_race_not_in_table(self):
        """actor_race がテーブルに無いとき NEUTRAL"""
        service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"human": Disposition.HOSTILE}},
        )
        actor = _comp("orc", "enemy")
        target = _comp("human", "player")
        assert service.get_disposition(actor, target) == Disposition.NEUTRAL

    def test_race_disposition_table_target_race_not_in_table(self):
        """target_race が actor のテーブルに無いとき NEUTRAL"""
        service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"human": Disposition.HOSTILE}},
        )
        actor = _comp("goblin", "enemy")
        target = _comp("elf", "player")
        assert service.get_disposition(actor, target) == Disposition.NEUTRAL

    def test_faction_hostility_takes_precedence(self):
        """勢力テーブルが種族より優先され HOSTILE になること"""
        service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"human": Disposition.NEUTRAL}},
            faction_hostility_table={"enemy": {"player"}},
        )
        actor = _comp("goblin", "enemy")
        target = _comp("human", "player")
        assert service.get_disposition(actor, target) == Disposition.HOSTILE

    def test_race_hostility_table_legacy_returns_hostile(self):
        """後方互換の race_hostility_table で HOSTILE が返ること"""
        service = ConfigurableHostilityService(
            race_hostility_table={"goblin": {"human", "elf"}},
        )
        actor = _comp("goblin", "enemy")
        target_human = _comp("human", "player")
        target_elf = _comp("elf", "player")
        assert service.get_disposition(actor, target_human) == Disposition.HOSTILE
        assert service.get_disposition(actor, target_elf) == Disposition.HOSTILE

    def test_race_disposition_overrides_race_hostility_legacy(self):
        """race_disposition_table が race_hostility_table より優先されること"""
        service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"human": Disposition.THREAT}},
            race_hostility_table={"goblin": {"human"}},
        )
        actor = _comp("goblin", "enemy")
        target = _comp("human", "player")
        assert service.get_disposition(actor, target) == Disposition.THREAT


class TestConfigurableHostilityServiceIsHostile:
    """is_hostile の正常・境界ケース"""

    def test_hostile_true_for_hostile(self):
        """HOSTILE のとき True"""
        service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"human": Disposition.HOSTILE}},
        )
        actor = _comp("goblin")
        target = _comp("human")
        assert service.is_hostile(actor, target) is True

    def test_hostile_true_for_prey(self):
        """PREY のとき True（敵対の一種）"""
        service = ConfigurableHostilityService(
            race_disposition_table={"wolf": {"rabbit": Disposition.PREY}},
        )
        actor = _comp("wolf")
        target = _comp("rabbit")
        assert service.is_hostile(actor, target) is True

    def test_hostile_false_for_threat(self):
        """THREAT のとき False（攻撃対象にしない）"""
        service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"dragon": Disposition.THREAT}},
        )
        actor = _comp("goblin")
        target = _comp("dragon")
        assert service.is_hostile(actor, target) is False

    def test_hostile_false_for_neutral(self):
        """NEUTRAL のとき False"""
        service = ConfigurableHostilityService()
        actor = _comp("goblin")
        target = _comp("human")
        assert service.is_hostile(actor, target) is False

    def test_hostile_false_for_ally(self):
        """ALLY のとき False（攻撃対象にしない）"""
        service = ConfigurableHostilityService(
            race_disposition_table={"human": {"elf": Disposition.ALLY}},
        )
        actor = _comp("human")
        target = _comp("elf")
        assert service.is_hostile(actor, target) is False


class TestConfigurableHostilityServiceIsThreat:
    """is_threat の正常・境界ケース"""

    def test_threat_true_for_threat(self):
        """THREAT のとき True"""
        service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"dragon": Disposition.THREAT}},
        )
        actor = _comp("goblin")
        target = _comp("dragon")
        assert service.is_threat(actor, target) is True

    def test_threat_false_for_hostile(self):
        """HOSTILE のとき False"""
        service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"human": Disposition.HOSTILE}},
        )
        actor = _comp("goblin")
        target = _comp("human")
        assert service.is_threat(actor, target) is False

    def test_threat_false_for_prey(self):
        """PREY のとき False"""
        service = ConfigurableHostilityService(
            race_disposition_table={"wolf": {"rabbit": Disposition.PREY}},
        )
        actor = _comp("wolf")
        target = _comp("rabbit")
        assert service.is_threat(actor, target) is False

    def test_threat_false_for_neutral(self):
        """NEUTRAL のとき False"""
        service = ConfigurableHostilityService()
        actor = _comp("goblin")
        target = _comp("human")
        assert service.is_threat(actor, target) is False

    def test_threat_false_for_ally(self):
        """ALLY のとき False"""
        service = ConfigurableHostilityService(
            race_disposition_table={"human": {"elf": Disposition.ALLY}},
        )
        actor = _comp("human")
        target = _comp("elf")
        assert service.is_threat(actor, target) is False


class TestConfigurableHostilityServiceIsPrey:
    """is_prey の正常・境界ケース"""

    def test_prey_true_for_prey(self):
        """PREY のとき True"""
        service = ConfigurableHostilityService(
            race_disposition_table={"wolf": {"rabbit": Disposition.PREY}},
        )
        actor = _comp("wolf")
        target = _comp("rabbit")
        assert service.is_prey(actor, target) is True

    def test_prey_false_for_hostile(self):
        """HOSTILE のとき False"""
        service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"human": Disposition.HOSTILE}},
        )
        actor = _comp("goblin")
        target = _comp("human")
        assert service.is_prey(actor, target) is False

    def test_prey_false_for_threat(self):
        """THREAT のとき False"""
        service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"dragon": Disposition.THREAT}},
        )
        actor = _comp("goblin")
        target = _comp("dragon")
        assert service.is_prey(actor, target) is False

    def test_prey_false_for_neutral(self):
        """NEUTRAL のとき False"""
        service = ConfigurableHostilityService()
        actor = _comp("wolf")
        target = _comp("rabbit")
        assert service.is_prey(actor, target) is False

    def test_prey_false_for_ally(self):
        """ALLY のとき False"""
        service = ConfigurableHostilityService(
            race_disposition_table={"human": {"elf": Disposition.ALLY}},
        )
        actor = _comp("human")
        target = _comp("elf")
        assert service.is_prey(actor, target) is False


class TestConfigurableHostilityServiceComponentRequired:
    """不正入力（component が None）の例外ケース"""

    def test_get_disposition_actor_comp_none_raises_exception(self):
        """get_disposition で actor_comp が None のとき ComponentRequiredForDispositionException"""
        service = ConfigurableHostilityService()
        target = _comp("human", "player")
        with pytest.raises(ComponentRequiredForDispositionException) as exc_info:
            service.get_disposition(None, target)
        assert "actor_comp" in str(exc_info.value)
        assert "None" in str(exc_info.value)
        assert exc_info.value.error_code == "BEHAVIOR.COMPONENT_REQUIRED_FOR_DISPOSITION"

    def test_get_disposition_target_comp_none_raises_exception(self):
        """get_disposition で target_comp が None のとき ComponentRequiredForDispositionException"""
        service = ConfigurableHostilityService()
        actor = _comp("goblin", "enemy")
        with pytest.raises(ComponentRequiredForDispositionException) as exc_info:
            service.get_disposition(actor, None)
        assert "target_comp" in str(exc_info.value)
        assert "None" in str(exc_info.value)
        assert exc_info.value.error_code == "BEHAVIOR.COMPONENT_REQUIRED_FOR_DISPOSITION"

    def test_is_hostile_actor_comp_none_raises_exception(self):
        """is_hostile で actor_comp が None のとき ComponentRequiredForDispositionException"""
        service = ConfigurableHostilityService()
        target = _comp("human")
        with pytest.raises(ComponentRequiredForDispositionException) as exc_info:
            service.is_hostile(None, target)
        assert "actor_comp" in str(exc_info.value)

    def test_is_hostile_target_comp_none_raises_exception(self):
        """is_hostile で target_comp が None のとき ComponentRequiredForDispositionException"""
        service = ConfigurableHostilityService()
        actor = _comp("goblin")
        with pytest.raises(ComponentRequiredForDispositionException) as exc_info:
            service.is_hostile(actor, None)
        assert "target_comp" in str(exc_info.value)

    def test_is_threat_actor_comp_none_raises_exception(self):
        """is_threat で actor_comp が None のとき ComponentRequiredForDispositionException"""
        service = ConfigurableHostilityService()
        target = _comp("dragon")
        with pytest.raises(ComponentRequiredForDispositionException):
            service.is_threat(None, target)

    def test_is_threat_target_comp_none_raises_exception(self):
        """is_threat で target_comp が None のとき ComponentRequiredForDispositionException"""
        service = ConfigurableHostilityService()
        actor = _comp("goblin")
        with pytest.raises(ComponentRequiredForDispositionException):
            service.is_threat(actor, None)

    def test_is_prey_actor_comp_none_raises_exception(self):
        """is_prey で actor_comp が None のとき ComponentRequiredForDispositionException"""
        service = ConfigurableHostilityService()
        target = _comp("rabbit")
        with pytest.raises(ComponentRequiredForDispositionException):
            service.is_prey(None, target)

    def test_is_prey_target_comp_none_raises_exception(self):
        """is_prey で target_comp が None のとき ComponentRequiredForDispositionException"""
        service = ConfigurableHostilityService()
        actor = _comp("wolf")
        with pytest.raises(ComponentRequiredForDispositionException):
            service.is_prey(actor, None)
