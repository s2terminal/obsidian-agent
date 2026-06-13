"""
Deep Research

Gemini Deep Research でクエリを調査し、結果を Markdown として
Obsidian Vault (ai-generated/research) に保存して Slack 通知する。
"""

import time
from datetime import datetime
from typing import Any

from google import genai

from common.config import get_ai_generated_dir, get_obsidian_root
from common.notifier import notify_slack
from common.obsidian import build_obsidian_open_url, make_safe_slug

MINI_MODEL = "gemini-2.5-flash"
RESEARCH_AGENT = "deep-research-pro-preview-12-2025"
POLL_INTERVAL_SECONDS = 10
OUTPUT_SUBDIR = "research"


def summarize_filename(client: genai.Client, query: str, text: str) -> str:
    prompt = (
        "次のリサーチ結果を保存するMarkdownファイル名として使う、短いタイトルを1つ作成してください。\n"
        "要件:\n"
        "- 内容を適切に要約する\n"
        "- できるだけ簡潔にする\n"
        "- 記号は使わない\n"
        "- ファイル名本体だけを返す\n\n"
        f"クエリ:\n{query}\n\n"
        f"リサーチ結果:\n{text[:4000]}"
    )
    try:
        response = client.models.generate_content(
            model=MINI_MODEL,
            contents=prompt,
        )
        candidate = (getattr(response, "text", None) or "").strip()
        if candidate:
            return make_safe_slug(candidate)
    except Exception as e:
        print(f"ファイル名要約の生成に失敗したため、クエリをもとにしたファイル名へフォールバックします: {e}")
    return make_safe_slug(query)


def build_output_content(query: str, text: str) -> str:
    body = text.lstrip("﻿").lstrip()
    return f"# Query\n\n{query}\n\n---\n\n{body}\n"


def run(query: str) -> None:
    query = query.strip()
    if not query:
        raise ValueError("クエリは空にできません。")

    client = genai.Client()

    interaction = client.interactions.create(
        input=query,
        agent=RESEARCH_AGENT,
        background=True,
    )

    print(f"リサーチを開始しました: {interaction.id}")
    notify_slack(f"リサーチを開始しました: {interaction.id}")

    while True:
        interaction = client.interactions.get(interaction.id)
        if interaction.status == "completed":
            interaction_any: Any = interaction
            outputs = getattr(interaction_any, "outputs", None) or []
            last_output = outputs[-1] if outputs else None
            text = getattr(last_output, "text", None) or str(last_output or "")
            content = build_output_content(query, text)
            slug = summarize_filename(client, query, text)
            filename = f"{datetime.now().strftime('%Y%m%d')}_{slug}.md"
            output_dir = get_ai_generated_dir(OUTPUT_SUBDIR)
            output_dir.mkdir(parents=True, exist_ok=True)
            filepath = output_dir / filename
            filepath.write_text(content, encoding="utf-8")
            print(f"保存しました: {filepath}")
            relative = filepath.resolve().relative_to(get_obsidian_root().resolve())
            obsidian_url = build_obsidian_open_url(relative)
            notify_slack(f"リサーチが完了し、保存されました: {obsidian_url}")
            break
        elif interaction.status == "failed":
            interaction_any: Any = interaction
            error = getattr(interaction_any, "error", "不明なエラー")
            print(f"リサーチに失敗しました: {error}")
            notify_slack(f"リサーチに失敗しました: {error}")
            break
        time.sleep(POLL_INTERVAL_SECONDS)
