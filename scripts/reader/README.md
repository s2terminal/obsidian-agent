# RSS Reader & Summarizer

RSSフィードから最新記事を取得し、Google ADK (Gemini) で日本語要約を生成するスクリプト。

## 実行方法

```bash
mise x -- uv run -m scripts.reader.main
mise x -- uv run -m scripts.reader.main --summarize-only
```

### 前提条件

- Python 3.14+, uv, mise
- .envにGemini API Keyと必要なパスを設定

## ファイル構成

```
scripts/reader/
├── main.py      # メインスクリプト
├── .cache/      # 記事キャッシュ（gitignore済み）
└── README.md    # このファイル
```

出力先:

```
ai-generated/feed/
└── {yyyy}/
    └── {mm-dd}.md   # スクリプト実行日ごとのファイル
```

## feed.yaml

購読するRSSフィードを管理するYAMLファイル。

```yaml
feeds:
- url: https://example.com/feed.xml
  last_fetched: null
- url: https://example.com/rss
  max_articles: 10
  last_fetched: null
```

| フィールド | 説明 |
|---|---|
| `url` | RSSフィードのURL |
| `last_fetched` | 最終取得時刻（ISO 8601）。通常実行時のみスクリプトが自動更新する |
| `max_articles` | フィードごとの最大要約件数（省略時: 5） |

## 要約のみモード（--summarize-only）

`--summarize-only` を付けると、要約を生成して標準出力へ流します。

- 要約ファイルは保存しない
- `feed.yaml` の `last_fetched` は更新しない
- Slack通知は送らない

## 処理フロー

1. `feed.yaml` に記載のあるフィードを取得
2. キャッシュと照合し、未処理の記事を特定
3. Google ADK (Gemini) で記事を日本語の箇条書きに要約
4. `ai-generated/feed/yyyy/mm-dd.md` に結果を書き出し
5. 書き出し成功後に `feed.yaml` の `last_fetched` を更新

## キャッシュの仕組み

`.cache/` ディレクトリに、フィードURLのSHA-256ハッシュをファイル名としたJSONを保存する。

各記事エントリは以下のステータスを持つ:

| ステータス | 意味 | 次回実行時の挙動 |
|---|---|---|
| `done` | fetch・要約ともに成功 | スキップ |
| `pending` | fetchは成功したが要約に失敗 | キャッシュからコンテンツを復元し、要約のみリトライ |

- `pending` エントリには `title`, `link`, `content`, `published` が保存されるため、再fetchは不要
- `done` エントリにはステータスのみ保存（コンテンツは破棄）

## 出力フォーマット

```markdown
## 2026/03/20

### [フィード](フィードURL)
#### [記事タイトル](https://example.com/article)

- 要約1
- 要約2
- 要約3

#### [別の記事](https://example.com/another)

- 要約1
- 要約2
```

- ファイル名 (`mm-dd.md`): スクリプト実行日
- 見出し (`## YYYY/MM/DD`): 記事の投稿日
- 同じ実行日に複数回実行した場合、同一ファイルに追記される
