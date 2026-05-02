import pytest
from datetime import timedelta
from db.database import SessionLocal
from models import Account, PostHistory, StyleProfile, ScheduledPost
from utils.time_utils import utc_now
from cli import cli
from click.testing import CliRunner


def test_full_account_lifecycle():
    """End-to-end: add account, generate content, analyze style, schedule post, cancel post."""
    runner = CliRunner()

    # 1. Add an account via CLI
    result = runner.invoke(cli, [
        "add-account",
        "--platform", "X",
        "--username", "e2e_test_user",
        "--token", "test_token_123",
    ])
    assert result.exit_code == 0, result.output
    assert "Account added:" in result.output

    # Get the account ID
    with SessionLocal() as db:
        acc = db.query(Account).filter(Account.username == "e2e_test_user").first()
        assert acc is not None
        account_id = acc.id

    # 2. List accounts
    result = runner.invoke(cli, ["list-accounts"])
    assert result.exit_code == 0
    assert "e2e_test_user" in result.output

    # 3. Generate content (mock Ollama to avoid network dependency)
    from brain.ollama_bridge import OllamaBridge
    original_chat = OllamaBridge.chat
    original_generate = OllamaBridge.generate
    original_embed = OllamaBridge.embeddings

    async def mock_chat(self, messages, model=None, temperature=None, max_tokens=None):
        return "E2E generated content!"

    async def mock_generate(self, prompt, model=None, temperature=None, max_tokens=None):
        return '{"tone": "casual", "topics": ["test"], "summary": "test style"}'

    async def mock_embed(self, text, model=None):
        return [0.1] * 768

    OllamaBridge.chat = mock_chat
    OllamaBridge.generate = mock_generate
    OllamaBridge.embeddings = mock_embed

    try:
        result = runner.invoke(cli, [
            "generate",
            "--account-id", str(account_id),
            "--topic", "end to end testing",
            "--mood", "happy",
        ])
        assert result.exit_code == 0, result.output
        assert len(result.output.strip()) > 0

        # Verify post was stored in DB
        with SessionLocal() as db:
            posts = db.query(PostHistory).filter(
                PostHistory.account_id == account_id,
                PostHistory.source == "brain"
            ).all()
            assert len(posts) >= 1

        # 4. Analyze style
        result = runner.invoke(cli, [
            "analyze-style",
            "--account-id", str(account_id),
        ])
        assert result.exit_code == 0, result.output
        assert "Style analyzed" in result.output

        with SessionLocal() as db:
            profile = db.query(StyleProfile).filter(StyleProfile.account_id == account_id).first()
            assert profile is not None
            assert profile.tone is not None

        # 5. Schedule a post
        schedule_time = (utc_now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        result = runner.invoke(cli, [
            "schedule",
            "--account-id", str(account_id),
            "--date", schedule_time,
            "Scheduled from e2e test",
        ])
        assert result.exit_code == 0, result.output
        assert "Scheduled post" in result.output

        with SessionLocal() as db:
            scheduled = db.query(ScheduledPost).filter(
                ScheduledPost.account_id == account_id
            ).all()
            assert len(scheduled) >= 1
            scheduled_id = scheduled[0].id

        # 6. List scheduled posts
        result = runner.invoke(cli, ["list-scheduled"])
        assert result.exit_code == 0
        assert "Scheduled from e2e test" in result.output

        # 7. Cancel the scheduled post
        result = runner.invoke(cli, ["cancel", "--post-id", str(scheduled_id)])
        assert result.exit_code == 0
        assert "cancelled" in result.output

        # 8. Regenerate variation
        result = runner.invoke(cli, [
            "regenerate",
            "--account-id", str(account_id),
            "Original test content here",
        ])
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0

        # 9. Export data
        result = runner.invoke(cli, ["export-data", "-o", "test_export.json"])
        assert result.exit_code == 0
        assert "Exported" in result.output
        import os
        assert os.path.exists("test_export.json")
        os.remove("test_export.json")

        # 10. Pipeline command (generate + schedule)
        schedule_time = (utc_now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
        result = runner.invoke(cli, [
            "pipeline",
            "--account-id", str(account_id),
            "--topic", "pipeline test",
            "--date", schedule_time,
        ])
        assert result.exit_code == 0, result.output
        assert "Generated content" in result.output
        assert "Scheduled post" in result.output

        # 11. Status command
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "Accounts:" in result.output

        # 12. Delete account
        result = runner.invoke(cli, ["delete-account", "--account-id", str(account_id)])
        assert result.exit_code == 0
        assert "Deleted account" in result.output

        with SessionLocal() as db:
            acc = db.get(Account, account_id)
            assert acc is None

    finally:
        OllamaBridge.chat = original_chat
        OllamaBridge.generate = original_generate
        OllamaBridge.embeddings = original_embed


def test_scheduler_cancel_post():
    """Verify scheduling and cancellation work end-to-end."""
    runner = CliRunner()

    with SessionLocal() as db:
        acc = Account(platform="X", username="sched_test")
        db.add(acc)
        db.commit()
        db.refresh(acc)
        account_id = acc.id

    schedule_time = (utc_now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    result = runner.invoke(cli, [
        "schedule",
        "--account-id", str(account_id),
        "--date", schedule_time,
        "Post to cancel",
    ])
    assert result.exit_code == 0

    with SessionLocal() as db:
        post = db.query(ScheduledPost).filter(ScheduledPost.account_id == account_id).first()
        assert post is not None
        post_id = post.id

    from scheduler.scheduler import You2Scheduler
    sched = You2Scheduler()
    assert sched.cancel_post(post_id) is True

    with SessionLocal() as db:
        post = db.get(ScheduledPost, post_id)
        assert post.status == "cancelled"

    sched.shutdown()

    # Cleanup
    with SessionLocal() as db:
        acc = db.get(Account, account_id)
        if acc:
            db.delete(acc)
            db.commit()


def test_error_handler_safe_call():
    from utils.error_handler import safe_call

    def good():
        return 42

    def bad():
        raise RuntimeError("fail")

    assert safe_call("good", good)["ok"] is True
    assert safe_call("bad", bad)["ok"] is False


def test_dry_run_mode():
    """Verify dry-run flag prevents real API calls."""
    runner = CliRunner()

    with SessionLocal() as db:
        acc = Account(platform="X", username="dryrun_test")
        db.add(acc)
        db.commit()
        db.refresh(acc)
        account_id = acc.id

    # post-x with --dry-run should not attempt real API call
    result = runner.invoke(cli, [
        "--dry-run", "post-x",
        "--account-id", str(account_id),
        "Test dry run content",
    ])
    assert result.exit_code == 0, result.output
    assert "[DRY RUN]" in result.output

    # post-tiktok with --dry-run
    result = runner.invoke(cli, [
        "--dry-run", "post-tiktok",
        "--account-id", str(account_id),
        "--video-path", "fake.mp4",
        "Test dry run caption",
    ])
    assert result.exit_code == 0, result.output
    assert "[DRY RUN]" in result.output

    # Cleanup
    with SessionLocal() as db:
        acc = db.get(Account, account_id)
        if acc:
            db.delete(acc)
            db.commit()
