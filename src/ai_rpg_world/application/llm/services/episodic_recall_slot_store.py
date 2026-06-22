"""想起スロット (working memory slot) — #526 後続 段階 3。

# 何のため

passive recall を毎 tick 独立に再計算する従来方式から、**前 tick で recall した
episode の一部を持ち越す** working memory 風の方式へ移行するための store。

狙いは 3 つ:

1. **想起の長続き**: 一度想起された episode が数 tick 居続けるので、
   recall section が tick 間で安定する → prefix cache が効きやすい
2. **想起数の上限**: スロット容量 N で recall section の太りを抑える
3. **構造的な慣化**: 滞在期間 L を超えた entry は強制退去 + クールダウン C
   の間は候補から外す (= 慣化を「score 減点」から「除外」に格上げ)

# 設計判断

- ``apply_slot_policy`` は純関数で境界値テスト可能。store は (1) prev_slot /
  cooldown を読み (2) decision を計算外で受けて apply するだけ
- in-memory のみ。permanent な being snapshot を汚さず、experiment run の
  単位でリセットされる
- 既存 ``IEpisodicRecallHabituationStore`` とは独立した sidecar として共存
  (slot enable 時は habituation を off にする運用を想定するが、コードレベルでは
  どちらも有効でも動く)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Dict, Optional, Protocol, runtime_checkable

from ai_rpg_world.domain.being.value_object.being_id import BeingId


@dataclass(frozen=True)
class RecallSlotEntry:
    """スロットに居る 1 episode。``entered_tick`` は最大滞在期間 L の判定に使う。"""

    episode_id: str
    entered_tick: int


@dataclass(frozen=True)
class RecallSlotPolicy:
    """スロット運用の 4 パラメータ。

    - ``capacity`` (N): 同時に意識に上る記憶の上限
    - ``insert_per_tick`` (K_insert): 1 tick で新規に挿入できる上限。残り
      ``capacity - K_insert`` 枠は前 tick から持ち越し (prefix cache 親和性)
    - ``max_residence`` (L): 1 episode が居続けられる tick 数。超えたら強制退去
    - ``cooldown_ticks`` (C): 退去後、再入できない tick 数
    """

    capacity: int
    insert_per_tick: int
    max_residence: int
    cooldown_ticks: int
    # 新規挿入の最小スコア (= multi_cue_score、cue 軸でマッチした distinct
    # canonical 数)。これ未満の候補は slot に入らない。default 2 は「2 軸以上
    # で当たった episode だけを鮮明な記憶として扱う」方針。0 で閾値無効化。
    # 弱い候補も後段の Afterglow index に乗ることで「ぼんやり覚えてる」状態
    # を表現できるようにし、slot は「希少資源」として強い signal だけが入る。
    insert_score_threshold: int = 2

    def __post_init__(self) -> None:
        for name in (
            "capacity",
            "insert_per_tick",
            "max_residence",
            "cooldown_ticks",
            "insert_score_threshold",
        ):
            v = getattr(self, name)
            if not isinstance(v, int) or isinstance(v, bool):
                raise TypeError(f"{name} must be int")
            if v < 0:
                raise ValueError(f"{name} must be 0 or greater")
        if self.insert_per_tick > self.capacity:
            raise ValueError(
                "insert_per_tick must be <= capacity "
                f"(got insert_per_tick={self.insert_per_tick}, capacity={self.capacity})"
            )


@dataclass(frozen=True)
class RecallSlotDecision:
    """1 tick のスロット更新内容。

    - ``retained``: 前 tick から持ち越した entry (順序保持)
    - ``inserted``: 今 tick で新規に入った entry
    - ``evicted_ids``: 今 tick で退去した episode_id (滞在期間超過のみ。
      新規が押し出すケースは含まない設計)
    - ``new_slot``: retained + inserted を順序保持で連結したもの。これが
      この tick で recall section に出す最終並び
    """

    retained: tuple[RecallSlotEntry, ...]
    inserted: tuple[RecallSlotEntry, ...]
    evicted_ids: tuple[str, ...]
    new_slot: tuple[RecallSlotEntry, ...]


def apply_slot_policy(
    *,
    prev_slot: Sequence[RecallSlotEntry],
    candidate_episode_ids_in_score_order: Sequence[str | tuple[str, int]],
    cooldown_until: Mapping[str, int],
    current_tick: int,
    policy: RecallSlotPolicy,
) -> RecallSlotDecision:
    """前 tick のスロット + 新規候補 + クールダウン状態から、今 tick の
    スロットを決定する純関数。

    アルゴリズム:

    1. ``prev_slot`` のうち滞在期間が L を超えたものを退去 (= evicted)。
       他は ``retained`` として順序保持
    2. 候補から ``retained`` と ``cooldown_until[eid] > current_tick`` のものを除く
    3. 空き枠 ``capacity - len(retained)`` と ``insert_per_tick`` の小さい方の数だけ、
       score 順に新規挿入。``insert_score_threshold`` 未満の score は除外
       (ペアでない素の ``str`` が渡されたら閾値判定を skip = 後方互換)
    4. ``new_slot`` = retained + inserted (順序保持)

    新規が高 score でも既存の retained を押し出さない (= prefix cache 重視)。
    候補は ``(episode_id, score)`` ペアでも素の ``str`` でも受け取れる。
    閾値を効かせたい呼び出し側はペア形式で渡す。
    """
    if not isinstance(current_tick, int) or isinstance(current_tick, bool):
        raise TypeError("current_tick must be int")
    if current_tick < 0:
        raise ValueError("current_tick must be 0 or greater")

    retained: list[RecallSlotEntry] = []
    evicted: list[str] = []
    for e in prev_slot:
        age = current_tick - e.entered_tick
        if age < 0:
            # 異常: 未来の entered_tick — 退去扱いで安全側に倒す
            evicted.append(e.episode_id)
            continue
        if age >= policy.max_residence:
            evicted.append(e.episode_id)
            continue
        retained.append(e)

    retained_ids = {e.episode_id for e in retained}
    # 同 tick で evict された episode は cooldown が反映される前でも候補から
    # 外す (= 退去直後の即時再入を防ぐ)。apply_decision で cooldown_until が
    # 書かれた後の tick からは ``cooldown_until`` の check で同じ判定が走る。
    evicted_set = set(evicted)

    free_slots = max(0, policy.capacity - len(retained))
    max_inserts = min(free_slots, policy.insert_per_tick)
    inserted: list[RecallSlotEntry] = []
    seen_inserted: set[str] = set()

    def _try_insert(*, ignore_threshold: bool) -> None:
        """候補列を 1 周して入れられるものを ``inserted`` に積む。

        ``ignore_threshold=True`` のときは score 閾値を無視する fallback。
        retained が空かつ閾値 pass の候補が 1 件も無い場合だけ呼び、
        slot が完全に空になるのを救済する。
        """
        for raw in candidate_episode_ids_in_score_order:
            if len(inserted) >= max_inserts:
                return
            if isinstance(raw, tuple):
                eid, score = raw
            else:
                eid, score = raw, None
            if eid in retained_ids or eid in seen_inserted or eid in evicted_set:
                continue
            if (
                not ignore_threshold
                and score is not None
                and policy.insert_score_threshold > 0
                and score < policy.insert_score_threshold
            ):
                continue
            # cooldown 中なら除外。current_tick >= cooldown_until で復帰
            cd = cooldown_until.get(eid)
            if cd is not None and current_tick < cd:
                continue
            inserted.append(
                RecallSlotEntry(episode_id=eid, entered_tick=current_tick)
            )
            seen_inserted.add(eid)

    _try_insert(ignore_threshold=False)
    # retained が空 + 閾値 pass の候補も 0 件のときだけ、弱い候補の救済挿入
    # を許す。retained が居るならその「鮮明な記憶」を弱い候補で水で薄めない。
    if not inserted and not retained:
        _try_insert(ignore_threshold=True)

    new_slot = tuple(retained) + tuple(inserted)
    return RecallSlotDecision(
        retained=tuple(retained),
        inserted=tuple(inserted),
        evicted_ids=tuple(evicted),
        new_slot=new_slot,
    )


@runtime_checkable
class IEpisodicRecallSlotStore(Protocol):
    """being ごとに「現在のスロット + クールダウン table」を保持する sidecar。

    実装は being ごとに隔離されること。
    """

    def get_slot(self, being_id: BeingId) -> tuple[RecallSlotEntry, ...]:
        """前 tick のスロット内容を返す。未記録なら空 tuple。"""
        ...

    def get_cooldown_until(self, being_id: BeingId) -> Mapping[str, int]:
        """退去済 episode の「再入可能になる tick」を episode_id → tick で返す。

        空 dict を返してよい (= クールダウン無し)。
        """
        ...

    def apply_decision(
        self,
        being_id: BeingId,
        decision: RecallSlotDecision,
        *,
        current_tick: int,
        cooldown_ticks: int,
    ) -> None:
        """1 tick 分の decision を反映する。

        - スロット内容を ``decision.new_slot`` で置き換える
        - ``decision.evicted_ids`` のそれぞれに対し
          ``cooldown_until[eid] = current_tick + cooldown_ticks`` を設定
        """
        ...


class InMemoryEpisodicRecallSlotStore(IEpisodicRecallSlotStore):
    """プロセスメモリ常駐の sidecar 実装。experiment run の単位で破棄される。

    being ごとに ``(slot, cooldown_until)`` を保持。
    """

    def __init__(self) -> None:
        self._slot_by_being: Dict[BeingId, tuple[RecallSlotEntry, ...]] = {}
        self._cooldown_by_being: Dict[BeingId, Dict[str, int]] = {}

    def get_slot(self, being_id: BeingId) -> tuple[RecallSlotEntry, ...]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        return self._slot_by_being.get(being_id, ())

    def get_cooldown_until(self, being_id: BeingId) -> Mapping[str, int]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        return dict(self._cooldown_by_being.get(being_id, {}))

    def apply_decision(
        self,
        being_id: BeingId,
        decision: RecallSlotDecision,
        *,
        current_tick: int,
        cooldown_ticks: int,
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(current_tick, int) or isinstance(current_tick, bool):
            raise TypeError("current_tick must be int")
        if current_tick < 0:
            raise ValueError("current_tick must be 0 or greater")
        if not isinstance(cooldown_ticks, int) or isinstance(cooldown_ticks, bool):
            raise TypeError("cooldown_ticks must be int")
        if cooldown_ticks < 0:
            raise ValueError("cooldown_ticks must be 0 or greater")

        self._slot_by_being[being_id] = tuple(decision.new_slot)
        if cooldown_ticks > 0 and decision.evicted_ids:
            cd_map = self._cooldown_by_being.setdefault(being_id, {})
            until = current_tick + cooldown_ticks
            for eid in decision.evicted_ids:
                # 同 episode が再 evict されたら最新 cooldown で上書き
                cd_map[eid] = until


__all__ = [
    "RecallSlotEntry",
    "RecallSlotPolicy",
    "RecallSlotDecision",
    "apply_slot_policy",
    "IEpisodicRecallSlotStore",
    "InMemoryEpisodicRecallSlotStore",
]

_ = Optional  # re-export hint for future use
