"""版の違う episode_id が同じ being の中で共存しても壊れない。

出来事の同一性の付け方を変えたので (`#e2` 接尾辞つきの新方式)、過去 run の
snapshot から再開すると、**旧 id の episode と新 id の episode が同じ being に
並ぶ**。これは仕様で、断絶自体は避けられない。避けられるのは「混ざったせいで
壊れる」ことだけなので、そこを固定する。

実資産は 2026-08-14 時点で 58 ファイル・1,777 件 (var/runs 配下)。
"""
from __future__ import annotations
from datetime import datetime, timezone
from ai_rpg_world.application.llm.services.afterglow_store import make_afterglow_handle, resolve_episode_id_prefix_from_handle
from ai_rpg_world.application.llm.services.episode_identity import EPISODE_ID_VERSION_SUFFIX, is_current_version
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import InMemorySubjectiveEpisodeStore
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
_NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
_OLD_ID = 'c4d308e7-1492-5f29-b251-9c7214e77fe5'
_NEW_ID = f'89b0cfdb-0adb-52ae-908f-b3c1deada88b{EPISODE_ID_VERSION_SUFFIX}'

def _episode(episode_id: str, what: str) -> SubjectiveEpisode:
    return SubjectiveEpisode(episode_id=episode_id, player_id=1, being_id=BeingId('being_w1_p1'), occurred_at=_NOW, game_time_label='12:00', source=EpisodeSource(event_ids=('e1',)), location=EpisodeLocation(spot_id=42, tile_area_ids=()), action=EpisodeAction(tool_name='explore'), who=('レナ',), what=what, why='why', observed='observed', expected='expected', outcome='ok', prediction_error=None, felt='felt', interpreted='interpreted', cues=())

class TestBothVersionsLiveInOneStore:
    """旧 id と新 id の episode が同じ being に並んでも、取り違えない。"""

    def test_both_are_kept_as_separate_episodes(self) -> None:
        """版の違う 2 件は別の出来事として保持される (片方が消えない)。"""
        store = InMemorySubjectiveEpisodeStore()
        being = BeingId('being_w1_p1')
        store.put_by_being(being, _episode(_OLD_ID, '昔の出来事'))
        store.put_by_being(being, _episode(_NEW_ID, 'いまの出来事'))
        assert store.get_by_being(being, _OLD_ID).what == '昔の出来事'
        assert store.get_by_being(being, _NEW_ID).what == 'いまの出来事'

    def test_the_version_of_each_id_is_readable(self) -> None:
        """どちらの版で作られた id かを機械的に判別できる。"""
        assert not is_current_version(_OLD_ID)
        assert is_current_version(_NEW_ID)

class TestRecallByHandleWorksForBothVersions:
    """handle からの引き当ては、版が混ざっても正しい出来事を引く。"""

    def test_each_handle_resolves_to_its_own_episode(self) -> None:
        """旧 id と新 id のどちらの handle も、それぞれの episode を引く。

        handle は id の先頭 6 文字なので、**版を接尾辞にしている限り**
        両者は別の handle になる。接頭辞にしていたら、新 id の handle は
        全部同じ 3 文字を共有して衝突する。
        """
        store = InMemorySubjectiveEpisodeStore()
        being = BeingId('being_w1_p1')
        store.put_by_being(being, _episode(_OLD_ID, '昔の出来事'))
        store.put_by_being(being, _episode(_NEW_ID, 'いまの出来事'))
        found = {}
        for episode_id in (_OLD_ID, _NEW_ID):
            prefix = resolve_episode_id_prefix_from_handle(make_afterglow_handle(episode_id))
            matches = [episode for episode in store.list_recent_by_being(being, limit=10) if episode.episode_id.startswith(prefix)]
            assert len(matches) == 1, f'{episode_id} の handle が一意に引けない'
            found[episode_id] = matches[0].what
        assert found[_OLD_ID] == '昔の出来事'
        assert found[_NEW_ID] == 'いまの出来事'

    def test_the_new_handle_is_built_from_the_uuid_not_the_version(self) -> None:
        """新 id の handle は uuid 部分から作られる (版が桁を食っていない)。"""
        handle = make_afterglow_handle(_NEW_ID)
        assert handle == 'ep_89b0cf'
        assert EPISODE_ID_VERSION_SUFFIX not in handle
