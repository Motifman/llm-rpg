"""モンスター個体ID から「肉眼観測できる範囲」の view DTO を作る resolver。

設計方針:
- 数値 HP は隠す。`healthy / wounded / dying` の 3 段階に丸めて公開。理由は
  現実世界では正確な HP を知る術がないため、姿勢や出血など定性的な手掛かり
  に近づけたいから。
- behavior_state は日本語ラベルへ変換する（LLM が即座に意味を取れるよう）。
- 死体（`MonsterStatusEnum.DEAD`）も同じセクションに混ぜる。表記は別文体。
- monster repository に居ない / 解決できない場合は None を返す。builder 側
  で snapshot から除外され、ターン中の race（aggregate と presence の一時的
  な不整合）で prompt 生成全体が落ちるのを防ぐ。

将来の拡張ポイント:
- 「弱っている」「警戒している」など個体ごとの差分テキストを description に
  押し込んで、複数個体識別の手掛かりにする
- pack_id / growth_stage の情報を可視化（ボス級の威圧感など）
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol

from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphMonsterEntry,
)
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId


HEALTH_HEALTHY = "healthy"
HEALTH_WOUNDED = "wounded"
HEALTH_DYING = "dying"
HEALTH_DEAD = "dead"

# 0.0 〜 1.0 の HP 比率を 3 段階バケットに丸めるしきい値。
# - dying: 30% 未満（明らかに弱っている）
# - wounded: 30% 以上 70% 未満
# - healthy: 70% 以上
_DYING_RATIO_THRESHOLD = 0.30
_WOUNDED_RATIO_THRESHOLD = 0.70


class IMonsterAggregateLookup(Protocol):
    """MonsterAggregate を取り出すための最小プロトコル。

    本物の MonsterRepository も `find_by_id` を持つのでそのまま渡せるが、
    依存を狭めるためテストでは MagicMock の duck typing で十分。
    """

    def find_by_id(self, monster_id: MonsterId) -> Optional[MonsterAggregate]:
        ...


_BEHAVIOR_LABEL_JP = {
    "IDLE": "落ち着いている",
    "PATROL": "巡回している",
    "CHASE": "こちらを追っている",
    "SEARCH": "何かを探している",
    "FLEE": "逃げようとしている",
    "RETURN": "持ち場に戻ろうとしている",
    "ENRAGE": "怒り狂っている",
}


def _bucket_hp(value: int, max_hp: int) -> str:
    """HP 比率から health バケット文字列を返す。

    max_hp が 0 のテンプレート（HP を持たない概念モンスター等）は healthy
    扱い。value が 0 は dying（死亡時は別途 is_dead で扱うのでここには来ない想定）。
    """
    if max_hp <= 0:
        return HEALTH_HEALTHY
    if value <= 0:
        return HEALTH_DYING
    ratio = value / max_hp
    if ratio < _DYING_RATIO_THRESHOLD:
        return HEALTH_DYING
    if ratio < _WOUNDED_RATIO_THRESHOLD:
        return HEALTH_WOUNDED
    return HEALTH_HEALTHY


def _behavior_label(state_value: str) -> str:
    """BehaviorStateEnum.value を LLM 向けの日本語短文に変換する。"""
    return _BEHAVIOR_LABEL_JP.get(state_value, state_value)


def build_monster_view_provider(
    monster_lookup: IMonsterAggregateLookup,
) -> Callable[[MonsterId], Optional[SpotGraphMonsterEntry]]:
    """`SpotGraphCurrentStateBuilder` に渡せる resolver を作って返す。

    aggregate からモンスターを引き、view DTO に整形する関数を closure で返す。
    monster_lookup が None を返した場合や名前解決に失敗した場合は None を返し、
    builder 側で snapshot から除外させる。
    """

    def _resolve(monster_id: MonsterId) -> Optional[SpotGraphMonsterEntry]:
        agg = monster_lookup.find_by_id(monster_id)
        if agg is None:
            return None
        template = agg.template
        name = (template.name or "").strip() or "何かのモンスター"

        is_dead = agg.status == MonsterStatusEnum.DEAD
        if is_dead:
            return SpotGraphMonsterEntry(
                monster_id=monster_id.value,
                display_name=name,
                # 死体に「行動状態」は無い。observer 視点では「動かない」が
                # 一番素直なので固定文言を採用。
                behavior_label="動かない",
                health_bucket=HEALTH_DEAD,
                is_dead=True,
            )

        hp = agg.hp
        health_bucket = _bucket_hp(hp.value, hp.max_hp)
        behavior_label = _behavior_label(agg.behavior_state.value)

        return SpotGraphMonsterEntry(
            monster_id=monster_id.value,
            display_name=name,
            behavior_label=behavior_label,
            health_bucket=health_bucket,
            is_dead=False,
        )

    return _resolve
