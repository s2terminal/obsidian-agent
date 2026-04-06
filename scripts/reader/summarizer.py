import os

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

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
