from unittest.mock import patch

from src.brain.generator import ContentGenerator


class DummyOllama:
    def chat(self, *args, **kwargs):
        return "Generated content from You2.0"


def test_content_generator_with_mock(monkeypatch):
    generator = ContentGenerator()
    # Patch the OllamaBridge
    monkeypatch.setattr(generator, "ollama", DummyOllama())
    # Also patch memory search to return empty list for simplicity
    with patch("src.brain.generator.top_k_similar_posts", return_value=[]):
        class DummyAcc:
            id = 1
            platform = "X"
            style_profile = None
        acc = DummyAcc()
        content = generator.generate(acc, [])
        assert isinstance(content, str)
        assert "Generated" in content or len(content) > 0
