from __future__ import annotations

import click
import sys
import os

# Fix Windows console encoding for bundled EXE only (avoid breaking pytest capture)
if getattr(sys, "frozen", False) and sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# PyInstaller bootstrap
if getattr(sys, "frozen", False):
    bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    src_path = os.path.join(bundle_dir, "src")
    if os.path.isdir(src_path) and src_path not in sys.path:
        sys.path.insert(0, src_path)
else:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from db.database import init_db, SessionLocal
from models import Account, PostHistory, StyleProfile, ScheduledPost
from brain.generator import ContentGenerator
from brain.style_learner import StyleLearner
from platforms.x_scraper import scrape_x_history
from platforms.tiktok_scraper import scrape_tiktok_history
from x_api.x_client import post_tweet
from tiktok.tiktok_client import upload_video
from scheduler.scheduler import You2Scheduler
from utils.logger import get_logger
from utils.time_utils import utc_now
from config.settings import load_settings

logger = get_logger("you2.cli")
settings = load_settings()


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


@cli.command()
def gui():
    """Launch the desktop GUI"""
    import flet as ft
    from main import main as gui_main
    ft.app(target=gui_main)


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


@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--topic', default='', help='Topic hint')
@click.option('--mood', default='', help='Mood')
def generate(account_id, topic, mood):
    """Generate a post for an account"""
    gen = ContentGenerator()
    content = gen.generate_and_store(account_id, topic_hint=topic, mood=mood)
    click.echo(content)


@cli.command()
@click.option('--account-id', type=int, required=True)
@click.argument('original-content')
def regenerate(account_id, original_content):
    """Regenerate a variation of existing content"""
    gen = ContentGenerator()
    content = gen.regenerate_variation(account_id, original_content)
    click.echo(content)


@cli.command()
@click.option('--account-id', type=int, required=True)
def analyze_style(account_id):
    """Analyze and learn writing style"""
    sl = StyleLearner()
    profile = sl.analyze_account(account_id)
    click.echo(f"Style analyzed for account {account_id}")
    click.echo(f"Tone: {profile.tone}")
    click.echo(f"Avg length: {profile.avg_post_length}")


@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--max-results', type=int, default=100)
def scrape_x(account_id, max_results):
    """Scrape X/Twitter history"""
    result = scrape_x_history(account_id, max_results)
    if result.get('ok'):
        click.echo(f"Imported {result['imported']} posts")
    else:
        click.echo(f"Error: {result.get('error')}")


@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--max-videos', type=int, default=50)
def scrape_tiktok(account_id, max_videos):
    """Scrape TikTok history"""
    result = scrape_tiktok_history(account_id, max_videos)
    if result.get('ok'):
        click.echo(f"Imported {result['imported']} videos")
    else:
        click.echo(f"Error: {result.get('error')}")


@cli.command()
@click.option('--account-id', type=int, required=True)
@click.argument('content')
def post_x(account_id, content):
    """Post to X immediately"""
    if settings.use_dry_run:
        click.echo(f"[DRY RUN] Would post to X: {content[:80]}...")
        return
    result = post_tweet(account_id, content)
    if result.get('ok'):
        click.echo(f"Posted: {result.get('tweet_id')}")
    else:
        click.echo(f"Error: {result.get('error')}")


@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--video-path', required=True)
@click.argument('caption')
def post_tiktok(account_id, video_path, caption):
    """Post video to TikTok"""
    if settings.use_dry_run:
        click.echo(f"[DRY RUN] Would post to TikTok: {caption[:80]}...")
        return
    result = upload_video(account_id, video_path, caption)
    if result.get('ok'):
        click.echo("Upload completed")
    else:
        click.echo(f"Error: {result.get('error')}")


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


@cli.command()
@click.option('--account-id', type=int, required=True)
@click.option('--topic', default='', help='Topic hint')
@click.option('--mood', default='', help='Mood')
@click.option('--date', required=True, help='Schedule date (YYYY-MM-DD HH:MM)')
@click.option('--media', help='Media path (for TikTok)')
def pipeline(account_id, topic, mood, date, media):
    """Full pipeline: generate content + schedule it for posting"""
    from datetime import datetime
    dt = datetime.strptime(date, '%Y-%m-%d %H:%M')
    if dt < utc_now():
        click.echo("Error: Scheduled time must be in the future")
        sys.exit(1)

    gen = ContentGenerator()
    content = gen.generate_and_store(account_id, topic_hint=topic, mood=mood)
    click.echo(f"Generated content ({len(content)} chars):")
    click.echo(content)
    click.echo()

    sched = You2Scheduler()
    post = sched.schedule_post(account_id, content, dt, media_path=media)
    click.echo(f"Scheduled post {post.id} for {dt}")
    sched.shutdown()


@cli.command()
@click.option('--account-id', type=int, required=True)
def reply_bot_check(account_id):
    """Run reply bot once for an account"""
    from platforms.x_reply_bot import XReplyBot
    with SessionLocal() as db:
        acc = db.get(Account, account_id)
    if not acc:
        click.echo("Account not found")
        sys.exit(1)
    bot = XReplyBot(acc)
    result = bot.run_once()
    if result.get('ok'):
        click.echo(f"Checked {result.get('mentions_checked', 0)} mentions, replied to {result.get('replied', 0)}")
    else:
        click.echo(f"Error: {result.get('error')}")


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


@cli.command()
def status():
    """Show system status (Ollama, accounts, scheduled posts)"""
    from brain.ollama_bridge import OllamaBridge
    bridge = OllamaBridge(settings.ollama_url)
    ollama_ok = bridge.is_available()
    click.echo(f"Ollama: {'connected' if ollama_ok else 'offline'} ({settings.ollama_url})")
    click.echo(f"Model: {settings.ollama_model}")
    click.echo(f"Embedding: {settings.embedding_model}")
    click.echo()

    with SessionLocal() as db:
        accounts = db.query(Account).count()
        posts = db.query(PostHistory).count()
        scheduled = db.query(ScheduledPost).filter(ScheduledPost.status == "scheduled").count()
    click.echo(f"Accounts: {accounts}")
    click.echo(f"Posts: {posts}")
    click.echo(f"Scheduled: {scheduled}")


if __name__ == '__main__':
    cli()
