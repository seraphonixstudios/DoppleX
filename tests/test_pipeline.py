import pytest
from datetime import timedelta
from db.database import SessionLocal
from models import Account, PostHistory, StyleProfile, ScheduledPost, ContentQueue
from pipeline.pipeline import PipelineEngine
from cli import cli
from click.testing import CliRunner
from utils.time_utils import utc_now


def test_content_queue_lifecycle():
    """Test full queue lifecycle: add → approve → publish → delete."""
    runner = CliRunner()

    # Create test account
    with SessionLocal() as db:
        acc = Account(platform="X", username="queue_test")
        db.add(acc)
        db.commit()
        db.refresh(acc)
        account_id = acc.id

    pipe = PipelineEngine()

    # 1. Queue content
    item = pipe.queue_content(
        account_id=account_id,
        content="Test queued content",
        platform="X",
        priority=3,
    )
    assert item.id is not None
    assert item.status == "draft"

    # 2. Approve
    assert pipe.approve_content(item.id) is True
    with SessionLocal() as db:
        item = db.get(ContentQueue, item.id)
        assert item.status == "approved"

    # 3. List queue
    items = pipe.list_queue(account_id=account_id)
    assert len(items) >= 1

    # 4. Delete
    assert pipe.delete_queue_item(item.id) is True
    with SessionLocal() as db:
        item = db.get(ContentQueue, item.id)
        assert item is None

    # Cleanup
    with SessionLocal() as db:
        acc = db.get(Account, account_id)
        if acc:
            db.delete(acc)
            db.commit()


def test_bulk_generate():
    """Test bulk generation across topics."""
    from brain.ollama_bridge import OllamaBridge
    original_chat = OllamaBridge.chat
    OllamaBridge.chat = lambda self, messages, model=None, temperature=None, max_tokens=None: "Bulk gen content!"
    original_generate = OllamaBridge.generate
    OllamaBridge.generate = lambda self, prompt, model=None, temperature=None, max_tokens=None: '{"tone": "casual", "topics": ["test"], "summary": "test style"}'
    original_embed = OllamaBridge.embeddings
    OllamaBridge.embeddings = lambda self, text, model=None: [0.1] * 768

    try:
        with SessionLocal() as db:
            acc = Account(platform="X", username="bulk_test")
            db.add(acc)
            db.commit()
            db.refresh(acc)
            account_id = acc.id

        pipe = PipelineEngine()
        items = pipe.bulk_generate(
            account_id=account_id,
            topics=["AI", "Python", "DevOps"],
            count_per_topic=2,
            platform="X",
        )
        assert len(items) == 6
        for item in items:
            assert item.status == "draft"
            assert len(item.content) > 0

        # Cleanup
        with SessionLocal() as db:
            acc = db.get(Account, account_id)
            if acc:
                db.delete(acc)
                db.commit()
    finally:
        OllamaBridge.chat = original_chat
        OllamaBridge.generate = original_generate
        OllamaBridge.embeddings = original_embed


def test_retry_failed():
    """Test retry logic for failed scheduled posts."""
    with SessionLocal() as db:
        acc = Account(platform="X", username="retry_test")
        db.add(acc)
        db.commit()
        db.refresh(acc)
        account_id = acc.id

        # Create a failed scheduled post
        post = ScheduledPost(
            account_id=account_id,
            content="Failed post",
            scheduled_at=utc_now() - timedelta(hours=1),
            status="failed",
            error_message="Test failure",
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        post_id = post.id

    pipe = PipelineEngine()
    count = pipe.retry_failed(account_id=account_id)
    assert count >= 1

    with SessionLocal() as db:
        post = db.get(ScheduledPost, post_id)
        assert post.status == "scheduled"
        assert post.scheduled_at > utc_now()

    # Cleanup
    with SessionLocal() as db:
        acc = db.get(Account, account_id)
        if acc:
            db.delete(acc)
            db.commit()


def test_best_times():
    """Test best posting time detection returns valid hours."""
    pipe = PipelineEngine()
    times = pipe.get_best_posting_times()
    assert len(times) > 0
    for hour, score in times:
        assert 0 <= hour <= 23
        assert isinstance(score, int)


def test_scrape_and_generate_pipeline():
    """Test the scrape → analyze → generate → queue pipeline."""
    from brain.ollama_bridge import OllamaBridge
    original_chat = OllamaBridge.chat
    OllamaBridge.chat = lambda self, messages, model=None, temperature=None, max_tokens=None: "Pipeline generated!"
    original_generate = OllamaBridge.generate
    OllamaBridge.generate = lambda self, prompt, model=None, temperature=None, max_tokens=None: '{"tone": "casual", "topics": ["test"], "summary": "test style"}'
    original_embed = OllamaBridge.embeddings
    OllamaBridge.embeddings = lambda self, text, model=None: [0.1] * 768

    try:
        with SessionLocal() as db:
            acc = Account(platform="X", username="pipeline_test")
            db.add(acc)
            db.commit()
            db.refresh(acc)
            account_id = acc.id

        pipe = PipelineEngine()
        result = pipe.scrape_and_generate(account_id, topic="testing", mood="happy")

        assert result["ok"] is True
        assert "content" in result
        assert result["generated"] is True

        # Cleanup
        with SessionLocal() as db:
            acc = db.get(Account, account_id)
            if acc:
                db.delete(acc)
                db.commit()
    finally:
        OllamaBridge.chat = original_chat
        OllamaBridge.generate = original_generate
        OllamaBridge.embeddings = original_embed


def test_cross_post():
    """Test cross-post scheduling."""
    with SessionLocal() as db:
        x_acc = Account(platform="X", username="x_cross")
        tiktok_acc = Account(platform="TikTok", username="tiktok_cross")
        db.add(x_acc)
        db.add(tiktok_acc)
        db.commit()
        db.refresh(x_acc)
        db.refresh(tiktok_acc)

    pipe = PipelineEngine()
    schedule_time = utc_now() + timedelta(days=1)
    result = pipe.cross_post(
        x_account_id=x_acc.id,
        tiktok_account_id=tiktok_acc.id,
        content="Cross-post test",
        schedule_at=schedule_time,
    )

    assert result["x"]["ok"] is True
    assert result["tiktok"]["ok"] is True
    assert "scheduled_id" in result["x"]

    # Cleanup
    with SessionLocal() as db:
        db.delete(x_acc)
        db.delete(tiktok_acc)
        db.commit()


def test_schedule_at_best_time():
    """Test scheduling at best time."""
    with SessionLocal() as db:
        acc = Account(platform="X", username="besttime_test")
        db.add(acc)
        db.commit()
        db.refresh(acc)
        account_id = acc.id

    pipe = PipelineEngine()
    post = pipe.schedule_at_best_time(account_id, "Best time content", day_offset=1)
    assert post.id is not None
    assert post.scheduled_at > utc_now()

    # Cleanup
    with SessionLocal() as db:
        acc = db.get(Account, account_id)
        if acc:
            db.delete(acc)
            db.commit()


def test_queue_cli_commands():
    """Test queue-related CLI commands."""
    runner = CliRunner()

    with SessionLocal() as db:
        acc = Account(platform="X", username="queue_cli_test")
        db.add(acc)
        db.commit()
        db.refresh(acc)
        account_id = acc.id

    # Mock Ollama
    from brain.ollama_bridge import OllamaBridge
    original_chat = OllamaBridge.chat
    OllamaBridge.chat = lambda self, messages, model=None, temperature=None, max_tokens=None: "CLI queued content!"

    try:
        # Queue content
        result = runner.invoke(cli, [
            "queue-content",
            "--account-id", str(account_id),
            "--topic", "CLI test",
        ])
        assert result.exit_code == 0, result.output
        assert "Queued item" in result.output

        # List queue
        result = runner.invoke(cli, ["queue-list", "--account-id", str(account_id)])
        assert result.exit_code == 0
        assert "draft" in result.output

        # Best times
        result = runner.invoke(cli, ["best-times"])
        assert result.exit_code == 0
        assert "Top posting hours" in result.output

    finally:
        OllamaBridge.chat = original_chat

    # Cleanup
    with SessionLocal() as db:
        acc = db.get(Account, account_id)
        if acc:
            db.delete(acc)
            db.commit()
