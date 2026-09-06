# Obsidian Agent

Obsidianのノートに対してAIエージェントで操作を行うツール群です。

.envを設定して、`mise run`で実行。

`OBSIDIAN_AGENT_DIR` には `feed.md` を置くディレクトリを `OBSIDIAN_ROOT` からの相対パスで指定。
設定は `obsidian_agent/feed.md`。

## ホストでmiseを使う

miseをインストールしたホストでは、コンテナを使わずに実行できます。
初回はmiseでNode.js、npm、uvをインストールします。

```bash
mise install
```

RSS / Markdown / Raindrop の Reader を実行します。

```bash
mise run run_reader
mise run feed_check
mise run run_reader -- --summarize-only
```

リサーチ機能のクエリは、`--`以降に指定します。

```bash
mise run run_research -- "調査したい内容"
```

## Podman Composeを使う

PodmanとPodman Composeをインストールし、開発用イメージをビルドします。

```bash
podman compose build
```

`compose.yaml`は開発用の`development`ステージを使用します。
開発用依存関係を含み、リポジトリを`/app`へマウントするため、
Pythonコードの変更はイメージの再ビルドなしで反映されます。
`pyproject.toml`または`uv.lock`を変更した場合は、イメージを再ビルドしてください。

開発用コンテナには固定の`ENTRYPOINT`を設定していません。
任意のコマンドを指定できるため、bashも直接起動できます。

```bash
podman compose run --rm app bash
```

### Podman Composeでアプリを実行する

RSS / Markdown / Raindrop の Reader を実行します。

```bash
podman compose run --rm app python main.py reader
```

設定したフィードの確認と、ファイルを更新しない要約のみの実行には、
以下のコマンドを使用します。

```bash
podman compose run --rm app python main.py reader check
podman compose run --rm app python main.py reader --summarize-only
```

リサーチ機能のクエリは、`research`以降に指定します。

```bash
podman compose run --rm app python main.py research "調査したい内容"
```

RSSリーダーのキャッシュは、Podmanの名前付きボリューム
`obsidian-agent_reader-cache`に保存されます。

### Podman Composeでテストする

開発用イメージにはpytestなどの開発用依存関係が含まれます。

```bash
podman compose run --rm app pytest tests/
```

## 実行用イメージをビルドする

`Containerfile`の最終ステージは、開発用依存関係を含まない`runtime`です。
Composeを使用しないイメージビルドでは、`runtime`ステージが使用されます。

```bash
podman build -t obsidian-agent .
```

## 開発者向け

以下のコマンドでテストを実行。

```bash
mise run test
```

LLMを実際に呼び出す評価テスト（`llm_eval` マーカー）は通常のテスト実行では除外されます。
明示的に実行するには以下のコマンドを使用してください。

```bash
mise run test -- -m llm_eval
mise x -- uv run adk eval \
  scripts/reader \
  tests/reader/summarizer_eval.test.json \
  --print_detailed_results
```

### ADK

https://adk.dev/tutorials/coding-with-ai/

ADKについてはSkillかMCPかllms.txtが使える。

```bash
npx skills add google/adk-docs/skills
```

## Raindrop の後で読む

`.env` に `RAINDROP_ACCESS_TOKEN` を設定し、`feed.md` にコレクション URL を追加します。
初回は最新1件、以降は保存日時に基づいて新着を取り込みます。API は GET のみで、Raindrop のデータは変更しません。
設定例と状態管理は [Reader の README](scripts/reader/README.md#raindrop-の設定) を参照してください。
