import os
from typing import Iterable
from game.core.database import Database


class SchemaInstaller:
    """
    schema ディレクトリにある .sql を読み込み、順番に実行してスキーマを構築するユーティリティ。
    参照用途の schema を初期化に使いたい場合に利用。
    
    使用例:
        db = Database(db_path)
        SchemaInstaller.apply_from_directory(db, os.path.join(BASE_DIR, 'game/core/schema'))
    """

    @staticmethod
    def _iter_sql_files(schema_dir: str) -> Iterable[str]:
        for name in sorted(os.listdir(schema_dir)):
            if not name.lower().endswith('.sql'):
                continue
            yield os.path.join(schema_dir, name)

    @staticmethod
    def apply_from_directory(db: Database, schema_dir: str) -> None:
        if not os.path.isdir(schema_dir):
            raise FileNotFoundError(f"Schema directory not found: {schema_dir}")

        scripts: list[str] = []
        for path in SchemaInstaller._iter_sql_files(schema_dir):
            with open(path, 'r', encoding='utf-8') as f:
                scripts.append(f.read())
        if not scripts:
            return

        # まとめて executescript しても良いが、エラー位置特定のため分割実行
        with db.transaction("IMMEDIATE"):
            for script in scripts:
                db.executescript(script)
