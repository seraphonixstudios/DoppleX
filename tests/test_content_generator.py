from unittest.mock import patch, MagicMock


class DummyOllama:
    def chat(self, *args, **kwargs):
        return "Generated content from You2.0"


def test_content_generator_with_mock(monkeypatch):
    from brain.generator import ContentGenerator
    generator = ContentGenerator()
    monkeypatch.setattr(generator, "ollama", DummyOllama())
    # Mock brain.generate_post to avoid DB dependencies
    monkeypatch.setattr(
        generator.brain, "generate_post",
        lambda account_id, topic_hint="", mood="": "Generated content from You2.0"
    )
    content = generator.generate(1, topic_hint="test", mood="happy")
    assert isinstance(content, str)
    assert "Generated" in content or len(content) > 0
