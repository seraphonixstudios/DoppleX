from __future__ import annotations

import asyncio
import click
import functools
import inspect
import sys
import os

# Fix Windows console encoding (avoid breaking pytest capture)
if sys.platform == "win32" and "pytest" not in sys.modules:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# PyInstaller bootstrap
if getattr(sys, "frozen", False):
    bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    src_path = os.path.join(bundle_dir, "src")
    if os.path.isdir(src_path) and src_path not in sys.path:
        sys.path.insert(0, src_path)
else:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from db.database import init_db, SessionLocal
from models import Account, PostHistory, StyleProfile, ScheduledPost, ContentQueue
from brain.generator import ContentGenerator
from brain.style_learner import StyleLearner
from platforms.x_scraper import scrape_x_history
from platforms.tiktok_scraper import scrape_tiktok_history
from x_api.x_client import post_tweet
from tiktok.tiktok_client import upload_video
from scheduler.scheduler import You2Scheduler
from pipeline.pipeline import PipelineEngine
from utils.logger import get_logger
from utils.time_utils import utc_now
from utils.error_handler import ErrorContext, _get_recovery_hint
from config.settings import load_settings

logger = get_logger("you2.cli")
settings = load_settings()


def _handle_command_error(ctx, operation, exc):
    """Centralized error handler for CLI commands."""
    hint = _get_recovery_hint(exc)
    logger.error(f"Command failed: {operation} | {type(exc).__name__}: {exc}")
    click.echo(click.style(f"Error: {exc}", fg="red"), err=True)
    click.echo(click.style(f"Hint: {hint}", fg="yellow"), err=True)
    ctx.exit(1)

def command_wrapper(operation: str):
    """Decorator to wrap CLI commands with error handling.
    
    Must be applied AFTER @cli.command() so it can patch the Click Command's callback.
    """
    def decorator(cmd):
        original_callback = cmd.callback
        is_async = inspect.iscoroutinefunction(original_callback)

        if is_async:
            @functools.wraps(original_callback)
            def sync_wrapper(*args, **kwargs):
                ctx = click.get_current_context()
                try:
                    return asyncio.run(original_callback(*args, **kwargs))
                except Exception as exc:
                    _handle_command_error(ctx, operation, exc)
            cmd.callback = sync_wrapper
        return cmd
    return decorator

@click.group()
@click.option('--debug', is_flag=True, help='Enable debug logging')
@click.option('--dry-run', is_flag=True, help='Simulate actions without making real API calls')
def cli(debug, dry_run):
    """You2.0 Social Brain - CLI"""
    init_db()
    if dry_run:
        settings.use_dry_run = True
        click.echo("[DRY RUN MODE] No real API calls will be made.")
    if debug:
        import logging
        logging.getLogger("you2").setLevel(logging.DEBUG)


@command_wrapper("gui")
@cli.command()
def gui():
    """Launch the desktop GUI"""
    import flet as ft
    from main import main as gui_main
    ft.app(target=gui_main)


# ─────────── Account Commands ───────────

@command_wrapper("add_account")
@cli.command()
@click.option('--platform', type=click.Choice(['X', 'TikTok']), required=True)
@click.option('--username', required=True)
@click.option('--token', help='Access/bearer token')
@click.option('--refresh', help='Refresh token')
@click.option('--cookies', help='Cookies JSON (TikTok)')
@click.option('--api-key', help='API key (X)')
@click.option('--api-secret', help='API secret (X)')
@click.option('--access-token', help='OAuth 1.0a access token (X)')
@click.option('--access-token-secret', help='OAuth 1.0a access token secret (X)')
def add_account(platform, username, token, refresh, cookies, api_key, api_secret, access_token, access_token_secret):
    """Add a social media account"""
    from encryption.crypto import encrypt
    with SessionLocal() as db:
        acc = Account(platform=platform, username=username)
        if token:
            acc.token_encrypted = encrypt(token)
        if refresh:
            acc.refresh_token_encrypted = encrypt(refresh)
        if cookies:
            acc.cookies_encrypted = encrypt(cookies)
        if api_key:
            acc.api_key_encrypted = encrypt(api_key)
        if api_secret:
            acc.api_secret_encrypted = encrypt(api_secret)
        if access_token:
            acc.access_token_encrypted = encrypt(access_token)
        if access_token_secret:
            acc.access_token_secret_encrypted = encrypt(access_token_secret)
        db.add(acc)
        db.commit()
        click.echo(f"Account added: {acc.id}")


@command_wrapper("delete_account")
@cli.command()
@click.option('--account-id', type=int, required=True)
def delete_account(account_id):
    """Delete an account and all its data"""
    with SessionLocal() as db:
        acc = db.get(Account, account_id)
        if not acc:
            click.echo(f"Account {account_id} not found")
            sys.exit(1)
        platform = acc.platform
        username = acc.username
        db.delete(acc)
        db.commit()
    click.echo(f"Deleted account {account_id} ({platform}: @{username})")


@command_wrapper("list_accounts")
@cli.command()
def list_accounts():
    """List all accounts"""
    with SessionLocal() as db:
        accounts = db.query(Account).order_by(Account.created_at.desc()).all()
    if not accounts:
        click.echo("No accounts configured.")
        return
    for a in accounts:
        expiry = ""
        if a.token_expiry:
            delta = a.token_expiry - utc_now()
            hrs = int(delta.total_seconds() // 3600)
            expiry = f" (expires in {hrs}h)" if hrs > 0 else " (expired)"
        click.echo(f"{a.id}: {a.platform} @{a.username} (active={a.is_active}){expiry}")


# ─────────── Content Generation ───────────

@command_wrapper("generate")
@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--topic', default='', help='Topic hint')
@click.option('--mood', default='', help='Mood')
async def generate(account_id, topic, mood):
    """Generate a post for an account"""
    gen = ContentGenerator()
    content = await gen.generate_and_store(account_id, topic_hint=topic, mood=mood)
    click.echo(content)


@command_wrapper("regenerate")
@cli.command()
@click.option('--account-id', type=int, required=True)
@click.argument('original-content')
async def regenerate(account_id, original_content):
    """Regenerate a variation of existing content"""
    gen = ContentGenerator()
    content = await gen.regenerate_variation(account_id, original_content)
    click.echo(content)


@command_wrapper("queue_content")
@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--topic', default='', help='Topic hint')
@click.option('--mood', default='', help='Mood')
async def queue_content(account_id, topic, mood):
    """Generate content and add to queue as draft"""
    pipe = PipelineEngine()
    item = pipe.queue_content(
        account_id=account_id,
        content="",
        topic_hint=topic,
        mood=mood,
        status="draft",
    )
    queue_id = item.id
    # Generate now
    gen = ContentGenerator()
    content = await gen.generate_and_store(account_id, topic_hint=topic, mood=mood)
    with SessionLocal() as db:
        item = db.get(ContentQueue, queue_id)
        item.content = content
        db.commit()
    click.echo(f"Queued item {queue_id} (draft)")
    click.echo(content)


@command_wrapper("bulk_generate")
@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--topics', required=True, help='Comma-separated topics')
@click.option('--count', type=int, default=1, help='Posts per topic')
@click.option('--platform', default='X', help='Target platform')
async def bulk_generate(account_id, topics, count, platform):
    """Generate multiple posts across topics"""
    pipe = PipelineEngine()
    topic_list = [t.strip() for t in topics.split(',')]
    items = await pipe.bulk_generate(
        account_id=account_id,
        topics=topic_list,
        count_per_topic=count,
        platform=platform,
    )
    click.echo(f"Generated and queued {len(items)} posts")
    for item in items:
        click.echo(f"  [{item.id}] {item.content[:60]}...")


# ─────────── Style & Scraping ───────────

@command_wrapper("analyze_style")
@cli.command()
@click.option('--account-id', type=int, required=True)
async def analyze_style(account_id):
    """Analyze and learn writing style"""
    sl = StyleLearner()
    profile = await sl.analyze_account(account_id)
    click.echo(f"Style analyzed for account {account_id}")
    click.echo(f"Tone: {profile.tone}")
    click.echo(f"Avg length: {profile.avg_post_length}")


@command_wrapper("scrape_x")
@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--max-results', type=int, default=100)
async def scrape_x(account_id, max_results):
    """Scrape X/Twitter history"""
    result = await scrape_x_history(account_id, max_results)
    if result.get('ok'):
        click.echo(f"Imported {result['imported']} posts")
    else:
        click.echo(f"Error: {result.get('error')}")


@command_wrapper("scrape_tiktok")
@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--max-videos', type=int, default=50)
async def scrape_tiktok(account_id, max_videos):
    """Scrape TikTok history"""
    result = await scrape_tiktok_history(account_id, max_videos)
    if result.get('ok'):
        click.echo(f"Imported {result['imported']} videos")
    else:
        click.echo(f"Error: {result.get('error')}")


@command_wrapper("full_pipeline")
@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--topic', default='', help='Topic hint')
@click.option('--mood', default='', help='Mood')
async def full_pipeline(account_id, topic, mood):
    """Full pipeline: scrape → analyze → generate → queue"""
    pipe = PipelineEngine()
    result = await pipe.scrape_and_generate(account_id, topic=topic, mood=mood, auto_queue=True)
    if result.get('ok'):
        click.echo(f"Scraped {result['scraped']} posts, style analyzed: {result['analyzed']}")
        click.echo(f"Generated ({len(result.get('content', ''))} chars):")
        click.echo(result.get('content', ''))
        if result.get('queued'):
            click.echo(f"Queued as item {result['queue_id']}")
    else:
        click.echo(f"Pipeline failed: {result.get('error')}")
        sys.exit(1)


# ─────────── Publishing ───────────

@command_wrapper("post_x")
@cli.command()
@click.option('--account-id', type=int, required=True)
@click.argument('content')
async def post_x(account_id, content):
    """Post to X immediately"""
    if settings.use_dry_run:
        click.echo(f"[DRY RUN] Would post to X: {content[:80]}...")
        return
    result = await post_tweet(account_id, content)
    if result.get('ok'):
        click.echo(f"Posted: {result.get('tweet_id')}")
    else:
        click.echo(f"Error: {result.get('error')}")


@command_wrapper("post_tiktok")
@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--video-path', required=True)
@click.argument('caption')
async def post_tiktok(account_id, video_path, caption):
    """Post video to TikTok"""
    if settings.use_dry_run:
        click.echo(f"[DRY RUN] Would post to TikTok: {caption[:80]}...")
        return
    result = await upload_video(account_id, video_path, caption)
    if result.get('ok'):
        click.echo("Upload completed")
    else:
        click.echo(f"Error: {result.get('error')}")


@command_wrapper("cross_post")
@cli.command()
@click.option('--x-account-id', type=int, required=True)
@click.option('--tiktok-account-id', type=int, required=True)
@click.option('--video-path', help='Video for TikTok')
@click.option('--date', help='Schedule date (YYYY-MM-DD HH:MM)')
@click.argument('content')
async def cross_post(x_account_id, tiktok_account_id, video_path, date, content):
    """Post to both X and TikTok simultaneously"""
    pipe = PipelineEngine()
    schedule_at = None
    if date:
        from datetime import datetime
        schedule_at = datetime.strptime(date, '%Y-%m-%d %H:%M')
    result = await pipe.cross_post(x_account_id, tiktok_account_id, content, video_path, schedule_at)
    click.echo(f"X: {result['x']}")
    click.echo(f"TikTok: {result['tiktok']}")


# ─────────── Scheduling ───────────

@command_wrapper("schedule")
@cli.command()
@click.option('--account-id', type=int, required=True)
@click.argument('content')
@click.option('--date', required=True, help='Schedule date (YYYY-MM-DD HH:MM)')
@click.option('--media', help='Media path (for TikTok)')
def schedule(account_id, content, date, media):
    """Schedule a post"""
    from datetime import datetime
    dt = datetime.strptime(date, '%Y-%m-%d %H:%M')
    if dt < utc_now():
        click.echo("Error: Scheduled time must be in the future")
        sys.exit(1)
    sched = You2Scheduler()
    post = sched.schedule_post(account_id, content, dt, media_path=media)
    click.echo(f"Scheduled post {post.id} for {dt}")


@command_wrapper("schedule_best_time")
@cli.command()
@click.option('--account-id', type=int, required=True)
@click.argument('content')
@click.option('--day-offset', type=int, default=1, help='Days from now')
@click.option('--media', help='Media path')
def schedule_best_time(account_id, content, day_offset, media):
    """Schedule a post at the optimal time for engagement"""
    pipe = PipelineEngine()
    post = pipe.schedule_at_best_time(account_id, content, day_offset=day_offset, media_path=media)
    click.echo(f"Scheduled post {post.id} for {post.scheduled_at} (best time)")


@command_wrapper("list_scheduled")
@cli.command()
def list_scheduled():
    """List scheduled posts"""
    sched = You2Scheduler()
    posts = sched.get_upcoming_posts()
    if not posts:
        click.echo("No upcoming scheduled posts.")
    for p in posts:
        click.echo(f"{p.id}: {p.scheduled_at} | {p.status} | {p.content[:50]}...")
    sched.shutdown()


@command_wrapper("cancel")
@cli.command()
@click.option('--post-id', type=int, required=True)
def cancel(post_id):
    """Cancel a scheduled post"""
    sched = You2Scheduler()
    if sched.cancel_post(post_id):
        click.echo(f"Post {post_id} cancelled")
    else:
        click.echo(f"Could not cancel post {post_id}")
    sched.shutdown()


@command_wrapper("retry_failed")
@cli.command()
@click.option('--account-id', type=int)
def retry_failed(account_id):
    """Retry failed scheduled posts and queue items"""
    pipe = PipelineEngine()
    count = pipe.retry_failed(account_id=account_id)
    click.echo(f"Retried {count} failed items")


@command_wrapper("pipeline")
@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--topic', default='', help='Topic hint')
@click.option('--mood', default='', help='Mood')
@click.option('--date', required=True, help='Schedule date (YYYY-MM-DD HH:MM)')
@click.option('--media', help='Media path (for TikTok)')
async def pipeline(account_id, topic, mood, date, media):
    """Full pipeline: generate content + schedule it for posting"""
    from datetime import datetime
    dt = datetime.strptime(date, '%Y-%m-%d %H:%M')
    if dt < utc_now():
        click.echo("Error: Scheduled time must be in the future")
        sys.exit(1)

    gen = ContentGenerator()
    content = await gen.generate_and_store(account_id, topic_hint=topic, mood=mood)
    click.echo(f"Generated content ({len(content)} chars):")
    click.echo(content)
    click.echo()

    sched = You2Scheduler()
    post = sched.schedule_post(account_id, content, dt, media_path=media)
    click.echo(f"Scheduled post {post.id} for {dt}")
    sched.shutdown()


# ─────────── Queue Management ───────────

@command_wrapper("queue_list")
@cli.command()
@click.option('--account-id', type=int)
@click.option('--status', help='Filter by status')
def queue_list(account_id, status):
    """List content queue items"""
    pipe = PipelineEngine()
    items = pipe.list_queue(account_id=account_id, status=status)
    if not items:
        click.echo("No queue items.")
        return
    for item in items:
        click.echo(f"[{item.id}] {item.status} (p{item.priority}) [{item.platform}] {item.content[:50]}...")


@command_wrapper("queue_approve")
@cli.command()
@click.option('--queue-id', type=int, required=True)
def queue_approve(queue_id):
    """Approve a draft queue item for publishing"""
    pipe = PipelineEngine()
    if pipe.approve_content(queue_id):
        click.echo(f"Item {queue_id} approved")
    else:
        click.echo(f"Could not approve item {queue_id}")


@command_wrapper("queue_publish")
@cli.command()
@click.option('--queue-id', type=int, required=True)
async def queue_publish(queue_id):
    """Publish a queued item immediately"""
    pipe = PipelineEngine()
    result = await pipe.publish_queued(queue_id)
    if result.get('ok'):
        click.echo(f"Published item {queue_id}")
    else:
        click.echo(f"Failed: {result.get('error')}")


@command_wrapper("queue_delete")
@cli.command()
@click.option('--queue-id', type=int, required=True)
def queue_delete(queue_id):
    """Delete a queue item"""
    pipe = PipelineEngine()
    if pipe.delete_queue_item(queue_id):
        click.echo(f"Deleted item {queue_id}")
    else:
        click.echo(f"Item {queue_id} not found")


# ─────────── Reply Bot ───────────

@command_wrapper("reply_bot_check")
@cli.command()
@click.option('--account-id', type=int, required=True)
async def reply_bot_check(account_id):
    """Run reply bot once for an account"""
    from platforms.x_reply_bot import XReplyBot
    with SessionLocal() as db:
        acc = db.get(Account, account_id)
    if not acc:
        click.echo("Account not found")
        sys.exit(1)
    bot = XReplyBot(acc)
    result = await bot.run_once()
    if result.get('ok'):
        click.echo(f"Checked {result.get('mentions_checked', 0)} mentions, replied to {result.get('replied', 0)}")
    else:
        click.echo(f"Error: {result.get('error')}")


# ─────────── Analytics & Export ───────────

@command_wrapper("export_data")
@cli.command()
@click.option('--output', '-o', default='you2_export.json', help='Output file path')
def export_data(output):
    """Export accounts, posts, and style profiles to JSON"""
    import json
    with SessionLocal() as db:
        accounts = db.query(Account).all()
        posts = db.query(PostHistory).order_by(PostHistory.created_at.desc()).all()
        profiles = db.query(StyleProfile).all()

    data = {
        "accounts": [
            {
                "id": a.id,
                "platform": a.platform,
                "username": a.username,
                "is_active": a.is_active,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            } for a in accounts
        ],
        "posts": [
            {
                "id": p.id,
                "account_id": p.account_id,
                "platform": p.platform,
                "content": p.content,
                "source": p.source,
                "generated": p.generated,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            } for p in posts
        ],
        "style_profiles": [
            {
                "id": sp.id,
                "account_id": sp.account_id,
                "tone": sp.tone,
                "avg_post_length": sp.avg_post_length,
                "style_summary": sp.style_summary,
            } for sp in profiles
        ],
    }

    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    click.echo(f"Exported {len(accounts)} accounts, {len(posts)} posts, {len(profiles)} style profiles to {output}")


@command_wrapper("status")
@cli.command()
def status():
    """Show system status (Ollama, accounts, scheduled posts, queue)"""
    from brain.ollama_bridge import OllamaBridge
    bridge = OllamaBridge(settings.ollama_url)
    ollama_ok = asyncio.run(bridge.is_available())
    click.echo(f"Ollama: {'connected' if ollama_ok else 'offline'} ({settings.ollama_url})")
    click.echo(f"Model: {settings.ollama_model}")
    click.echo(f"Embedding: {settings.embedding_model}")
    click.echo()

    with SessionLocal() as db:
        accounts = db.query(Account).count()
        posts = db.query(PostHistory).count()
        scheduled = db.query(ScheduledPost).filter(ScheduledPost.status == "scheduled").count()
        queue_draft = db.query(ContentQueue).filter(ContentQueue.status == "draft").count()
        queue_approved = db.query(ContentQueue).filter(ContentQueue.status == "approved").count()
    click.echo(f"Accounts: {accounts}")
    click.echo(f"Posts: {posts}")
    click.echo(f"Scheduled: {scheduled}")
    click.echo(f"Queue (draft/approved): {queue_draft}/{queue_approved}")


@command_wrapper("best_times")
@cli.command()
@click.option('--account-id', type=int)
def best_times(account_id):
    """Show best posting times based on engagement history"""
    pipe = PipelineEngine()
    times = pipe.get_best_posting_times(account_id)
    click.echo("Top posting hours (engagement-based):")
    for hour, score in times:
        click.echo(f"  {hour:02d}:00 — score: {score}")


if __name__ == '__main__':
    cli()
