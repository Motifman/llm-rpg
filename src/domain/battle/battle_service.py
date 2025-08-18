import random
from typing import List
from src.domain.battle.battle_action import ActionType, BattleAction
from src.domain.battle.battle_result import BattleActionResult, TurnStartResult, TurnEndResult
from src.domain.battle.battle_participant import BattleParticipant
from src.domain.battle.battle_enum import BuffType, StatusEffectType
from src.domain.battle.compatible_table import COMPATIBLE_TABLE


class BattleService:
    """複雑な戦闘ロジックを調整"""
    CRITICAL_MULTIPLIER = 1.25
    IF_DEFENDER_DEFENDING_MULTIPLIER = 0.5
    BURN_DAMAGE_AMOUNT = 20
    POISON_DAMAGE_RATE = 0.1
    BLESSING_HEAL_AMOUNT = 20
    WAKE_RATE = 0.1
    CONFUSION_DAMAGE_MULTIPLIER = 0.5
    
    def _check_rate(self, rate: float) -> bool:
        """確率チェック"""
        return random.random() < rate
    
    def _check_compatible_multiplier(self, attacker_action: BattleAction, defender: BattleParticipant) -> float:
        """相性チェック"""
        return COMPATIBLE_TABLE.get((attacker_action.element, defender.entity.element), 1.0)
    
    def _calculate_damage(self, attacker: BattleParticipant, defender: BattleParticipant, action: BattleAction, is_critical: bool) -> int:
        """ダメージ計算"""
        # 基本ダメージ計算
        damage = attacker.entity.attack
        damage *= action.damage_multiplier
        
        # バフチェック
        multiplier = attacker.get_buff_multiplier(BuffType.ATTACK)
        damage *= multiplier

        # 相性チェック
        multiplier = self._check_compatible_multiplier(action, defender)
        damage *= multiplier

        # 種族特攻チェック
        multiplier = action.race_attack_multiplier.get(defender.entity.race, 1.0)
        damage *= multiplier
        
        # クリティカルダメージチェック
        if is_critical:
            damage *= self.CRITICAL_MULTIPLIER

        # ディフェンスチェック
        defence = defender.entity.defense
        if defender.entity.is_defending():
            defence *= self.IF_DEFENDER_DEFENDING_MULTIPLIER
        
        # バフチェック
        multiplier = defender.get_buff_multiplier(BuffType.DEFENSE)
        defence *= multiplier

        # ダメージ軽減
        damage = max(damage - defence, 0)

        return int(damage)

    def process_turn_start(self, attacker: BattleParticipant) -> TurnStartResult:
        """ターン開始時の処理"""
        attacker.entity.un_defend()
        messages: List[str] = []
        can_act = True
        self_damage = 0
        recovered_status_effects = []

        status_effects = attacker.get_status_effects()
        for status_effect_type in status_effects:
            if status_effect_type == StatusEffectType.SLEEP:
                if self._check_rate(self.WAKE_RATE):
                    attacker.recover_status_effects(status_effect_type)
                    recovered_status_effects.append(status_effect_type)
                    messages.append(f"{attacker.entity.name}は眠りから覚めた！")
                else:
                    messages.append(f"{attacker.entity.name}は眠っているようだ...")
                    can_act = False
            elif status_effect_type == StatusEffectType.PARALYSIS:
                messages.append(f"{attacker.entity.name}は体が麻痺して動けないようだ...")
                can_act = False
            elif status_effect_type == StatusEffectType.CONFUSION:
                damage = int(attacker.entity.attack * self.CONFUSION_DAMAGE_MULTIPLIER)
                attacker.entity.take_damage(damage)
                self_damage += damage
                messages.append(f"{attacker.entity.name}は混乱により自分に{damage}のダメージを与えた！")
                can_act = False
            elif status_effect_type == StatusEffectType.CURSE:
                duration = attacker.get_status_effect_remaining_duration(StatusEffectType.CURSE)
                messages.append(f"{attacker.entity.name}は残り{duration}ターンで死ぬ呪いにかかっている...")

        attacker.process_status_effects_on_turn_start()
        attacker.process_buffs_on_turn_start()
        return TurnStartResult(
            can_act=can_act,
            messages=messages,
            self_damage=self_damage,
            recovered_status_effects=recovered_status_effects,
        )

    def can_act(self, attacker: BattleParticipant) -> bool:
        """行動可能かどうか"""
        return True

    def process_turn_end(self, attacker: BattleParticipant) -> TurnEndResult:
        """ターン終了時の処理"""
        messages: List[str] = []
        damage_from_status_effects = 0
        healing_from_status_effects = 0
        expired_status_effects = []
        expired_buffs = []
        
        if attacker.has_status_effect(StatusEffectType.BURN):
            attacker.entity.take_damage(self.BURN_DAMAGE_AMOUNT)
            damage_from_status_effects += self.BURN_DAMAGE_AMOUNT
            messages.append(f"{attacker.entity.name}はやけどにより{self.BURN_DAMAGE_AMOUNT}のダメージを受けた！")
        if attacker.has_status_effect(StatusEffectType.POISON):
            damage = int(attacker.entity.hp * self.POISON_DAMAGE_RATE)
            attacker.entity.take_damage(damage)
            damage_from_status_effects += damage
            messages.append(f"{attacker.entity.name}は毒により{damage}のダメージを受けた！")
        if attacker.has_status_effect(StatusEffectType.BLESSING):
            attacker.entity.heal(self.BLESSING_HEAL_AMOUNT)
            healing_from_status_effects += self.BLESSING_HEAL_AMOUNT
            messages.append(f"{attacker.entity.name}は神の加護により{self.BLESSING_HEAL_AMOUNT}HP回復した！")
        if attacker.has_status_effect(StatusEffectType.CURSE):
            if attacker.get_status_effect_remaining_duration(StatusEffectType.CURSE) == 0:
                attacker.recover_status_effects(StatusEffectType.CURSE)
                curse_damage = attacker.entity.hp
                attacker.entity.take_damage(curse_damage)
                damage_from_status_effects += curse_damage
                expired_status_effects.append(StatusEffectType.CURSE)
                messages.append(f"{attacker.entity.name}は呪いが発動し{curse_damage}のダメージを受けた！")
        
        # 期限切れになった状態異常とバフを記録
        original_status_effects = set(attacker.get_status_effects())
        original_buffs = set(attacker.buffs_remaining_duration.keys())
        
        attacker.process_status_effects_on_turn_end()
        attacker.process_buffs_on_turn_end()
        
        # 期限切れになった状態異常を記録
        current_status_effects = set(attacker.get_status_effects())
        expired_status_effects.extend(list(original_status_effects - current_status_effects))
        
        # 期限切れになったバフを記録
        current_buffs = set(attacker.buffs_remaining_duration.keys())
        expired_buffs.extend(list(original_buffs - current_buffs))
        
        return TurnEndResult(
            messages=messages,
            is_attacker_defeated=not attacker.entity.is_alive(),
            damage_from_status_effects=damage_from_status_effects,
            healing_from_status_effects=healing_from_status_effects,
            expired_status_effects=expired_status_effects,
            expired_buffs=expired_buffs,
        )
    
    def execute_attack(self, attacker: BattleParticipant, defenders: List[BattleParticipant], action: BattleAction) -> BattleActionResult:
        """攻撃を実行"""
        messages = []
        hp_consumed = action.hp_cost or 0
        mp_consumed = action.mp_cost or 0
        
        # 魔法攻撃が可能かチェック
        if attacker.has_status_effect(StatusEffectType.SILENCE) and action.action_type == ActionType.MAGIC:
            return BattleActionResult.create_failure(
                messages=[f"{attacker.entity.name}は沈黙しているようだ..."],
                failure_reason="silenced",
            )
        
        # MPチェック
        if action.mp_cost is not None and not attacker.entity.can_consume_mp(action.mp_cost):
            return BattleActionResult.create_failure(
                messages=[f"{attacker.entity.name}はMPが足りず、{action.name}を実行できないようだ"],
                failure_reason="insufficient_mp",
            )
        
        # HP, MP消費
        if action.mp_cost is not None:
            attacker.entity.consume_mp(action.mp_cost)
            messages.append(f"{attacker.entity.name}は{action.mp_cost}MPを消費した！")
        if action.hp_cost is not None:
            attacker.entity.take_damage(action.hp_cost)
            messages.append(f"{attacker.entity.name}は{action.hp_cost}HPを消費した！")

        # 命中率チェック
        if action.hit_rate is not None and not self._check_rate(action.hit_rate):
            messages.append(f"{attacker.entity.name}の攻撃が外れた！")
            return BattleActionResult.create_failure(
                messages=messages,
                failure_reason="missed",
                hp_consumed=hp_consumed,
                mp_consumed=mp_consumed,
            )
        
        # 回避率チェック（各defender個別にチェック）
        evaded_defenders = []
        for defender in defenders:
            if self._check_rate(defender.entity.evasion_rate):
                evaded_defenders.append(defender)
                messages.append(f"{defender.entity.name}は攻撃を回避した！")
        
        # 全員が回避した場合は攻撃失敗
        if len(evaded_defenders) == len(defenders):
            return BattleActionResult.create_failure(
                messages=messages,
                failure_reason="evaded",
                hp_consumed=hp_consumed,
                mp_consumed=mp_consumed,
            )
        
        # 収集用変数
        target_ids = [defender.entity_id for defender in defenders]
        damages = []
        critical_hits = []
        compatibility_multipliers = []
        applied_status_effects = []
        applied_buffs = []
        
        # ダメージ計算
        for defender in defenders:
            # 回避したdefenderはスキップ
            if defender in evaded_defenders:
                damages.append(0)
                critical_hits.append(False)
                compatibility_multipliers.append(1.0)
                continue
            
            # クリティカル判定
            is_critical = self._check_rate(attacker.entity.critical_rate)
            critical_hits.append(is_critical)
            
            # 相性倍率を取得
            compatibility_multiplier = self._check_compatible_multiplier(action, defender)
            compatibility_multipliers.append(compatibility_multiplier)
            
            damage = self._calculate_damage(attacker, defender, action, is_critical)
            damages.append(damage)
            defender.entity.take_damage(damage)
            
            crit_msg = "クリティカル！" if is_critical else ""
            messages.append(f"{attacker.entity.name}は{defender.entity.name}に{damage}のダメージを与えた！{crit_msg}")

        # 状態異常処理
        if action.status_effect_rate:
            for i, defender in enumerate(defenders):
                # 回避したdefenderはスキップ
                if defender in evaded_defenders:
                    continue
                for status_effect_type, rate in action.status_effect_rate.items():
                    if self._check_rate(rate):
                        duration = action.status_effect_duration[status_effect_type]
                        defender.add_status_effect(status_effect_type, duration)
                        applied_status_effects.append((target_ids[i], status_effect_type, duration))
                        messages.append(f"{defender.entity.name}は「{status_effect_type.value}」の状態異常を受けた！")
        
        # バフ処理
        if action.buff_multiplier:
            for i, defender in enumerate(defenders):
                # 回避したdefenderはスキップ
                if defender in evaded_defenders:
                    continue
                for buff_type, multiplier in action.buff_multiplier.items():
                    duration = action.buff_duration[buff_type]
                    defender.add_buff(buff_type, duration, multiplier)
                    applied_buffs.append((target_ids[i], buff_type, multiplier, duration))
                    messages.append(f"{defender.entity.name}は「{buff_type.value}」のバフを受けた！")
        
        # 死亡判定
        is_target_defeated = [not defender.entity.is_alive() for defender in defenders]

        return BattleActionResult.create_success(
            messages=messages,
            target_ids=target_ids,
            damages=damages,
            healing_amounts=[0] * len(target_ids),  # 攻撃では回復なし
            is_target_defeated=is_target_defeated,
            applied_status_effects=applied_status_effects,
            applied_buffs=applied_buffs,
            hp_consumed=hp_consumed,
            mp_consumed=mp_consumed,
            critical_hits=critical_hits,
            compatibility_multipliers=compatibility_multipliers,
        )
    
    def execute_defend(self, defender: BattleParticipant, action: BattleAction) -> BattleActionResult:
        """防御を実行"""
        defender.entity.defend()
        return BattleActionResult.create_success(
            messages=[f"{defender.entity.name}は守りの構えをとった！"],
            target_ids=[defender.entity_id],
            damages=[0],
            healing_amounts=[0],
            is_target_defeated=[False],
        )
    
    def execute_heal(self, healer: BattleParticipant, target: BattleParticipant, action: BattleAction) -> BattleActionResult:
        """回復を実行"""
        messages = []
        # MPチェック
        if not healer.entity.can_consume_mp(action.mp_cost):
            return BattleActionResult.create_failure(
                messages=[f"{healer.entity.name}はMPが足りず、「{action.name}」を実行できないようだ"],
                failure_reason="insufficient_mp",
            )

        # HP, MP消費
        if action.mp_cost is not None:
            healer.entity.consume_mp(action.mp_cost)
            messages.append(f"{healer.entity.name}は{action.mp_cost}MPを消費した！")
        if action.hp_cost is not None:
            healer.entity.take_damage(action.hp_cost)
            messages.append(f"{healer.entity.name}は{action.hp_cost}HPを消費した！")

        # 回復
        heal_amount = action.heal_amount or 0
        if heal_amount > 0:
            target.entity.heal(heal_amount)
            messages.append(f"{target.entity.name}は{heal_amount}HP回復した！")

        return BattleActionResult.create_success(
            messages=messages,
            target_ids=[target.entity_id],
            damages=[0],  # 回復ではダメージなし
            healing_amounts=[heal_amount],
            is_target_defeated=[False],
            hp_consumed=action.hp_cost or 0,
            mp_consumed=action.mp_cost or 0,
        ) 