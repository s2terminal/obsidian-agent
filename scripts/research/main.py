"""
Deep Research

Gemini Deep Research でクエリを調査し、結果を Markdown として
Obsidian Vault (ai-generated/research) に保存して Slack 通知する。
"""

import re
import time
from datetime import datetime

from google import genai

from common.config import get_ai_generated_dir, get_obsidian_root
from common.notifier import notify_slack
from common.obsidian import build_obsidian_open_url, make_safe_slug

MINI_MODEL = "gemini-2.5-flash"
RESEARCH_AGENT = "deep-research-pro-preview-12-2025"
POLL_INTERVAL_SECONDS = 10
OUTPUT_SUBDIR = "research"
# Interactions API のステータスのうち、リトライせず終了扱いにするもの（completed 以外の終端状態）
FAILURE_STATUSES = ("failed", "cancelled", "incomplete", "budget_exceeded")

SOURCE_SECTION_RE = re.compile(
    r"(?im)^(?:#{1,6}\s+sources|\*\*sources:\*\*|sources:)\s*$"
)
SOURCE_LINK_RE = re.compile(
    r"(?m)^\s*(\d+)\.\s+\[[^\]\n]+\]\((https?://[^\s)]+)\)\s*$"
)
CITATION_RE = re.compile(r"\[cite:\s*(\d+(?:\s*,\s*\d+)*)\s*\]", re.IGNORECASE)


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


def link_citations(text: str) -> str:
    """本文中の ``[cite: 1, 2]`` を Sources の Markdown リンクへ変換する。"""
    source_section = SOURCE_SECTION_RE.search(text)
    if not source_section:
        return text

    sources = {
        number: url
        for number, url in SOURCE_LINK_RE.findall(text[source_section.end() :])
    }
    if not sources:
        return text

    def replace(match: re.Match[str]) -> str:
        numbers = [number.strip() for number in match.group(1).split(",")]
        links = [f"[{number}]({sources[number]})" for number in numbers if number in sources]
        missing = [number for number in numbers if number not in sources]
        if missing:
            links.append(f"[cite: {', '.join(missing)}]")
        return ", ".join(links)

    return CITATION_RE.sub(replace, text)


def build_output_content(query: str, text: str) -> str:
    body = link_citations(text.lstrip("﻿").lstrip())
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
            # 新しい steps スキーマでは末尾のモデル出力テキストを output_text で取得する
            text = interaction.output_text
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
        elif interaction.status in FAILURE_STATUSES:
            print(f"リサーチに失敗しました: status={interaction.status}")
            notify_slack(f"リサーチに失敗しました: status={interaction.status}")
            break
        time.sleep(POLL_INTERVAL_SECONDS)
