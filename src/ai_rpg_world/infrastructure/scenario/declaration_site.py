"""読み込みエラーに、宣言のありかを足す。

## なぜ層ごとに足すか

「どこで宣言されているか」は 1 か所に無い。spot の id を知っているのは spot を
読む層、物体の id を知っているのは物体を読む層、``action_name`` を知っているのは
操作を読む層である。**効果を読む層は、そのどれも知らない。**

引数で下まで運ぶ形も採れるが、各層は自分の担当ぶんしか埋められないので、
運ぶ文字列を組む処理が結局層ごとに要る。**知っている層が、知っていることを
足す**方が短い。

## 捕まえる型を絞る

``ScenarioLoadError`` **だけ**を捕まえる。ここで ``Exception`` を広く捕まえると、
コードのバグ (``KeyError`` / ``AttributeError``) が「**あなたのシナリオの
ここが間違っています**」というメッセージに化ける。

これは静かな失敗より厄介である。**嘘の診断が付いた騒がしい失敗**は、読んだ人を
シナリオの方へ何時間も歩かせる。

## 元の理由を落とさない

足すのは前置きだけで、元のメッセージはそのまま残す。言い換えると、**意味が
変わった失敗**になる。例外の型も変えない。型が変わると、それを名指しで
捕まえている検査が黙って外れる。

いまは ``ScenarioLoadError`` にサブクラスが無いので基底型で投げ直している。
**サブクラスができたら ``type(exc)(...)`` で投げ直すこと。** そうしないと
投げ直しで型が平坦化され、サブクラスを名指しで捕まえている検査が黙って外れる。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError


@contextmanager
def declaring(where: str) -> Iterator[None]:
    """この中で出た読み込みエラーに、``where`` を前置きとして足す。

    入れ子にすると外側の層ほど前に付くので、``spot 'x' の 物体 'y' の
    操作 'z' の 効果:`` のように、広い方から狭い方への順で読める。
    """
    try:
        yield
    except ScenarioLoadError as exc:
        raise ScenarioLoadError(f"{where} {exc}") from exc


__all__ = ["declaring"]
