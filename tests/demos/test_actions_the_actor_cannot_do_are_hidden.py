"""自分にできない対人行為が、同席者行に出ないことを保証する。

## 何が起きていたか

クルーの観測に、同席者ごとに毎ターンこれが並んでいた。

    - "セナ" [背後から襲う (strike_down・暗い場所のみ・解体用カッターが要る)]
    - "クゼ" [背後から襲う (strike_down・暗い場所のみ・解体用カッターが要る)]
    - "アオイ" [背後から襲う (strike_down・暗い場所のみ・解体用カッターが要る)]

実行すれば「あなたにそんな真似はできない。」で必ず失敗する。「選べるのに
必ず失敗する手を並べない」(#860) に真正面から反していた。しかも
**クルーに「自分は人を殺せる」と誤解させる**。

## なぜ漏れたか

オブジェクトへの行動は候補を組む段階で ``PLAYER_STATE_IS`` を見ている
(keeper に本物の点検が出ないのはそのため)。対人行為だけ見ていなかった。

原因は #860 の設計そのものにある。``_is_offerable`` は「その行に見えて
いる公開事実」しか受け取らない形にしてあり、対象の秘密を守る仕組みとして
強い。**その締め出しが、行動者自身の情報にまで及んでいた。**

自分の役割は自分が知っている事実なので、これで絞っても何も漏れない。

## 守り続けるべき境界

行動者自身の状態 (``PLAYER_STATE_IS``) と、対象の状態
(``TARGET_PLAYER_STATE_IS``) は**別の軸**。後者で候補を絞ると、ラベルの
有無から誰がクルーかが読めてしまう。このファイルはその境界も見張る。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.player_interaction_application_service import (  # noqa: E501
    PlayerInteractionApplicationService,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI = PlayerId(1)   # crew
_KUZE = PlayerId(3)   # keeper

#: 全員が集会室に居る状態で観測すれば、同席者行が 3 人ぶん出る。
_KILL_LABEL = "背後から襲う"


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _rows_offering_the_kill(runtime, player_id: PlayerId) -> list[str]:
    return [
        line.strip()
        for line in runtime.build_observation(player_id).splitlines()
        if _KILL_LABEL in line
    ]


class TestTheKillIsOnlyOfferedToWhoCanDoIt:
    """殺せる者にだけ出る。"""

    def test_a_crew_member_is_not_offered_the_kill(self, runtime) -> None:
        """クルーの同席者行に「背後から襲う」が出ない。"""
        assert _rows_offering_the_kill(runtime, _MORI) == []

    def test_the_impostor_is_still_offered_the_kill(self, runtime) -> None:
        """インポスターには今までどおり出る。

        消しすぎると殺しそのものが発見されなくなる。宣言されていても
        行動一覧に出なければ、LLM からは存在しないのと同じ。
        """
        # 人数を焼き付けない。**シナリオに人を足すたびに落ちる**のは、
        # このテストが見たいこと (襲えるのはインポスターだけか) と関係が無い。
        crew_count = sum(
            1
            for p in runtime.scenario.player_spawns
            if p.initial_state.get("role") == "crew"
        )

        assert len(_rows_offering_the_kill(runtime, _KUZE)) == crew_count

    def test_the_hints_survive_for_the_impostor(self, runtime) -> None:
        """インポスター側では前提条件のヒントも残る。

        「暗い場所でだけ襲える」が消えると、失敗して初めて分かる形に戻る。
        """
        row = _rows_offering_the_kill(runtime, _KUZE)[0]

        assert "暗い場所のみ" in row
        assert "解体用カッター" in row


class TestTheRestOfTheRowIsUntouched:
    """同席者行の他の要素は変わらない。"""

    def test_the_names_are_still_listed(self, runtime) -> None:
        """同席者の名前は今までどおり並ぶ。

        行ごと消えると、誰が居るのか分からなくなる。
        """
        observation = runtime.build_observation(_MORI)

        for name in ("セナ", "クゼ", "アオイ"):
            assert f'"{name}"' in observation

    def test_the_header_still_explains_giving(self, runtime) -> None:
        """物を渡せることの案内は残る。"""
        assert "give_item" in runtime.build_observation(_MORI)


class _Cond:
    def __init__(self, condition_type, required_state=None) -> None:
        self.condition_type = condition_type
        self.required_state = required_state


class _Idef:
    def __init__(self, *conds) -> None:
        self.preconditions = list(conds)


def _offerable(idef, actor_state) -> bool:
    return PlayerInteractionApplicationService._is_offerable(
        idef,
        target_is_incapacitated=False,
        target_is_eliminated=False,
        actor_state=actor_state,
    )


class TestOnlyTheActorsOwnStateIsUsed:
    """絞り込みに使うのは行動者自身の状態だけ。"""

    def test_a_matching_actor_state_passes(self) -> None:
        """自分の状態が条件と一致すれば出る。"""
        idef = _Idef(
            _Cond(InteractionConditionTypeEnum.PLAYER_STATE_IS, {"role": "keeper"})
        )

        assert _offerable(idef, {"role": "keeper"}) is True

    def test_a_mismatching_actor_state_hides_it(self) -> None:
        """自分の状態が条件と違えば出ない。"""
        idef = _Idef(
            _Cond(InteractionConditionTypeEnum.PLAYER_STATE_IS, {"role": "keeper"})
        )

        assert _offerable(idef, {"role": "crew"}) is False

    def test_the_targets_hidden_role_never_filters(self) -> None:
        """対象の役割条件では絞り込まない。

        **これを絞ると、ラベルの有無から誰がクルーかが読める。** 行動者
        自身の状態を見るようにした変更が、うっかり対象側にも及んでいない
        ことを確かめる。
        """
        idef = _Idef(
            _Cond(
                InteractionConditionTypeEnum.TARGET_PLAYER_STATE_IS, {"role": "crew"}
            )
        )

        assert _offerable(idef, {"role": "keeper"}) is True

    def test_a_condition_without_a_required_state_is_not_offered(self) -> None:
        """required_state の無い state 条件は出さない。

        判定材料が無いものを黙って通すと、**書き損じた条件が効かないまま
        素通りする**。シナリオを直すまで気付けない側に倒す。
        """
        idef = _Idef(_Cond(InteractionConditionTypeEnum.PLAYER_STATE_IS, None))

        assert _offerable(idef, {"role": "keeper"}) is False

    def test_every_declared_key_must_match(self) -> None:
        """複数キーの条件は、すべて一致して初めて出る。

        担当制 (`{"role": "crew", "duty": "wiring"}`) がこの形。
        """
        idef = _Idef(
            _Cond(
                InteractionConditionTypeEnum.PLAYER_STATE_IS,
                {"role": "crew", "duty": "wiring"},
            )
        )

        assert _offerable(idef, {"role": "crew", "duty": "wiring"}) is True
        assert _offerable(idef, {"role": "crew", "duty": "weather"}) is False


class TestCallersThatDoNotPassTheActorState:
    """行動者の状態を渡さない経路の挙動は変わらない。"""

    def test_nothing_is_filtered_without_it(self) -> None:
        """渡さなければ絞り込まない。

        既存の呼び出しを黙って壊さないため。役割条件を持つ行為が出たまま
        になるだけで、いままでと同じ挙動に留まる。
        """
        idef = _Idef(
            _Cond(InteractionConditionTypeEnum.PLAYER_STATE_IS, {"role": "keeper"})
        )

        assert (
            PlayerInteractionApplicationService._is_offerable(
                idef, target_is_incapacitated=False, target_is_eliminated=False
            )
            is True
        )
