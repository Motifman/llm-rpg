"""出来事の同一性を、prompt の見た目に依存させない。

## なぜこのテストが要るか

`episode_id` は fingerprint の uuid5 で、そこに**描画済みの直近の出来事
テキスト**が入っていた。つまり「行動履歴に呼び出し形式を併記する」
(`c051a47a`) のような**表示の変更が、同じ出来事の id を変えていた**。

いまはどの経路も id を再計算しないので壊れていない (snapshot は id を素通し、
主観補完は draft の id を持ち回る)。壊れるのは再エンコードを伴う機能
(replay / バックフィル / 版を跨ぐ分析) を足したときで、そのとき気付ける
保証が無い。だから同一性の材料を先に structural な値だけへ絞る。

版は接尾辞 `#e2` で示す。**接頭辞にはしない** — afterglow の handle は
`episode_id` の先頭 6 文字から作られるので、先頭を版で潰すと handle の
エントロピーが 3 文字になり、想起が別の出来事を引き当てる。
"""
from __future__ import annotations
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from datetime import datetime, timezone
from typing import Any, Tuple
from ai_rpg_world.application.llm.contracts.chunk_encoding import build_chunk_encoding_input
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto, ToolRuntimeContextDto
from ai_rpg_world.application.llm.services.action_episode_draft_builder import ActionEpisodeDraftBuilder
from ai_rpg_world.application.llm.services.action_result_store import ActionResultEntry
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import ChunkEpisodeDraftBuilder
from ai_rpg_world.application.llm.services.episode_identity import EPISODE_ID_VERSION_SUFFIX
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
_T0 = datetime(2026, 7, 5, 9, 0, tzinfo=timezone.utc)

def _action(summary: str='explore(浜辺)', result: str='何も見つからなかった') -> ActionResultEntry:
    return ActionResultEntry(action_summary=summary, result_summary=result, occurred_at=_T0, tool_name='explore')

def _observation(prose: str) -> ObservationEntry:
    return ObservationEntry(occurred_at=_T0, output=ObservationOutput(prose=prose, structured={'type': 'x'}, observation_category='environment'), game_time_label=None)

def _chunk_episode_id(*, prose: str='砂浜には何もなかった', action: ActionResultEntry | None=None) -> str:
    """チャンクを 1 つ閉じ、その episode_id を返す。

    ``prose`` と行動の要約文は、どちらも「直近の出来事」として prompt へ
    描画される値。**同一性の材料にしてはいけない側**なので、ここを振って
    id が動かないことを見る。
    """
    inp = build_chunk_encoding_input(PlayerId(1), (_observation(prose),), (action or _action(),))
    return ChunkEpisodeDraftBuilder().build(inp, being_id=BeingId('being-test')).episode_id

def _action_episode_id(**overrides: Any) -> str:
    """1 行動ぶんのエピソードを組み、その episode_id を返す。"""
    args = {'player_id': 1, 'being_id': BeingId('being-test'), 'occurred_at': _T0, 'tool_name': 'interact', 'canonical_arguments': {'intention': '箱の中身を確かめる'}, 'runtime_context': ToolRuntimeContextDto(targets={}, current_spot_id=7), 'command_result': LlmCommandResultDto(success=True, message='開封に成功した。'), 'action_summary': '宝箱を調べた', 'result_summary': '開封に成功した。', 'episodic_cues': ()}
    args.update(overrides)
    return ActionEpisodeDraftBuilder().build(**args).episode_id

class TestRenderingDoesNotChangeIdentity:
    """表示を変えても、同じ出来事は同じ id のままになる。"""

    def test_the_same_input_yields_the_same_id(self) -> None:
        """同じ入力からは何度組み立てても同じ id になる (決定論)。"""
        assert _chunk_episode_id() == _chunk_episode_id()

    def test_rewording_an_observation_keeps_the_id(self) -> None:
        """「直近の出来事」に載る観測文を書き換えても id は変わらない。

        c051a47a (行動履歴に呼び出し形式を併記する) や 5cf1b9b4 (時刻ラベルの
        削除) は、まさにこの文面を変えて id を変えていた。
        """
        before = _chunk_episode_id(prose='砂浜には何もなかった')
        after = _chunk_episode_id(prose='[昨日] 砂浜には何もなかった / 呼び出し: explore()')
        assert before == after

    def test_rewording_the_result_summary_keeps_the_id(self) -> None:
        """行動結果の要約文を書き換えても id は変わらない (結果の要約は表示文)。"""
        before = _chunk_episode_id(action=_action(result='何も見つからなかった'))
        after = _chunk_episode_id(action=_action(result='収穫はなかった'))
        assert before == after

    def test_rewording_a_tool_message_keeps_the_action_episode_id(self) -> None:
        """行動エピソードも、ツール結果の文面を書き換えただけでは id が変わらない。"""
        before = _action_episode_id(command_result=LlmCommandResultDto(success=True, message='開封に成功した。'))
        after = _action_episode_id(command_result=LlmCommandResultDto(success=True, message='蓋が開いた。'))
        assert before == after

class TestIdentityStillSeparatesDifferentEvents:
    """材料を削っても、別の出来事は別の id になる。"""

    def test_a_different_player_gets_a_different_id(self) -> None:
        """別のプレイヤーの同時刻の行動は、別の id になる。"""
        assert _action_episode_id(player_id=1) != _action_episode_id(player_id=2)

    def test_a_different_time_gets_a_different_id(self) -> None:
        """時刻が違えば別の id になる。"""
        later = datetime(2026, 7, 5, 9, 30, tzinfo=timezone.utc)
        assert _action_episode_id() != _action_episode_id(occurred_at=later)

    def test_a_different_tool_gets_a_different_id(self) -> None:
        """使った道具が違えば別の id になる。"""
        assert _action_episode_id() != _action_episode_id(tool_name='explore')

    def test_success_and_failure_are_different_events(self) -> None:
        """同じ道具でも、成功と失敗は別の出来事として区別される。"""
        failed = LlmCommandResultDto(success=False, message='開封に成功した。', error_code='LOCKED')
        assert _action_episode_id() != _action_episode_id(command_result=failed)

class TestTheVersionIsVisibleAndMachineReadable:
    """新方式の id は、旧 id と見分けられる。"""

    def test_new_ids_carry_the_version_suffix(self) -> None:
        """新しく作られた id は版の接尾辞で終わる。"""
        assert _chunk_episode_id().endswith(EPISODE_ID_VERSION_SUFFIX)
        assert _action_episode_id().endswith(EPISODE_ID_VERSION_SUFFIX)

    def test_old_ids_are_distinguishable(self) -> None:
        """旧 id (接尾辞なし) と新 id を機械的に区別できる。"""
        old = 'c4d308e7-1492-5f29-b251-9c7214e77fe5'
        assert not old.endswith(EPISODE_ID_VERSION_SUFFIX)
        assert _chunk_episode_id().endswith(EPISODE_ID_VERSION_SUFFIX)

    def test_the_version_does_not_eat_the_handle_entropy(self) -> None:
        """版は接尾辞なので、handle (先頭 6 文字) は uuid 部分から作られる。

        接頭辞にすると handle は全部 `ep_e2-…` になり、実質 3 文字しか残らない。
        1 being あたり数十件の episode で誕生日衝突が起き、想起が別の出来事を
        引き当てる。
        """
        from ai_rpg_world.application.llm.services.afterglow_store import make_afterglow_handle
        ids = {_action_episode_id(player_id=pid, occurred_at=datetime(2026, 7, 5, 9, minute, tzinfo=timezone.utc)) for pid in range(1, 11) for minute in range(0, 30)}
        handles = {make_afterglow_handle(i) for i in ids}
        assert len(ids) == 300
        assert len(handles) == len(ids), f'handle が衝突している。版が id の先頭を潰していないか (id {len(ids)} 件に対し handle {len(handles)} 件)'
