import os

import pytest
from google.adk.evaluation import AgentEvaluator

AGENT_MODULE = "reader.agent"
EVAL_FILE = os.path.join(os.path.dirname(__file__), "summarizer_eval.test.json")


@pytest.mark.llm_eval
@pytest.mark.asyncio
async def test_summarizer_eval():
    await AgentEvaluator.evaluate(
        agent_module=AGENT_MODULE,
        eval_dataset_file_path_or_dir=EVAL_FILE,
        num_runs=1,
    )
