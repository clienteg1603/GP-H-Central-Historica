"""Entrada da distribuição Windows a partir da v0.48.1.

Mantém o monólito histórico intacto nesta fase e instala extensões finas antes
de criar a janela principal. Isso reduz o risco de contaminar o Meta congelado.
"""
from __future__ import annotations

import multiprocessing as mp

import gph_central as central
from gph_round_advisor import install_round_advisor
from gph_version import APP_VERSION


# A versão efetiva precisa existir antes de a janela e as preferências de
# atualização serem criadas. _is_newer_version tinha o valor antigo capturado
# como argumento default, então ela é redefinida para usar a versão efetiva.
central.APP_VERSION = APP_VERSION


def _is_newer_version(candidate, current=None):
    if current is None:
        current = APP_VERSION
    return central._version_key(candidate) > central._version_key(current)


central._is_newer_version = _is_newer_version
install_round_advisor(central)


def main():
    mp.freeze_support()
    try:
        app = central.App()
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
