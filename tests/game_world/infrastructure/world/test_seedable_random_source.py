from __future__ import annotations

from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource


def _draw(source: SeedableRandomSource, count: int) -> list[float]:
    return [source.next_fraction() for _ in range(count)]


class TestSeedableRandomSource:
    """SeedableRandomSource が、シードで並びを決め、0 以上 1 未満の値を返すことを保証する。"""

    def test_same_seed_draws_same_fractions_within_zero_to_one(self) -> None:
        """同じシードの 2 つは同じ並びを返し、どの値も 0 以上 1 未満に収まる。"""
        first = _draw(SeedableRandomSource(seed=42), 100)
        second = _draw(SeedableRandomSource(seed=42), 100)

        assert first == second
        assert all(0.0 <= fraction < 1.0 for fraction in first)

    def test_without_seed_two_sources_draw_different_fractions(self) -> None:
        """シードを渡さない 2 つは、違う並びを返す。"""
        first = _draw(SeedableRandomSource(), 10)
        second = _draw(SeedableRandomSource(), 10)

        assert first != second
