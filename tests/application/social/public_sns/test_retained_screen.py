"""公開SNS画面は取得時の内容を予算内で保持し、明示的な終了で消える。"""
from datetime import datetime, timezone

from ai_rpg_world.application.common.execution_provenance import ExecutionProvenance
from ai_rpg_world.application.social.public_sns.contracts import PublicSnsContentDto, PublicSnsPage
from ai_rpg_world.application.social.public_sns.retained_screen import MAX_SCREEN_CHARS, PublicSnsScreenStore


def test_screen_is_bounded_and_keeps_source_and_targets():
    """長い本文があっても表示上限を超えず、対象識別子と実行の出典を保持する。"""
    source = ExecutionProvenance('execution-1', 1, 3, 'provider-call', None)
    rows = tuple(PublicSnsContentDto(f'post-{i}', 'post', '作者', '文' * 9000, datetime.now(timezone.utc), 'author-1') for i in range(10))
    store = PublicSnsScreenStore()
    screen = store.show(1, 'posts', PublicSnsPage(rows, 'next-page'), source)
    assert len(screen.text) <= MAX_SCREEN_CHARS
    assert 'post-9' in screen.text
    assert 'next-page' in screen.text
    assert screen.provenance == source
    assert '省略' in screen.text
    assert 'execution-1' not in screen.text


def test_screen_round_trip_and_close():
    """保存と復元で画面と出典が残り、close後は当人の画面だけ消える。"""
    source = ExecutionProvenance('execution-1', 1, 3)
    store = PublicSnsScreenStore()
    store.show(1, 'posts', PublicSnsPage(()), source)
    restored = PublicSnsScreenStore()
    restored.restore(store.capture())
    assert restored.get(1) == store.get(1)
    restored.close(1)
    assert restored.get(1) is None
