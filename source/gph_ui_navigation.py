"""Etapa 2 da cura visual do GP-H: estrutura principal e navegação.

A camada é exclusivamente visual. Ela reaproveita as páginas e comandos já
existentes, reorganizando a sidebar e a barra inferior sem tocar em banco,
Meta, métodos, auditoria ou geração de jogos.
"""
from __future__ import annotations

NAVIGATION_VERSION = "2.0"
NAVIGATION_INFO = {
    "stage": 2,
    "visual_only": True,
    "changes_meta": False,
    "changes_database": False,
    "changes_generators": False,
    "changes_methods": False,
}

SIDEBAR_WIDTH = 224

OPERATION_ITEMS = (
    ("Início", "show_home", "home", False),
    ("Jogos do dia", "show_games_day", "results", False),
    ("Jogar", "show_play_page", "ticket", False),
    ("Decisão", "show_decision_page", "generator", False),
)

ANALYSIS_ITEMS = (
    ("Pesquisa", "show_search", "search", True),
    ("Estatísticas", "show_statistics_page", "statistics", True),
    ("Puxadas", "show_pulls_page", "pulls", True),
    ("Métodos", "show_methods_page", "methods", True),
)

BOTTOM_ITEMS = (
    ("Resultados", "show_results", "results", False),
    ("Configurações", "show_base_config", "database", True),
)

PAGE_TO_NAV = {
    "home": "Início",
    "home_animals": "Início",
    "games_day": "Jogos do dia",
    "play": "Jogar",
    "decision": "Decisão",
    "results": "Resultados",
    "search": "Pesquisa",
    "statistics": "Estatísticas",
    "pulls": "Puxadas",
    "methods": "Métodos",
    "base": "Configurações",
}


def navigation_spec():
    return {
        "operation": tuple(OPERATION_ITEMS),
        "analysis": tuple(ANALYSIS_ITEMS),
        "bottom": tuple(BOTTOM_ITEMS),
        "page_to_nav": dict(PAGE_TO_NAV),
        "width": SIDEBAR_WIDTH,
    }


def _section_label(app, central, parent, text):
    label = central.tk.Label(
        parent,
        text=text,
        bg=app.colors["sidebar"],
        fg=app.colors["muted"],
        font=(central.UI_FONT_SEMIBOLD, max(8, central.UI_FONT_SIZES["secondary"] - 1)),
        anchor="w",
        padx=5,
        pady=0,
    )
    label.pack(fill="x", padx=14, pady=(12, 5))
    return label


def _divider(app, central, parent, *, pady=(10, 7)):
    line = central.tk.Frame(parent, bg=app.colors["divider"], height=1)
    line.pack(fill="x", padx=14, pady=pady)
    return line


def _add_nav_row(app, central, parent, label, command_name, icon_key, secondary=False):
    row = central.tk.Frame(parent, bg=app.colors["sidebar"], bd=0, highlightthickness=0)
    row.pack(fill="x", padx=(8, 10), pady=2)

    indicator = central.tk.Frame(row, bg=app.colors["sidebar"], width=3, bd=0)
    indicator.pack(side="left", fill="y")
    indicator.pack_propagate(False)

    command = getattr(app, command_name)
    img = app.nav_icon_images.get(icon_key) if icon_key else None
    btn = central.tk.Button(
        row,
        text=label,
        image=img if img else "",
        compound="left",
        command=command,
        bg=app.colors["sidebar"],
        fg=app.colors["muted"] if secondary else app.colors["text"],
        activebackground=app.colors["hover"],
        activeforeground=app.colors["text"],
        relief="flat",
        bd=0,
        highlightthickness=0,
        anchor="w",
        padx=12,
        pady=9,
        font=(central.UI_FONT_SEMIBOLD, central.UI_FONT_SIZES["body"]),
        cursor="hand2",
    )
    btn.pack(side="left", fill="x", expand=True)

    app.nav_buttons[label] = btn
    app.nav_button_icon_keys[label] = icon_key
    app._gph_nav_rows[label] = row
    app._gph_nav_indicators[label] = indicator
    app._gph_nav_secondary[label] = bool(secondary)

    def enter(_event=None, name=label):
        if getattr(app, "_gph_active_nav", None) != name:
            app._gph_nav_rows[name].configure(bg=app.colors["hover"])
            app.nav_buttons[name].configure(bg=app.colors["hover"], fg=app.colors["text"])

    def leave(_event=None, name=label):
        if getattr(app, "_gph_active_nav", None) != name:
            app._gph_nav_rows[name].configure(bg=app.colors["sidebar"])
            app.nav_buttons[name].configure(
                bg=app.colors["sidebar"],
                fg=app.colors["muted"] if app._gph_nav_secondary.get(name) else app.colors["text"],
            )

    for widget in (row, btn, indicator):
        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", leave, add="+")
    return btn


def _rebuild_sidebar(app, central):
    sidebar = getattr(app, "sidebar", None)
    if sidebar is None:
        return

    for child in list(sidebar.winfo_children()):
        child.destroy()

    sidebar.configure(bg=app.colors["sidebar"], width=SIDEBAR_WIDTH)
    sidebar.pack_propagate(False)

    app.nav_buttons = {}
    app.nav_button_icon_keys = {}
    app._gph_nav_rows = {}
    app._gph_nav_indicators = {}
    app._gph_nav_secondary = {}
    app._gph_active_nav = None

    brand = central.tk.Frame(sidebar, bg=app.colors["sidebar"], bd=0)
    brand.pack(fill="x", padx=12, pady=(16, 8))

    if getattr(app, "logo_sidebar", None) is not None:
        central.tk.Label(
            brand,
            image=app.logo_sidebar,
            bg=app.colors["sidebar"],
            bd=0,
        ).pack(anchor="w")
    else:
        central.tk.Label(
            brand,
            text="GP-H",
            bg=app.colors["sidebar"],
            fg=app.colors["text"],
            font=(central.UI_FONT_SEMIBOLD, 20),
            anchor="w",
        ).pack(fill="x")

    central.tk.Label(
        brand,
        text="CENTRAL HISTÓRICA",
        bg=app.colors["sidebar"],
        fg=app.colors["muted"],
        font=(central.UI_FONT_SEMIBOLD, central.UI_FONT_SIZES["secondary"]),
        anchor="w",
    ).pack(fill="x", pady=(5, 0))
    central.tk.Label(
        brand,
        text=f"v{central.APP_VERSION}  •  canal Teste",
        bg=app.colors["sidebar"],
        fg=app.colors["muted"],
        font=(central.UI_FONT_FAMILY, central.UI_FONT_SIZES["secondary"]),
        anchor="w",
    ).pack(fill="x", pady=(2, 0))

    _divider(app, central, sidebar, pady=(6, 5))

    main_nav = central.tk.Frame(sidebar, bg=app.colors["sidebar"], bd=0)
    main_nav.pack(fill="x")

    _section_label(app, central, main_nav, "OPERAÇÃO")
    for item in OPERATION_ITEMS:
        _add_nav_row(app, central, main_nav, *item)

    _section_label(app, central, main_nav, "ANÁLISE")
    for item in ANALYSIS_ITEMS:
        _add_nav_row(app, central, main_nav, *item)

    spacer = central.tk.Frame(sidebar, bg=app.colors["sidebar"], bd=0)
    spacer.pack(fill="both", expand=True)

    bottom = central.tk.Frame(sidebar, bg=app.colors["sidebar"], bd=0)
    bottom.pack(fill="x", side="bottom", pady=(0, 12))
    _divider(app, central, bottom, pady=(0, 8))
    _section_label(app, central, bottom, "ACOMPANHAMENTO")
    for item in BOTTOM_ITEMS:
        _add_nav_row(app, central, bottom, *item)

    try:
        app._update_results_nav_badge()
    except Exception:
        pass

    active = PAGE_TO_NAV.get(getattr(app, "_page", None))
    if active:
        app._set_active_nav(active)


def _polish_status_bar(app, central):
    status = getattr(app, "status", None)
    account = getattr(app, "account_status", None)
    if status is None or account is None:
        return
    bar = status.master
    style = central.ttk.Style(app)
    try:
        style.configure("GPHBottomBar.TFrame", background=app.colors["card2"])
        style.configure(
            "GPHBottomStatus.TLabel",
            background=app.colors["card2"],
            foreground=app.colors["muted"],
            font=(central.UI_FONT_FAMILY, central.UI_FONT_SIZES["secondary"]),
        )
        bar.configure(style="GPHBottomBar.TFrame", padding=(18, 6, 18, 7))
        status.configure(style="GPHBottomStatus.TLabel")
        account.configure(style="GPHBottomStatus.TLabel")
    except Exception:
        pass

    content = getattr(app, "content", None)
    if content is not None:
        try:
            content.configure(padding=(20, 14, 20, 12))
        except Exception:
            pass


def _apply_active_state(app, central, label):
    if not getattr(app, "_gph_nav_rows", None):
        return False

    app._gph_active_nav = label
    for name, btn in app.nav_buttons.items():
        active = name == label
        row = app._gph_nav_rows.get(name)
        indicator = app._gph_nav_indicators.get(name)
        secondary = app._gph_nav_secondary.get(name, False)
        bg = app.colors["selection"] if active else app.colors["sidebar"]
        fg = app.colors["text"] if active or not secondary else app.colors["muted"]
        if row is not None:
            row.configure(bg=bg)
        if indicator is not None:
            indicator.configure(bg=app.colors["accent"] if active else app.colors["sidebar"])
        btn.configure(
            bg=bg,
            fg=fg,
            activebackground=app.colors["selection"] if active else app.colors["hover"],
            activeforeground=app.colors["text"],
        )
        key = app.nav_button_icon_keys.get(name)
        if key:
            image = (app.nav_icon_active_images if active else app.nav_icon_images).get(key)
            if image is not None:
                btn.configure(image=image)
    return True


def install_navigation_polish(central):
    """Instala a navegação da etapa 2 sem alterar páginas ou regras de negócio."""
    app_cls = central.App
    if getattr(app_cls, "_gph_ui_navigation_installed", False):
        return NAVIGATION_INFO

    original_build_ui = app_cls._build_ui
    original_set_active_nav = app_cls._set_active_nav

    def build_ui(self, *args, **kwargs):
        result = original_build_ui(self, *args, **kwargs)
        try:
            _rebuild_sidebar(self, central)
            _polish_status_bar(self, central)
        except Exception as exc:
            # A navegação é visual-only: uma falha de acabamento nunca deve
            # impedir o usuário de abrir a Central.
            self._gph_navigation_error = str(exc)
        return result

    def set_active_nav(self, label):
        try:
            if _apply_active_state(self, central, label):
                return None
        except Exception:
            pass
        return original_set_active_nav(self, label)

    app_cls._build_ui = build_ui
    app_cls._set_active_nav = set_active_nav
    app_cls._gph_ui_navigation_installed = True
    central.GPH_UI_NAVIGATION_VERSION = NAVIGATION_VERSION
    return NAVIGATION_INFO
