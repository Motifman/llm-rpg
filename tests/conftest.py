import pytest

_LIVE_API_TIMEOUT_SECONDS = 120


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.get_closest_marker("live_api") and not item.get_closest_marker("timeout"):
            item.add_marker(pytest.mark.timeout(_LIVE_API_TIMEOUT_SECONDS))
