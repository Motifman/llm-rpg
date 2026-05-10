"""tick 駆動でスポットグラフ世界のモンスター行動を一括実行する。

本サービスは「policy = 候補選び + 行動優先順位」を担当し、各行動の実体
（attack / move）はそれぞれ専用のオーケストレーター・aggregate メソッドへ
委譲する。

各モンスターについて毎 tick 以下の優先順で 1 アクションを試みる:

0. **hunger tick**: 飢餓進行 → 閾値超過で starve（即死、後続スキップ）
1. **react_to_attack** (Phase 4a): 直近に攻撃を受けたモンスターが
   `reaction_to_attack` policy に従って FLEE (逃走) / CHASE (反撃) を
   実行。state は `_behavior_state` に永続化される
2. **attack player**: ENEMY + ALIVE + cooldown 切れ + 同スポットに生存
   プレイヤーが居る → `SpotAttackOrchestrator.execute_monster_attack`
3. **predation**: hungry + 同スポットに prey 種族の生存モンスターが居る →
   `SpotAttackOrchestrator.execute_predation_attack`
4. **forage**: hungry + 同スポットに preferred 食材アイテムが居る → 食べる
5. **wander**: 上記いずれも発動しない場合、`ecology_type != AMBUSH` かつ
   `idle_wander_chance` で抽選に当選すれば隣接スポットへランダム移動

複数の monster が居る tick では ID 昇順でループする（PR #127 と同じ policy）。
1 tick で 1 monster 1 アクションが原則。

呼び出し導線:
- 想定接続先は presentation 側の tick driver / または将来の wiring。
  attack 経路は orchestrator が graph save まで担うが、wander 経路は本
  サービスが tick 末で graph save を行う（move_monster は monster aggregate
  を変更しないため graph 単体の save で十分）。

ランダムソース:
- `random_source` を引数で受け取れるようにし、テストでは固定 seed の
  `random.Random(seed)` を渡して決定的に検証する。

世界フラグ:
- `world_flags_provider` で passage 通行条件 (鍵フラグ等) を解決。未設定の
  起動構成では空 frozenset を渡す（モンスターがフラグ依存通路を通れない
  形になる、安全側）。
"""

from __future__ import annotations

import logging
import random
from typing import Callable, FrozenSet, List, Optional

from ai_rpg_world.application.monster.services.monster_reaction_handler import (
    MonsterReactionHandler,
)
from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import (
    MonsterAggregate,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.monster.enum.monster_enum import (
    EcologyTypeEnum,
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ConnectionNotPassableException,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAteGroundItemEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)
from ai_rpg_world.domain.world_graph.value_object.spot_attack_outcome import (
    AttackOutcome,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

logger = logging.getLogger(__name__)

WorldFlagsProvider = Callable[[], FrozenSet[str]]


class SpotMonsterBehaviorTickService:
    """tick 単位でモンスター行動を統合実行する。

    現状サポートする行動: attack / wander。後続フェーズで pursuit /
    foraging / environment interaction が同じ priority chain に追加される
    想定。
    """

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        monster_repository: MonsterRepository,
        player_status_repository: PlayerStatusRepository,
        attack_orchestrator: SpotAttackOrchestrator,
        *,
        random_source: Optional[random.Random] = None,
        world_flags_provider: Optional[WorldFlagsProvider] = None,
        spot_interior_repository: Optional["ISpotInteriorRepository"] = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._monster_repository = monster_repository
        self._player_status_repository = player_status_repository
        self._orchestrator = attack_orchestrator
        # 注入されない場合はモジュールデフォルトの Random（非決定的）を使う。
        # 本番運用では同じインスタンスを渡し続けることで再現性を制御できる。
        self._random = random_source or random.Random()
        self._world_flags_provider = world_flags_provider
        # Phase 3a: 採食 (forage) で地面アイテムを消費する際に必要。注入されない
        # 場合は forage 行動が常にスキップされる（後方互換 / 未配線構成許容）。
        self._spot_interior_repository = spot_interior_repository
        # Phase 4a 反撃 / 逃走の処理は handler に委譲。FLEE 中の wander は
        # tick service 側の `_try_wander_force` を再利用する (chance 無視版)。
        self._reaction = MonsterReactionHandler(
            monster_repository=monster_repository,
            player_status_repository=player_status_repository,
            attack_orchestrator=attack_orchestrator,
            force_wander_fn=self._try_wander_force,
        )

    def tick(self, current_tick: WorldTick) -> List[AttackOutcome]:
        """1 tick 分のモンスター行動を一括実行する。

        Returns:
            当該 tick で実際に発生した attack の結果一覧。
            wander の結果は graph に積まれた event で観測されるためここでは
            返さない（必要になったら戻り値型を BehaviorOutcome 系に拡張する）。
        """
        graph = self._spot_graph_repository.find_graph()
        attack_outcomes: List[AttackOutcome] = []
        any_graph_change = False
        # `any_state_changed` は forage/starve でも True に倒すが、それらは
        # 関連リポジトリ（monster / interior）を既に save しているため
        # `any_graph_change` の判定材料は graph 上で event が積まれた行動
        # （forage と wander）のみで十分。

        for monster_id in sorted(
            graph.monster_spot_mapping().keys(), key=lambda m: m.value
        ):
            spot_id = graph.get_monster_spot(monster_id)
            monster = self._monster_repository.find_by_id(monster_id)
            if monster is None:
                logger.debug(
                    "tick: monster_repository returned None for %s (placed at %s)",
                    monster_id.value,
                    spot_id.value,
                )
                continue

            if monster.status != MonsterStatusEnum.ALIVE:
                continue

            # --- 0. 飢餓 tick ---
            # hunger を 1 tick 進め、starvation 閾値を一定 tick 超えたら
            # `monster.starve()` で死亡させる。生存していればこの tick の
            # 他のアクション（attack/forage/wander）も継続する。
            died_of_starvation = self._tick_hunger_and_maybe_starve(
                monster, current_tick
            )
            if died_of_starvation:
                # 飢餓死した monster は graph presence からは自動除去しない
                # （Phase 1 と同じ方針: despawn は別 PR）。MonsterDiedEvent は
                # monster aggregate 側で発火済み。
                continue

            # --- 1. react_to_attack (反撃 / 逃走) ---
            # 直近 grace_ticks 以内に攻撃を受けた + reaction_to_attack !=
            # PASSIVE の monster が、template policy に従って FLEE / CHASE
            # 状態に遷移し、その状態に対応するアクション（逃走移動 or 反撃）を
            # 1 つ実行する。state は ALIVE 中の `_behavior_state` に永続。
            reaction_outcome = self._reaction.try_react(
                monster, graph, spot_id, current_tick
            )
            if reaction_outcome is not None:
                if reaction_outcome.executed:
                    attack_outcomes.append(reaction_outcome)
                # state 遷移や move が起きた可能性があるので graph save 必要。
                # graph に event が積まれていれば下の attack_outcomes と
                # 並んで観測される。
                any_graph_change = True
                continue

            # --- 2. attack 優先 ---
            # `_maybe_attack` は前提条件 (ENEMY / cooldown 切れ / 同スポット
            # の生存プレイヤー有り) を満たした場合のみ実行を試みて
            # `AttackOutcome` を返す。前提が欠けるなら None を返し、wander に
            # フォールバックさせる。
            attack_outcome = self._maybe_attack(
                monster, graph, spot_id, current_tick
            )
            if attack_outcome is not None:
                attack_outcomes.append(attack_outcome)
                if attack_outcome.executed:
                    # 攻撃成立で 1 tick の行動消化。orchestrator 側で graph
                    # save 済み。
                    continue
                # 攻撃を試みたが不成立 (visibility / target_down / zero_damage)
                # の場合、現状は wander にフォールバックする。「対象を見ながら
                # wander で離れる」のは世界観的にやや不自然だが、最小実装では
                # 動的態度 (FLEE 等) を持たないため許容する。Phase 2 で pursuit
                # / behavior_state を入れるときに「攻撃失敗 → 留まる」を別途
                # 表現する想定。

            # --- 3. predation (捕食) ---
            # hungry な捕食者で、同 spot に prey 種族の生存モンスターが居れば
            # 攻撃する（多 tick 戦闘モデル）。orchestrator が damage 適用 +
            # 致命時 hunger 回復 + record_attacked_by_in_spot を担当。
            # priority は player attack の後 / forage の前: プレイヤーが
            # 目の前に居るときは player を優先（事前合意）。
            predation_outcome = self._maybe_predate(
                monster, graph, spot_id, current_tick
            )
            if predation_outcome is not None:
                attack_outcomes.append(predation_outcome)
                if predation_outcome.executed:
                    # 捕食成立で 1 tick の行動消化。orchestrator 側で graph
                    # save 済み。
                    continue
                # 捕食を試みたが不成立 (cooldown / not_visible / zero_damage)
                # の場合は forage / wander にフォールバック。

            # --- 4. forage (採食) ---
            # hunger >= forage_threshold + 同スポットに preferred 食材あり
            # → 1 個食べて hunger 減少。graph に MonsterAteGroundItemEvent が
            # 積まれるので tick 末で graph save が必要。
            # 採食成立で `continue`（同 tick の wander スキップ）するのは:
            # (a) 採食を 1 アクションとして消化し、満腹直後に動き回るのは
            #     生物的に不自然
            # (b) 1 tick = 1 行動の不変条件を attack/wander と同じく維持する
            # 将来「採食 → そのまま移動」を許したい場合はこの continue を外し
            # priority chain を「順次進む」モデルに変える必要がある。
            if self._try_forage(monster, graph, spot_id):
                any_graph_change = True
                continue

            # --- 5. wander フォールバック ---
            if self._try_wander(monster, graph, spot_id):
                any_graph_change = True

        # forage / wander で graph state が変わった場合は明示 save。attack 経路は
        # orchestrator 側で graph.save() を呼ぶため、同 tick で「一部 monster
        # が attack + 別 monster が forage/wander」のケースでは graph.save() が
        # 2 回呼ばれる。SQLite / InMemory リポジトリでは冪等で問題ないが、
        # 将来的に楽観ロック等を導入する場合は orchestrator から save を
        # 切り離して tick 末で 1 回に集約する設計に見直す必要がある
        # （PR #131 レビューの MEDIUM 指摘）。
        if any_graph_change:
            self._spot_graph_repository.save(graph)

        return attack_outcomes

    # 反撃 / 逃走 (Phase 4a) は `MonsterReactionHandler` に切り出した。
    # 当サービスの tick() chain step 1 から `self._reaction.try_react()` で呼ぶ。

    def _try_wander_force(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
    ) -> bool:
        """`idle_wander_chance` を無視した強制版 wander。FLEE で使う。

        passable な接続が無ければ False（逃げ場なし、その場で立ち往生）。
        """
        connections = graph.iter_outgoing_connections_from(spot_id)
        if not connections:
            return False
        world_flags = (
            self._world_flags_provider()
            if self._world_flags_provider is not None
            else frozenset()
        )
        owned_item_spec_ids: FrozenSet[ItemSpecId] = frozenset()
        passable = sorted(
            (
                conn for conn in connections
                if graph.can_traverse_connection(
                    conn.connection_id, owned_item_spec_ids, world_flags
                )
            ),
            key=lambda c: c.connection_id.value,
        )
        if not passable:
            return False
        picked = self._random.choice(passable)
        try:
            graph.move_monster(
                monster_id=monster.monster_id,
                connection_id=picked.connection_id,
                owned_item_spec_ids=owned_item_spec_ids,
                world_flags=world_flags,
            )
        except ConnectionNotPassableException:
            return False
        return True

    # ------------------------------------------------------------------
    # 内部 - attack
    # ------------------------------------------------------------------

    def _maybe_attack(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        current_tick: WorldTick,
    ) -> Optional[AttackOutcome]:
        """攻撃の前提条件を満たせば実行を試みる。実行しない場合は None。"""
        if monster.template.faction != MonsterFactionEnum.ENEMY:
            return None
        if not monster.can_attack_now(current_tick):
            return None
        target = self._pick_target(graph, spot_id)
        if target is None:
            return None
        return self._orchestrator.execute_monster_attack(
            attacker_monster=monster,
            target_player=target,
            graph=graph,
            spot_id=spot_id,
            current_tick=current_tick,
        )

    def _pick_target(
        self, graph: SpotGraphAggregate, spot_id: SpotId
    ) -> Optional[PlayerStatusAggregate]:
        """同スポットに居るプレイヤーから ID 昇順で最初の生存者を返す。"""
        presence = graph.presence_at(spot_id)
        for entity_id in sorted(
            presence.present_entity_ids, key=lambda e: e.value
        ):
            player = self._player_status_repository.find_by_id(
                PlayerId(entity_id.value)
            )
            if player is None:
                continue
            if player.is_down:
                continue
            return player
        return None

    # ------------------------------------------------------------------
    # 内部 - predation (Phase 3b)
    # ------------------------------------------------------------------

    def _maybe_predate(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        current_tick: WorldTick,
    ) -> Optional[AttackOutcome]:
        """hungry + 同スポットに prey 種族の生存モンスターが居れば捕食を試みる。

        前提条件 (満たさなければ None を返す):
        - `template.starvation_ticks > 0`（飢餓有効テンプレ）
        - `template.prey_races` に少なくとも 1 種族登録
        - `monster.hunger >= template.forage_threshold`（forage と同じ閾値を共有）
        - `monster.can_attack_now(current_tick)` が True
        - 同スポットに prey 種族の生存モンスターが少なくとも 1 体

        実行:
        - prey は ID 昇順で先頭の生存個体を選ぶ
        - orchestrator.execute_predation_attack に loaded aggregate を渡す
        - 戻り値の `AttackOutcome` をそのまま callers に返す
        """
        template = monster.template
        if template.starvation_ticks <= 0:
            return None
        if not template.prey_races:
            return None
        if monster.hunger < template.forage_threshold:
            return None
        if not monster.can_attack_now(current_tick):
            return None

        prey = self._pick_prey(graph, spot_id, template.prey_races, monster.monster_id)
        if prey is None:
            return None

        return self._orchestrator.execute_predation_attack(
            attacker_monster=monster,
            prey_monster=prey,
            graph=graph,
            spot_id=spot_id,
            current_tick=current_tick,
        )

    def _pick_prey(
        self,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
        prey_races: FrozenSet[Race],
        attacker_monster_id: MonsterId,
    ) -> Optional[MonsterAggregate]:
        """同スポットの生存モンスターから prey 種族にマッチする 1 体を返す。

        ID 昇順で先頭の生存個体を選ぶ。攻撃者自身は当然除外する（同種が
        prey に含まれていても自分は襲わない）。
        """
        presence = graph.monster_presence_at(spot_id)
        for candidate_id in sorted(
            presence.present_monster_ids, key=lambda m: m.value
        ):
            if candidate_id == attacker_monster_id:
                continue
            candidate = self._monster_repository.find_by_id(candidate_id)
            if candidate is None:
                continue
            if candidate.status != MonsterStatusEnum.ALIVE:
                continue
            if candidate.template.race not in prey_races:
                continue
            return candidate
        return None

    # ------------------------------------------------------------------
    # 内部 - wander
    # ------------------------------------------------------------------

    def _try_wander(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
    ) -> bool:
        """`idle_wander_chance` で抽選し、当選すれば passable 接続を 1 つ選んで移動。

        Returns:
            実際に移動が行われたら True（graph state が変化したら True）。
        """
        if monster.template.ecology_type == EcologyTypeEnum.AMBUSH:
            # 待ち伏せ型は徘徊しない（初期位置で獲物を待つ習性）。
            return False
        chance = monster.template.idle_wander_chance
        if chance <= 0.0:
            return False
        if self._random.random() >= chance:
            return False

        connections = graph.iter_outgoing_connections_from(spot_id)
        if not connections:
            return False

        world_flags = (
            self._world_flags_provider()
            if self._world_flags_provider is not None
            else frozenset()
        )
        owned_item_spec_ids: FrozenSet[ItemSpecId] = frozenset()

        # passable な接続だけ抽出。`can_traverse_connection` は traversable +
        # passage_conditions の両方を見るので、鍵が要る扉やフラグ依存通路は
        # この時点で除外される。connection_id 昇順でソートして決定的に。
        passable = sorted(
            (
                conn for conn in connections
                if graph.can_traverse_connection(
                    conn.connection_id, owned_item_spec_ids, world_flags
                )
            ),
            key=lambda c: c.connection_id.value,
        )
        if not passable:
            return False

        picked = self._random.choice(passable)
        try:
            graph.move_monster(
                monster_id=monster.monster_id,
                connection_id=picked.connection_id,
                owned_item_spec_ids=owned_item_spec_ids,
                world_flags=world_flags,
            )
        except ConnectionNotPassableException:
            # 上の `can_traverse_connection` フィルタで除外されているはずなので
            # 通常パスでは到達しない。到達する場合は (a) フィルタロジックの
            # バグ、または (b) `move_monster` 内の `can_pass` と
            # `can_traverse_connection` の判定が乖離する想定外ケース。
            # 隠蔽せず warning で記録する。
            logger.warning(
                "tick: monster %s passed pre-filter but move_monster raised "
                "ConnectionNotPassableException for connection %s "
                "(filter/move logic out of sync)",
                monster.monster_id.value,
                picked.connection_id.value,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # 内部 - hunger / starvation
    # ------------------------------------------------------------------

    def _tick_hunger_and_maybe_starve(
        self,
        monster: MonsterAggregate,
        current_tick: WorldTick,
    ) -> bool:
        """飢餓を 1 tick 進めて、しきい値超過なら starvation 死亡させる。

        Returns:
            True なら飢餓死した（監督 aggregate に MonsterDiedEvent 発火済み、
            monster_repo に save 済み）。False なら生存継続（hunger は
            進行している可能性あり、monster_repo に save 済み）。
        """
        # template の飢餓設定が無効なら no-op で False
        if monster.template.starvation_ticks <= 0:
            return False
        if monster.template.hunger_increase_per_tick <= 0:
            return False

        should_starve = monster.tick_hunger(current_tick)
        if should_starve:
            monster.starve(current_tick)
            self._monster_repository.save(monster)
            return True

        # hunger は進んだので monster_repo に save。
        self._monster_repository.save(monster)
        return False

    # ------------------------------------------------------------------
    # 内部 - forage (採食)
    # ------------------------------------------------------------------

    def _try_forage(
        self,
        monster: MonsterAggregate,
        graph: SpotGraphAggregate,
        spot_id: SpotId,
    ) -> bool:
        """`hunger >= forage_threshold` のとき、同スポットの preferred 食材を
        1 個食べる。

        Returns:
            実際に食べたら True（graph に event 積まれた + interior + monster
            は save 済み）。食材が無い / 飢餓未閾値 / interior 未注入 で False。
        """
        if self._spot_interior_repository is None:
            return False

        template = monster.template
        if template.starvation_ticks <= 0:
            return False
        if not template.preferred_feed_item_spec_ids:
            return False
        if template.hunger_decrease_on_feed <= 0.0:
            # `record_feed` は `hunger_decrease <= 0` を no-op で抜ける仕様。
            # アイテムだけ消費して hunger が回復しない silent failure を防ぐため、
            # 採食自体をスキップしてテンプレ設定ミスを観測しやすくする。
            return False

        # MonsterAggregate.hunger プロパティ経由でアクセス。
        if monster.hunger < template.forage_threshold:
            return False

        spot_node = graph.get_spot(spot_id)
        interior = self._spot_interior_repository.find_by_spot_id(spot_id)
        if interior is None:
            return False

        # preferred_feed_item_spec_ids にマッチするアイテムを `item_instance_id`
        # 昇順で 1 つ選ぶ（決定的）。
        preferred = template.preferred_feed_item_spec_ids
        candidates = sorted(
            (g for g in interior.ground_items if g.item_spec_id in preferred),
            key=lambda g: g.item_instance_id.value,
        )
        if not candidates:
            return False

        eaten = candidates[0]
        new_interior = interior.without_ground_item(eaten.item_instance_id)
        self._spot_interior_repository.save(spot_id, new_interior)

        monster.record_feed(template.hunger_decrease_on_feed)
        self._monster_repository.save(monster)

        graph.add_event(
            MonsterAteGroundItemEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                monster_id=monster.monster_id,
                spot_id=spot_id,
                item_instance_id=eaten.item_instance_id,
                item_spec_id=eaten.item_spec_id,
            )
        )
        return True
