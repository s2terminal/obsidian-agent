# Obsidian Agent

.envを設定して、`mise run`で実行。

## 開発者向け

以下のコマンドでテストを実行。

```
$ mise run test
```

LLMを実際に呼び出す評価テスト（`llm_eval` マーカー）は通常のテスト実行では除外されます。
明示的に実行するには以下のコマンドを使用してください。

```
$ mise run test -- -m llm_eval
$ mise x -- uv run adk eval \
  scripts/reader \
  tests/reader/summarizer_eval.test.json \
  --print_detailed_results
```
