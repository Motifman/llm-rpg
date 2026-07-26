"""同席者行の対人 action が、その相手に**いま使えるものだけ**になることを保証する。

## なぜ

`take` は倒れている相手にしか使えないのに、**立っている相手の行にも出ていた**。
action ラベルが snapshot 単位の 1 本のタプルで、全員の行に同じ一覧が出るため。

v4 第 3 回 run では take が 16 回すべて失敗し (全部「相手は動いている。奪えない」)、
interact 失敗 77 件の主因になった。医師のエイダが仲間の腕を「診よう」として
take を誤射する、という質的な壊れ方もしている。

## ゲートの不変条件

**ゲートの入力は、その行に既に見えている事実の部分集合でなければならない。**

見えていない事実でゲートすると、ラベルの有無そのものが情報漏れになる。
「crew にしか使えない action が出ている = あの人は crew だ」と読めてしまう。

| 対象の状態 | 公開性 | 扱い |
|---|---|---|
| 行動不能 (`is_down` / `is_dead`) | 行に既に出ている | ゲートに使う |
| 役割 (`TARGET_PLAYER_STATE_IS`) | **秘匿** | 使わない。実行時に失敗して学ばせる |
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DARKENED_STATION = _REPO_ROOT / "data" / "scenarios" / "darkened_station.json"

_MORI = PlayerId(1)   # crew
_SENA = PlayerId(2)   # crew
_KUZE = PlayerId(3)   # keeper


def _row_for(runtime, viewer: PlayerId, target_name: str) -> str:
    """viewer から見た prompt のうち、target の同席者行を返す。"""
    from ai_rpg_world.application.llm.services._label_allocator import LabelAllocator
    from ai_rpg_world.application.llm.services._runtime_target_collector import (
        RuntimeTargetCollector,
    )
    from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
        SpotGraphUiContextBuilder,
    )

    snapshot = runtime._state_builder.build_snapshot(int(viewer))
    lines: list[str] = []
    SpotGraphUiContextBuilder()._build_entity_section(
        snapshot, LabelAllocator(), RuntimeTargetCollector(), lines
    )
    matched = [line for line in lines if target_name in line]
    assert matched, f"{target_name} の行が見つからない: {lines}"
    return matched[0]


@pytest.fixture()
def runtime(tmp_path: Path):
    """三人を同じスポットに揃えた runtime。"""
    scenario = json.loads(_DARKENED_STATION.read_text(encoding="utf-8"))
    path = tmp_path / "station.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")

    rt = create_world_runtime(path)
    graph = rt._spot_graph_repo.find_graph()
    spot = graph.get_entity_spot(EntityId.create(int(_MORI)))
    for pid in (_SENA, _KUZE):
        graph.unplace_entity(EntityId.create(int(pid)))
        graph.place_entity(EntityId.create(int(pid)), spot)
    rt._spot_graph_repo.save(graph)
    return rt


def _knock_down(runtime, player_id: PlayerId) -> None:
    status = runtime._player_status_repo.find_by_id(player_id)
    status.apply_damage(status.hp.value)
    runtime._player_status_repo.save(status)


class TestIncapacitatedOnlyActionsAreGated:
    """倒れている相手にしか使えない action は、その行にだけ出る。"""

    def test_standing_target_row_has_no_take(self, runtime) -> None:
        """立っている相手の行に take が出ない。

        出ていたぶんが v4 第 3 回 run の take 16 回全失敗になった。
        """
        assert "take" not in _row_for(runtime, _MORI, "セナ")

    def test_downed_target_row_has_take(self, runtime) -> None:
        """倒れている相手の行には take が出る。

        まったく出さないと、対人行為が宣言されていても発見されない。
        使える相手の行にだけ出すのが要件。
        """
        _knock_down(runtime, _SENA)

        assert "take" in _row_for(runtime, _MORI, "セナ")

    def test_gating_is_per_row_not_per_snapshot(self, runtime) -> None:
        """同じ prompt の中で、行ごとに違う一覧が出る。

        snapshot 単位の 1 本のタプルだと、ここが必ず同じになる。
        """
        _knock_down(runtime, _SENA)

        downed_row = _row_for(runtime, _MORI, "セナ")
        standing_row = _row_for(runtime, _MORI, "クゼ")

        assert "take" in downed_row
        assert "take" not in standing_row


class TestHiddenStateIsNotUsedForGating:
    """秘匿の状態でゲートしない (ラベルの有無から漏らさない)。"""

    def test_role_gated_action_appears_on_every_standing_row(self, runtime) -> None:
        """役割で絞られる action は、役割にかかわらず同じように出る。

        `strike_down` は `TARGET_PLAYER_STATE_IS {role: crew}` を持つ。
        crew の行にだけ出すと、**ラベルの有無が「あの人は crew だ」を
        漏らす**。誰が crew かは会議で推理する対象であって、prompt が
        教えるものではない。
        """
        crew_row = _row_for(runtime, _KUZE, "セナ")     # role=crew
        keeper_row = _row_for(runtime, _MORI, "クゼ")   # role=keeper

        assert ("strike_down" in crew_row) == ("strike_down" in keeper_row)


class TestBuiltInPlayerToolsAreDiscoverable:
    """組み込みの対人 tool も同じ行に出す。

    行の ``[...]`` に出ていたのは **シナリオ宣言の player_interactions だけ**で、
    組み込みの `tend_to_player` は入っていなかった。

    v4 第 3 回 run で医師のエイダが「システム上プレイヤーへの interact は take
    しか定義されていない」と推論したのは、**彼女から見て正確な観察**だった。
    行の一覧を「この人にできることの全集合」と読むのは自然で、実際そう読める
    形になっている。take をゲートするだけだと、彼女の行には何も残らず
    「人には何もできない」と読めてしまう。
    """

    def test_downed_target_row_offers_tending(self, runtime) -> None:
        """倒れている相手の行に tend_to_player が出る。"""
        _knock_down(runtime, _SENA)

        assert "tend_to_player" in _row_for(runtime, _MORI, "セナ")

    def test_standing_target_row_does_not(self, runtime) -> None:
        """立っている相手には出ない (介抱する対象ではない)。"""
        assert "tend_to_player" not in _row_for(runtime, _MORI, "セナ")
