"""非同期配送の設定を profile と同じ解決入口で検証する。"""

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig


def test_profile_can_set_async_delivery_limits() -> None:
    """スレッド数・未反映件数・終了待ちを指定すると、解決済み設定と trace の値に残る。"""
    config = ResolvedLlmRuntimeConfig.from_mapping(values={
        "ASYNC_EVENT_WORKERS": "3", "ASYNC_EVENT_MAX_PENDING": "7", "ASYNC_EVENT_SHUTDOWN_TIMEOUT_SECONDS": "0.5",
    })
    assert (config.async_event_workers, config.async_event_max_pending, config.async_event_shutdown_timeout_seconds) == (3, 7, .5)
    assert config.to_trace_dict()["async_event_workers"] == 3


def test_defaults_are_two_workers_one_hundred_jobs_and_ten_seconds() -> None:
    """設定を省略すると、2スレッド・未反映100件・終了待ち10秒を使う。"""
    config = ResolvedLlmRuntimeConfig.from_mapping(values={})
    assert (config.async_event_workers, config.async_event_max_pending, config.async_event_shutdown_timeout_seconds) == (2, 100, 10)


@pytest.mark.parametrize("key,value", [
    ("ASYNC_EVENT_WORKERS", "0"), ("ASYNC_EVENT_WORKERS", "-1"),
    ("ASYNC_EVENT_MAX_PENDING", "0"), ("ASYNC_EVENT_MAX_PENDING", "1.5"),
    ("ASYNC_EVENT_SHUTDOWN_TIMEOUT_SECONDS", "-1"), ("ASYNC_EVENT_SHUTDOWN_TIMEOUT_SECONDS", "nan"),
    ("ASYNC_EVENT_SHUTDOWN_TIMEOUT_SECONDS", "inf"), ("ASYNC_EVENT_WORKER", "2"),
])
def test_invalid_or_unknown_profile_setting_is_rejected(key, value) -> None:
    """無効な件数や待ち時間、未知のキーを指定すると、解決時に拒否する。"""
    with pytest.raises(ValueError):
        ResolvedLlmRuntimeConfig.from_mapping(values={key: value})


@pytest.mark.parametrize("overrides", [
    {"async_event_workers": True}, {"async_event_max_pending": 0},
    {"async_event_shutdown_timeout_seconds": float("nan")},
])
def test_direct_construction_also_validates_settings(overrides) -> None:
    """直接の構築でも、不正な非同期の設定は拒否する。"""
    with pytest.raises(ValueError):
        ResolvedLlmRuntimeConfig.for_tests(**overrides)
