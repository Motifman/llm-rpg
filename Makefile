.PHONY: test test-cov test-html clean install dev-install help

# デフォルトターゲット
help:
	@echo "利用可能なコマンド:"
	@echo "  make install      - 依存関係をインストール"
	@echo "  make dev-install  - 開発用依存関係をインストール"
	@echo "  make test         - テストを実行"
	@echo "  make test-cov     - カバレッジ付きでテストを実行"
	@echo "  make test-html    - HTMLカバレッジレポートを生成"
	@echo "  make clean        - 一時ファイルを削除"

# 依存関係のインストール
install:
	pip install -r requirements.txt

# 開発用依存関係のインストール
dev-install: install
	pip install pytest pytest-cov

# 基本的なテスト実行
test:
	pytest

# カバレッジ付きテスト実行
test-cov:
	pytest --cov=src --cov-report=term-missing

# HTMLカバレッジレポート生成
test-html:
	pytest --cov=src --cov-report=html --cov-report=term
	@echo "HTMLレポートが htmlcov/index.html に生成されました"

# 一時ファイルの削除
clean:
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete 