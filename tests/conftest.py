import pytest


@pytest.fixture(autouse=True)
def chinese_prompts(request, monkeypatch):
    """Most tests assert on prompt text in Chinese, so they run with KNOSIS_LANG=zh; test_lang.py covers the English default."""
    if request.module.__name__ != "test_lang":
        monkeypatch.setenv("KNOSIS_LANG", "zh")
