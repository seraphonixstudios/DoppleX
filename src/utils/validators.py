from __future__ import annotations

import re
import html
from typing import Optional, List, Tuple
from datetime import datetime, timedelta


class ValidationError(ValueError):
    """Raised when input validation fails."""
    pass


# ────────────────────────── Input Sanitization ──────────────────────────

def sanitize_text(text: str, max_length: int = 5000, allow_newlines: bool = True) -> str:
    """Sanitize user text input: strip, escape HTML, enforce length."""
    if not isinstance(text, str):
        raise ValidationError("Input must be a string")
    
    text = text.strip()
    
    # Escape HTML to prevent XSS in logs/web views
    text = html.escape(text)
    
    # Remove control chars except newlines/tabs
    if allow_newlines:
        text = "".join(c for c in text if c == "\n" or c == "\t" or (c.isprintable() or c.isspace()))
    else:
        text = "".join(c for c in text if c.isprintable() or c.isspace())
    
    # Collapse multiple spaces
    text = re.sub(r" +", " ", text)
    
    if len(text) > max_length:
        raise ValidationError(f"Input exceeds maximum length of {max_length} characters")
    
    return text


def sanitize_username(username: str) -> str:
    """Validate and sanitize a social media username."""
    if not username or not isinstance(username, str):
        raise ValidationError("Username is required")
    
    username = username.strip().lstrip("@")
    
    # Allow ASCII letters, numbers, underscores, dots, hyphens only
    if not re.match(r"^[\w\.-]+$", username, flags=re.ASCII):
        raise ValidationError("Username contains invalid characters. Use only letters, numbers, underscores, dots, and hyphens.")
    
    if len(username) < 1 or len(username) > 50:
        raise ValidationError("Username must be between 1 and 50 characters")
    
    return username


def sanitize_platform(platform: str) -> str:
    """Validate platform name."""
    valid = {"X", "TikTok", "Twitter"}
    platform = platform.strip()
    if platform not in valid:
        raise ValidationError(f"Invalid platform '{platform}'. Must be one of: {', '.join(sorted(valid))}")
    # Normalize Twitter to X
    return "X" if platform == "Twitter" else platform


def sanitize_token(token: str) -> str:
    """Validate API token format."""
    if not token or not isinstance(token, str):
        raise ValidationError("Token is required")
    token = token.strip()
    if len(token) < 8:
        raise ValidationError("Token is too short (minimum 8 characters)")
    if len(token) > 2048:
        raise ValidationError("Token is too long (maximum 2048 characters)")
    # Reject obvious placeholder tokens
    lower = token.lower()
    if lower in ("token", "test", "example", "dummy", "placeholder", "your_token_here"):
        raise ValidationError("Token appears to be a placeholder. Please provide a real token.")
    return token


def sanitize_file_path(path: str, allowed_extensions: Optional[List[str]] = None) -> str:
    """Validate file path for uploads."""
    if not path or not isinstance(path, str):
        raise ValidationError("File path is required")
    
    import os
    path = os.path.normpath(path.strip())
    
    # Prevent directory traversal
    if ".." in path or path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        # Allow absolute paths on Windows (C:\...) but reject UNC and traversal
        if not (len(path) > 2 and path[1] == ":" and path[2] == os.sep):
            raise ValidationError("Invalid file path. Directory traversal is not allowed.")
    
    if allowed_extensions:
        ext = os.path.splitext(path)[1].lower()
        if ext not in allowed_extensions:
            raise ValidationError(f"Invalid file type '{ext}'. Allowed: {', '.join(allowed_extensions)}")
    
    return path


def sanitize_hashtags(hashtags: List[str]) -> List[str]:
    """Validate and sanitize hashtag list."""
    result = []
    for tag in hashtags:
        if not isinstance(tag, str):
            continue
        tag = tag.strip().lstrip("#")
        if not tag:
            continue
        # Only allow alphanumeric and underscores
        if not re.match(r"^\w+$", tag):
            continue
        if len(tag) > 50:
            continue
        result.append(tag)
    return result[:30]  # Max 30 hashtags


def sanitize_schedule_date(date_str: str) -> datetime:
    """Validate and parse schedule date string."""
    formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d"]
    dt = None
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            break
        except ValueError:
            continue
    
    if dt is None:
        raise ValidationError("Invalid date format. Use YYYY-MM-DD HH:MM or YYYY-MM-DD")
    
    # Prevent scheduling too far in the past
    from utils.time_utils import utc_now
    if dt < utc_now() - timedelta(minutes=1):
        raise ValidationError("Scheduled time must be in the future")
    
    # Prevent scheduling too far in the future (1 year max)
    if dt > utc_now() + timedelta(days=365):
        raise ValidationError("Cannot schedule more than 1 year in advance")
    
    return dt


# ────────────────────────── Rate Limiting ──────────────────────────

class RateLimiter:
    """Simple in-memory rate limiter for API operations."""
    
    def __init__(self):
        self._windows: dict = {}
    
    def check(self, key: str, max_requests: int = 10, window_seconds: int = 60) -> Tuple[bool, int]:
        """Check if operation is allowed. Returns (allowed, remaining)."""
        from utils.time_utils import utc_now
        now = utc_now()
        window_start = now - timedelta(seconds=window_seconds)
        
        # Get existing timestamps for this key
        timestamps = self._windows.get(key, [])
        
        # Remove old entries
        timestamps = [t for t in timestamps if t > window_start]
        
        if len(timestamps) >= max_requests:
            self._windows[key] = timestamps
            return False, 0
        
        timestamps.append(now)
        self._windows[key] = timestamps
        return True, max_requests - len(timestamps)
    
    def reset(self, key: str):
        """Reset rate limit for a key."""
        self._windows.pop(key, None)


# Global rate limiter instance
_rate_limiter = RateLimiter()


def rate_limit(key_prefix: str, max_requests: int = 10, window_seconds: int = 60):
    """Decorator to rate-limit a function."""
    import functools
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{key_prefix}:{func.__name__}"
            allowed, remaining = _rate_limiter.check(key, max_requests, window_seconds)
            if not allowed:
                raise ValidationError(f"Rate limit exceeded. Try again in {window_seconds} seconds.")
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ────────────────────────── SQL Injection Guards ──────────────────────────

# SQLAlchemy 2.0 ORM already protects against SQL injection when using
# the query API properly. These are extra defensive checks for raw strings.

SQL_KEYWORDS = {"drop", "delete", "truncate", "alter", "grant", "revoke", "exec", "execute", "union", "insert", "update"}
SQL_PATTERN = re.compile(r"[;\"]|--|/\*|\*/", re.IGNORECASE)


def check_sql_injection(value: str) -> bool:
    """Check if a string contains potential SQL injection patterns."""
    if not value:
        return True
    
    lower = value.lower()
    
    # Check for dangerous SQL characters
    if SQL_PATTERN.search(value):
        return False
    
    # Check for SQL keywords in suspicious contexts
    words = set(re.findall(r"\b\w+\b", lower))
    if words & SQL_KEYWORDS:
        # If SQL keywords appear, require the string to be mostly alphanumeric
        # with common punctuation (not SQL operators)
        if re.search(r"[;\"']", value):
            return False
    
    return True


def validate_no_sql_injection(**fields) -> None:
    """Validate that string fields don't contain SQL injection patterns."""
    for name, value in fields.items():
        if isinstance(value, str) and not check_sql_injection(value):
            raise ValidationError(f"Field '{name}' contains invalid characters")


# ────────────────────────── Content Validation ──────────────────────────

MAX_POST_LENGTHS = {
    "X": 280,
    "TikTok": 2200,
}


def validate_post_content(content: str, platform: str) -> None:
    """Validate post content for a specific platform."""
    if not content or not isinstance(content, str):
        raise ValidationError("Post content is required")
    
    content = content.strip()
    if not content:
        raise ValidationError("Post content cannot be empty")
    
    max_len = MAX_POST_LENGTHS.get(platform, 5000)
    if len(content) > max_len:
        raise ValidationError(f"Post exceeds {platform} maximum length of {max_len} characters")
    
    # Check for SQL injection
    if not check_sql_injection(content):
        raise ValidationError("Post content contains invalid characters")


def validate_account_id(account_id) -> int:
    """Validate account ID."""
    try:
        aid = int(account_id)
    except (TypeError, ValueError):
        raise ValidationError("Account ID must be an integer")
    
    if aid <= 0:
        raise ValidationError("Account ID must be positive")
    
    return aid


def validate_positive_int(value, name: str = "value") -> int:
    """Validate a positive integer."""
    try:
        val = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be an integer")
    
    if val <= 0:
        raise ValidationError(f"{name} must be positive")
    
    return val


# ────────────────────────── Safe Defaults ──────────────────────────

SAFE_MOODS = {"", "happy", "excited", "thoughtful", "casual", "professional", "serious", "humorous", "inspirational", "controversial"}

def validate_mood(mood: str) -> str:
    """Validate and normalize mood."""
    mood = mood.strip().lower()
    if len(mood) > 50:
        mood = mood[:50]
    if mood and mood not in SAFE_MOODS:
        # Allow custom moods but sanitize
        try:
            mood = sanitize_text(mood, max_length=50, allow_newlines=False)
        except ValidationError:
            mood = mood[:50]
    return mood


def validate_topic_hint(topic: str) -> str:
    """Validate topic hint."""
    if not topic:
        return ""
    return sanitize_text(topic, max_length=200, allow_newlines=False)
