"""インタラクション効果の適用先。

効果を「行為者本人」に当てるか「行為の対象に選ばれたプレイヤー」に当てるかを
表す (対人インタラクション基盤。docs/memory_system/interpersonal_interaction_design.md)。

これまで効果はすべて行為者に固定されていた。物体は人に影響できるのに、人は人に
影響できない、という非対称があり、殺害・盗み・手当て・毒といった対人行為が
シナリオで書けなかった。

`EffectVisibility` を parameters dict と分離して first-class 属性にしたのと同じ
理由で、`target` も `InteractionEffect` の属性として持つ。将来 `target` という名の
パラメータを使う効果が出てきても衝突しない。

未知の値は読み込み時に `ScenarioLoadError` で落とす。`visibility` の既存パースは
不正値を黙って既定へ倒すが、その書き方をここで踏襲してはいけない。
``"TARGET_PLAYERS"`` の綴り間違いが ``ACTOR`` に落ちると **自分に致死ダメージ**
が入る。
"""

from __future__ import annotations

from enum import Enum


class EffectTarget(Enum):
    """効果をどちらの主体に適用するか。"""

    ACTOR = "ACTOR"
    """行為者本人。既定値で、これまでの挙動と同じ。"""

    TARGET_PLAYER = "TARGET_PLAYER"
    """行為の対象に選ばれたプレイヤー。対象が解決できなければ実行自体が失敗する。"""


__all__ = ["EffectTarget"]
