from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from .config import APP_NAME, DEFAULT_MODEL, USER_ID

summarizer_agent = Agent(
    name="summarizer",
    model=DEFAULT_MODEL,
    instruction=(
        "あなたは記事要約アシスタントです。"
        "与えられた記事を日本語で3〜5個の箇条書きで要約してください。"
        "各項目は「- 」で始め、簡潔に1〜2文でまとめてください。"
        "箇条書きのみを出力し、それ以外の前置きや説明は不要です。"
        "すべての内容は日本語で出力してください。"
        "5W1Hをできるだけ明確にしてください。誤「新機能をリリース」→正「x月x日、GitHubが新機能をリリース」"
    ),
)


async def summarize(runner: InMemoryRunner, title: str, content: str) -> str:
    message = (
        f"以下の記事を日本語で要約してください。\n\n"
        f"タイトル: {title}\n\n"
        f"内容:\n{content[:8000]}"
    )
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
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    responses.append(part.text)
    return "".join(responses).strip()
