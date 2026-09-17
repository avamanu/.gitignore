import pytest

from pr_agent import llm


def test_parses_a_fenced_json_block():
    assert llm.parse_json(['```json\n{"subject": "Hi", "body": "There"}\n```']) == {
        "subject": "Hi", "body": "There"}


def test_prefers_the_last_block_when_the_model_thinks_out_loud():
    assert llm.parse_json(["Let me consider {this}.", '{"fit": "strong"}'])["fit"] == "strong"


def test_raises_a_readable_error_when_there_is_no_json():
    with pytest.raises(ValueError, match="did not return valid JSON"):
        llm.parse_json(["I could not complete that."])


def test_missing_api_key_stops_with_a_useful_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_client", None)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        llm.client()
