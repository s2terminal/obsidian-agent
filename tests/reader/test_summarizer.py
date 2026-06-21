from typing import AsyncGenerator

import pytest
from google.adk.agents import Agent
from google.adk.agents import SequentialAgent
from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import Field

from reader.config import APP_NAME
from reader.summarizer import (
    _skip_selector_when_format_forced,
    _summary_writer_instruction,
    FORCE_SUMMARY_FORMAT_KEY,
    forced_summary_format,
    SummaryFormatSelection,
    summarize,
    summarizer_agent,
    summary_format_selector_agent,
    summary_writer_agent,
)


class DummyReadonlyContext:
    def __init__(self, state: dict[str, str]):
        self.state = state


def _request_text(llm_request: LlmRequest) -> str:
    assert llm_request.contents is not None
    assert llm_request.contents

    user_content = llm_request.contents[0]
    assert user_content.parts is not None
    assert user_content.parts

    text = user_content.parts[0].text
    assert text is not None
    return text


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


def make_runner(
    selector_responses: list[str],
    writer_responses: list[str],
    *,
    skip_callback: bool = False,
) -> tuple[InMemoryRunner, MockLlm, MockLlm]:
    """判定・要約の各サブエージェントにMockLlmを設定したInMemoryRunnerを生成する。"""
    selector_llm = MockLlm(model="mock-model", responses=selector_responses)
    writer_llm = MockLlm(model="mock-model", responses=writer_responses)
    selector_kwargs = {}
    if skip_callback:
        # 本番の判定エージェントと同じく、強制形式時に判定LLMをスキップさせる
        selector_kwargs["before_agent_callback"] = _skip_selector_when_format_forced
    selector_agent = Agent(
        name=summary_format_selector_agent.name,
        model=selector_llm,
        instruction=summary_format_selector_agent.instruction,
        description=summary_format_selector_agent.description,
        output_schema=summary_format_selector_agent.output_schema,
        output_key=summary_format_selector_agent.output_key,
        **selector_kwargs,
    )
    writer_agent = Agent(
        name=summary_writer_agent.name,
        model=writer_llm,
        instruction=summary_writer_agent.instruction,
        description=summary_writer_agent.description,
    )
    agent = SequentialAgent(
        name=summarizer_agent.name,
        sub_agents=[selector_agent, writer_agent],
    )
    return InMemoryRunner(agent=agent, app_name=APP_NAME), selector_llm, writer_llm


class TestSummarize:
    def test_selector_agent_uses_literal_output_schema(self):
        assert summary_format_selector_agent.output_schema == SummaryFormatSelection
        assert summary_format_selector_agent.output_key == "summary_format"

    def test_writer_instruction_switches_to_single_sentence_prompt(self):
        instruction = _summary_writer_instruction(
            DummyReadonlyContext(
                {"summary_format": '{"summary_format": "single_sentence"}'}
            )
        )

        assert "140文字以内の一文" in instruction
        assert "3〜5個の箇条書き" not in instruction

    def test_writer_instruction_switches_to_bullet_list_prompt(self):
        instruction = _summary_writer_instruction(
            DummyReadonlyContext(
                {"summary_format": '{"summary_format": "bullet_list"}'}
            )
        )

        assert "3〜5個の箇条書き" in instruction
        assert "140文字以内の一文" not in instruction

    @pytest.mark.asyncio
    async def test_returns_text(self):
        runner, _, _ = make_runner(
            ['{"summary_format": "bullet_list"}'], ["- 要約ポイント1\n- 要約ポイント2"]
        )

        result = await summarize(runner, "Test Title", "Test content body")

        assert "要約ポイント1" in result
        assert "要約ポイント2" in result

    @pytest.mark.asyncio
    async def test_concatenates_multiple_events(self):
        runner, _, _ = make_runner(
            ['{"summary_format": "bullet_list"}'], ["- ポイント1", "\n- ポイント2"]
        )

        result = await summarize(runner, "Title", "Content")

        assert "ポイント1" in result
        assert "ポイント2" in result

    @pytest.mark.asyncio
    async def test_strips_whitespace(self):
        runner, _, _ = make_runner(
            ['{"summary_format": "single_sentence"}'], ["  - 要約  "]
        )

        result = await summarize(runner, "Title", "Content")

        assert result == "- 要約"

    @pytest.mark.asyncio
    async def test_sends_title_and_content_to_llm(self):
        runner, selector_llm, writer_llm = make_runner(
            ['{"summary_format": "single_sentence"}'], ["- 要約"]
        )

        await summarize(runner, "My Title", "My content body")

        assert len(selector_llm.received_requests) == 1
        assert len(writer_llm.received_requests) == 1

        selector_request_text = _request_text(selector_llm.received_requests[0])
        writer_request_text = _request_text(writer_llm.received_requests[0])

        assert "My Title" in selector_request_text
        assert "My content body" in selector_request_text
        assert "My Title" in writer_request_text
        assert "My content body" in writer_request_text

    @pytest.mark.asyncio
    async def test_truncates_content_at_8000_chars(self):
        long_content = "x" * 10000
        runner, selector_llm, writer_llm = make_runner(
            ['{"summary_format": "single_sentence"}'], ["- 要約"]
        )

        await summarize(runner, "Title", long_content)

        selector_request_text = _request_text(selector_llm.received_requests[0])
        writer_request_text = _request_text(writer_llm.received_requests[0])

        assert "x" * 8000 in selector_request_text
        assert "x" * 8001 not in selector_request_text
        assert "x" * 8000 in writer_request_text
        assert "x" * 8001 not in writer_request_text


class TestForcedSummaryFormat:
    def test_high_forces_bullet_list(self):
        assert forced_summary_format("high") == "bullet_list"

    def test_low_forces_single_sentence(self):
        assert forced_summary_format("low") == "single_sentence"

    def test_normal_returns_none(self):
        assert forced_summary_format("normal") is None

    def test_unknown_or_missing_returns_none(self):
        assert forced_summary_format("urgent") is None
        assert forced_summary_format(None) is None


class TestSkipSelectorCallback:
    def test_returns_none_when_not_forced(self):
        ctx = DummyReadonlyContext({})
        assert _skip_selector_when_format_forced(ctx) is None

    def test_sets_format_and_returns_content_when_forced(self):
        ctx = DummyReadonlyContext({FORCE_SUMMARY_FORMAT_KEY: "single_sentence"})

        result = _skip_selector_when_format_forced(ctx)

        assert ctx.state["summary_format"] == "single_sentence"
        assert result is not None
        assert result.parts is not None
        assert "single_sentence" in result.parts[0].text


class TestSummarizeWithImportance:
    @pytest.mark.asyncio
    async def test_low_importance_skips_selector(self):
        # selector_responses は空: 判定LLMが呼ばれないことを検証する
        runner, selector_llm, _ = make_runner([], ["短い一文要約"], skip_callback=True)

        result = await summarize(runner, "Title", "Content", importance="low")

        assert result == "短い一文要約"
        assert len(selector_llm.received_requests) == 0

    @pytest.mark.asyncio
    async def test_high_importance_skips_selector(self):
        runner, selector_llm, _ = make_runner([], ["- 詳細1\n- 詳細2"], skip_callback=True)

        result = await summarize(runner, "Title", "Content", importance="high")

        assert "詳細1" in result
        assert len(selector_llm.received_requests) == 0

    @pytest.mark.asyncio
    async def test_normal_importance_runs_selector(self):
        runner, selector_llm, _ = make_runner(
            ['{"summary_format": "bullet_list"}'], ["- 要約"], skip_callback=True
        )

        await summarize(runner, "Title", "Content", importance="normal")

        assert len(selector_llm.received_requests) == 1
