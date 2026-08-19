"""Prompt asset loading tests.

Verifies the suggest prompt is loadable from ``assets/prompts/`` (source or
wheel) and degrades gracefully to an inline fallback when the file is missing
or empty.
"""

import ss_dcl.llm as llm


def test_suggest_prompt_loads_from_repo_asset():
    """The packaged prompt file exists, is non-empty, and matches what the
    module loaded at import time."""
    prompt_file = llm._suggest_prompt_file()
    assert prompt_file.is_file(), f"{prompt_file} missing"
    text = prompt_file.read_text(encoding="utf-8").strip()
    assert text
    assert text == llm._SUGGEST_PROMPT


def test_load_suggest_prompt_reads_file(tmp_path):
    """A custom prompt file is read verbatim (stripped)."""
    p = tmp_path / "prompt.txt"
    p.write_text("  \n  You are a captioning model.  \n", encoding="utf-8")
    assert llm._load_suggest_prompt(p) == "You are a captioning model."


def test_load_suggest_prompt_missing_file_falls_back(tmp_path):
    """A missing file returns the inline fallback, not an exception."""
    missing = tmp_path / "nope.txt"
    assert llm._load_suggest_prompt(missing) == llm._SUGGEST_PROMPT_FALLBACK


def test_load_suggest_prompt_empty_file_falls_back(tmp_path):
    """An empty file returns the inline fallback."""
    p = tmp_path / "prompt.txt"
    p.write_text(" \n\t\n ", encoding="utf-8")
    assert llm._load_suggest_prompt(p) == llm._SUGGEST_PROMPT_FALLBACK


def test_fallback_prompt_is_valid_json_instruction():
    """Even the fallback must keep the JSON contract the client expects."""
    assert '"filename"' in llm._SUGGEST_PROMPT_FALLBACK
    assert "JSON" in llm._SUGGEST_PROMPT_FALLBACK
