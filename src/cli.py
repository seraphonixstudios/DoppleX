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
from models import Account
from brain.generator import ContentGenerator
from brain.style_learner import StyleLearner
from platforms.x_scraper import scrape_x_history
from platforms.tiktok_scraper import scrape_tiktok_history
from x_api.x_client import post_tweet
from tiktok.tiktok_client import upload_video
from scheduler.scheduler import You2Scheduler
from utils.logger import get_logger

logger = get_logger("you2.cli")


@click.group()
@click.option('--debug', is_flag=True, help='Enable debug logging')
def cli(debug):
    """You2.0 Social Brain - CLI"""
    init_db()
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
def add_account(platform, username, token, refresh, cookies, api_key, api_secret):
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
        db.add(acc)
        db.commit()
        click.echo(f"Account added: {acc.id}")


@cli.command()
def list_accounts():
    """List all accounts"""
    with SessionLocal() as db:
        accounts = db.query(Account).all()
    for a in accounts:
        click.echo(f"{a.id}: {a.platform} @{a.username} (active={a.is_active})")


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
    sched = You2Scheduler()
    post = sched.schedule_post(account_id, content, dt, media_path=media)
    click.echo(f"Scheduled post {post.id} for {dt}")


@cli.command()
def list_scheduled():
    """List scheduled posts"""
    sched = You2Scheduler()
    posts = sched.get_upcoming_posts()
    for p in posts:
        click.echo(f"{p.id}: {p.scheduled_at} | {p.status} | {p.content[:50]}...")
    sched.shutdown()


if __name__ == '__main__':
    cli()
