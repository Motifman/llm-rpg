"""出来事の同一性 (episode_id) の付け方を 1 か所に置く。

## 材料に描画済みテキストを入れない

`episode_id` は fingerprint の uuid5 で、以前は材料に**直近の出来事の
箇条書き**や**結果の要約文**が入っていた。どちらも prompt に出す文面
なので、表示を変えるだけで同じ出来事の id が変わっていた (実例:
`c051a47a` の「呼び出し: …」1 行追加、`5cf1b9b4` の時刻ラベル削除)。

材料にしてよいのは、表示の都合で動かない値だけ — 誰が・いつ・何の道具で・
成否は、といった出来事の構造そのもの。

## 版は接尾辞で示す

**接頭辞にはしない。** afterglow の handle は `episode_id` の先頭 6 文字
から作られるので、先頭を版で潰すと実質 3 文字しか残らず、1 being 数十件の
episode で誕生日衝突が起きて想起が別の出来事を引き当てる。

末尾なら handle は uuid 部分から作られたままで、`endswith` で版を判別
できる。旧 id (接尾辞なし) の資産とは断絶するが、断絶自体は避けられない
ので「どちらの版か目で分かる」ことを優先した。
"""

from __future__ import annotations

import uuid

#: 出来事の同一性の付け方の版。id の末尾に付ける。
EPISODE_ID_VERSION_SUFFIX = "#e2"

#: uuid5 の名前空間。版を変えても名前空間は変えない (版は接尾辞で示す)。
EPISODE_ID_NAMESPACE = uuid.UUID("018fc4d2-a6b1-7c3f-8120-ac5ed1e942b0")


def build_episode_id(fingerprint_parts: tuple[str, ...]) -> str:
    """出来事の構造から、版つきの episode_id を作る。

    ``fingerprint_parts`` には**表示の都合で動かない値だけ**を渡すこと。
    prompt に出す文面を混ぜると、表示を変えた瞬間に同じ出来事が別の id に
    なる。
    """
    fingerprint = "|".join(fingerprint_parts)
    return f"{uuid.uuid5(EPISODE_ID_NAMESPACE, fingerprint)}{EPISODE_ID_VERSION_SUFFIX}"


def is_current_version(episode_id: str) -> bool:
    """その id が現行の付け方で作られたか (旧資産との見分けに使う)。"""
    return isinstance(episode_id, str) and episode_id.endswith(EPISODE_ID_VERSION_SUFFIX)


__all__ = [
    "EPISODE_ID_NAMESPACE",
    "EPISODE_ID_VERSION_SUFFIX",
    "build_episode_id",
    "is_current_version",
]
