from __future__ import annotations

import typing as typing

import flet as ft


def show_error(page: ft.Page, title: str, message: str, trace: str | None = None) -> None:
    """Display a robust error modal. Optional stack trace can be shown via a toggle."""
    try:
        trace_area = ft.TextField(label="Trace", value=trace or "", height=180, multiline=True, visible=False)
        def _close(_):
            page.dialog = None
            page.update()
        toggle = ft.TextButton("Show Trace", on_click=lambda e: setattr(trace_area, "visible", not getattr(trace_area, "visible", False)) or page.update())
        content_col = ft.Column([
            ft.Text(message),
            toggle,
            trace_area,
        ])
        dialog = ft.AlertDialog(
            title=ft.Text(title),
            content=content_col,
            actions=[ft.TextButton("OK", on_click=_close)],
        )
        page.dialog = dialog
        if hasattr(page, "show_dialog"):
            page.show_dialog(dialog)  # type: ignore
        else:
            # Fallback: a simple snackbar if dialogs API isn't present
            page.snack_bar = ft.SnackBar(ft.Text(f"{title}: {message}"))
            page.snack_bar.open = True
            page.update()
        page.update()
    except Exception:
        # Best-effort fallback: update UI state minimally
        if hasattr(page, "update"):
            page.update()

def show_error_with_trace(page: ft.Page, title: str, message: str, trace: str | None = None) -> None:
    """Compatibility wrapper to surface an error with optional stack trace toggle."""
    show_error(page, title, message, trace=trace)
