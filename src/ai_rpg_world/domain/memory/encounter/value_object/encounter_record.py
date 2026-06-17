"""``EncounterRecord``: 「ある対象と何回 / いつ会ったか」を保持する Value Object。

設計判断 (docs/memory_system/perception_memory_join_design.md):

- state は最小に。``first_seen_tick`` / ``last_seen_tick`` / ``count`` の 3 つだけ。
  intensity / context は必要になってから追加する
- 不変 (frozen)。``observed_again`` で新しい instance を返す immutable update。
  これは「記録の改ざんが起きない」を構造で保証するため
- 「忘却」は当面入れない。snapshot resume の integrity を優先し、token 圧迫が
  観測されたら decay を後付けする
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.memory.encounter.exception.encounter_exception import (
    EncounterRecordRuleException,
    EncounterRecordValidationException,
)


@dataclass(frozen=True)
class EncounterRecord:
    """ある対象 (``EncounterKey``) に対する遭遇履歴。

    不変条件:
        - ``first_seen_tick >= 0``
        - ``last_seen_tick >= first_seen_tick``
        - ``count >= 1`` (1 度も遭遇していないなら record そのものが存在しない)

    例:
        >>> r = EncounterRecord.first(now_tick=10)
        >>> r.count, r.first_seen_tick, r.last_seen_tick
        (1, 10, 10)
        >>> r2 = r.observed_again(now_tick=42)
        >>> r2.count, r2.first_seen_tick, r2.last_seen_tick
        (2, 10, 42)
    """

    first_seen_tick: int
    last_seen_tick: int
    count: int

    def __post_init__(self) -> None:
        if not isinstance(self.first_seen_tick, int) or isinstance(
            self.first_seen_tick, bool
        ):
            raise EncounterRecordValidationException(
                "first_seen_tick must be int"
            )
        if not isinstance(self.last_seen_tick, int) or isinstance(
            self.last_seen_tick, bool
        ):
            raise EncounterRecordValidationException(
                "last_seen_tick must be int"
            )
        if not isinstance(self.count, int) or isinstance(self.count, bool):
            raise EncounterRecordValidationException("count must be int")
        if self.first_seen_tick < 0:
            raise EncounterRecordValidationException(
                f"first_seen_tick must be >= 0 (got {self.first_seen_tick})"
            )
        if self.last_seen_tick < self.first_seen_tick:
            raise EncounterRecordValidationException(
                f"last_seen_tick ({self.last_seen_tick}) must be >= "
                f"first_seen_tick ({self.first_seen_tick})"
            )
        if self.count < 1:
            raise EncounterRecordValidationException(
                f"count must be >= 1 (got {self.count})"
            )

    @property
    def is_first(self) -> bool:
        """初回遭遇 (= まだ 1 度しか見ていない) なら True。"""
        return self.count == 1

    def ticks_since_last(self, current_tick: int) -> int:
        """``current_tick`` までの最後の遭遇からの tick 数。

        ``current_tick < last_seen_tick`` (= 時系列が逆行) は呼出側の bug なので
        例外で表明する。
        """
        if not isinstance(current_tick, int) or isinstance(current_tick, bool):
            raise EncounterRecordValidationException("current_tick must be int")
        if current_tick < self.last_seen_tick:
            raise EncounterRecordRuleException(
                f"current_tick ({current_tick}) must be >= last_seen_tick "
                f"({self.last_seen_tick})"
            )
        return current_tick - self.last_seen_tick

    # ────────────────────────────────────────────────────────
    # Immutable update
    # ────────────────────────────────────────────────────────

    @classmethod
    def first(cls, *, now_tick: int) -> "EncounterRecord":
        """初回遭遇の record を生成する。

        ``count=1``, ``first_seen=last_seen=now_tick``。
        """
        return cls(
            first_seen_tick=now_tick,
            last_seen_tick=now_tick,
            count=1,
        )

    def observed_again(self, *, now_tick: int) -> "EncounterRecord":
        """再遭遇を反映した新しい record を返す (immutable update)。

        - ``last_seen_tick`` を ``now_tick`` に更新
        - ``count`` を +1
        - ``first_seen_tick`` は不変

        ``now_tick < last_seen_tick`` は時系列逆行なので業務ルール違反として
        例外を投げる。同 tick (``now_tick == last_seen_tick``) は許容する
        (= 同 tick 内で複数 observation が来た場合)。
        """
        if not isinstance(now_tick, int) or isinstance(now_tick, bool):
            raise EncounterRecordValidationException("now_tick must be int")
        if now_tick < self.last_seen_tick:
            raise EncounterRecordRuleException(
                f"now_tick ({now_tick}) must be >= last_seen_tick "
                f"({self.last_seen_tick})"
            )
        return EncounterRecord(
            first_seen_tick=self.first_seen_tick,
            last_seen_tick=now_tick,
            count=self.count + 1,
        )


__all__ = ["EncounterRecord"]
