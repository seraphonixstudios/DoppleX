"""Developer console overlay for debugging and error inspection."""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from typing import List, Dict, Any

import flet as ft

from ui.cyber_theme import Neon, MONO, terminal_container, neon_button, ghost_button


class DevConsole:
    """In-app developer console for live logs, errors, and diagnostics."""

    MAX_LOG_LINES = 500
    MAX_ERROR_HISTORY = 50

    def __init__(self, page: ft.Page):
        self.page = page
        self._error_history: List[Dict[str, Any]] = []
        self._log_lines: List[str] = []
        self._overlay_visible = False

        # Console UI components
        self._error_list = ft.ListView(expand=True, spacing=4)
        self._log_view = ft.TextField(
            multiline=True,
            min_lines=15,
            max_lines=25,
            read_only=True,
            bgcolor=Neon.BLACK,
            color=Neon.GREEN,
            border_color=Neon.BORDER,
            text_style=ft.TextStyle(font_family=MONO, size=11),
        )
        self._detail_view = ft.TextField(
            multiline=True,
            min_lines=10,
            max_lines=15,
            read_only=True,
            bgcolor=Neon.BLACK,
            color=Neon.GREEN,
            border_color=Neon.BORDER,
            text_style=ft.TextStyle(font_family=MONO, size=10),
        )
        self._status_text = ft.Text("DevConsole ready", color=Neon.GRAY, size=11, font_family=MONO)

        self._build_overlay()

    def _build_overlay(self):
        """Build the developer console overlay container."""
        # Build tabs separately to avoid assignment-in-expression issues
        self._tabs = ft.Tabs(
            selected_index=0,
            animation_duration=150,
            tabs=[
                ft.Tab(
                    text="Logs",
                    content=ft.Column([
                        ft.Row([
                            ft.Text("Recent log entries:", color=Neon.GRAY, size=11, font_family=MONO),
                            ft.Container(expand=True),
                            ghost_button("Refresh", self._refresh_logs, color=Neon.GREEN),
                        ]),
                        self._log_view,
                    ], expand=True),
                ),
                ft.Tab(
                    text="Errors",
                    content=ft.Column([
                        ft.Row([
                            ft.Text("Recent errors:", color=Neon.GRAY, size=11, font_family=MONO),
                            ft.Container(expand=True),
                            ghost_button("Copy Error", self._copy_selected_error, color=Neon.AMBER),
                        ]),
                        self._error_list,
                        ft.Divider(height=1, color=Neon.BORDER),
                        ft.Text("Detail:", color=Neon.GRAY, size=11, font_family=MONO),
                        self._detail_view,
                    ], expand=True),
                ),
                ft.Tab(
                    text="System",
                    content=ft.Column([
                        ft.Text("System Information", color=Neon.GREEN, size=14,
                                weight=ft.FontWeight.BOLD, font_family=MONO),
                        ft.Text(f"Python: {sys.version}", color=Neon.GREEN, size=11, font_family=MONO),
                        ft.Text(f"Platform: {sys.platform}", color=Neon.GREEN, size=11, font_family=MONO),
                        ft.Text(f"Frozen: {getattr(sys, 'frozen', False)}", color=Neon.GREEN, size=11, font_family=MONO),
                        ft.Text(f"CWD: {os.getcwd()}", color=Neon.GREEN, size=11, font_family=MONO),
                        ft.Text(f"Executable: {sys.executable}", color=Neon.GREEN, size=11, font_family=MONO),
                        ft.Divider(height=1, color=Neon.BORDER),
                        ft.Text(f"Error count: {len(self._error_history)}", color=Neon.AMBER, size=11, font_family=MONO),
                    ], scroll=ft.ScrollMode.AUTO, expand=True),
                ),
            ],
            expand=True,
        )

        self._overlay = ft.Container(
            content=ft.Column([
                # Header bar
                ft.Row([
                    ft.Text("DEVELOPER CONSOLE", size=16, weight=ft.FontWeight.BOLD,
                            color=Neon.GREEN, font_family=MONO),
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.Icons.COPY,
                        tooltip="Copy logs to clipboard",
                        icon_color=Neon.GREEN,
                        on_click=self._copy_logs,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLEAR_ALL,
                        tooltip="Clear console",
                        icon_color=Neon.AMBER,
                        on_click=self._clear_console,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        tooltip="Close (Esc)",
                        icon_color=Neon.RED,
                        on_click=self.hide,
                    ),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=1, color=Neon.BORDER),
                self._tabs,
                ft.Divider(height=1, color=Neon.BORDER),
                self._status_text,
            ], spacing=8),
            bgcolor=Neon.PANEL_BG,
            border=ft.border.all(2, Neon.GREEN),
            border_radius=ft.border_radius.all(4),
            padding=16,
            margin=ft.margin.all(40),
            shadow=ft.BoxShadow(blur_radius=20, color=Neon.GREEN, spread_radius=2),
            alignment=ft.alignment.center,
            visible=False,
        )

    def attach(self, page: ft.Page):
        """Attach the overlay to the page."""
        if self._overlay not in page.overlay:
            page.overlay.append(self._overlay)

    def show(self):
        """Show the developer console."""
        self._overlay.visible = True
        self._overlay_visible = True
        self._refresh_logs()
        self._refresh_errors()
        self._status_text.value = f"DevConsole open | {len(self._error_history)} errors"
        self.page.update()

    def hide(self, _=None):
        """Hide the developer console."""
        self._overlay.visible = False
        self._overlay_visible = False
        self.page.update()

    def toggle(self):
        """Toggle visibility."""
        if self._overlay_visible:
            self.hide()
        else:
            self.show()

    def log_error(self, exc_type, exc_value, exc_tb):
        """Record an exception in the console history."""
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "type": exc_type.__name__ if exc_type else "Unknown",
            "message": str(exc_value),
            "traceback": tb_str,
        }
        self._error_history.insert(0, entry)
        self._error_history = self._error_history[:self.MAX_ERROR_HISTORY]
        
        # Also append to log view immediately if visible
        if self._overlay_visible:
            self._refresh_errors()
            self._status_text.value = f"New error: {entry['type']} — {entry['message'][:60]}"
            self.page.update()

    def _refresh_logs(self, _=None):
        """Reload logs from file."""
        log_path = os.path.join("logs", "you2.log")
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                self._log_lines = lines[-self.MAX_LOG_LINES:]
                self._log_view.value = "".join(self._log_lines)
            except Exception as e:
                self._log_view.value = f"Error reading logs: {e}"
        else:
            self._log_view.value = "No log file found at logs/you2.log"
        self.page.update()

    def _refresh_errors(self, _=None):
        """Refresh the error list UI."""
        self._error_list.controls.clear()
        for i, err in enumerate(self._error_history):
            color = Neon.RED if "error" in err["type"].lower() else Neon.AMBER
            self._error_list.controls.append(
                ft.Container(
                    ft.Row([
                        ft.Text(err["time"], color=Neon.GRAY, size=10, font_family=MONO, width=60),
                        ft.Text(err["type"], color=color, size=11, font_family=MONO, width=120),
                        ft.Text(err["message"][:80], color=Neon.GREEN, size=11, font_family=MONO, expand=True),
                    ], spacing=8),
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    bgcolor=Neon.BLACK if i % 2 == 0 else "#0A0A0A",
                    border_radius=ft.border_radius.all(2),
                    on_click=lambda e, idx=i: self._show_error_detail(idx),
                    data=i,
                )
            )
        self.page.update()

    def _show_error_detail(self, index: int):
        """Show full traceback for selected error."""
        if 0 <= index < len(self._error_history):
            err = self._error_history[index]
            self._detail_view.value = f"[{err['time']}] {err['type']}: {err['message']}\n\n{err['traceback']}"
            self.page.update()

    def _copy_logs(self, _=None):
        """Copy current log content to clipboard."""
        self.page.set_clipboard(self._log_view.value or "")
        self._status_text.value = "Logs copied to clipboard"
        self.page.update()

    def _copy_selected_error(self, _=None):
        """Copy selected error detail to clipboard."""
        self.page.set_clipboard(self._detail_view.value or "")
        self._status_text.value = "Error copied to clipboard"
        self.page.update()

    def _clear_console(self, _=None):
        """Clear error history and logs view."""
        self._error_history.clear()
        self._log_lines.clear()
        self._log_view.value = ""
        self._detail_view.value = ""
        self._error_list.controls.clear()
        self._status_text.value = "Console cleared"
        self.page.update()
