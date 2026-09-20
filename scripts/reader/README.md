# Reader & Summarizer

RSS / Markdown / Raindrop から最新記事を取得し、Google ADK (Gemini) で日本語要約を生成するスクリプト。

## 実行方法

ホストでmiseを使う場合:

```bash
mise run run_reader
mise run feed_check
mise run feed_check -- --fetch
mise run feed_check -- --summarize
```

Podman Composeを使う場合:

```bash
podman compose run --rm app python main.py reader
podman compose run --rm app python main.py reader check --fetch
podman compose run --rm app python main.py reader check --summarize
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

- `url`: フィードまたは Raindrop コレクションの URL。必須、ファイル内で一意
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

## チェックモード（reader check）

`main.py reader check` は、設定と実行状態の確認をまとめたコマンドです。
どのモードでもファイル・状態は一切更新しません。

| コマンド | 動作 |
|---|---|
| `reader check` | `feed.md` の設定と `status.yaml` の取得位置・未処理件数を表示（ネットワークアクセスなし） |
| `reader check --fetch` | 上記に加えて実際にフィードを取得し、取得件数・新着件数・要約対象の目安を表示（要約はしない） |
| `reader check --summarize` | 取得した記事の要約まで行い、標準出力へ流す |

`--fetch` は `active: false` のフィードを取得しません。取得に失敗したフィードは
`fetch : 失敗 (理由)` と表示し、他のフィードの確認は続行します。
トークン未設定などの取得エラー以外は、秘密情報の混入を避けるため例外の型だけを表示します。

`--fetch` の表示項目:

- `entries`: フィードから取得できた記事の総数（Raindrop は取得位置より新しい記事のみ）
- `new_entries`: `last_fetched` より新しく、次回の要約対象になる記事数
- `retry`: 要約に失敗して再試行を待っている記事数（Raindrop は未処理の保存記事数）
- `summarize`: `max_articles` の上限を適用した要約件数の目安

`--summarize` は以下のとおり副作用がありません。

- 要約ファイルは保存しない
- `status.yaml` の `last_fetched` は更新しない
- Slack通知は送らない
- RSS のキャッシュと Raindrop の記事状態も変更しない

`--fetch` と `--summarize` を同時に指定した場合は、二重取得を避けるため `--summarize` の動作になります。

## 処理フロー

1. `feed.md` の設定と `status.yaml` の取得時刻を読み、フィードを取得
2. キャッシュと照合し、未処理の記事を特定
3. Google ADK (Gemini) で記事を日本語の箇条書きに要約
4. `ai-generated/feed/yyyy/mm-dd.md` に結果を書き出し
5. RSS / Markdown は書き出し成功後に `last_fetched` を更新。Raindrop は取得位置と記事を要約前に保存し、出力後に完了状態を保存

## キャッシュの仕組み

`.cache/` ディレクトリに、フィードURLのSHA-256ハッシュをファイル名としたJSONを保存する。

RSS / Markdown のキャッシュは要約失敗記事だけを保存する。
Raindrop は `status.yaml` の `raindrop` に、URL ごとの取得位置（`last_fetched` / `boundary_ids`）と
記事（`items`）を保存する。

## Raindrop の設定

個人用 Test token を `.env` の `RAINDROP_ACCESS_TOKEN` に設定し、既存の `feed.md` に URL を追加する。
トークンは [Raindrop のアプリ設定](https://app.raindrop.io/settings/integrations)で発行する。
`type` は URL から自動判定するため不要。

```yaml
feeds:
  - 後で読む:
    active: true
    url: https://app.raindrop.io/my/12345678
    title: Raindrop の後で読む
    importance: normal
```

- URL の ID は自分のコレクションに置き換える。全体は `/my/0`、未分類は `/my/-1`。

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
