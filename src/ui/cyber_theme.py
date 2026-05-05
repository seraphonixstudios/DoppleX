"""Cyberpunk / Matrix / Atlantean tech theme for You2.0 Social Brain UI.

Aesthetic: Terminal from a futuristic underwater city.
Neon greens, electric blues, deep abyssal blacks, amber warnings.
Max Headroom glitch + Matrix rain + Atlantean geometric tech.
"""
from __future__ import annotations

import random
import string
import flet as ft


# ─────────────────────────── Color Palette ───────────────────────────

class Neon:
    """Neon accent colors"""
    GREEN = "#39FF14"          # Classic Matrix green
    GREEN_BRIGHT = "#00FF41"   # Brighter terminal green
    GREEN_DIM = "#0A3A0A"      # Dark background green
    CYAN = "#00F0FF"           # Electric Atlantean blue
    CYAN_DIM = "#003B3D"       # Deep water blue
    AMBER = "#FFB000"          # Warning/Max Headroom amber
    AMBER_DIM = "#3D2A00"
    MAGENTA = "#FF00A0"        # Accent
    RED = "#FF2A2A"
    WHITE = "#E0E0E0"
    GRAY = "#8A8A8A"
    BLACK = "#050505"          # Almost black
    DEEP_BLUE = "#0A0A1A"      # Deep abyss
    PANEL_BG = "#0D1117"       # Terminal panel background
    BORDER = "#1A2A1A"         # Subtle green-tinted border
    BORDER_GLOW = "#39FF1430"  # Transparent glow


# ─────────────────────────── Font Styles ───────────────────────────

MONO = "Consolas, 'Courier New', monospace"


def neon_text(text: str, size: int = 14, color: str = Neon.GREEN, weight=ft.FontWeight.NORMAL) -> ft.Text:
    """Create text with subtle glow effect."""
    return ft.Text(
        text,
        size=size,
        color=color,
        weight=weight,
        font_family=MONO,
    )


def glitch_text(text: str, size: int = 24) -> ft.Text:
    """Create a glitched-looking title with shadow offset."""
    return ft.Stack([
        # Shadow offset (cyan)
        ft.Text(text, size=size, color=Neon.CYAN, opacity=0.6,
                font_family=MONO, weight=ft.FontWeight.BOLD,
                offset=ft.Offset(-0.003, 0.003)),
        # Main text (green)
        ft.Text(text, size=size, color=Neon.GREEN,
                font_family=MONO, weight=ft.FontWeight.BOLD),
        # Highlight offset (white)
        ft.Text(text, size=size, color=Neon.WHITE, opacity=0.3,
                font_family=MONO, weight=ft.FontWeight.BOLD,
                offset=ft.Offset(0.002, -0.002)),
    ])


# ─────────────────────────── Container Factories ───────────────────────────

def neon_card(content, width=None, height=None, border_color=Neon.BORDER, glow_color=Neon.BORDER_GLOW) -> ft.Card:
    """Create a card with neon border and subtle glow."""
    return ft.Card(
        content=ft.Container(
            content=content,
            padding=16,
            bgcolor=Neon.PANEL_BG,
            border=ft.border.all(1, border_color),
            border_radius=ft.border_radius.all(2),
            width=width,
            height=height,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=8,
                color=glow_color,
                offset=ft.Offset(0, 0),
            ),
        ),
        elevation=0,
    )


def terminal_container(content, padding=16, border_color=Neon.BORDER) -> ft.Container:
    """Container styled like a terminal panel."""
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=Neon.PANEL_BG,
        border=ft.border.all(1, border_color),
        border_radius=ft.border_radius.all(2),
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=4,
            color=Neon.BORDER_GLOW,
            offset=ft.Offset(0, 0),
        ),
    )


def neon_button(text: str, on_click, color=Neon.GREEN, icon=None) -> ft.ElevatedButton:
    """Create a neon-styled button."""
    btn = ft.ElevatedButton(
        text,
        on_click=on_click,
        icon=icon,
        style=ft.ButtonStyle(
            color=Neon.BLACK,
            bgcolor=color,
            shape=ft.RoundedRectangleBorder(radius=2),
            padding=ft.padding.symmetric(horizontal=20, vertical=12),
            text_style=ft.TextStyle(font_family=MONO, weight=ft.FontWeight.BOLD),
            overlay_color=Neon.WHITE,
        ),
    )
    return btn


def ghost_button(text: str, on_click, color=Neon.GREEN) -> ft.OutlinedButton:
    """Outlined neon button (ghost style)."""
    return ft.OutlinedButton(
        text,
        on_click=on_click,
        style=ft.ButtonStyle(
            color=color,
            side=ft.BorderSide(1, color),
            shape=ft.RoundedRectangleBorder(radius=2),
            padding=ft.padding.symmetric(horizontal=20, vertical=12),
            text_style=ft.TextStyle(font_family=MONO),
        ),
    )


def neon_input(label: str, **kwargs) -> ft.TextField:
    """Create a terminal-styled text input."""
    defaults = dict(
        label=label,
        border_color=Neon.BORDER,
        focused_border_color=Neon.GREEN,
        cursor_color=Neon.GREEN,
        color=Neon.GREEN,
        bgcolor=Neon.BLACK,
        text_style=ft.TextStyle(font_family=MONO, color=Neon.GREEN),
        label_style=ft.TextStyle(font_family=MONO, color=Neon.GRAY, size=12),
        border_radius=ft.border_radius.all(2),
    )
    defaults.update(kwargs)
    return ft.TextField(**defaults)


def neon_dropdown(label: str, options, **kwargs) -> ft.Dropdown:
    """Create a terminal-styled dropdown."""
    return ft.Dropdown(
        label=label,
        options=options,
        border_color=Neon.BORDER,
        focused_border_color=Neon.GREEN,
        color=Neon.GREEN,
        bgcolor=Neon.BLACK,
        text_style=ft.TextStyle(font_family=MONO, color=Neon.GREEN),
        label_style=ft.TextStyle(font_family=MONO, color=Neon.GRAY, size=12),
        border_radius=ft.border_radius.all(2),
        **kwargs,
    )


# ─────────────────────────── Status Indicators ───────────────────────────

def status_badge(text: str, status: str = "ok") -> ft.Container:
    """Create a pulsing status badge."""
    colors = {
        "ok": (Neon.GREEN, Neon.GREEN_DIM),
        "warning": (Neon.AMBER, Neon.AMBER_DIM),
        "error": (Neon.RED, "#3D0A0A"),
        "info": (Neon.CYAN, Neon.CYAN_DIM),
    }
    fg, bg = colors.get(status, (Neon.GRAY, Neon.BLACK))
    return ft.Container(
        ft.Text(text, size=10, color=fg, font_family=MONO, weight=ft.FontWeight.BOLD),
        bgcolor=bg,
        padding=ft.padding.symmetric(horizontal=8, vertical=4),
        border_radius=ft.border_radius.all(2),
        border=ft.border.all(1, fg),
    )


# ─────────────────────────── Scanline Effect ───────────────────────────

def scanline_overlay() -> ft.Container:
    """CRT scanline overlay - horizontal lines across the screen."""
    lines = ft.Column(
        [ft.Container(height=2, bgcolor="#00000020") for _ in range(200)],
        spacing=2,
        expand=True,
    )
    return ft.Container(
        lines,
        expand=True,
        opacity=0.15,
        pointer_event="none",  # Let clicks pass through
    )


# ─────────────────────────── Matrix Rain Header ───────────────────────────

class MatrixRainHeader(ft.Container):
    """Animated Matrix rain header with glitch title."""

    def __init__(self, title: str = "YOU2.0", height: int = 100):
        super().__init__()
        self.title_str = title
        self.height = height
        self.bgcolor = Neon.BLACK
        self.padding = ft.padding.all(16)
        self.border = ft.border.all(1, Neon.BORDER)
        self.border_radius = ft.border_radius.all(2)

        # Build the static content (rain is simulated with random chars)
        self._build_content()

    def _build_content(self):
        # Random matrix characters in background
        katakana = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ"
        chars = string.ascii_letters + string.digits + katakana
        rain_chars = []
        for _ in range(60):
            rain_chars.append(
                ft.Text(
                    random.choice(chars),
                    size=random.choice([8, 10, 12]),
                    color=Neon.GREEN,
                    opacity=random.uniform(0.05, 0.3),
                    font_family=MONO,
                )
            )

        rain_grid = ft.Wrap(
            rain_chars,
            spacing=8,
            run_spacing=4,
            alignment=ft.WrapAlignment.CENTER,
        )

        # Glitch title
        title_stack = ft.Stack([
            ft.Text(self.title_str, size=32, color=Neon.CYAN, opacity=0.5,
                    font_family=MONO, weight=ft.FontWeight.BOLD,
                    offset=ft.Offset(-0.004, 0.004)),
            ft.Text(self.title_str, size=32, color=Neon.GREEN,
                    font_family=MONO, weight=ft.FontWeight.BOLD,
                    shadow=ft.BoxShadow(blur_radius=12, color=Neon.GREEN, spread_radius=2)),
        ], alignment=ft.alignment.center)

        self.content = ft.Stack([
            rain_grid,
            ft.Container(
                title_stack,
                alignment=ft.alignment.center,
                bgcolor=Neon.BLACK,
                opacity=0.85,
                padding=ft.padding.symmetric(horizontal=20, vertical=8),
            ),
        ], expand=True)


# ─────────────────────────── Page Theme ───────────────────────────

def apply_page_theme(page: ft.Page):
    """Apply the full cyberpunk theme to a Flet page."""
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = Neon.DEEP_BLUE
    page.padding = 12
    page.fonts = {
        "mono": "https://github.com/google/fonts/raw/main/apache/robotomono/RobotoMono%5Bwght%5D.ttf",
    }
    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=Neon.GREEN,
            on_primary=Neon.BLACK,
            secondary=Neon.CYAN,
            surface=Neon.PANEL_BG,
            on_surface=Neon.GREEN,
        ),
        text_theme=ft.TextTheme(
            body_medium=ft.TextStyle(font_family=MONO, color=Neon.GREEN),
            body_large=ft.TextStyle(font_family=MONO, color=Neon.GREEN),
            title_large=ft.TextStyle(font_family=MONO, color=Neon.GREEN, weight=ft.FontWeight.BOLD),
        ),
    )
