from __future__ import annotations

import math
import random
import string
import typing as t

import textwrap
import flet as ft


def matrix_header(title: str = "YOU2.0") -> ft.Container:
    # Simple neon header with a Matrix-inspired look
    neon_color = "#39FF14"
    header = ft.Text(title, size=28, color=neon_color)
    header_row = ft.Row([header], alignment=ft.MainAxisAlignment.CENTER)
    # Neon glow container
    return ft.Container(
        ft.Column([header_row, ft.Text("" , size=12, color="#00AA00")] ),
        height=90,
        bgcolor=ft.Colors.BLACK,
        padding=ft.Padding(12),
        border_radius=ft.border_radius(6),
        border=ft.border.all(1, ft.Colors.BLUE_400),
    )
