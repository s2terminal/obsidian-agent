# RSS Reader & Summarizer

RSSフィードから最新記事を取得し、Google ADK (Gemini) で日本語要約を生成するスクリプト。

## 実行方法

ホストでmiseを使う場合:

```bash
mise run run_reader
mise run run_reader -- --summarize-only
```

Podman Composeを使う場合:

```bash
podman compose run --rm app python main.py reader
podman compose run --rm app python main.py reader --summarize-only
```

### 前提条件

- mise、またはPodmanとPodman Compose
- `.env`にGemini API Keyとホスト側の必要なパスを設定

## ファイル構成

- `scripts/reader/main.py`: フィード取得と要約の実行処理。
- `scripts/reader/.cache/`: 要約失敗記事のキャッシュ（gitignore済み）。
- `ai-generated/feed/{yyyy}/{mm-dd}.md`: 実行日ごとの要約出力。

## フィード設定と実行状態

環境変数 `OBSIDIAN_AGENT_DIR` は、`OBSIDIAN_ROOT` からの相対パスでディレクトリを指定します。

```dotenv
OBSIDIAN_ROOT=/path/to/obsidian/Vault
OBSIDIAN_AGENT_DIR=obsidian_agent
```

### feed.md（人間が編集する設定）

この例では `/path/to/obsidian/Vault/obsidian_agent/feed.md` にMarkdownとして保存し、最初の `yaml` コードブロックから設定を読み込みます。

````markdown
# 購読フィード

```yaml
feeds:
- url: https://example.com/feed.xml
  title: 表示用のフィード名
  active: true
- url: https://example.com/rss
  max_articles: 10
  importance: low
```
````

- `url`: フィードURL。必須、ファイル内で一意
- `title`: 任意の表示名。RSS本体のタイトルより優先します。
- `active`: `false` のフィードは処理しません。
- `max_articles`: 最大要約件数。省略時は通常5件、取得時刻のない新規フィードは1件。
- `importance`: 要約の詳しさ。省略時は `normal` 。
- `type`: `markdown` を指定するとMarkdown形式として取得。URL末尾が `.md` または `.md.txt` の場合も自動判定。

### importance（重要度）による要約の出し分け

フィードごとに `importance` を設定すると、要約の詳しさを切り替えられる。

| 値 | 挙動 |
|---|---|
| `high` | 常に詳細な箇条書き（3〜5個）で要約する |
| `normal` | 記事内容から一文要約か箇条書き要約かを自動判定する（デフォルト） |
| `low` | 詳細な要約はせず、常に140文字以内の一文で簡潔に要約する |

重要でないフィード（`low`）では詳細な要約を省くことで、要約の判定LLM呼び出しも省略される。

## 要約のみモード（--summarize-only）

`main.py reader --summarize-only` を付けると、要約を生成して標準出力へ流します。

- 要約ファイルは保存しない
- `status.yaml` の `last_fetched` は更新しない
- Slack通知は送らない

## 処理フロー

1. `feed.md` の設定と `status.yaml` の取得時刻を読み、フィードを取得
2. キャッシュと照合し、未処理の記事を特定
3. Google ADK (Gemini) で記事を日本語の箇条書きに要約
4. `ai-generated/feed/yyyy/mm-dd.md` に結果を書き出し
5. 書き出し成功後に `status.yaml` の `last_fetched` を更新

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
