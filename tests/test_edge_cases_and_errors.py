"""Edge case, validator integration, GUI, and async error handling tests."""
from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timedelta

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils.validators import (
    sanitize_text,
    sanitize_username,
    sanitize_platform,
    sanitize_token,
    sanitize_file_path,
    sanitize_hashtags,
    sanitize_schedule_date,
    validate_post_content,
    validate_account_id,
    validate_positive_int,
    validate_mood,
    validate_topic_hint,
    check_sql_injection,
    ValidationError,
    RateLimiter,
)
from utils.time_utils import utc_now


# ────────────────────────────────
# 1. Edge Case Tests
# ────────────────────────────────

class TestSanitizeTextEdgeCases:
    def test_empty_string(self):
        assert sanitize_text("") == ""

    def test_whitespace_only(self):
        assert sanitize_text("   \n\t  ") == ""

    def test_very_long_content(self):
        long_text = "A" * 10000
        with pytest.raises(ValidationError):
            sanitize_text(long_text, max_length=5000)

    def test_exactly_max_length(self):
        text = "A" * 5000
        assert len(sanitize_text(text, max_length=5000)) == 5000

    def test_html_escaping(self):
        result = sanitize_text("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_control_chars_removed(self):
        result = sanitize_text("hello\x00\x01\x02world")
        assert "\x00" not in result
        assert "hello" in result
        assert "world" in result

    def test_multiple_spaces_collapsed(self):
        assert sanitize_text("hello    world") == "hello world"

    def test_non_string_input(self):
        with pytest.raises(ValidationError):
            sanitize_text(12345)
        with pytest.raises(ValidationError):
            sanitize_text(None)


class TestSanitizeUsernameEdgeCases:
    def test_empty_username(self):
        with pytest.raises(ValidationError):
            sanitize_username("")
        with pytest.raises(ValidationError):
            sanitize_username(None)

    def test_username_with_at_symbol(self):
        assert sanitize_username("@john_doe") == "john_doe"

    def test_username_too_long(self):
        with pytest.raises(ValidationError):
            sanitize_username("a" * 51)

    def test_invalid_characters(self):
        with pytest.raises(ValidationError):
            sanitize_username("john<doe")
        with pytest.raises(ValidationError):
            sanitize_username("john doe")  # spaces not allowed

    def test_unicode_username(self):
        with pytest.raises(ValidationError):
            sanitize_username("用户名称")


class TestSanitizeTokenEdgeCases:
    def test_empty_token(self):
        with pytest.raises(ValidationError):
            sanitize_token("")
        with pytest.raises(ValidationError):
            sanitize_token(None)

    def test_short_token(self):
        with pytest.raises(ValidationError):
            sanitize_token("abc123")

    def test_placeholder_tokens(self):
        with pytest.raises(ValidationError):
            sanitize_token("your_token_here")
        with pytest.raises(ValidationError):
            sanitize_token("placeholder")
        with pytest.raises(ValidationError):
            sanitize_token("test")

    def test_very_long_token(self):
        with pytest.raises(ValidationError):
            sanitize_token("x" * 3000)


class TestSanitizeFilePathEdgeCases:
    def test_directory_traversal(self):
        with pytest.raises(ValidationError):
            sanitize_file_path("../../../etc/passwd")
        with pytest.raises(ValidationError):
            sanitize_file_path("..\\windows\\system32\\config")

    def test_valid_relative_path(self):
        assert sanitize_file_path("images/photo.jpg") == os.path.normpath("images/photo.jpg")

    def test_valid_windows_path(self):
        path = sanitize_file_path("C:\\Users\\User\\file.txt")
        assert ".." not in path

    def test_extension_validation(self):
        with pytest.raises(ValidationError):
            sanitize_file_path("file.exe", allowed_extensions=[".jpg", ".png"])
        assert sanitize_file_path("file.jpg", allowed_extensions=[".jpg", ".png"])


class TestSanitizeHashtagsEdgeCases:
    def test_empty_list(self):
        assert sanitize_hashtags([]) == []

    def test_too_many_hashtags(self):
        tags = [f"tag{i}" for i in range(50)]
        result = sanitize_hashtags(tags)
        assert len(result) == 30

    def test_invalid_characters_filtered(self):
        result = sanitize_hashtags(["good", "bad<tag", "also good", "", None, 123])
        # Spaces in "also good" cause it to be skipped by regex; "good" from "also good" isn't extracted
        assert "good" in result
        assert "bad<tag" not in result
        assert "also_good" not in result  # space prevents match

    def test_hash_prefix_stripped(self):
        assert sanitize_hashtags(["#hello", "world"]) == ["hello", "world"]


class TestSanitizeScheduleDateEdgeCases:
    def test_past_date(self):
        past = (utc_now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        with pytest.raises(ValidationError):
            sanitize_schedule_date(past)

    def test_far_future_date(self):
        future = (utc_now() + timedelta(days=400)).strftime("%Y-%m-%d %H:%M")
        with pytest.raises(ValidationError):
            sanitize_schedule_date(future)

    def test_invalid_format(self):
        with pytest.raises(ValidationError):
            sanitize_schedule_date("not-a-date")
        with pytest.raises(ValidationError):
            sanitize_schedule_date("2025/01/01")

    def test_valid_date(self):
        future = (utc_now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        result = sanitize_schedule_date(future)
        assert isinstance(result, datetime)


# ────────────────────────────────
# 2. Validator Integration Tests
# ────────────────────────────────

class TestPostContentValidation:
    def test_x_content_too_long(self):
        long_post = "A" * 300
        with pytest.raises(ValidationError):
            validate_post_content(long_post, "X")

    def test_tiktok_content_ok(self):
        long_post = "A" * 2000
        validate_post_content(long_post, "TikTok")  # Should not raise

    def test_empty_content(self):
        with pytest.raises(ValidationError):
            validate_post_content("", "X")
        with pytest.raises(ValidationError):
            validate_post_content("   ", "X")

    def test_sql_injection_in_content(self):
        with pytest.raises(ValidationError):
            validate_post_content("Hello'; DROP TABLE posts; --", "X")


class TestAccountIdValidation:
    def test_valid_id(self):
        assert validate_account_id("123") == 123
        assert validate_account_id(456) == 456

    def test_invalid_types(self):
        with pytest.raises(ValidationError):
            validate_account_id("abc")
        with pytest.raises(ValidationError):
            validate_account_id(None)
        with pytest.raises(ValidationError):
            validate_account_id(-5)
        with pytest.raises(ValidationError):
            validate_account_id(0)


class TestPositiveIntValidation:
    def test_valid_values(self):
        assert validate_positive_int(10, "count") == 10
        assert validate_positive_int("5", "limit") == 5

    def test_invalid_values(self):
        with pytest.raises(ValidationError):
            validate_positive_int(0, "count")
        with pytest.raises(ValidationError):
            validate_positive_int(-1, "count")
        with pytest.raises(ValidationError):
            validate_positive_int("abc", "count")


class TestMoodValidation:
    def test_safe_moods(self):
        assert validate_mood("happy") == "happy"
        assert validate_mood("") == ""
        assert validate_mood("PROFESSIONAL") == "professional"

    def test_custom_mood(self):
        assert validate_mood("Mysterious") == "mysterious"

    def test_long_mood_truncated(self):
        long_mood = "x" * 100
        result = validate_mood(long_mood)
        assert len(result) <= 50


class TestTopicHintValidation:
    def test_empty_topic(self):
        assert validate_topic_hint("") == ""
        assert validate_topic_hint(None) == ""

    def test_valid_topic(self):
        assert validate_topic_hint("Artificial Intelligence") == "Artificial Intelligence"

    def test_topic_sanitized(self):
        result = validate_topic_hint("AI<script>")
        assert "<script>" not in result


class TestSQLInjectionDetection:
    def test_safe_strings(self):
        assert check_sql_injection("Hello world") is True
        assert check_sql_injection("What's up?") is True
        assert check_sql_injection("Test 123") is True

    def test_dangerous_patterns(self):
        assert check_sql_injection("'; DROP TABLE users; --") is False
        assert check_sql_injection('" OR "1"="1') is False
        assert check_sql_injection("test--comment") is False
        assert check_sql_injection("test/*comment*/") is False


class TestRateLimiter:
    def test_basic_limiting(self):
        limiter = RateLimiter()
        # Should allow first 5 requests
        for i in range(5):
            allowed, remaining = limiter.check("test_key", max_requests=5, window_seconds=60)
            assert allowed is True
            assert remaining == 5 - (i + 1)
        
        # 6th request should be blocked
        allowed, remaining = limiter.check("test_key", max_requests=5, window_seconds=60)
        assert allowed is False
        assert remaining == 0

    def test_different_keys_independent(self):
        limiter = RateLimiter()
        # Use up key_a
        for _ in range(5):
            limiter.check("key_a", max_requests=5, window_seconds=60)
        assert limiter.check("key_a", max_requests=5, window_seconds=60)[0] is False
        
        # key_b should still work
        assert limiter.check("key_b", max_requests=5, window_seconds=60)[0] is True

    def test_reset(self):
        limiter = RateLimiter()
        limiter.check("key", max_requests=5, window_seconds=60)
        limiter.reset("key")
        allowed, remaining = limiter.check("key", max_requests=5, window_seconds=60)
        assert allowed is True
        assert remaining == 4


# ────────────────────────────────
# 3. GUI Component Tests
# ────────────────────────────────

class TestGUIBootstrap:
    """Test that GUI modules can be imported without errors."""
    
    def test_main_imports(self):
        """main.py should import cleanly (flet optional guarded)."""
        # This just verifies no syntax/import errors at module level
        import main
        assert hasattr(main, "You2App")
        assert hasattr(main, "main")

    def test_matrix_banner_imports(self):
        from ui.matrix_banner import matrix_header
        assert callable(matrix_header)

    def test_tray_manager_imports(self):
        from ui.tray_manager import TrayManager
        assert TrayManager is not None

    def test_dialogs_imports(self):
        from ui.dialogs import show_error, show_error_with_trace
        assert callable(show_error)
        assert callable(show_error_with_trace)


class TestSettingsPersistence:
    """Test that settings load/save correctly."""
    
    def test_settings_load(self):
        from config.settings import load_settings
        s = load_settings()
        assert s is not None
        assert hasattr(s, "ollama_url")
        assert hasattr(s, "ollama_model")
        assert hasattr(s, "temperature")

    def test_settings_save_load_roundtrip(self):
        from config.settings import load_settings
        s = load_settings()
        original_temp = s.temperature
        try:
            s.temperature = 0.77
            s.save_to_disk()
            
            s2 = load_settings()
            assert abs(s2.temperature - 0.77) < 0.01
        finally:
            s.temperature = original_temp
            s.save_to_disk()


# ────────────────────────────────
# 4. Async Error Handling Tests
# ────────────────────────────────

@pytest.mark.asyncio
class TestAsyncOllamaBridgeErrors:
    """Test OllamaBridge handles network errors gracefully."""
    
    async def test_chat_offline(self):
        from brain.ollama_bridge import OllamaBridge
        bridge = OllamaBridge(base_url="http://192.0.2.1:9999")  # Non-routable IP
        result = await bridge.chat([{"role": "user", "content": "test"}])
        assert result is None or "error" in str(result).lower()

    async def test_generate_offline(self):
        from brain.ollama_bridge import OllamaBridge
        bridge = OllamaBridge(base_url="http://192.0.2.1:9999")
        result = await bridge.generate("test prompt")
        assert result is None or "error" in str(result).lower()

    async def test_is_available_offline(self):
        from brain.ollama_bridge import OllamaBridge
        bridge = OllamaBridge(base_url="http://192.0.2.1:9999")
        available = await bridge.is_available()
        assert available is False

    async def test_embeddings_offline(self):
        from brain.ollama_bridge import OllamaBridge
        bridge = OllamaBridge(base_url="http://192.0.2.1:9999")
        result = await bridge.embeddings("test text")
        assert result is None or len(result) == 0


@pytest.mark.asyncio
class TestAsyncXClientErrors:
    """Test XClient handles errors gracefully."""
    
    def _make_account(self, **kwargs):
        from models import Account
        acc = Account(platform="X", username="test")
        for k, v in kwargs.items():
            setattr(acc, k, v)
        return acc
    
    async def test_post_tweet_invalid_credentials(self):
        from x_api.x_client import XClient
        acc = self._make_account(token_encrypted=b"invalid")
        client = XClient(account=acc)
        result = await client.post_tweet("test")
        # Should fail gracefully, not crash
        assert result is None or isinstance(result, dict)

    async def test_get_user_tweets_invalid_token(self):
        from x_api.x_client import XClient
        acc = self._make_account(token_encrypted=b"invalid")
        client = XClient(account=acc)
        result = await client.get_user_tweets("12345")
        assert result is None or isinstance(result, list)


@pytest.mark.asyncio
class TestAsyncBrainEngineErrors:
    """Test BrainEngine handles offline Ollama."""
    
    async def test_generate_post_offline(self):
        from brain.brain import BrainEngine
        engine = BrainEngine(ollama_base_url="http://192.0.2.1:9999")
        result = await engine.generate_post(account_id=1, topic_hint="test")
        # Should return fallback or None, not crash
        assert result is None or isinstance(result, str)

    async def test_generate_reply_offline(self):
        from brain.brain import BrainEngine
        engine = BrainEngine(ollama_base_url="http://192.0.2.1:9999")
        result = await engine.generate_reply(account_id=1, original_post="hello")
        assert result is None or isinstance(result, str)


@pytest.mark.asyncio
class TestAsyncPipelineErrors:
    """Test PipelineEngine handles failures gracefully."""
    
    async def test_publish_queued_no_db_entries(self):
        from pipeline.pipeline import PipelineEngine
        pipe = PipelineEngine()
        # publish_queued requires queue_id, but we can test it doesn't crash with invalid id
        result = await pipe.publish_queued(queue_id=99999)
        assert result is None or isinstance(result, dict) or isinstance(result, list)

    async def test_bulk_generate_offline(self):
        from pipeline.pipeline import PipelineEngine
        pipe = PipelineEngine()
        result = await pipe.bulk_generate(account_id=1, topics=["test"])
        assert isinstance(result, list)


@pytest.mark.asyncio
class TestAsyncStyleLearnerErrors:
    """Test StyleLearner handles missing data."""
    
    async def test_analyze_account_not_found(self):
        from brain.style_learner import StyleLearner
        learner = StyleLearner(ollama_base_url="http://192.0.2.1:9999")
        with pytest.raises(ValueError, match="Account 99999 not found"):
            await learner.analyze_account(99999)  # Non-existent account


@pytest.mark.asyncio
class TestAsyncVectorStoreErrors:
    """Test VectorStore handles offline embedding service."""
    
    async def test_search_similar_offline(self):
        from embeddings.vector_store import VectorStore
        store = VectorStore(ollama_base_url="http://192.0.2.1:9999")
        result = await store.search_similar_posts(account_id=1, query="test")
        assert isinstance(result, list)

    async def test_search_memory_offline(self):
        from embeddings.vector_store import VectorStore
        store = VectorStore(ollama_base_url="http://192.0.2.1:9999")
        result = await store.search_memory(account_id=1, query="test")
        assert isinstance(result, list)


@pytest.mark.asyncio
class TestAsyncReplyBotErrors:
    """Test XReplyBot handles API failures."""
    
    def _make_account(self, **kwargs):
        from models import Account
        acc = Account(platform="X", username="test")
        for k, v in kwargs.items():
            setattr(acc, k, v)
        return acc
    
    async def test_fetch_mentions_invalid_credentials(self):
        from platforms.x_reply_bot import XReplyBot
        acc = self._make_account(token_encrypted=b"invalid")
        bot = XReplyBot(account=acc)
        result = await bot.fetch_mentions()
        assert isinstance(result, list)

    async def test_run_once_invalid_account(self):
        from platforms.x_reply_bot import XReplyBot
        acc = self._make_account(token_encrypted=b"invalid")
        bot = XReplyBot(account=acc)
        result = await bot.run_once()
        assert isinstance(result, dict)
