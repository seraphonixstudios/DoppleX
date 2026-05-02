import pytest
from unittest.mock import patch, MagicMock


class DummyOllama:
    async def chat(self, *args, **kwargs):
        return "Generated content from You2.0"


@pytest.mark.asyncio
async def test_content_generator_with_mock(monkeypatch):
    from brain.generator import ContentGenerator
    generator = ContentGenerator()
    monkeypatch.setattr(generator, "ollama", DummyOllama())

    async def mock_generate_post(account_id, topic_hint="", mood=""):
        return "Generated content from You2.0"

    monkeypatch.setattr(generator.brain, "generate_post", mock_generate_post)
    content = await generator.generate(1, topic_hint="test", mood="happy")
    assert isinstance(content, str)
    assert "Generated" in content or len(content) > 0
