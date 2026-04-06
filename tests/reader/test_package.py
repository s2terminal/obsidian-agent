import importlib
import sys


def test_import_reader_does_not_import_agent(monkeypatch):
    for module_name in ("reader", "reader.agent", "reader.summarizer"):
        monkeypatch.delitem(sys.modules, module_name, raising=False)

    importlib.import_module("reader")

    assert "reader.agent" not in sys.modules
    assert "reader.summarizer" not in sys.modules
