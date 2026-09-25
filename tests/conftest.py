import pytest
from app.core.planner import planner as singleton_planner


@pytest.fixture(autouse=True)
def _deterministic_planner():
    """
    Keep tests offline and deterministic even when real Groq/OpenRouter
    keys are present in .env — the LLM path is tested separately with a
    mocked _call_llm on a fresh planner instance.
    """
    singleton_planner.force_heuristic = True
    yield
    singleton_planner.force_heuristic = False
