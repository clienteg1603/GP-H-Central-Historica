"""Otimização de fluidez da interface do GP-H.

Reduz trabalho visual síncrono nas trocas de página sem alterar regras de negócio.
Os pós-processamentos visuais das etapas 5–8 são reagendados para o próximo ciclo
Tk, chamadas repetidas são coalescidas e configuração de estilos é reutilizada
enquanto o tema não mudar.
"""
from __future__ import annotations

from functools import wraps
from time import perf_counter

PERFORMANCE_VERSION = "1.0"
PERFORMANCE_INFO = {
    "performance_only": True,
    "changes_meta": False,
    "changes_database": False,
    "changes_generators": False,
    "changes_methods": False,
    "changes_financial": False,
    "changes_round_audit": False,
    "combobox_popup_native": True,
}

DEFER_MS = 1
TRACKED_METHODS = (
    "show_home",
    "show_games_day",
    "show_play_page",
    "show_decision_page",
    "show_search",
    "show_statistics_page",
    "show_pulls_page",
    "show_methods_page",
    "show_results",
    "show_base_config",
)


def _perf_store(app):
    store = getattr(app, "_gph_ui_performance", None)
    if not isinstance(store, dict):
        store = {
            "page_ms": {},
            "polish_ms": {},
            "runs": {},
            "scheduled": 0,
            "cancelled": 0,
        }
        try:
            app._gph_ui_performance = store
        except Exception:
            pass
    return store


def _record(app, bucket, key, elapsed_ms):
    store = _perf_store(app)
    values = store.setdefault(bucket, {})
    previous = values.get(key)
    values[key] = {
        "last": round(float(elapsed_ms), 2),
        "max": round(max(float(elapsed_ms), float((previous or {}).get("max", 0.0))), 2),
    }
    runs = store.setdefault("runs", {})
    runs[key] = int(runs.get(key, 0)) + 1


def _page_is_current(app, expected_pages):
    if not expected_pages:
        return True
    current = getattr(app, "_page", None)
    # Alguns testes/diálogos antigos não expõem _page. Nesse caso não bloqueamos.
    if current is None:
        return True
    return current in set(expected_pages)


def schedule_polish(app, key, callback, *, expected_pages=()):
    """Agenda um polimento visual sem bloquear o clique que abriu a página.

    Uma nova solicitação com a mesma chave cancela a anterior. Isso evita trabalho
    desperdiçado quando o usuário navega rapidamente entre telas/subabas.
    """
    pending = getattr(app, "_gph_ui_polish_pending", None)
    if not isinstance(pending, dict):
        pending = {}
        try:
            app._gph_ui_polish_pending = pending
        except Exception:
            pass

    old = pending.pop(key, None)
    if old is not None:
        try:
            app.after_cancel(old)
            _perf_store(app)["cancelled"] += 1
        except Exception:
            pass

    def run():
        pending.pop(key, None)
        if not _page_is_current(app, expected_pages):
            return None
        started = perf_counter()
        try:
            return callback()
        finally:
            _record(app, "polish_ms", key, (perf_counter() - started) * 1000.0)

    try:
        handle = app.after(DEFER_MS, run)
        pending[key] = handle
        _perf_store(app)["scheduled"] += 1
        return handle
    except Exception:
        # Compatibilidade com testes e objetos antigos sem scheduler Tk.
        return run()


def _style_signature(app, central):
    colors = getattr(app, "colors", {}) or {}
    color_keys = (
        "card", "card2", "entry", "text", "muted", "border", "selection",
        "hover", "accent", "accent_hover", "success", "warning", "danger",
    )
    sizes = getattr(central, "UI_FONT_SIZES", {}) or {}
    return (
        tuple((key, colors.get(key)) for key in color_keys),
        getattr(central, "UI_FONT_FAMILY", None),
        getattr(central, "UI_FONT_SEMIBOLD", None),
        tuple(sorted((str(k), str(v)) for k, v in sizes.items())),
        getattr(central, "UI_TABLE_ROWHEIGHT", None),
    )


def _cached_style_config(group, original):
    @wraps(original)
    def wrapped(app, central, *args, **kwargs):
        cache = getattr(app, "_gph_ui_style_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            try:
                app._gph_ui_style_cache = cache
            except Exception:
                pass
        signature = _style_signature(app, central)
        if cache.get(group) == signature:
            return None
        result = original(app, central, *args, **kwargs)
        cache[group] = signature
        return result
    return wrapped


def _deferred(original, *, key_builder, expected_builder):
    @wraps(original)
    def wrapper(app, central, *args, **kwargs):
        key = key_builder(*args, **kwargs)
        expected = expected_builder(*args, **kwargs)
        return schedule_polish(
            app,
            key,
            lambda: original(app, central, *args, **kwargs),
            expected_pages=expected,
        )
    return wrapper


def _wrap_page_timers(central):
    app_cls = central.App
    if getattr(app_cls, "_gph_ui_page_timers_installed", False):
        return

    for name in TRACKED_METHODS:
        original = getattr(app_cls, name, None)
        if original is None or getattr(original, "_gph_perf_timed", False):
            continue

        @wraps(original)
        def timed(self, *args, __fn=original, __name=name, **kwargs):
            started = perf_counter()
            try:
                return __fn(self, *args, **kwargs)
            finally:
                _record(self, "page_ms", __name, (perf_counter() - started) * 1000.0)

        timed._gph_perf_timed = True
        setattr(app_cls, name, timed)

    app_cls._gph_ui_page_timers_installed = True


def install_ui_performance(central, bootstrap_namespace=None):
    """Instala a camada de fluidez antes da criação de ``App``."""
    app_cls = central.App
    if getattr(app_cls, "_gph_ui_performance_installed", False):
        return PERFORMANCE_INFO

    import gph_ui_analysis as analysis
    import gph_ui_decision as decision
    import gph_ui_navigation as navigation

    # Configuração de estilos é relativamente cara e antes era repetida a cada
    # abertura de página. Reconfigura apenas quando cores/fontes realmente mudam.
    analysis.configure_analysis_styles = _cached_style_config(
        "analysis", analysis.configure_analysis_styles
    )
    analysis.configure_results_styles = _cached_style_config(
        "results", analysis.configure_results_styles
    )
    analysis.configure_settings_styles = _cached_style_config(
        "settings", analysis.configure_settings_styles
    )
    decision.configure_decision_styles = _cached_style_config(
        "decision", decision.configure_decision_styles
    )

    # Os wrappers já instalados nas etapas visuais resolvem estes nomes em tempo
    # de execução. Trocá-los por agendadores preserva a mesma lógica visual, mas
    # devolve o controle ao Tk antes do passeio recursivo pela árvore de widgets.
    navigation.polish_analysis_page = _deferred(
        navigation.polish_analysis_page,
        key_builder=lambda page_key, *a, **k: "analysis",
        expected_builder=lambda page_key, *a, **k: (str(page_key),),
    )
    decision.polish_decision_page = _deferred(
        decision.polish_decision_page,
        key_builder=lambda current_view="summary", *a, **k: "decision",
        expected_builder=lambda current_view="summary", *a, **k: ("decision",),
    )
    analysis.polish_settings_page = _deferred(
        analysis.polish_settings_page,
        key_builder=lambda section="account", *a, **k: "settings",
        expected_builder=lambda section="account", *a, **k: ("base",),
    )

    # O wrapper de Resultados vive em gph_bootstrap e consulta seu global em
    # tempo de execução. Substituímos somente essa referência, sem reembrulhar
    # a página nem tocar em auditoria/resultado.
    if isinstance(bootstrap_namespace, dict):
        current_results = bootstrap_namespace.get("polish_results_page")
        if callable(current_results):
            bootstrap_namespace["polish_results_page"] = _deferred(
                current_results,
                key_builder=lambda page_key, *a, **k: "results",
                expected_builder=lambda page_key, *a, **k: (str(page_key),),
            )

    _wrap_page_timers(central)
    app_cls._gph_ui_performance_installed = True
    central.GPH_UI_PERFORMANCE_VERSION = PERFORMANCE_VERSION
    return PERFORMANCE_INFO
