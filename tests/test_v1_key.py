# shows the Gemini key reaching the API, run with -s to read the printed evidence

import os

import pytest

pytestmark = pytest.mark.live_llm

# names the same variable LLM_Shell.llm reads, copied because that module does not import yet
KEY = "GEMINI_API_KEY"

# picks one cheap stable model, this test only proves the key is accepted
MODEL = "gemini-3.8-flash"

# asks for something whose right answer is one unmistakable word
QUESTION = "Reply with the single word DRIFTER and nothing else."


def _masked(key: str) -> str:
    # shows enough of the key to recognise it, never the whole secret
    return f"{key[:6]}...{key[-4:]} ({len(key)} chars)"


def test_gemini_key_is_accepted():
    key = os.environ.get(KEY)
    if not key:
        pytest.skip(f"{KEY} is not set")
    print(f"\n{KEY} = {_masked(key)}")

    from google import genai
    from google.genai import types

    with genai.Client(http_options=types.HttpOptions(timeout=60_000)) as client:
        reply = client.interactions.create(model=MODEL, input=QUESTION).output_text.strip()
    print(f"{MODEL} answered: {reply!r}")
    assert "DRIFTER" in reply.upper()
