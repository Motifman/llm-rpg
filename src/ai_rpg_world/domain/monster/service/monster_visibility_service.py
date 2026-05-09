"""モンスター視点の視認可能性判定（純粋ドメインサービス）。

スポットグラフ戦闘で「モンスターはこのプレイヤーを攻撃可能か？」の前段階に
当たる「肉眼で捉えられているか？」を、環境（光量）とモンスター能力
（dark_vision）の AND/OR で判定する。

設計上の前提:
- スポット内に居ることは前段で確認済み（このサービスはスポットを跨がない）
- 距離・遮蔽・隠密スキル等は扱わない（最小実装）
- monster の knowing/awareness（追跡記憶）は扱わない。常に「今この瞬間に
  目に入るか」のみ
"""

from __future__ import annotations

from ai_rpg_world.domain.monster.value_object.monster_template import (
    MonsterTemplate,
)
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum


class MonsterVisibilityService:
    """環境光量 + dark_vision フラグから視認可否を判定する純粋関数。"""

    def can_see_target(
        self,
        monster_template: MonsterTemplate,
        effective_lighting: LightingEnum,
    ) -> bool:
        """モンスターがその場のプレイヤーを視認できるか。

        判定ルール:
        - `has_dark_vision=True` のテンプレは光量によらず常に True
        - そうでない場合、`effective_lighting` が `DARK` なら False
        - それ以外（DIM 含む）は True

        DIM での視認は最小実装として True に倒している。後で「薄暗いと
        命中率が下がる」のような確率的処理を入れる際の拡張ポイントは
        `attack_chance(effective_lighting)` を別メソッドで足す形を想定。
        """
        if monster_template.has_dark_vision:
            return True
        return effective_lighting not in (LightingEnum.DARK, LightingEnum.PITCH_BLACK)
