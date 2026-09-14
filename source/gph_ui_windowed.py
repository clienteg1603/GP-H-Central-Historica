"""Compatibilidade da janela principal em modo normal (não maximizado).

A partir da v0.48.22 a Central deixa de forçar a maximização na abertura e a
Home pode reduzir um pouco a altura mínima das cinco linhas de bichos. Em tela
maior elas continuam expandindo normalmente pelo ``weight=1`` já existente.

Esta camada é exclusivamente visual: não altera banco, Meta, métodos,
geradores, financeiro, resultados ou regras de atraso.
"""
from __future__ import annotations

WINDOWED_LAYOUT_VERSION = "1.0"
HOME_ANIMAL_ROW_MINSIZE = 78

WINDOWED_LAYOUT_INFO = {
    "visual_only": True,
    "changes_meta": False,
    "changes_database": False,
    "changes_generators": False,
    "changes_methods": False,
    "changes_financial": False,
    "changes_results": False,
    "forces_maximized_startup": False,
}


def _do_not_force_maximize(_self):
    """Callback compatível com o legado, agora deliberadamente sem efeito.

    ``App.__init__`` histórico ainda agenda ``_maximize_main_window`` no primeiro
    ciclo do Tk. Substituímos o método antes de a instância ser criada, portanto
    o callback agendado já aponta para esta implementação e a janela permanece
    no estado normal definido pelo próprio Tk/geometry.
    """
    return None


def compact_home_for_windowed(app):
    """Permite à grade dos 25 bichos ceder altura para a faixa de atrasos.

    O layout original usa cinco linhas com ``weight=1`` e ``minsize=88``. O
    mínimo menor não muda a aparência quando há altura sobrando; apenas evita
    que a soma dos mínimos empurre/corte "Atrasos atuais" em uma janela normal.
    """
    grid = getattr(app, "home_grid", None)
    if grid is None:
        return False
    try:
        for row in range(5):
            grid.grid_rowconfigure(
                row,
                weight=1,
                uniform="animalrows",
                minsize=HOME_ANIMAL_ROW_MINSIZE,
            )
        app._gph_home_windowed_row_minsize = HOME_ANIMAL_ROW_MINSIZE
        return True
    except Exception:
        return False


def install_windowed_layout(central):
    """Instala os dois ajustes visuais antes da criação da janela principal."""
    app_cls = central.App
    if getattr(app_cls, "_gph_windowed_layout_installed", False):
        return WINDOWED_LAYOUT_INFO

    # Preserva a referência apenas para diagnóstico; não é chamada na abertura.
    if not hasattr(app_cls, "_gph_original_maximize_main_window"):
        app_cls._gph_original_maximize_main_window = getattr(
            app_cls, "_maximize_main_window", None
        )
    app_cls._maximize_main_window = _do_not_force_maximize

    original_show_home = getattr(app_cls, "show_home", None)
    if original_show_home is not None:
        def show_home_windowed(self, *args, **kwargs):
            result = original_show_home(self, *args, **kwargs)
            compact_home_for_windowed(self)
            return result

        app_cls.show_home = show_home_windowed

    app_cls._gph_windowed_layout_installed = True
    central.GPH_UI_WINDOWED_LAYOUT_VERSION = WINDOWED_LAYOUT_VERSION
    return WINDOWED_LAYOUT_INFO
