"""インベントリ文脈のアプリケーション層。

## services の実装をここで再輸出しない理由

以前は ``ItemStackingApplicationService`` を再輸出していた。**そのためこの
パッケージ配下の submodule を 1 つ import すると services が読み込まれた。**
Python はパッケージの ``__init__`` を先に実行するので、例外を 1 つ取るだけで
実装まで付いてくる。

これが循環 import の火種になる (#1018 で ``llm`` 側が実際に発火した)。再輸出は
``from ai_rpg_world.application.inventory import ...`` の形で一度も使われて
いなかった (``src/`` ``tests/`` ``scripts/`` で 0 件)。利用側は実体のモジュールを
直接指している。**実装は各モジュールから直接 import する。**

__all__ は空にしてある。他の 3 パッケージ (guild / speech / harvest) は契約と
例外を再輸出しているので __all__ を持つ。ここだけ宣言が無いと「書き忘れ」と
区別がつかないため、意図的に何も公開していないことを明示する。
"""

__all__: list[str] = []
