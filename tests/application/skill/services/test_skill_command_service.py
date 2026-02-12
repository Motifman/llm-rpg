import pytest
from ai_rpg_world.application.skill.services.skill_command_service import SkillCommandService
from ai_rpg_world.application.skill.contracts.commands import (
    EquipPlayerSkillCommand,
    ActivatePlayerAwakenedModeCommand,
    UsePlayerSkillCommand,
    GrantSkillDeckExpCommand,
    AcceptSkillProposalCommand
)
from ai_rpg_world.application.skill.exceptions.command.skill_command_exception import SkillCommandException
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.aggregate.skill_deck_progress_aggregate import SkillDeckProgressAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillHitPatternType, SkillProposalType
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.player.enum.player_enum import Element
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.skill.value_object.skill_proposal import SkillProposal

class _FakeUow:
    def __init__(self):
        self.events = []
        self.committed = False

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def add_events(self, events): self.events.extend(events)
    def process_sync_events(self): pass

class _InMemoryRepo:
    def __init__(self): self.data = {}
    def find_by_id(self, id): return self.data.get(id)
    def save(self, entity): self.data[getattr(entity, list(entity.__dict__.keys())[0])] = entity

# 簡易的なリポジトリ実装
class _LoadoutRepo(_InMemoryRepo):
    def save(self, entity): self.data[entity.loadout_id] = entity
    def find_by_owner_id(self, owner_id: int):
        for loadout in self.data.values():
            if loadout.owner_id == owner_id: return loadout
        return None

class _SpecRepo(_InMemoryRepo):
    def save(self, entity): self.data[entity.skill_id] = entity

class _ProgressRepo(_InMemoryRepo):
    def save(self, entity): self.data[entity.progress_id] = entity
    def find_by_owner_id(self, owner_id: int):
        for progress in self.data.values():
            if progress.owner_id == owner_id: return progress
        return None

class _PlayerRepo(_InMemoryRepo):
    def save(self, entity): self.data[entity.player_id] = entity

def _sample_skill(skill_id: int, mp_cost=0) -> SkillSpec:
    return SkillSpec(
        skill_id=SkillId(skill_id),
        name=f"skill-{skill_id}",
        element=Element.NEUTRAL,
        deck_cost=1,
        cast_lock_ticks=1,
        cooldown_ticks=5,
        power_multiplier=1.2,
        hit_pattern=SkillHitPattern.single_pulse(SkillHitPatternType.MELEE, HitBoxShape.single_cell()),
        mp_cost=mp_cost
    )

def _sample_status(player_id: int) -> PlayerStatusAggregate:
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor.for_level(1),
        exp_table=ExpTable(100, 2.0),
        growth=Growth(1, 0, ExpTable(100, 2.0)),
        gold=Gold(0),
        hp=Hp.create(100, 100),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100)
    )

class TestSkillCommandService:
    @pytest.fixture
    def setup(self):
        loadout_repo = _LoadoutRepo()
        spec_repo = _SpecRepo()
        progress_repo = _ProgressRepo()
        player_repo = _PlayerRepo()
        uow = _FakeUow()
        service = SkillCommandService(loadout_repo, spec_repo, progress_repo, player_repo, uow)
        return service, loadout_repo, spec_repo, progress_repo, player_repo, uow

    class TestEquipPlayerSkill:
        def test_equip_success(self, setup):
            service, loadout_repo, spec_repo, _, _, _ = setup
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 100, 10, 10)
            skill = _sample_skill(1)
            loadout_repo.save(loadout)
            spec_repo.save(skill)

            service.equip_player_skill(EquipPlayerSkillCommand(100, 1, DeckTier.NORMAL, 0, 1))
            assert loadout_repo.find_by_id(SkillLoadoutId(1)).normal_deck.get_skill(0) == skill

        def test_equip_fails_when_owner_mismatch(self, setup):
            service, loadout_repo, spec_repo, _, _, _ = setup
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 100, 10, 10)
            loadout_repo.save(loadout)
            
            with pytest.raises(SkillCommandException, match="owner mismatch"):
                service.equip_player_skill(EquipPlayerSkillCommand(999, 1, DeckTier.NORMAL, 0, 1))

    class TestUsePlayerSkill:
        def test_use_skill_success_consumes_mp(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, _ = setup
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 100, 10, 10)
            skill = _sample_skill(1, mp_cost=10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)
            spec_repo.save(skill)
            player_repo.save(_sample_status(100))

            service.use_player_skill(UsePlayerSkillCommand(100, 1, 0, 10))
            
            status = player_repo.find_by_id(PlayerId(100))
            assert status.mp.value == 40
            assert loadout_repo.find_by_id(SkillLoadoutId(1)).can_use_skill(0, 10) is False

        def test_use_skill_fails_when_insufficient_mp(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, _ = setup
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 100, 10, 10)
            skill = _sample_skill(1, mp_cost=999)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)
            spec_repo.save(skill)
            player_repo.save(_sample_status(100))

            with pytest.raises(SkillCommandException, match="MPが不足しています"):
                service.use_player_skill(UsePlayerSkillCommand(100, 1, 0, 10))

        def test_use_skill_fails_when_insufficient_hp(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, _ = setup
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 100, 10, 10)
            # HPを100消費するスキル（現在HPは100）
            # consume_resources では hp_cost >= self._hp.value でエラーになる
            skill = SkillSpec(
                skill_id=SkillId(1),
                name="suicide-skill",
                element=Element.NEUTRAL,
                deck_cost=1,
                cast_lock_ticks=1,
                cooldown_ticks=5,
                power_multiplier=1.2,
                hit_pattern=SkillHitPattern.single_pulse(SkillHitPatternType.MELEE, HitBoxShape.single_cell()),
                hp_cost=100
            )
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)
            spec_repo.save(skill)
            player_repo.save(_sample_status(100))

            with pytest.raises(SkillCommandException, match="HPが不足しています"):
                service.use_player_skill(UsePlayerSkillCommand(100, 1, 0, 10))

    class TestAcceptSkillProposal:
        def test_accept_proposal_updates_loadout(self, setup):
            service, loadout_repo, spec_repo, progress_repo, _, _ = setup
            # owner_id = 100
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(100), 100, 10, 10)
            loadout_repo.save(loadout)
            
            progress = SkillDeckProgressAggregate(SkillDeckProgressId(1), 100)
            proposal = SkillProposal(1, SkillProposalType.ADD, SkillId(2), deck_tier=DeckTier.NORMAL, target_slot_index=0)
            progress.register_proposals([proposal])
            progress_repo.save(progress)
            
            skill = _sample_skill(2)
            spec_repo.save(skill)

            service.accept_skill_proposal(AcceptSkillProposalCommand(1, 1))
            
            assert loadout_repo.find_by_id(SkillLoadoutId(100)).normal_deck.get_skill(0) == skill
            assert len(progress_repo.find_by_id(SkillDeckProgressId(1)).pending_proposals) == 0

        def test_accept_proposal_for_awakened_deck(self, setup):
            service, loadout_repo, spec_repo, progress_repo, _, _ = setup
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(100), 100, 10, 10)
            loadout_repo.save(loadout)
            
            progress = SkillDeckProgressAggregate(SkillDeckProgressId(1), 100)
            # 覚醒デッキ向けの提案
            proposal = SkillProposal(1, SkillProposalType.ADD, SkillId(3), deck_tier=DeckTier.AWAKENED, target_slot_index=0)
            progress.register_proposals([proposal])
            progress_repo.save(progress)
            
            skill = _sample_skill(3)
            spec_repo.save(skill)

            service.accept_skill_proposal(AcceptSkillProposalCommand(1, 1))
            
            assert loadout_repo.find_by_id(SkillLoadoutId(100)).awakened_deck.get_skill(0) == skill

        def test_accept_proposal_fails_when_loadout_not_found(self, setup):
            service, loadout_repo, spec_repo, progress_repo, _, _ = setup
            # ロードアウトを保存しない
            
            progress = SkillDeckProgressAggregate(SkillDeckProgressId(1), 100)
            proposal = SkillProposal(1, SkillProposalType.ADD, SkillId(2), deck_tier=DeckTier.NORMAL, target_slot_index=0)
            progress.register_proposals([proposal])
            progress_repo.save(progress)
            
            spec_repo.save(_sample_skill(2))

            with pytest.raises(SkillCommandException, match="skill loadout not found for owner"):
                service.accept_skill_proposal(AcceptSkillProposalCommand(1, 1))

        def test_reject_proposal_clears_pending(self, setup):
            service, _, _, progress_repo, _, _ = setup
            progress = SkillDeckProgressAggregate(SkillDeckProgressId(1), 100)
            proposal = SkillProposal(1, SkillProposalType.ADD, SkillId(2), deck_tier=DeckTier.NORMAL, target_slot_index=0)
            progress.register_proposals([proposal])
            progress_repo.save(progress)

            from ai_rpg_world.application.skill.contracts.commands import RejectSkillProposalCommand
            service.reject_skill_proposal(RejectSkillProposalCommand(1, 1))
            
            assert len(progress_repo.find_by_id(SkillDeckProgressId(1)).pending_proposals) == 0

    class TestActivatePlayerAwakenedMode:
        def test_activate_awakened_mode_success_consumes_resources(self, setup):
            service, loadout_repo, _, _, player_repo, _ = setup
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 100, 10, 10)
            loadout_repo.save(loadout)
            status = _sample_status(100)
            player_repo.save(status)

            command = ActivatePlayerAwakenedModeCommand(
                player_id=100,
                loadout_id=1,
                current_tick=10,
                duration_ticks=50,
                cooldown_reduction_rate=0.5,
                mp_cost=20,
                stamina_cost=30,
                hp_cost=0
            )
            service.activate_player_awakened_mode(command)

            # リソース消費の確認
            updated_status = player_repo.find_by_id(PlayerId(100))
            assert updated_status.mp.value == 30
            assert updated_status.stamina.value == 70
            
            # 覚醒状態の確認
            updated_loadout = loadout_repo.find_by_id(SkillLoadoutId(1))
            assert updated_loadout.awaken_state.is_active is True
            assert updated_loadout.awaken_state.active_until_tick == 60

        def test_activate_awakened_mode_fails_when_insufficient_stamina(self, setup):
            service, loadout_repo, _, _, player_repo, _ = setup
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 100, 10, 10)
            loadout_repo.save(loadout)
            status = _sample_status(100)
            player_repo.save(status)

            # スタミナ不足(100 < 999)
            command = ActivatePlayerAwakenedModeCommand(100, 1, 10, 50, 0.5, stamina_cost=999)
            
            with pytest.raises(SkillCommandException, match="スタミナが不足しています"):
                service.activate_player_awakened_mode(command)

    class TestErrorHandling:
        def test_handle_domain_exception(self, setup):
            service, loadout_repo, spec_repo, _, _, _ = setup
            # ロードアウトが存在しないケース
            with pytest.raises(SkillCommandException, match="skill loadout not found"):
                service.equip_player_skill(EquipPlayerSkillCommand(100, 999, DeckTier.NORMAL, 0, 1))

        def test_handle_unexpected_exception(self, setup):
            service, _, _, _, _, _ = setup
            from ai_rpg_world.application.skill.exceptions.base_exception import SkillSystemErrorException
            
            # command が None の場合に AttributeError が発生するはず
            with pytest.raises(SkillSystemErrorException):
                service.equip_player_skill(None)
