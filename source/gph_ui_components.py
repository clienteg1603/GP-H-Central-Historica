"""Componentes reutilizáveis da cura visual do GP-H."""
from __future__ import annotations

from tkinter import ttk

CARD_PADDING = 12


def card(parent, *, alternate=False, padding=CARD_PADDING, **kwargs):
    style = "PanelAlt.TFrame" if alternate else "Panel.TFrame"
    return ttk.Frame(parent, style=style, padding=padding, **kwargs)


def page_header(parent, title, subtitle=None):
    frame = ttk.Frame(parent, style="Surface.TFrame")
    ttk.Label(frame, text=title, style="PageTitle.TLabel").pack(anchor="w")
    if subtitle:
        ttk.Label(
            frame,
            text=subtitle,
            style="PageSubtitle.TLabel",
            wraplength=1100,
            justify="left",
        ).pack(anchor="w", pady=(3, 0))
    return frame


def section_header(parent, title, subtitle=None):
    frame = ttk.Frame(parent, style="Panel.TFrame")
    ttk.Label(frame, text=title, style="SectionTitle.TLabel").pack(anchor="w")
    if subtitle:
        ttk.Label(
            frame,
            text=subtitle,
            style="CardMuted.TLabel",
            wraplength=1000,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))
    return frame


def metric(parent, title, value, subtitle=None):
    frame = card(parent, alternate=True, padding=10)
    ttk.Label(frame, text=title, style="Card2Muted.TLabel").pack(anchor="w")
    ttk.Label(frame, text=str(value), style="Metric.TLabel").pack(anchor="w", pady=(2, 0))
    if subtitle:
        ttk.Label(frame, text=subtitle, style="Card2Muted.TLabel").pack(anchor="w", pady=(2, 0))
    return frame


def toolbar(parent, *, padding=(0, 0)):
    return ttk.Frame(parent, style="Surface.TFrame", padding=padding)


def primary_button(parent, text, command, **kwargs):
    return ttk.Button(parent, text=text, command=command, style="Primary.TButton", **kwargs)


def secondary_button(parent, text, command, **kwargs):
    return ttk.Button(parent, text=text, command=command, style="Secondary.TButton", **kwargs)


def danger_button(parent, text, command, **kwargs):
    return ttk.Button(parent, text=text, command=command, style="Danger.TButton", **kwargs)
