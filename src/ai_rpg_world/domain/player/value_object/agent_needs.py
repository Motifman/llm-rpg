"""エージェントの欲求コレクション。

複数の欲求（空腹、疲労等）を不変に管理する。
PlayerStatusAggregate に保持される。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

from ai_rpg_world.domain.player.value_object.agent_need import AgentNeed, NeedType


@dataclass(frozen=True)
class AgentNeeds:
    """エージェントの全欲求を保持する不変コレクション。"""

    _needs: Tuple[AgentNeed, ...]

    @classmethod
    def empty(cls) -> AgentNeeds:
        return cls(())

    @classmethod
    def default(cls, max_value: int = 100) -> AgentNeeds:
        """デフォルトの欲求セット（空腹・疲労を0で初期化）。"""
        return cls((
            AgentNeed.create(NeedType.HUNGER, 0, max_value),
            AgentNeed.create(NeedType.FATIGUE, 0, max_value),
        ))

    def get(self, need_type: NeedType) -> Optional[AgentNeed]:
        for n in self._needs:
            if n.need_type == need_type:
                return n
        return None

    def with_updated(self, updated: AgentNeed) -> AgentNeeds:
        """指定欲求を更新した新しいコレクションを返す。

        NeedType が既に登録されていれば置換、未登録なら末尾に追加する。
        """
        new_needs = tuple(
            updated if n.need_type == updated.need_type else n
            for n in self._needs
        )
        # 未登録の場合は追加
        if not any(n.need_type == updated.need_type for n in self._needs):
            new_needs = self._needs + (updated,)
        return AgentNeeds(new_needs)

    def increase_all(self, rates: Dict[NeedType, int]) -> AgentNeeds:
        """全欲求を指定レートで増加させる（tick経過用）。"""
        new_needs = []
        for n in self._needs:
            rate = rates.get(n.need_type, 0)
            new_needs.append(n.increase(rate) if rate > 0 else n)
        return AgentNeeds(tuple(new_needs))

    def describe_all(self) -> Tuple[str, ...]:
        """全欲求の状態テキストをタプルで返す。"""
        return tuple(n.describe() for n in self._needs)

    def describe_all_with_deltas(
        self, deltas: "Mapping[NeedType, int]"
    ) -> Tuple[str, ...]:
        """PR-T: 各 need の状態テキストに「前 turn からの delta」を併記したタプル
        を返す。``deltas`` に該当 need が無いか 0 のときは従来の describe と
        同じ表現になる。

        delta は ``PlayerStatusAggregate.compute_need_deltas()`` で計算した値を
        想定。LLM が trajectory (= 改善中 / 悪化中) を能動的に追えるようにする
        ための表示。
        """
        return tuple(
            n.describe(delta=deltas.get(n.need_type, 0)) for n in self._needs
        )

    @property
    def has_critical(self) -> bool:
        """いずれかの欲求が危険レベルか。"""
        return any(n.is_critical for n in self._needs)

    def __len__(self) -> int:
        return len(self._needs)

    def __iter__(self):
        return iter(self._needs)
