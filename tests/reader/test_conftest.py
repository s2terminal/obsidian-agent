import os
from types import SimpleNamespace

import pytest

from tests.reader.conftest import _should_enable_langfuse, pytest_configure


@pytest.mark.parametrize(
    ("markexpr", "expected"),
    [
        ("", False),
        ("llm_eval", True),
        ("llm_eval and smoke", True),
        ("smoke or llm_eval", True),
        ("not llm_eval", False),
        ("smoke and not llm_eval", False),
        ("smoke", False),
    ],
)
def test_should_enable_langfuse(markexpr, expected):
    assert _should_enable_langfuse(markexpr) is expected


def test_pytest_configure_enables_langfuse_for_llm_eval(monkeypatch):
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    config = SimpleNamespace(option=SimpleNamespace(markexpr="llm_eval and smoke"))

    pytest_configure(config)

    assert os.environ["LANGFUSE_TRACING_ENABLED"] == "true"


def test_pytest_configure_disables_langfuse_without_llm_eval(monkeypatch):
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    config = SimpleNamespace(option=SimpleNamespace(markexpr="not llm_eval"))

    pytest_configure(config)

    assert os.environ["LANGFUSE_TRACING_ENABLED"] == "false"
