"""Entrada da distribuição Windows a partir da v0.48.1.

Mantém o monólito histórico intacto nesta fase e instala extensões finas antes
de criar a janela principal. Isso reduz o risco de contaminar o Meta congelado.
"""
from __future__ import annotations

import multiprocessing as mp

import gph_central as central
import gph_round_advisor as round_advisor
from gph_bugfix_round_targets import install_round_target_hotfix
from gph_meta_freeze_guard import install_meta_freeze_guard
from gph_profile_recovery import install_profile_recovery
from gph_round_advisor import install_round_advisor
from gph_round_advisor_guard import install_round_advisor_guard
from gph_ui_foundation import apply_ui_foundation, prepare_ui_foundation
from gph_ui_navigation import install_navigation_polish
from gph_ui_play import install_play_polish
from gph_ui_decision import install_decision_polish
from gph_ui_analysis import install_settings_polish, polish_results_page
from gph_ui_final_audit import apply_final_audit
from gph_ui_windowed import install_windowed_layout
from gph_ui_performance import install_ui_performance
from gph_version import APP_VERSION

central.APP_VERSION = APP_VERSION


def _is_newer_version(candidate, current=None):
    if current is None:
        current = APP_VERSION
    return central._version_key(candidate) > central._version_key(current)


def _install_results_polish():
    app_cls = central.App
    if getattr(app_cls, "_gph_ui_results_installed", False):
        return

    for method_name, page_key in (("show_results", "results"), ("show_games_day", "games_day")):
        original = getattr(app_cls, method_name, None)
        if original is None:
            continue

        def make_wrapper(fn, key):
            def wrapper(self, *args, **kwargs):
                result = fn(self, *args, **kwargs)
                try:
                    polish_results_page(self, central, key)
                except Exception as exc:
                    self._gph_results_polish_error = str(exc)
                return result
            return wrapper

        setattr(app_cls, method_name, make_wrapper(original, page_key))

    app_cls._gph_ui_results_installed = True


central._is_newer_version = _is_newer_version
install_round_target_hotfix(central)
# v0.48.24: toda auditoria de resultados e um watchdog silencioso garantem
# que a próxima rodada operacional receba Meta congelado antes do resultado.
install_meta_freeze_guard(central)
prepare_ui_foundation(central)
install_navigation_polish(central)
install_profile_recovery(central)
install_round_advisor(central)
install_round_advisor_guard(round_advisor, APP_VERSION)
install_play_polish(round_advisor, APP_VERSION)
install_decision_polish(central)
_install_results_polish()
install_settings_polish(central)
# v0.48.22: mantém a janela principal em modo normal na abertura e permite
# que as linhas da Home cedam altura quando a tela não estiver maximizada.
install_windowed_layout(central)
# Instalada por último para envolver as extensões visuais já existentes sem
# mudar sua lógica: apenas reagenda/cancela trabalho de apresentação repetido.
install_ui_performance(central, globals())


def main():
    mp.freeze_support()
    try:
        app = central.App()
        apply_ui_foundation(app, central)
        apply_final_audit(app, central)
        if not getattr(app, "_startup_cancelled", False):
            app.mainloop()
    except BaseException as exc:
        try:
            central.write_crash_log(exc)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
