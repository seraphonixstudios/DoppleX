"""Matrix rain header with glitch effects and Atlantean tech aesthetic."""
from __future__ import annotations

import random
import string

import flet as ft

from ui.cyber_theme import Neon, MONO

# Mix of ASCII, katakana, and Atlantean-inspired runes
MATRIX_CHARS = (
    string.ascii_letters
    + string.digits
    + "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ"
    + "◈◉◊○●◐◑◒◓◔◕"
    + "▁▂▃▄▅▆▇█"
    + "▖▗▘▙▚▛▜▝▞▟"
)


def _random_char() -> str:
    return random.choice(MATRIX_CHARS)


def matrix_header(title: str = "YOU2.0") -> ft.Container:
    """Build a cyberpunk Matrix/Atlantean header with animated rain background."""

    # Generate a grid of semi-transparent falling characters
    rain_chars = []
    for _ in range(80):
        rain_chars.append(
            ft.Text(
                _random_char(),
                size=random.choice([7, 9, 11]),
                color=random.choice([Neon.GREEN, Neon.GREEN_BRIGHT, Neon.CYAN]),
                opacity=random.uniform(0.05, 0.35),
                font_family=MONO,
            )
        )

    rain_grid = ft.Wrap(
        rain_chars,
        spacing=6,
        run_spacing=2,
        alignment=ft.WrapAlignment.CENTER,
    )

    # Glitchy title with RGB split
    title_stack = ft.Stack([
        # Cyan ghost (left offset)
        ft.Text(
            title,
            size=30,
            color=Neon.CYAN,
            opacity=0.5,
            font_family=MONO,
            weight=ft.FontWeight.BOLD,
            offset=ft.Offset(-0.005, 0.003),
        ),
        # Main green title with glow
        ft.Text(
            title,
            size=30,
            color=Neon.GREEN,
            font_family=MONO,
            weight=ft.FontWeight.BOLD,
            shadow=ft.BoxShadow(
                blur_radius=14,
                color=Neon.GREEN,
                spread_radius=2,
                offset=ft.Offset(0, 0),
            ),
        ),
        # White highlight (right offset)
        ft.Text(
            title,
            size=30,
            color=Neon.WHITE,
            opacity=0.25,
            font_family=MONO,
            weight=ft.FontWeight.BOLD,
            offset=ft.Offset(0.003, -0.003),
        ),
    ], alignment=ft.alignment.center)

    # Subtitle with terminal cursor blink
    subtitle_row = ft.Row([
        ft.Text(
            "NEURAL_SOCIAL_INTERFACE v1.0.0",
            size=11,
            color=Neon.CYAN,
            opacity=0.7,
            font_family=MONO,
        ),
        ft.Text(
            "_",
            size=11,
            color=Neon.GREEN,
            font_family=MONO,
            opacity=0.9,
        ),
    ], alignment=ft.MainAxisAlignment.CENTER, spacing=4)

    return ft.Container(
        content=ft.Stack([
            # Background rain
            ft.Container(rain_grid, alignment=ft.alignment.center, opacity=0.6),
            # Scanline overlay
            ft.Container(
                ft.Column(
                    [ft.Container(height=2, bgcolor="#00000030") for _ in range(30)],
                    spacing=2,
                ),
                opacity=0.2,
                expand=True,
            ),
            # Title panel
            ft.Container(
                ft.Column([
                    title_stack,
                    subtitle_row,
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                alignment=ft.alignment.center,
                bgcolor=Neon.BLACK,
                opacity=0.88,
                padding=ft.padding.symmetric(horizontal=24, vertical=10),
                border_radius=ft.border_radius.all(2),
                border=ft.border.all(1, Neon.BORDER),
            ),
        ], expand=True),
        height=100,
        bgcolor=Neon.BLACK,
        padding=ft.padding.all(12),
        border_radius=ft.border_radius.all(2),
        border=ft.border.all(1, Neon.BORDER),
        shadow=ft.BoxShadow(
            blur_radius=12,
            color=Neon.BORDER_GLOW,
            spread_radius=0,
            offset=ft.Offset(0, 0),
        ),
    )
