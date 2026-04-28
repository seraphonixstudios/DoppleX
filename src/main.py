from __future__ import annotations

import json
from datetime import datetime, timedelta
import time
from datetime import datetime, timedelta
import time
from typing import List
import os

import flet as ft
from db.database import SessionLocal, init_db
from models import Account, PostHistory, StyleProfile
from brain.brain import BrainEngine
from brain.ollama_bridge import OllamaBridge
from platforms.x_poster import post_text as x_post_text
from platforms.tiktok_poster import post_video as tiktok_post_video
from utils.logger import get_logger
from utils.audit import log_action
from ui.matrix_banner import matrix_header as matrix_header_banner
from utils.error_handler import safe_call
from brain.generator import ContentGenerator
from oauth.oauth_config import PROVIDERS
from oauth.oauth_manager import authorize_provider, refresh_provider
import threading
from encryption.crypto import encrypt


logger = get_logger("you2.ui")


def _refresh_accounts(db) -> List[Account]:
    return db.query(Account).all()


def main(page: ft.Page) -> None:
    page.title = "You2.0 Social Brain"
    page.theme_mode = ft.ThemeMode.DARK
    page.vertical_alignment = ft.MainAxisAlignment.START

    init_db()
    brain = BrainEngine()
    # Add cyberpunk matrix banner header at the top
    header_banner = matrix_header_banner("YOU2.0")
    try:
        page.add(header_banner)
    except Exception:
        # In case UI patching fails, just log and continue
        pass

    # UI components
    accounts_col = ft.Column()
    generated_post_box = ft.TextArea(label="Generated Post", height=120, multiline=True)
    status_text = ft.Text()
    # OAuth authorize helper (runs in background to avoid blocking UI)
    oauth_status_x = ft.Text()
    oauth_status_tiktok = ft.Text()
def _authorize(provider: str):
    def _run():
        res = authorize_provider(provider)
        # Surface errors via modal dialogs if anything went wrong
        if isinstance(res, str) and ("failed" in res.lower() or "error" in res.lower() or res.lower().startswith("oauth")):
            try:
                from ui.dialogs import show_error
                show_error(page, "OAuth Error", res)
            except Exception:
                pass
        if provider == "X":
            oauth_status_x.value = res
        else:
            oauth_status_tiktok.value = res
        page.update()
    t = threading.Thread(target=_run, daemon=True)
    t.start()

def _refresh(provider: str):
    def _run():
        res = refresh_provider(provider)
        if isinstance(res, dict) and res.get("ok"):
            expiry = res.get("expires_in")
            if provider == "X":
                oauth_status_x.value = f"Refreshed: expires in {expiry}"
            else:
                oauth_status_tiktok.value = f"Refreshed: expires in {expiry}"
        else:
            msg = res.get("error", "OAuth refresh failed") if isinstance(res, dict) else str(res)
            try:
                from ui.dialogs import show_error
                show_error(page, "OAuth Refresh Error", msg)
            except Exception:
                pass
        page.update()
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    logs_box = ft.TextArea(label="Logs", height=180, multiline=True, read_only=True)
    log_level_dropdown = ft.Dropdown(
        options=[ft.dropdown.Option("ALL"), ft.dropdown.Option("INFO"), ft.dropdown.Option("WARNING"), ft.dropdown.Option("ERROR")],
        value="ALL",
        label="Filter Level",
        width=180,
    )
    log_search_box = ft.TextField(label="Search", width=240)
    def _read_logs_filtered():
        path = os.path.join("logs", "you2.log")
        if not os.path.exists(path):
            logs_box.value = "No logs yet."
            page.update()
            return
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        level = log_level_dropdown.value
        keyword = log_search_box.value or ""
        def _match(line: str) -> bool:
            if level != "ALL":
                if f"| {level} |" not in line:
                    return False
            if keyword and keyword.lower() not in line.lower():
                return False
            return True
        filtered = [ln for ln in lines[-500:] if _match(ln)]
        logs_box.value = "\n".join(filtered) if filtered else "No logs match filters."
        page.update()
    apply_filters_btn = ft.ElevatedButton(text="Apply Filters", on_click=lambda _: _read_logs_filtered())
    def read_logs():
        log_path = os.path.join("logs", "you2.log")
        if not os.path.exists(log_path):
            logs_box.value = "No logs yet."
        else:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            logs_box.value = "\n".join(lines[-500:])
        page.update()
    refresh_logs_btn = ft.ElevatedButton(text="Refresh Logs", on_click=lambda _: read_logs())
    export_logs_btn = ft.ElevatedButton(text="Export Logs", on_click=lambda _: _export_logs())
    logs_panel = ft.Container(
        ft.Column([
            ft.Row([ft.Text("Logs"), log_level_dropdown, log_search_box, apply_filters_btn], alignment=ft.MainAxisAlignment.START),
            logs_box,
            refresh_logs_btn,
            export_logs_btn,
        ]),
        padding=ft.Padding(12),
        border_radius=ft.border_radius(8),
        border=ft.border.all(1, ft.colors.GREEN_400),
    )
    def _export_logs():
        mod = __import__('src.utils.log_export', fromlist=['export_logs'])
        path = mod.export_logs()
        if path:
            status_text.value = f"Logs exported to {path}"
        else:
            status_text.value = "No logs to export"
        read_logs()
        page.update()

    export_logs_btn = ft.ElevatedButton(text="Export Logs", on_click=lambda _: _export_logs())
    logs_panel = ft.Container(
        ft.Column([
            ft.Text("Logs"),
            logs_box,
            refresh_logs_btn,
            export_logs_btn,
        ]),
        padding=ft.Padding(12),
        border_radius=ft.border_radius(8),
        border=ft.border.all(1, ft.colors.GREEN_400),
    )
    # Auto-refresh logs in background
    try:
        def _auto_refresh_loop():
            import time as _time
            while True:
                read_logs()
                _time.sleep(5)
    _t = __import__('threading').Thread(target=_auto_refresh_loop, daemon=True)
    _t.start()
    except Exception:
        pass
    # Token expiry UI updater
    token_expiry_x = ft.Text()
    token_expiry_tiktok = ft.Text()
    def _expiry_updater():
        import time as _time
        while True:
            try:
                with SessionLocal() as db:
                    ax = db.query(Account).filter(Account.platform == "X").first()
                    at = db.query(Account).filter(Account.platform == "TikTok").first()
                def fmt(acc):
                    if getattr(acc, 'token_expiry', None):
                        delta = acc.token_expiry - datetime.utcnow()
                        secs = int(delta.total_seconds())
                        if secs < 0:
                            return 'expired'
                        h = secs // 3600
                        m = (secs % 3600) // 60
                        return f"{h}h {m}m"
                    return 'not set'
                expiry_x = fmt(ax) if ax else 'not set'
                expiry_t = fmt(at) if at else 'not set'
                token_expiry_x.value = f"X expiry: {expiry_x}"
                token_expiry_tiktok.value = f"TikTok expiry: {expiry_t}"
                page.update()
            except Exception:
                pass
            _time.sleep(60)
    _expiry_thread = __import__('threading').Thread(target=_expiry_updater, daemon=True)
    _expiry_thread.start()
    # OAuth status indicators (defined above, reuse existing names)

    # Form to add account
    platform_dropdown = ft.Dropdown(
        options=[ft.dropdown.Option("X"), ft.dropdown.Option("TikTok")],
        value="X",
        label="Platform",
        width=260,
    )
    username_input = ft.TextField(label="Username", width=260)
    token_input = ft.TextField(label="Token (encrypted in DB)", width=260, password=True)
    refresh_input = ft.TextField(label="Refresh Token", width=260, password=True)
    cookies_input = ft.TextField(label="Cookies JSON (encrypted)", width=260, height=60, multiline=True)

    def refresh_accounts(_=None):
        accounts_col.controls.clear()
        with SessionLocal() as db:
            accounts = _refresh_accounts(db)
        for a in accounts:
            accounts_col.controls.append(ft.Row([
                ft.Text(f"{a.platform}: {a.username or ''}"),
                ft.IconButton("delete", on_click=lambda e, aid=a.id: _remove_account(aid))
            ]))
        page.update()

    def _remove_account(aid: int):
        with SessionLocal() as db:
            acc = db.query(Account).get(aid)
            if acc:
                db.delete(acc)
                db.commit()
        refresh_accounts()

    def add_account_clicked(_=None):
        platform = platform_dropdown.value
        username = username_input.value or None
        token = token_input.value or None
        refresh = refresh_input.value or None
        cookies = cookies_input.value or None
        with SessionLocal() as db:
            ac = Account(platform=platform, username=username)
            if token:
                ac.token_encrypted = encrypt(token)
            if refresh:
                ac.refresh_token_encrypted = encrypt(refresh)
            if cookies:
                ac.cookies_encrypted = encrypt(cookies)
            db.add(ac)
            db.commit()
            log_action("account_added", account_id=ac.id, status="success", details=f"platform={platform}, user={username}")
        refresh_accounts()
        status_text.value = f"Account added: {platform} {username or ''}"
        page.update()

    add_btn = ft.ElevatedButton(text="Add Account", on_click=add_account_clicked)

    accounts_section = ft.Container(
        ft.Column([
            ft.Text("Accounts"),
            ft.Divider(),
            platform_dropdown,
            username_input,
            token_input,
            refresh_input,
            cookies_input,
            add_btn,
        ]),
        padding=ft.Padding(12),
        border_radius=ft.border_radius(8),
        border=ft.border.all(1, ft.colors.BLUE_400),
    )

    # Learn style and generate post (Part 1 baseline)
    def learn_style_clicked(_=None):
        with SessionLocal() as db:
            acc = db.query(Account).first()
            if not acc:
                status_text.value = "No accounts available to learn style."
                page.update()
                return
            last_posts = db.query(PostHistory).filter(PostHistory.account_id == acc.id).order_by(PostHistory.created_at.desc()).limit(30).all()
            style_json = acc.style_profile.profile_json if acc.style_profile else "{}"
            new_profile = StyleProfile(account_id=acc.id, profile_json=json.dumps({"tone": "casual", "topics": ["tech", "lifestyle"]}))
            db.add(new_profile)
            db.commit()
            log_action("style_learned", account_id=acc.id, status="success", details=f"style_profile_id={new_profile.id}")
            status_text.value = "Style profile learned (Part 2 baseline)."
            page.update()

    learn_btn = ft.ElevatedButton(text="Learn My Style", on_click=learn_style_clicked)

    def generate_post_clicked(_=None):
        with SessionLocal() as db:
            acc = db.query(Account).first()
            if not acc:
                generated_post_box.value = "No accounts configured."
                page.update()
                return
            last_posts = db.query(PostHistory).filter(PostHistory.account_id == acc.id).order_by(PostHistory.created_at).limit(30).all()
            generator = ContentGenerator()
            result = safe_call("GeneratePost", generator.generate_and_store, acc, last_posts)
            if result["ok"]:
                content = result["value"]
            else:
                content = f"Error generating content: {result.get('error')}"
            generated_post_box.value = content
            log_action("content_generated", account_id=acc.id, status="success", details=f"length={len(content)}")
            page.update()

    gen_btn = ft.ElevatedButton(text="Generate Post", on_click=generate_post_clicked)

    publish_platform_dropdown = ft.Dropdown(
        options=[ft.dropdown.Option("X"), ft.dropdown.Option("TikTok")],
        value="X",
        label="Publish Target",
        width=260,
    )
    video_path_input = ft.TextField(label="TikTok video path", width=260, multiline=False)
    caption_input = ft.TextField(label="TikTok caption", width=260, multiline=True, height=60)
    publish_button = ft.ElevatedButton(text="Publish Now", on_click=lambda _: publish_live_clicked())

    def publish_live_clicked(_=None):
        target = publish_platform_dropdown.value
        with SessionLocal() as db:
            acc = None
            if target == "X":
                acc = db.query(Account).filter(Account.platform == "X").first()
            else:
                acc = db.query(Account).filter(Account.platform == "TikTok").first()
            if not acc:
                status_text.value = f"No account configured for {target}."
                page.update()
                return
            last_posts = db.query(PostHistory).filter(PostHistory.account_id == acc.id).order_by(PostHistory.created_at).limit(30).all()
            generator = ContentGenerator()
            result = safe_call("PublishContent", generator.generate_and_store, acc, last_posts)
            content = result["value"] if result.get("ok") else f"Error generating content: {result.get('error')}"
            if target == "X":
                res = x_post_text(acc, content)
                if res.get("ok"):
                    post = PostHistory(account_id=acc.id, platform="X", content=content, post_id=None, metadata=json.dumps({"live_post": True}))
                    db.add(post)
                    db.commit()
                    log_action("live_post", account_id=acc.id, status="success", details="platform=X; content_len=" + str(len(content)))
                    status_text.value = "Live post to X completed."
                else:
                    status_text.value = f"X post failed: {res.get('error')}"
            else:
                video = video_path_input.value or ""
                cap = caption_input.value or content
                dry_run_env = str(os.environ.get("YOU2_TIKTOK_DRY_RUN", "0")).lower() in ("1", "true", "yes")
                res = tiktok_post_video(acc, video, cap, dry_run=dry_run_env)
                if res.get("ok"):
                    post = PostHistory(account_id=acc.id, platform="TikTok", content=cap, post_id=None, metadata=json.dumps({"live_post": True}))
                    db.add(post)
                    db.commit()
                    log_action("live_post", account_id=acc.id, status="success", details="platform=TikTok; content_len=" + str(len(cap)))
                    status_text.value = "Live TikTok post attempted."
                else:
                    status_text.value = f"TikTok post failed: {res.get('error')}"
            page.update()

    publish_section = ft.Container(
        ft.Column([
            ft.Text("Publish Live"),
            ft.Row([publish_platform_dropdown, video_path_input, caption_input, publish_button], alignment=ft.MainAxisAlignment.START),
        ]),
        padding=ft.Padding(12),
        border_radius=ft.border_radius(8),
        border=ft.border.all(1, ft.colors.ORANGE_400),
    )

    # OAuth Panel (live auth wiring)
    oauth_panel = ft.Container(
        ft.Column([
            ft.Text("OAuth Manager", size=16, weight=ft.FontWeight.BOLD),
            ft.Row([
            ft.ElevatedButton(text="Authorize X", on_click=lambda _: _authorize("X")),
            ft.ElevatedButton(text="Authorize TikTok", on_click=lambda _: _authorize("TikTok")),
            ft.ElevatedButton(text="Refresh X", on_click=lambda _: _refresh("X")),
            ft.ElevatedButton(text="Refresh TikTok", on_click=lambda _: _refresh("TikTok"))
            ], alignment=ft.MainAxisAlignment.START),
            ft.Row([ft.Text("X:"), oauth_status_x], alignment=ft.MainAxisAlignment.START),
            ft.Row([ft.Text("X expiry:"), token_expiry_x], alignment=ft.MainAxisAlignment.START),
            ft.Row([ft.Text("TikTok:"), oauth_status_tiktok], alignment=ft.MainAxisAlignment.START),
            ft.Row([ft.Text("TikTok expiry:"), token_expiry_tiktok], alignment=ft.MainAxisAlignment.START),
        ]),
        padding=ft.Padding(12),
        border_radius=ft.border_radius(8),
        border=ft.border.all(1, ft.colors.BLUE_400),
    )

    # Layout
    left_col = ft.Column([accounts_section, oauth_panel, logs_panel, status_text], width=360, spacing=12)
    right_col = ft.Column([learn_btn, publish_section, gen_btn, generated_post_box], spacing=12)

    page.add(ft.Row([left_col, right_col], vertical_alignment=ft.MainAxisAlignment.START))


if __name__ == "__main__":
    ft.app(target=main, view=ft.WEB_BROWSER)
