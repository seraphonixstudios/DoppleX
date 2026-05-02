from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from typing import List

# PyInstaller bootstrap: ensure src/ is on path when frozen
if getattr(sys, "frozen", False):
    bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    src_path = os.path.join(bundle_dir, "src")
    if os.path.isdir(src_path) and src_path not in sys.path:
        sys.path.insert(0, src_path)
else:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import flet as ft
from utils.time_utils import utc_now

from db.database import SessionLocal, init_db
from models import Account, PostHistory, StyleProfile, ScheduledPost, AuditLog
from brain.brain import BrainEngine
from brain.style_learner import StyleLearner
from brain.generator import ContentGenerator
from platforms.x_poster import post_text as x_post_text
from platforms.tiktok_poster import post_video as tiktok_post_video
from platforms.x_scraper import scrape_x_history
from platforms.tiktok_scraper import scrape_tiktok_history
from platforms.x_reply_bot import XReplyBot
from scheduler.scheduler import You2Scheduler
from utils.logger import get_logger
from utils.audit import log_action
from encryption.crypto import encrypt, decrypt
from oauth.oauth_config import PROVIDERS
from oauth.oauth_manager import authorize_provider, refresh_provider
from ui.matrix_banner import matrix_header
from ui.tray_manager import TrayManager
from config.settings import load_settings
from image_gen.sd_client import ImageGenerator
from analytics import metrics
from utils.error_handler import ErrorContext, log_exception, notify_error, _get_recovery_hint

logger = get_logger("you2.ui")
settings = load_settings()


def _refresh_accounts(db) -> List[Account]:
    return db.query(Account).order_by(Account.created_at.desc()).all()


def _refresh_posts(db, account_id: int | None = None, limit: int = 50) -> List[PostHistory]:
    query = db.query(PostHistory).order_by(PostHistory.created_at.desc())
    if account_id:
        query = query.filter(PostHistory.account_id == account_id)
    return query.limit(limit).all()


def _refresh_scheduled(db, account_id: int | None = None) -> List[ScheduledPost]:
    query = db.query(ScheduledPost).order_by(ScheduledPost.scheduled_at)
    if account_id:
        query = query.filter(ScheduledPost.account_id == account_id)
    return query.all()


class You2App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "You2.0 Social Brain"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 20
        self.page.window_width = 1400
        self.page.window_height = 900

        init_db()
        self.scheduler = You2Scheduler()
        self.brain = BrainEngine()
        self.generator = ContentGenerator()
        self.style_learner = StyleLearner()
        self.settings = settings
        self.tray = TrayManager(on_show=self._show_window, on_exit=self._exit_app)

        # Hook window close → minimize to tray
        self.page.window.prevent_close = True
        self.page.window.on_event = self._on_window_event

        self._build_ui()
        self._start_background_tasks()
        self._start_tray()
        self._setup_keyboard_shortcuts()

    def _setup_keyboard_shortcuts(self):
        """Set up global keyboard shortcuts."""
        def on_keyboard(e: ft.KeyboardEvent):
            # Ctrl+1-9: Switch tabs
            if e.ctrl and e.key.isdigit():
                idx = int(e.key) - 1
                if 0 <= idx < len(self.nav_rail.destinations):
                    self.nav_rail.selected_index = idx
                    self._on_nav_change(None)
            # Ctrl+G: Generate
            elif e.ctrl and e.key.lower() == "g":
                self.nav_rail.selected_index = 3
                self._on_nav_change(None)
            # Ctrl+P: Post Now (if on generate tab)
            elif e.ctrl and e.key.lower() == "p":
                self.nav_rail.selected_index = 3
                self._on_nav_change(None)
            # Ctrl+S: Schedule
            elif e.ctrl and e.key.lower() == "s":
                self.nav_rail.selected_index = 4
                self._on_nav_change(None)
            # Ctrl+H: History
            elif e.ctrl and e.key.lower() == "h":
                self.nav_rail.selected_index = 5
                self._on_nav_change(None)
            # Ctrl+Q: Quit
            elif e.ctrl and e.key.lower() == "q":
                self._exit_app()
        self.page.on_keyboard_event = on_keyboard

    def _on_window_event(self, e):
        if e.data == "close":
            if self.tray.is_available():
                self.page.window.visible = False
                self.page.update()
                logger.info("Window minimized to tray")
            else:
                self._exit_app()

    def _show_window(self):
        """Restore window from tray."""
        def _restore():
            self.page.window.visible = True
            self.page.window.focus()
            self.page.update()
        if self.page.platform_thread_id:
            self.page.run_thread(_restore)
        else:
            _restore()

    def _exit_app(self):
        """Fully exit the application."""
        logger.info("Shutting down from tray")
        self.tray.stop()
        self.scheduler.shutdown()
        self.page.window.destroy()

    def _start_tray(self):
        """Start the system tray icon."""
        if self.tray.start():
            # Hook scheduler publish events for notifications
            original_publish = self.scheduler._publish
            def _publish_with_notify(scheduled_post_id: int):
                original_publish(scheduled_post_id)
                try:
                    with SessionLocal() as db:
                        post = db.get(ScheduledPost, scheduled_post_id)
                        if post and post.status == "published":
                            self.tray.notify(
                                "Post Published",
                                f"Scheduled post published to {post.account.platform}"
                            )
                        elif post and post.status == "failed":
                            self.tray.notify(
                                "Post Failed",
                                f"Scheduled post failed: {post.error_message or 'Unknown error'}"
                            )
                except Exception:
                    pass
            self.scheduler._publish = _publish_with_notify

    def _show_error(self, title: str, exc: Exception, show_snackbar: bool = True):
        """Display an error to the user via snackbar, tray notification, and logs."""
        hint = _get_recovery_hint(exc)
        message = f"{title}: {exc}"
        logger.error("GUI error | %s | %s | Hint: %s", title, exc, hint)
        
        if show_snackbar:
            try:
                self.page.show_snack_bar(
                    ft.SnackBar(
                        content=ft.Text(f"{message} (Hint: {hint})"),
                        action="Dismiss",
                        bgcolor=ft.colors.RED_400,
                    )
                )
            except Exception:
                pass
        
        # Tray notification for critical errors
        if self.tray.is_available():
            notify_error(title, str(exc) + f" ({hint})", self.tray)

    def _safe_ui_call(self, title: str, func, *args, **kwargs):
        """Wrap a UI callback with error handling."""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log_exception(f"UI operation failed: {title}", e)
            self._show_error(title, e)
            return None

    def _build_ui(self):
        # Header
        header = matrix_header("YOU2.0")

        # Navigation rail
        self.nav_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            min_extended_width=200,
            group_alignment=-0.9,
            destinations=[
                ft.NavigationRailDestination(icon=ft.icons.DASHBOARD, label="Dashboard"),
                ft.NavigationRailDestination(icon=ft.icons.ACCOUNT_CIRCLE, label="Accounts"),
                ft.NavigationRailDestination(icon=ft.icons.PSYCHOLOGY, label="Style"),
                ft.NavigationRailDestination(icon=ft.icons.CREATE, label="Generate"),
                ft.NavigationRailDestination(icon=ft.icons.SCHEDULE, label="Scheduler"),
                ft.NavigationRailDestination(icon=ft.icons.HISTORY, label="History"),
                ft.NavigationRailDestination(icon=ft.icons.ANALYTICS, label="Analytics"),
                ft.NavigationRailDestination(icon=ft.icons.CHAT, label="Reply Bot"),
                ft.NavigationRailDestination(icon=ft.icons.SETTINGS, label="Settings"),
            ],
            on_change=self._on_nav_change,
        )

        # Content area
        self.content_area = ft.Container(expand=True)

        # Status bar
        self.status_text = ft.Text("Ready", size=12)
        self.ollama_status = ft.Text("Ollama: checking...", size=12)

        # Layout
        self.page.add(
            ft.Column([
                header,
                ft.Row([
                    self.nav_rail,
                    ft.VerticalDivider(width=1),
                    self.content_area,
                ], expand=True),
                ft.Divider(height=1),
                ft.Row([self.status_text, ft.Text(" | ", size=12), self.ollama_status], alignment=ft.MainAxisAlignment.START),
            ], expand=True)
        )

        self._show_dashboard()

    def _on_nav_change(self, e):
        index = e.control.selected_index
        if index == 0:
            self._show_dashboard()
        elif index == 1:
            self._show_accounts()
        elif index == 2:
            self._show_style()
        elif index == 3:
            self._show_generate()
        elif index == 4:
            self._show_scheduler()
        elif index == 5:
            self._show_history()
        elif index == 6:
            self._show_analytics()
        elif index == 7:
            self._show_reply_bot()
        elif index == 8:
            self._show_settings()

    def _start_background_tasks(self):
        def check_ollama():
            while True:
                try:
                    available = asyncio.run(self.brain.ollama.is_available())
                    model = self.settings.ollama_model
                    self.ollama_status.value = f"Ollama: {'connected' if available else 'offline'} ({model})"
                    self.page.update()
                except Exception:
                    pass
                import time
                time.sleep(10)

        t = threading.Thread(target=check_ollama, daemon=True)
        t.start()

    def _show_dashboard(self):
        with SessionLocal() as db:
            accounts = db.query(Account).count()
            posts = db.query(PostHistory).count()
            scheduled = db.query(ScheduledPost).filter(ScheduledPost.status == "scheduled").count()
            published = db.query(ScheduledPost).filter(ScheduledPost.status == "published").count()
            recent_posts = db.query(PostHistory).order_by(PostHistory.created_at.desc()).limit(5).all()

        recent_list = ft.Column([
            ft.ListTile(
                title=ft.Text(p.content[:80] + "..." if len(p.content) > 80 else p.content, size=12),
                subtitle=ft.Text(f"{p.platform} | {p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else ''}", size=10),
            ) for p in recent_posts
        ], scroll=ft.ScrollMode.AUTO, height=200)

        self.content_area.content = ft.Column([
            ft.Text("Dashboard", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([
                self._stat_card("Accounts", str(accounts), ft.icons.ACCOUNT_CIRCLE),
                self._stat_card("Total Posts", str(posts), ft.icons.POST_ADD),
                self._stat_card("Scheduled", str(scheduled), ft.icons.SCHEDULE),
                self._stat_card("Published", str(published), ft.icons.CHECK_CIRCLE),
            ], wrap=True),
            ft.Divider(),
            ft.Text("Recent Activity", size=18, weight=ft.FontWeight.BOLD),
            recent_list,
        ], scroll=ft.ScrollMode.AUTO, expand=True)
        self.page.update()

    def _stat_card(self, title: str, value: str, icon):
        return ft.Card(
            content=ft.Container(
                ft.Column([
                    ft.Icon(icon, size=32),
                    ft.Text(value, size=28, weight=ft.FontWeight.BOLD),
                    ft.Text(title, size=12),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=20,
                width=160,
            )
        )

    def _show_accounts(self):
        accounts_col = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

        def refresh_accounts():
            accounts_col.controls.clear()
            with SessionLocal() as db:
                accounts = _refresh_accounts(db)
            if not accounts:
                accounts_col.controls.append(
                    ft.Container(
                        ft.Column([
                            ft.Icon(ft.icons.ACCOUNT_CIRCLE_OUTLINED, size=48, color=ft.colors.GREY_600),
                            ft.Text("No accounts yet", size=16, weight=ft.FontWeight.BOLD),
                            ft.Text("Add your first X or TikTok account using the form on the left", size=12, color=ft.colors.GREY_400),
                        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        alignment=ft.alignment.center,
                        padding=40,
                    )
                )
            else:
                for a in accounts:
                    expiry = ""
                    if a.token_expiry:
                        delta = a.token_expiry - utc_now()
                        hrs = int(delta.total_seconds() // 3600)
                        expiry = f" (expires in {hrs}h)" if hrs > 0 else " (expired)"

                    accounts_col.controls.append(
                        ft.Card(
                            content=ft.Container(
                                ft.Column([
                                    ft.Row([
                                        ft.Text(f"{a.platform}", weight=ft.FontWeight.BOLD, size=16),
                                        ft.Text(f"@{a.username or 'unknown'}{expiry}", size=12),
                                        ft.IconButton(ft.icons.DELETE, tooltip="Delete", on_click=lambda e, aid=a.id: remove_account(aid)),
                                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                    ft.Text(f"Active: {a.is_active}", size=11),
                                ]),
                                padding=12,
                            )
                        )
                    )
            self.page.update()

        def remove_account(aid: int):
            with SessionLocal() as db:
                acc = db.get(Account, aid)
                if acc:
                    db.delete(acc)
                    db.commit()
            refresh_accounts()
            self.status_text.value = f"Account {aid} removed"
            self.page.update()

        # Add account form
        platform_dd = ft.Dropdown(
            options=[ft.dropdown.Option("X"), ft.dropdown.Option("TikTok")],
            value="X",
            label="Platform",
            width=200,
        )
        username_tf = ft.TextField(label="Username", width=300)
        token_tf = ft.TextField(label="Bearer Token / Access Token (OAuth 2.0)", width=400, password=True)
        refresh_tf = ft.TextField(label="Refresh Token", width=400, password=True)
        api_key_tf = ft.TextField(label="API Key (X OAuth 1.0a)", width=400, password=True)
        api_secret_tf = ft.TextField(label="API Secret (X OAuth 1.0a)", width=400, password=True)
        access_token_tf = ft.TextField(label="Access Token (X OAuth 1.0a)", width=400, password=True)
        access_token_secret_tf = ft.TextField(label="Access Token Secret (X OAuth 1.0a)", width=400, password=True)
        cookies_tf = ft.TextField(label="Cookies JSON (TikTok)", width=400, multiline=True, min_lines=2, max_lines=4)

        def add_account_clicked(_):
            with SessionLocal() as db:
                ac = Account(
                    platform=platform_dd.value,
                    username=username_tf.value or None,
                    is_active=True,
                )
                if token_tf.value:
                    ac.token_encrypted = encrypt(token_tf.value)
                if refresh_tf.value:
                    ac.refresh_token_encrypted = encrypt(refresh_tf.value)
                if api_key_tf.value:
                    ac.api_key_encrypted = encrypt(api_key_tf.value)
                if api_secret_tf.value:
                    ac.api_secret_encrypted = encrypt(api_secret_tf.value)
                if access_token_tf.value:
                    ac.access_token_encrypted = encrypt(access_token_tf.value)
                if access_token_secret_tf.value:
                    ac.access_token_secret_encrypted = encrypt(access_token_secret_tf.value)
                if cookies_tf.value:
                    ac.cookies_encrypted = encrypt(cookies_tf.value)
                db.add(ac)
                db.commit()
                log_action("account_added", account_id=ac.id, status="success", details=f"platform={platform_dd.value}")
            refresh_accounts()
            self.status_text.value = "Account added"
            self.page.update()

        # OAuth panel
        oauth_status_x = ft.Text(size=12)
        oauth_status_tiktok = ft.Text(size=12)
        token_expiry_x = ft.Text(size=12)
        token_expiry_tiktok = ft.Text(size=12)

        def _run_oauth(provider: str, status_ctrl: ft.Text):
            def _task():
                res = authorize_provider(provider)
                status_ctrl.value = str(res)[:200]
                self.page.update()
            threading.Thread(target=_task, daemon=True).start()

        def _run_refresh(provider: str, status_ctrl: ft.Text, expiry_ctrl: ft.Text):
            def _task():
                res = refresh_provider(provider)
                if isinstance(res, dict) and res.get("ok"):
                    status_ctrl.value = "Refreshed successfully"
                    expiry = res.get("expires_in")
                    if expiry:
                        expiry_ctrl.value = f"Expires in {expiry // 3600}h"
                else:
                    err = res.get("error", "Refresh failed") if isinstance(res, dict) else str(res)
                    status_ctrl.value = f"Error: {err}"
                self.page.update()
            threading.Thread(target=_task, daemon=True).start()

        oauth_panel = ft.Column([
            ft.Text("OAuth Manager", size=16, weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.ElevatedButton("Authorize X", on_click=lambda _: _run_oauth("X", oauth_status_x)),
                ft.ElevatedButton("Refresh X", on_click=lambda _: _run_refresh("X", oauth_status_x, token_expiry_x)),
            ]),
            ft.Row([ft.Text("X status:"), oauth_status_x]),
            ft.Row([ft.Text("X expiry:"), token_expiry_x]),
            ft.Divider(),
            ft.Row([
                ft.ElevatedButton("Authorize TikTok", on_click=lambda _: _run_oauth("TikTok", oauth_status_tiktok)),
                ft.ElevatedButton("Refresh TikTok", on_click=lambda _: _run_refresh("TikTok", oauth_status_tiktok, token_expiry_tiktok)),
            ]),
            ft.Row([ft.Text("TikTok status:"), oauth_status_tiktok]),
            ft.Row([ft.Text("TikTok expiry:"), token_expiry_tiktok]),
        ])

        self.content_area.content = ft.Column([
            ft.Text("Accounts", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.Column([
                    ft.Text("Add Account", size=16, weight=ft.FontWeight.BOLD),
                    platform_dd,
                    username_tf,
                    token_tf,
                    refresh_tf,
                    api_key_tf,
                    api_secret_tf,
                    access_token_tf,
                    access_token_secret_tf,
                    cookies_tf,
                    ft.ElevatedButton("Add Account", on_click=add_account_clicked),
                ], width=450, scroll=ft.ScrollMode.AUTO),
                ft.VerticalDivider(width=1),
                ft.Column([
                    ft.Text("Existing Accounts", size=16, weight=ft.FontWeight.BOLD),
                    accounts_col,
                ], expand=True, scroll=ft.ScrollMode.AUTO),
            ], expand=True),
            ft.Divider(),
            oauth_panel,
        ], scroll=ft.ScrollMode.AUTO, expand=True)

        refresh_accounts()
        self.page.update()

    def _show_style(self):
        account_dd = ft.Dropdown(label="Select Account", width=300)
        style_output = ft.TextField(multiline=True, min_lines=6, max_lines=10, read_only=True, expand=True)
        status = ft.Text()

        def refresh_accounts():
            account_dd.options.clear()
            with SessionLocal() as db:
                accounts = db.query(Account).all()
            for a in accounts:
                label = f"{a.platform}: @{a.username or 'unknown'}"
                account_dd.options.append(ft.dropdown.Option(str(a.id), label))
            if accounts:
                account_dd.value = str(accounts[0].id)
            self.page.update()

        async def analyze_clicked(_):
            if not account_dd.value:
                status.value = "Select an account first"
                self.page.update()
                return
            analyze_btn.disabled = True
            style_spinner.visible = True
            status.value = "Analyzing style... (this may take a minute)"
            self.page.update()

            try:
                profile = await self.style_learner.analyze_account(int(account_dd.value))
                style = profile.profile_json
                style_parsed = json.loads(style) if style else {}
                lines = [
                    f"Tone: {profile.tone or style_parsed.get('tone', 'unknown')}",
                    f"Topics: {', '.join(json.loads(profile.topics) if profile.topics else style_parsed.get('topics', []))}",
                    f"Avg Length: {profile.avg_post_length or style_parsed.get('avg_length', 'unknown')} chars",
                    f"Hashtags: {', '.join(json.loads(profile.common_hashtags) if profile.common_hashtags else style_parsed.get('hashtags', []))}",
                    f"Summary: {profile.style_summary or style_parsed.get('summary', '')}",
                ]
                style_output.value = "\n".join(lines)
                status.value = "Style analysis complete"
            except Exception as e:
                status.value = f"Error: {str(e)}"
                self._show_error("Style analysis failed", e)
            finally:
                analyze_btn.disabled = False
                style_spinner.visible = False
                self.page.update()

        async def scrape_and_learn_clicked(_):
            if not account_dd.value:
                status.value = "Select an account first"
                self.page.update()
                return
            scrape_learn_btn.disabled = True
            style_spinner.visible = True
            status.value = "Scraping history and learning style..."
            self.page.update()

            try:
                aid = int(account_dd.value)
                with SessionLocal() as db:
                    acc = db.get(Account, aid)
                    if not acc:
                        status.value = "Account not found"
                        self.page.update()
                        return

                if acc.platform == "X":
                    res = await scrape_x_history(aid, max_results=100)
                elif acc.platform == "TikTok":
                    res = await scrape_tiktok_history(aid, max_videos=50)
                else:
                    status.value = "Unknown platform"
                    self.page.update()
                    return

                if res.get("ok"):
                    status.value = f"Scraped {res.get('imported', 0)} posts. Analyzing style..."
                    self.page.update()
                    profile = await self.style_learner.analyze_account(aid)
                    style_parsed = json.loads(profile.profile_json) if profile.profile_json else {}
                    lines = [
                        f"Tone: {profile.tone or style_parsed.get('tone', 'unknown')}",
                        f"Topics: {', '.join(json.loads(profile.topics) if profile.topics else style_parsed.get('topics', []))}",
                        f"Avg Length: {profile.avg_post_length or style_parsed.get('avg_length', 'unknown')} chars",
                        f"Hashtags: {', '.join(json.loads(profile.common_hashtags) if profile.common_hashtags else style_parsed.get('hashtags', []))}",
                        f"Summary: {profile.style_summary or style_parsed.get('summary', '')}",
                    ]
                    style_output.value = "\n".join(lines)
                    status.value = f"Scraped {res.get('imported', 0)} posts and analyzed style"
                else:
                    status.value = f"Scrape failed: {res.get('error')}"
            except Exception as e:
                status.value = f"Scrape failed: {str(e)}"
                self._show_error("Scrape and learn failed", e)
            finally:
                scrape_learn_btn.disabled = False
                style_spinner.visible = False
                self.page.update()

        refresh_accounts()

        analyze_btn = ft.ElevatedButton("Analyze Style", on_click=analyze_clicked)
        scrape_learn_btn = ft.ElevatedButton("Scrape & Learn", on_click=scrape_and_learn_clicked)
        style_spinner = ft.ProgressRing(width=16, height=16, visible=False)

        self.content_area.content = ft.Column([
            ft.Text("Style Learning", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([account_dd, analyze_btn, scrape_learn_btn, style_spinner]),
            status,
            ft.Text("Style Profile:", weight=ft.FontWeight.BOLD),
            style_output,
        ], scroll=ft.ScrollMode.AUTO, expand=True)
        self.page.update()

    def _show_generate(self):
        account_dd = ft.Dropdown(label="Select Account", width=300)
        topic_tf = ft.TextField(label="Topic hint (optional)", width=400)
        mood_tf = ft.TextField(label="Mood (optional)", width=300)
        output_tf = ft.TextField(multiline=True, min_lines=6, max_lines=12, read_only=True, expand=True)
        status = ft.Text()

        # Image generation controls
        img_prompt_tf = ft.TextField(label="Image prompt", width=500, multiline=True, min_lines=2)
        img_status = ft.Text()
        img_preview = ft.Image(width=256, height=256, fit=ft.ImageFit.CONTAIN)
        img_path_display = ft.Text(size=12)

        def refresh_accounts():
            account_dd.options.clear()
            with SessionLocal() as db:
                accounts = db.query(Account).all()
            for a in accounts:
                label = f"{a.platform}: @{a.username or 'unknown'}"
                account_dd.options.append(ft.dropdown.Option(str(a.id), label))
            if accounts:
                account_dd.value = str(accounts[0].id)
            self.page.update()

        async def generate_clicked(_):
            if not account_dd.value:
                status.value = "Select an account"
                self.page.update()
                return
            generate_btn.disabled = True
            generate_spinner.visible = True
            status.value = "Generating..."
            self.page.update()

            try:
                content = await self.generator.generate_and_store(
                    int(account_dd.value),
                    topic_hint=topic_tf.value or "",
                    mood=mood_tf.value or "",
                )
                output_tf.value = content
                status.value = f"Generated ({len(content)} chars)"
            except Exception as e:
                status.value = f"Error: {str(e)}"
                self._show_error("Content generation failed", e)
            finally:
                generate_btn.disabled = False
                generate_spinner.visible = False
                self.page.update()

        async def regenerate_clicked(_):
            if not output_tf.value:
                status.value = "Generate something first"
                self.page.update()
                return
            regenerate_btn.disabled = True
            status.value = "Regenerating variation..."
            self.page.update()

            try:
                content = await self.generator.regenerate_variation(int(account_dd.value), output_tf.value)
                output_tf.value = content
                status.value = f"Regenerated ({len(content)} chars)"
            except Exception as e:
                status.value = f"Error: {str(e)}"
                self._show_error("Regeneration failed", e)
            finally:
                regenerate_btn.disabled = False
                self.page.update()

        async def post_now_clicked(_):
            if not account_dd.value or not output_tf.value:
                status.value = "Select account and generate content first"
                self.page.update()
                return
            post_btn.disabled = True
            status.value = "Posting..."
            self.page.update()

            try:
                aid = int(account_dd.value)
                with SessionLocal() as db:
                    acc = db.get(Account, aid)
                if not acc:
                    status.value = "Account not found"
                    self.page.update()
                    return

                if acc.platform == "X":
                    res = await x_post_text(acc, output_tf.value)
                elif acc.platform == "TikTok":
                    status.value = "TikTok requires a video file. Use the Publish tab."
                    self.page.update()
                    return
                else:
                    res = {"ok": False, "error": "Unknown platform"}

                if res.get("ok"):
                    status.value = f"Posted to {acc.platform}!"
                else:
                    status.value = f"Post failed: {res.get('error')}"
            except Exception as e:
                status.value = f"Error: {str(e)}"
                self._show_error("Post now failed", e)
            finally:
                post_btn.disabled = False
                self.page.update()

        async def generate_image_clicked(_):
            if not img_prompt_tf.value:
                img_status.value = "Enter an image prompt"
                self.page.update()
                return
            img_status.value = "Generating image... (this may take a minute)"
            self.page.update()

            try:
                gen = ImageGenerator()
                if not gen.is_available():
                    img_status.value = "Stable Diffusion WebUI not running. Start it at http://localhost:7860"
                    self.page.update()
                    return
                path = gen.generate(img_prompt_tf.value)
                if path:
                    img_preview.src = str(path)
                    img_path_display.value = str(path)
                    img_status.value = f"Image saved: {path.name}"
                else:
                    img_status.value = "Image generation failed"
            except Exception as e:
                img_status.value = f"Error: {str(e)}"
                self._show_error("Image generation failed", e)
            self.page.update()

        async def post_with_image_clicked(_):
            if not account_dd.value or not output_tf.value:
                status.value = "Generate text content first"
                self.page.update()
                return
            if not img_path_display.value:
                status.value = "Generate an image first"
                self.page.update()
                return

            post_img_btn.disabled = True
            status.value = "Posting with image..."
            self.page.update()

            try:
                aid = int(account_dd.value)
                with SessionLocal() as db:
                    acc = db.get(Account, aid)
                if not acc or acc.platform != "X":
                    status.value = "Image posts only supported for X currently"
                    self.page.update()
                    return

                from x_api.x_client import XClient
                client = XClient(acc)
                media_id = await client.upload_media(img_path_display.value)
                if not media_id:
                    status.value = "Image upload failed. Ensure OAuth 1.0a credentials (API key + access token) are set."
                    self.page.update()
                    return

                res = await client.post_tweet(output_tf.value, media_ids=[media_id])
                if res.get("ok"):
                    status.value = f"Posted to X with image!"
                else:
                    status.value = f"Post failed: {res.get('error')}"
            except Exception as e:
                status.value = f"Error: {str(e)}"
                self._show_error("Post with image failed", e)
            finally:
                post_img_btn.disabled = False
                self.page.update()

        refresh_accounts()

        generate_btn = ft.ElevatedButton("Generate", on_click=generate_clicked)
        regenerate_btn = ft.ElevatedButton("Regenerate Variation", on_click=regenerate_clicked)
        post_btn = ft.ElevatedButton("Post Now", on_click=post_now_clicked)
        generate_spinner = ft.ProgressRing(width=16, height=16, visible=False)
        post_img_btn = ft.ElevatedButton("Post with Image", on_click=post_with_image_clicked)

        self.content_area.content = ft.Column([
            ft.Text("Content Generation", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([account_dd, topic_tf, mood_tf]),
            ft.Row([
                generate_btn,
                generate_spinner,
                regenerate_btn,
                post_btn,
            ]),
            status,
            ft.Text("Generated Content:", weight=ft.FontWeight.BOLD),
            output_tf,
            ft.Divider(),
            ft.Text("Image Generation", size=18, weight=ft.FontWeight.BOLD),
            ft.Row([img_prompt_tf]),
            ft.Row([
                ft.ElevatedButton("Generate Image", on_click=generate_image_clicked),
                post_img_btn,
            ]),
            img_status,
            img_path_display,
            img_preview,
        ], scroll=ft.ScrollMode.AUTO, expand=True)
        self.page.update()

    def _show_scheduler(self):
        account_dd = ft.Dropdown(label="Select Account", width=300)
        content_tf = ft.TextField(label="Content", multiline=True, min_lines=4, max_lines=8, width=500)
        media_tf = ft.TextField(label="Media path (TikTok video)", width=400)
        date_picker = ft.TextField(label="Date (YYYY-MM-DD)", width=150)
        time_picker = ft.TextField(label="Time (HH:MM)", width=100)
        scheduled_list = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)
        status = ft.Text()

        def refresh_accounts():
            account_dd.options.clear()
            with SessionLocal() as db:
                accounts = db.query(Account).all()
            for a in accounts:
                label = f"{a.platform}: @{a.username or 'unknown'}"
                account_dd.options.append(ft.dropdown.Option(str(a.id), label))
            if accounts:
                account_dd.value = str(accounts[0].id)
            self.page.update()

        def refresh_scheduled():
            scheduled_list.controls.clear()
            with SessionLocal() as db:
                posts = _refresh_scheduled(db)
            for p in posts:
                scheduled_list.controls.append(
                    ft.Card(
                        content=ft.Container(
                            ft.Row([
                                ft.Column([
                                    ft.Text(p.content[:60] + "..." if len(p.content) > 60 else p.content, size=12),
                                    ft.Text(f"{p.scheduled_at.strftime('%Y-%m-%d %H:%M')} | {p.status}", size=10),
                                ], expand=True),
                                ft.IconButton(ft.icons.DELETE, tooltip="Cancel", on_click=lambda e, pid=p.id: cancel_post(pid)),
                            ]),
                            padding=8,
                        )
                    )
                )
            self.page.update()

        def schedule_clicked(_):
            if not account_dd.value or not content_tf.value or not date_picker.value or not time_picker.value:
                status.value = "Fill in all required fields"
                self.page.update()
                return
            try:
                dt = datetime.strptime(f"{date_picker.value} {time_picker.value}", "%Y-%m-%d %H:%M")
                if dt < utc_now():
                    status.value = "Scheduled time must be in the future"
                    self.page.update()
                    return
            except ValueError:
                status.value = "Invalid date/time format"
                self.page.update()
                return

            self.scheduler.schedule_post(
                int(account_dd.value),
                content_tf.value,
                dt,
                media_path=media_tf.value or None,
            )
            status.value = "Post scheduled!"
            refresh_scheduled()
            self.page.update()

        def cancel_post(pid: int):
            if self.scheduler.cancel_post(pid):
                status.value = "Post cancelled"
            else:
                status.value = "Could not cancel post"
            refresh_scheduled()
            self.page.update()

        refresh_accounts()
        refresh_scheduled()

        # ── Content Calendar ──
        calendar_grid = ft.GridView(
            runs_count=7,
            max_extent=80,
            child_aspect_ratio=1.2,
            spacing=4,
            run_spacing=4,
            height=340,
        )
        calendar_month_label = ft.Text(size=16, weight=ft.FontWeight.BOLD)

        def build_calendar(year: int = None, month: int = None):
            from calendar import monthcalendar, month_name
            now = utc_now()
            year = year or now.year
            month = month or now.month
            calendar_month_label.value = f"{month_name[month]} {year}"
            calendar_grid.controls.clear()
            # Day headers
            for day_name in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
                calendar_grid.controls.append(
                    ft.Container(
                        ft.Text(day_name, size=10, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                        alignment=ft.alignment.center,
                        bgcolor=ft.colors.GREY_800,
                        border_radius=4,
                    )
                )
            # Get scheduled posts for this month
            with SessionLocal() as db:
                posts = db.query(ScheduledPost).filter(
                    ScheduledPost.status == "scheduled",
                ).all()
            post_days = {}
            for p in posts:
                if p.scheduled_at and p.scheduled_at.year == year and p.scheduled_at.month == month:
                    day = p.scheduled_at.day
                    post_days.setdefault(day, 0)
                    post_days[day] += 1
            # Build grid
            for week in monthcalendar(year, month):
                for day in week:
                    if day == 0:
                        calendar_grid.controls.append(ft.Container())
                    else:
                        count = post_days.get(day, 0)
                        color = ft.colors.BLUE_400 if count > 0 else ft.colors.GREY_800
                        calendar_grid.controls.append(
                            ft.Container(
                                ft.Column([
                                    ft.Text(str(day), size=12, text_align=ft.TextAlign.CENTER),
                                    ft.Text(f"{count} post{'s' if count != 1 else ''}" if count else "", size=9, color=ft.colors.WHITE70),
                                ], alignment=ft.MainAxisAlignment.CENTER, spacing=2),
                                alignment=ft.alignment.center,
                                bgcolor=color,
                                border_radius=4,
                                padding=2,
                            )
                        )
            self.page.update()

        build_calendar()

        self.content_area.content = ft.Column([
            ft.Text("Scheduler", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([account_dd]),
            ft.Row([content_tf]),
            ft.Row([media_tf]),
            ft.Row([date_picker, time_picker, ft.ElevatedButton("Schedule Post", on_click=schedule_clicked)]),
            status,
            ft.Divider(),
            ft.Text("Content Calendar", size=18, weight=ft.FontWeight.BOLD),
            calendar_month_label,
            calendar_grid,
            ft.Divider(),
            ft.Text("Upcoming Posts:", weight=ft.FontWeight.BOLD),
            scheduled_list if scheduled_list.controls else ft.Text("No scheduled posts yet. Use the form above to schedule your first post!", italic=True, color=ft.colors.GREY_400),
        ], scroll=ft.ScrollMode.AUTO, expand=True)
        self.page.update()

    def _show_history(self):
        account_dd = ft.Dropdown(label="Filter by Account", width=300, options=[ft.dropdown.Option("0", "All Accounts")])
        search_tf = ft.TextField(label="Search posts...", width=300, hint_text="Type to filter by content")
        posts_list = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)
        status = ft.Text()
        result_count = ft.Text("", size=12, color=ft.colors.GREY_400)

        def refresh_accounts():
            account_dd.options = [ft.dropdown.Option("0", "All Accounts")]
            with SessionLocal() as db:
                accounts = db.query(Account).all()
            for a in accounts:
                label = f"{a.platform}: @{a.username or 'unknown'}"
                account_dd.options.append(ft.dropdown.Option(str(a.id), label))
            account_dd.value = "0"
            self.page.update()

        def refresh_posts():
            posts_list.controls.clear()
            aid = int(account_dd.value) if account_dd.value else 0
            query_text = search_tf.value.strip().lower() if search_tf.value else ""
            with SessionLocal() as db:
                query = db.query(PostHistory).order_by(PostHistory.created_at.desc())
                if aid > 0:
                    query = query.filter(PostHistory.account_id == aid)
                if query_text:
                    query = query.filter(PostHistory.content.ilike(f"%{query_text}%"))
                posts = query.limit(100).all()
            
            result_count.value = f"Showing {len(posts)} post{'s' if len(posts) != 1 else ''}"
            
            if not posts:
                posts_list.controls.append(
                    ft.Container(
                        ft.Column([
                            ft.Icon(ft.icons.SEARCH_OFF, size=48, color=ft.colors.GREY_600),
                            ft.Text("No posts found", size=16, weight=ft.FontWeight.BOLD),
                            ft.Text("Try adjusting your search or filter", size=12, color=ft.colors.GREY_400),
                        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        alignment=ft.alignment.center,
                        padding=40,
                    )
                )
            else:
                for p in posts:
                    posts_list.controls.append(
                        ft.Card(
                            content=ft.Container(
                                ft.Column([
                                    ft.Text(p.content[:120] + "..." if len(p.content) > 120 else p.content, size=12),
                                    ft.Text(f"{p.platform} | {p.source} | {p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else ''}", size=10),
                                ]),
                                padding=8,
                            )
                        )
                    )
            self.page.update()

        def on_search_change(_):
            refresh_posts()

        search_tf.on_change = on_search_change

        async def scrape_clicked(_):
            if not account_dd.value or account_dd.value == "0":
                status.value = "Select a specific account to scrape"
                self.page.update()
                return
            status.value = "Scraping history..."
            self.page.update()

            scrape_btn.disabled = True
            hist_spinner.visible = True
            status.value = "Scraping history..."
            self.page.update()

            try:
                aid = int(account_dd.value)
                with SessionLocal() as db:
                    acc = db.get(Account, aid)
                if not acc:
                    status.value = "Account not found"
                    self.page.update()
                    return

                if acc.platform == "X":
                    res = await scrape_x_history(aid, max_results=100)
                elif acc.platform == "TikTok":
                    res = await scrape_tiktok_history(aid, max_videos=50)
                else:
                    status.value = "Unknown platform"
                    self.page.update()
                    return

                if res.get("ok"):
                    status.value = f"Scraped {res.get('imported', 0)} posts"
                else:
                    status.value = f"Scrape failed: {res.get('error')}"
                refresh_posts()
            except Exception as e:
                status.value = f"Error: {str(e)}"
                self._show_error("History scrape failed", e)
            finally:
                scrape_btn.disabled = False
                hist_spinner.visible = False
                self.page.update()

        refresh_accounts()
        refresh_posts()

        account_dd.on_change = lambda _: refresh_posts()

        scrape_btn = ft.ElevatedButton("Scrape History", on_click=scrape_clicked)
        hist_spinner = ft.ProgressRing(width=16, height=16, visible=False)

        self.content_area.content = ft.Column([
            ft.Text("Post History", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([account_dd, search_tf, scrape_btn, hist_spinner]),
            result_count,
            status,
            posts_list,
        ], scroll=ft.ScrollMode.AUTO, expand=True)
        self.page.update()

    def _show_analytics(self):
        account_dd = ft.Dropdown(label="Filter by Account", width=300, options=[ft.dropdown.Option("0", "All Accounts")])
        status = ft.Text()

        # Chart containers
        posts_chart_container = ft.Container(height=200)
        engagement_container = ft.Column()
        platform_breakdown_container = ft.Column()
        top_posts_container = ft.Column()

        def refresh_accounts():
            account_dd.options = [ft.dropdown.Option("0", "All Accounts")]
            with SessionLocal() as db:
                accounts = db.query(Account).all()
            for a in accounts:
                label = f"{a.platform}: @{a.username or 'unknown'}"
                account_dd.options.append(ft.dropdown.Option(str(a.id), label))
            account_dd.value = "0"
            self.page.update()

        def refresh_analytics():
            aid = int(account_dd.value) if account_dd.value else 0
            account_id = aid if aid > 0 else None

            # Post counts by day
            daily = metrics.get_post_counts_by_day(days=30)
            if daily:
                max_count = max(c for _, c in daily) if daily else 1
                bar_groups = []
                for i, (day, count) in enumerate(daily[-14:]):  # last 14 days
                    bar_groups.append(
                        ft.BarChartGroup(
                            x=i,
                            bar_rods=[ft.BarChartRod(
                                from_y=0,
                                to_y=count,
                                width=16,
                                color=ft.colors.BLUE_400,
                                tooltip=ft.Tooltip(f"{day}: {count}"),
                            )]
                        )
                    )
                posts_chart_container.content = ft.BarChart(
                    bar_groups=bar_groups,
                    bottom_axis=ft.ChartAxis(labels=[]),
                    left_axis=ft.ChartAxis(labels_size=20, title=ft.Text("Posts"), title_size=20),
                    horizontal_grid_lines=ft.ChartGridLines(color=ft.colors.GREY_800, width=1),
                    tooltip_bgcolor=ft.colors.with_opacity(0.8, ft.colors.GREY_800),
                    max_y=max_count + 1,
                    expand=True,
                )
            else:
                posts_chart_container.content = ft.Text("No post data available")

            # Engagement summary
            eng = metrics.get_engagement_summary(account_id)
            engagement_container.controls = [
                ft.Text("Engagement Summary", weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.Text(f"Posts: {eng['total_posts']}"),
                    ft.Text(f"Likes: {eng['total_likes']}"),
                    ft.Text(f"Replies: {eng['total_replies']}"),
                    ft.Text(f"Retweets: {eng['total_retweets']}"),
                ]),
                ft.Row([
                    ft.Text(f"Avg Likes: {eng['avg_likes']}"),
                    ft.Text(f"Avg Replies: {eng['avg_replies']}"),
                    ft.Text(f"Avg Retweets: {eng['avg_retweets']}"),
                ]),
            ]

            # Platform breakdown
            platforms = metrics.get_platform_breakdown()
            platform_breakdown_container.controls = [
                ft.Text("Platform Breakdown", weight=ft.FontWeight.BOLD),
            ] + [ft.Text(f"{platform}: {count}") for platform, count in platforms.items()]

            # Top posts
            top = metrics.get_top_posts(account_id, limit=5)
            top_posts_container.controls = [ft.Text("Top Performing Posts", weight=ft.FontWeight.BOLD)]
            for p in top:
                top_posts_container.controls.append(
                    ft.ListTile(
                        title=ft.Text(p['content'][:80] + "...", size=12),
                        subtitle=ft.Text(f"Score: {p['score']} | {p['platform']}", size=10),
                    )
                )

            self.page.update()

        refresh_accounts()
        refresh_analytics()
        account_dd.on_change = lambda _: refresh_analytics()

        self.content_area.content = ft.Column([
            ft.Text("Analytics Dashboard", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([account_dd]),
            status,
            ft.Text("Posts per Day (last 14 days)", weight=ft.FontWeight.BOLD),
            posts_chart_container,
            ft.Divider(),
            engagement_container,
            ft.Divider(),
            platform_breakdown_container,
            ft.Divider(),
            top_posts_container,
        ], scroll=ft.ScrollMode.AUTO, expand=True)
        self.page.update()

    def _show_reply_bot(self):
        account_dd = ft.Dropdown(label="Select X Account", width=300)
        status = ft.Text()
        reply_log = ft.Column(scroll=ft.ScrollMode.AUTO, height=300)
        bot_enabled_switch = ft.Switch(label="Reply Bot Enabled", value=False)
        auto_reply_switch = ft.Switch(label="Auto-reply to all mentions", value=False)
        freq_slider = ft.Slider(min=5, max=60, divisions=11, label="{value} min", value=15, width=300)

        def refresh_accounts():
            account_dd.options.clear()
            with SessionLocal() as db:
                accounts = db.query(Account).filter(Account.platform == "X").all()
            for a in accounts:
                label = f"@{a.username or 'unknown'}"
                account_dd.options.append(ft.dropdown.Option(str(a.id), label))
            if accounts:
                account_dd.value = str(accounts[0].id)
                # Load settings
                acc = accounts[0]
                bot_enabled_switch.value = acc.reply_bot_enabled or False
                auto_reply_switch.value = acc.auto_reply_enabled or False
                freq_slider.value = acc.reply_bot_frequency or 15
            self.page.update()

        def save_settings_clicked(_):
            if not account_dd.value:
                status.value = "Select an account"
                self.page.update()
                return
            with SessionLocal() as db:
                acc = db.get(Account, int(account_dd.value))
                if acc:
                    acc.reply_bot_enabled = bot_enabled_switch.value
                    acc.auto_reply_enabled = auto_reply_switch.value
                    acc.reply_bot_frequency = int(freq_slider.value)
                    db.commit()
            status.value = "Settings saved"
            self.page.update()

        def start_bot_clicked(_):
            if not account_dd.value:
                status.value = "Select an account"
                self.page.update()
                return
            aid = int(account_dd.value)
            freq = int(freq_slider.value)
            self.scheduler.start_reply_bot(aid, interval_minutes=freq)
            status.value = f"Reply bot started (every {freq} min)"
            self.page.update()

        def stop_bot_clicked(_):
            if not account_dd.value:
                status.value = "Select an account"
                self.page.update()
                return
            self.scheduler.stop_reply_bot(int(account_dd.value))
            status.value = "Reply bot stopped"
            self.page.update()

        async def check_now_clicked(_):
            if not account_dd.value:
                status.value = "Select an account"
                self.page.update()
                return
            check_btn.disabled = True
            reply_spinner.visible = True
            status.value = "Checking mentions..."
            self.page.update()

            try:
                aid = int(account_dd.value)
                with SessionLocal() as db:
                    acc = db.get(Account, aid)
                if not acc:
                    status.value = "Account not found"
                    self.page.update()
                    return

                bot = XReplyBot(acc)
                result = await bot.run_once()

                if result.get("ok"):
                    status.value = f"Checked {result.get('mentions_checked', 0)} mentions, replied to {result.get('replied', 0)}"
                    # Show recent reply history
                    with SessionLocal() as db:
                        replies = db.query(PostHistory).filter(
                            PostHistory.account_id == aid,
                            PostHistory.source == "reply_bot"
                        ).order_by(PostHistory.created_at.desc()).limit(10).all()
                    reply_log.controls = [
                        ft.ListTile(
                            title=ft.Text(r.content[:80] + "...", size=12),
                            subtitle=ft.Text(f"Reply to @{r.reply_to_username} | {r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else ''}", size=10),
                        ) for r in replies
                    ]
                else:
                    status.value = f"Check failed: {result.get('error')}"
            except Exception as e:
                status.value = f"Error: {str(e)}"
                self._show_error("Reply bot check failed", e)
            finally:
                check_btn.disabled = False
                reply_spinner.visible = False
                self.page.update()

        refresh_accounts()

        check_btn = ft.ElevatedButton("Check Now", on_click=check_now_clicked)
        reply_spinner = ft.ProgressRing(width=16, height=16, visible=False)

        self.content_area.content = ft.Column([
            ft.Text("Reply Bot", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([account_dd]),
            ft.Row([bot_enabled_switch, auto_reply_switch]),
            ft.Row([ft.Text("Check frequency:"), freq_slider]),
            ft.Row([
                ft.ElevatedButton("Save Settings", on_click=save_settings_clicked),
                ft.ElevatedButton("Start Bot", on_click=start_bot_clicked),
                ft.ElevatedButton("Stop Bot", on_click=stop_bot_clicked),
                check_btn,
                reply_spinner,
            ]),
            status,
            ft.Text("Recent Replies:", weight=ft.FontWeight.BOLD),
            reply_log,
        ], scroll=ft.ScrollMode.AUTO, expand=True)
        self.page.update()

    def _show_settings(self):
        ollama_url = ft.TextField(label="Ollama URL", value=self.settings.ollama_url, width=400)
        ollama_model = ft.TextField(label="Ollama Model", value=self.settings.ollama_model, width=300)
        embedding_model = ft.TextField(label="Embedding Model", value=self.settings.embedding_model, width=300)
        sd_url = ft.TextField(label="Stable Diffusion WebUI URL", value=self.settings.sd_webui_url, width=400)
        temp_slider = ft.Slider(min=0.0, max=1.5, value=self.settings.temperature, label="{value}", width=300)
        logs_box = ft.TextField(multiline=True, min_lines=10, max_lines=20, read_only=True, expand=True)
        update_status = ft.Text("Click 'Check for Updates' to see if a new version is available.", size=12)
        update_spinner = ft.ProgressRing(width=16, height=16, visible=False)

        def save_settings_clicked(_):
            self.settings.ollama_url = ollama_url.value
            self.settings.ollama_model = ollama_model.value
            self.settings.embedding_model = embedding_model.value
            self.settings.sd_webui_url = sd_url.value
            self.settings.temperature = temp_slider.value
            self.settings.save_to_disk()
            self.status_text.value = "Settings saved to disk"
            self.page.update()

        def refresh_logs():
            log_path = os.path.join("logs", "you2.log")
            if not os.path.exists(log_path):
                logs_box.value = "No logs yet."
            else:
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        lines = f.read().splitlines()
                    logs_box.value = "\n".join(lines[-500:])
                except Exception as e:
                    logs_box.value = f"Error reading logs: {e}"
            self.page.update()

        def check_updates_clicked(_):
            update_spinner.visible = True
            update_status.value = "Checking for updates..."
            self.page.update()

            def _task():
                try:
                    from utils.updater import check_for_updates, get_update_info_text
                    result = check_for_updates()
                    text = get_update_info_text(result)
                    update_status.value = text
                except Exception as e:
                    update_status.value = f"Could not check for updates: {e}"
                finally:
                    update_spinner.visible = False
                    self.page.update()

            threading.Thread(target=_task, daemon=True).start()

        refresh_logs()

        self.content_area.content = ft.Column([
            ft.Text("Settings", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Ollama Configuration", weight=ft.FontWeight.BOLD),
            ollama_url,
            ollama_model,
            embedding_model,
            ft.Text("Image Generation", weight=ft.FontWeight.BOLD),
            sd_url,
            ft.Row([ft.Text("Temperature:"), temp_slider]),
            ft.ElevatedButton("Save Settings", on_click=save_settings_clicked),
            ft.Divider(),
            ft.Text("Updates", weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.ElevatedButton("Check for Updates", on_click=check_updates_clicked),
                update_spinner,
            ]),
            update_status,
            ft.Divider(),
            ft.Text("Logs", weight=ft.FontWeight.BOLD),
            ft.Row([ft.ElevatedButton("Refresh Logs", on_click=lambda _: refresh_logs())]),
            logs_box,
        ], scroll=ft.ScrollMode.AUTO, expand=True)
        self.page.update()


def main(page: ft.Page):
    app = You2App(page)


if __name__ == "__main__":
    ft.app(target=main)
