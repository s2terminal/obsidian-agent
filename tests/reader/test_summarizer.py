from typing import AsyncGenerator

import pytest
from google.adk.agents import Agent
from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import Field

from reader.config import APP_NAME
from reader.summarizer import summarize, summarizer_agent


class MockLlm(BaseLlm):
    """テスト用モックLLM。事前定義されたテキストを順に返す。"""

    model: str = "mock-model"
    responses: list[str] = Field(default_factory=list)
    received_requests: list[LlmRequest] = Field(default_factory=list)

    @classmethod
    def supported_models(cls) -> list[str]:
        # モデルインスタンスを Agent に直接渡すため、このメソッドは使用されない
        return ["mock-model"]

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.received_requests.append(llm_request)
        # responses の各要素がストリーミングの1チャンクに対応する
        for text in self.responses:
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=text)])
            )


def make_runner(responses: list[str]) -> tuple[InMemoryRunner, MockLlm]:
    """MockLlmを使用したInMemoryRunnerを生成する。"""
    llm = MockLlm(model="mock-model", responses=responses)
    agent = Agent(
        name=summarizer_agent.name,
        model=llm,
        instruction=summarizer_agent.instruction,
    )
    return InMemoryRunner(agent=agent, app_name=APP_NAME), llm


class TestSummarize:
    @pytest.mark.asyncio
    async def test_returns_text(self):
        runner, _ = make_runner(["- 要約ポイント1\n- 要約ポイント2"])

        result = await summarize(runner, "Test Title", "Test content body")

        assert "要約ポイント1" in result
        assert "要約ポイント2" in result

    @pytest.mark.asyncio
    async def test_concatenates_multiple_events(self):
        runner, _ = make_runner(["- ポイント1", "\n- ポイント2"])

        result = await summarize(runner, "Title", "Content")

        assert "ポイント1" in result
        assert "ポイント2" in result

    @pytest.mark.asyncio
    async def test_strips_whitespace(self):
        runner, _ = make_runner(["  - 要約  "])

        result = await summarize(runner, "Title", "Content")

        assert result == "- 要約"

    @pytest.mark.asyncio
    async def test_sends_title_and_content_to_llm(self):
        runner, llm = make_runner(["- 要約"])

        await summarize(runner, "My Title", "My content body")

        assert len(llm.received_requests) == 1
        request = llm.received_requests[0]
        user_content = request.contents[0]
        request_text = user_content.parts[0].text
        assert "My Title" in request_text
        assert "My content body" in request_text

    @pytest.mark.asyncio
    async def test_truncates_content_at_8000_chars(self):
        long_content = "x" * 10000
        runner, llm = make_runner(["- 要約"])

        await summarize(runner, "Title", long_content)

        request = llm.received_requests[0]
        user_content = request.contents[0]
        request_text = user_content.parts[0].text
        assert "x" * 8000 in request_text
        assert "x" * 8001 not in request_text
