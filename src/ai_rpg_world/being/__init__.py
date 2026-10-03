"""経験を持つ AI 主体 (Being) の文脈。

環境 (ゲームなど) から独立させ、同じ Being が記憶を持ったまま環境を行き来できる
ようにする。環境とは ``contract`` の型だけで結ぶ。ゲームのパッケージを import
しないことは ``tests/architecture/test_being_package_import_boundary.py`` が見張る。
"""
