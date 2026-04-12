import os
import json
from typing import Literal

from google.adk.agents import Agent
from google.adk.agents import SequentialAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel
from pydantic import Field

from .config import APP_NAME, DEFAULT_MODEL, USER_ID


def _is_langfuse_enabled() -> bool:
    value = os.getenv("LANGFUSE_TRACING_ENABLED", "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _noop_observe(*args, **kwargs):
    def decorator(func):
        return func

    return decorator


observe = _noop_observe
get_client = None

if _is_langfuse_enabled():
    try:
        from langfuse import get_client as _langfuse_get_client
        from langfuse import observe as _langfuse_observe

        observe = _langfuse_observe
        get_client = _langfuse_get_client
    except (ModuleNotFoundError, ImportError):
        # Langfuse が利用できない場合でも要約処理自体は継続する
        pass

SummaryFormat = Literal["single_sentence", "bullet_list"]


class SummaryFormatSelection(BaseModel):
    summary_format: SummaryFormat = Field(
        description="要約形式。single_sentence か bullet_list のどちらか。"
    )


def _normalize_summary_format(value: object) -> SummaryFormat | None:
    if isinstance(value, dict):
        return _normalize_summary_format(value.get("summary_format"))

    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if normalized.startswith("{"):
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return _normalize_summary_format(parsed.get("summary_format"))

    normalized = normalized.strip('"').strip("'")
    if normalized == "single_sentence":
        return "single_sentence"
    if normalized == "bullet_list":
        return "bullet_list"
    return None


def _summary_writer_instruction(context: ReadonlyContext) -> str:
    summary_format = _normalize_summary_format(context.state.get("summary_format"))
    common_instruction = (
        "あなたは記事要約アシスタントです。"
        "すべての内容は日本語で出力してください。"
        "5W1Hをできるだけ明確にしてください。"
        "誤『新機能をリリース』→正『x月x日、GitHubが新機能をリリース』"
    )

    if summary_format == "single_sentence":
        return (
            common_instruction
            + "事実のみを伝える簡単なニュース記事として扱い、140文字以内の一文で要約してください。"
            + "一文のみを出力し、前置きや補足は不要です。"
        )

    if summary_format == "bullet_list":
        return (
            common_instruction
            + "解説・分析・複数論点を含む記事として扱い、3〜5個の箇条書きで要約してください。"
            + "各項目は『- 』で始め、簡潔に1〜2文でまとめてください。"
            + "箇条書きのみを出力し、それ以外の前置きや説明は不要です。"
        )

    return (
        common_instruction
        + "要約形式が判定できなかったため、安全側で3〜5個の箇条書きで要約してください。"
        + "各項目は『- 』で始め、簡潔に1〜2文でまとめてください。"
        + "箇条書きのみを出力し、それ以外の前置きや説明は不要です。"
    )

summary_format_selector_agent = Agent(
    name="summary_format_selector",
    model=DEFAULT_MODEL,
    description="記事が一文要約向きか箇条書き要約向きかを判定する。",
    instruction=(
        "あなたは記事要約形式の判定アシスタントです。"
        "与えられた記事を読み、一文形式か箇条書き形式のどちらで要約すべきかだけを判断してください。\n"
        "\n"
        "【single_sentence】を選ぶ条件:\n"
        "・人事発表、イベント告知、価格改定など、分析や解説を含まない簡単な事実報道\n"
        "・要点がほぼ1つで、短いニュースとして伝えれば十分な記事\n"
        "\n"
        "【bullet_list】を選ぶ条件:\n"
        "・新しいコンセプト、技術、知見を解説する記事\n"
        "・重要なソフトウェアリリースや製品発表で、新機能や背景説明がある記事\n"
        "・分析、考察、比較、意見を含む記事\n"
        "・論点や要点が複数ある記事\n"
        "\n"
        "`single_sentence` または `bullet_list` のどちらか一方を出力してください。"
    ),
    output_schema=SummaryFormatSelection,
    output_key="summary_format",
)

summary_writer_agent = Agent(
    name="summary_writer",
    model=DEFAULT_MODEL,
    description="判定済みの要約形式に従って記事要約を書く。",
    instruction=_summary_writer_instruction,
)

summarizer_agent = SequentialAgent(
    name="summarizer",
    sub_agents=[summary_format_selector_agent, summary_writer_agent],
)


@observe(as_type="generation", capture_input=False, capture_output=False)
async def summarize(runner: InMemoryRunner, title: str, content: str) -> str:
    message = (
        f"以下の記事を日本語で要約してください。\n\n"
        f"タイトル: {title}\n\n"
        f"内容:\n{content[:8000]}"
    )
    if get_client is not None:
        try:
            get_client().update_current_generation(
                input=message,
                model=DEFAULT_MODEL,
            )
        except Exception as e:
            print(f"Langfuse入力トレーシング失敗: {e}")
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID
    )
    responses: list[str] = []
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session.id,
        new_message=types.Content(
            role="user", parts=[types.Part(text=message)]
        ),
    ):
        if event.author != summary_writer_agent.name:
            continue
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    responses.append(part.text)
    result = "".join(responses).strip()
    if get_client is not None:
        try:
            get_client().update_current_generation(output=result)
        except Exception as e:
            print(f"Langfuse出力トレーシング失敗: {e}")
    return result
