"""InMemory repo が集約保存/取得時に未 publish のドメインイベントを持ち越さないことを固定する。

規約変更 (B): リポジトリは「状態」を永続化するものであり、「未 publish のドメイン
イベント queue」は永続化対象ではない。旧実装は deepcopy がイベントごと集約を
canonical に焼き付け、後続の ``find_by_id → get_events → publish`` (speak / interact
など) が既に publish 済みのイベントを拾って再放出していた。実 run
v3coop_stagnation_003 では 1 個の PlayerRevivedEvent が 46 tick / 141 観測に増幅し
記憶を汚染した (silent failure)。

本テストは ``_clone`` チョークポイント (save/find が通る) で必ずイベントが drain
されることを保証する。ドメインイベントの publish は emission サイトや UnitOfWork が
「原本 (save に渡した集約)」から行う経路が担っており、そこは壊さない。
"""

from __future__ import annotations

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from tests.domain.player.aggregate.test_player_status_aggregate import (
    create_test_status_aggregate,
)


class TestInMemoryRepositoryDrainsPendingEvents:
    """save/find が返す・格納する集約は未 publish のドメインイベントを持たない。"""

    def test_saved_aggregate_is_stored_without_pending_events(self) -> None:
        """イベントを持つ集約を (clear せず) save しても、canonical には残らない。"""
        repo = InMemoryPlayerStatusRepository()
        agg = create_test_status_aggregate(player_id=1, hp=100)
        agg.apply_damage(9999)  # HP 0 → 戦闘不能 + PlayerDownedEvent
        assert agg.get_events(), "前提: 原本にはイベントが積まれている"

        repo.save(agg)  # save→clear の逆順 (buggy 呼び出し) を模しても canonical は汚れない

        refetched = repo.find_by_id(PlayerId(1))
        assert refetched is not None
        assert refetched.get_events() == []

    def test_revive_event_not_refetched(self) -> None:
        """復帰イベントを持つ集約を save→find し直しても、そのイベントは再取得されない。

        再放出バグの核心: canonical が PlayerRevivedEvent を保持し続けると、次に
        find した集約が get_events でそれを拾い publish して観測を汚す。
        """
        repo = InMemoryPlayerStatusRepository()
        agg = create_test_status_aggregate(player_id=1, hp=100)
        agg.apply_damage(9999)  # down
        agg.clear_events()
        agg.revive(hp_recovery_rate=0.4)  # PlayerRevivedEvent
        assert any(
            type(e).__name__ == "PlayerRevivedEvent" for e in agg.get_events()
        ), "前提: 原本に PlayerRevivedEvent がある"

        repo.save(agg)

        refetched = repo.find_by_id(PlayerId(1))
        assert refetched is not None
        assert refetched.get_events() == []

    def test_save_does_not_mutate_caller_original_events(self) -> None:
        """save は格納 clone だけを drain し、呼び出し元が渡した原本の events は触らない。

        emission サイト / UnitOfWork は save に渡した「原本」から get_events して
        publish する。ここを壊すと本番のイベント配信が止まるので固定する。
        """
        repo = InMemoryPlayerStatusRepository()
        agg = create_test_status_aggregate(player_id=1, hp=100)
        agg.apply_damage(9999)
        repo.save(agg)
        # 原本はイベントを保持したまま (caller が publish→clear する契約)
        assert any(type(e).__name__ == "PlayerDownedEvent" for e in agg.get_events())
