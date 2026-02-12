import logging
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.combat.event.combat_events import HitBoxHitRecordedEvent
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository


class CombatAggroHandler(EventHandler[HitBoxHitRecordedEvent]):
    """HitBoxヒットイベントを受けて被弾したアクターのヘイト（ターゲット）を更新するハンドラ"""

    def __init__(
        self,
        hit_box_repository: HitBoxRepository,
        physical_map_repository: PhysicalMapRepository,
        unit_of_work: UnitOfWork,
    ):
        self._hit_box_repository = hit_box_repository
        self._physical_map_repository = physical_map_repository
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: HitBoxHitRecordedEvent):
        try:
            hit_box = self._hit_box_repository.find_by_id(event.aggregate_id)
            if not hit_box:
                return

            physical_map = self._physical_map_repository.find_by_spot_id(hit_box.spot_id)
            if not physical_map:
                return

            try:
                owner_obj = physical_map.get_object(event.owner_id)
                target_obj = physical_map.get_object(event.target_id)
            except ObjectNotFoundException:
                return

            # 攻撃者がアクターでない場合（罠など）はヘイト処理をスキップ
            if not owner_obj.is_actor:
                return

            # 被弾したオブジェクトがアクターでない場合もスキップ
            if not target_obj.is_actor:
                return

            # 被弾したオブジェクトが自律行動コンポーネントを持っているか確認
            component = target_obj.component
            if not isinstance(component, AutonomousBehaviorComponent):
                return

            # 攻撃者をターゲットとして認識させる
            component.spot_target(owner_obj.object_id, owner_obj.coordinate)
            
            # 物理マップの変更（コンポーネントの状態変更）を保存
            self._physical_map_repository.save(physical_map)
            
            # マップから発生したイベントがあればUnitOfWorkに追加
            self._unit_of_work.add_events(physical_map.get_events())
            physical_map.clear_events()
        except Exception as e:
            self._logger.exception(f"Unexpected error in CombatAggroHandler: {str(e)}")
