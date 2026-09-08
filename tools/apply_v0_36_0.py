from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENTRAL = ROOT / "source" / "gph_central.py"
DOC = ROOT / "source" / "DOCUMENTACAO_GP-H.txt"
UPDATES = ROOT / "source" / "ATUALIZACOES_PROGRAMA_v0.35.txt"
BAT = ROOT / "source" / "GERAR_EXE_WINDOWS.bat"


def _app_method_span(text: str, name: str):
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "App":
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == name:
                    lines = text.splitlines(keepends=True)
                    start = child.lineno - 1
                    end = child.end_lineno
                    return start, end, "".join(lines[start:end])
    raise RuntimeError(f"Método App.{name} não encontrado")


def _replace_app_method(text: str, name: str, new_source: str) -> str:
    start, end, _old = _app_method_span(text, name)
    lines = text.splitlines(keepends=True)
    if new_source and not new_source.endswith("\n"):
        new_source += "\n"
    lines[start:end] = [new_source]
    return "".join(lines)


def _insert_after_app_method(text: str, name: str, extra_source: str) -> str:
    start, end, old = _app_method_span(text, name)
    if not old.endswith("\n"):
        old += "\n"
    if extra_source and not extra_source.startswith("\n"):
        extra_source = "\n" + extra_source
    return _replace_app_method(text, name, old + extra_source)


def _wrap_main_page(text: str, method_name: str, key: str, after_title: bool = True) -> str:
    _start, _end, src = _app_method_span(text, method_name)
    if f'_make_scrollable_page_body(self.content, "{key}")' in src:
        return text

    dedented = textwrap.dedent(src)
    fn = ast.parse(dedented).body[0]

    if after_title:
        target_stmt = None
        for stmt in fn.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call = stmt.value
                if isinstance(call.func, ast.Attribute) and call.func.attr == "_page_title":
                    target_stmt = stmt
                    break
        if target_stmt is None:
            raise RuntimeError(f"_page_title não encontrado em {method_name}")
        insert_at = target_stmt.end_lineno
    else:
        insert_at = None
        for idx, line in enumerate(src.splitlines(), start=1):
            if "self._page =" in line:
                insert_at = idx
                break
        if insert_at is None:
            raise RuntimeError(f"self._page não encontrado em {method_name}")

    # Primeiro redireciona os filhos que eram montados diretamente em self.content.
    modified = src.replace("self.content", "body")
    lines = modified.splitlines(keepends=True)
    lines.insert(insert_at, f'        body = self._make_scrollable_page_body(self.content, "{key}")\n')
    return _replace_app_method(text, method_name, "".join(lines))


def _wrap_app_toplevel_outer(text: str, method_name: str, window_var: str, key: str) -> str:
    _start, _end, src = _app_method_span(text, method_name)
    if f'_make_scrollable_page_body({window_var}, "{key}")' in src:
        return text
    pattern = re.compile(
        rf"outer\s*=\s*ttk\.Frame\(\s*{re.escape(window_var)}\s*,\s*padding\s*=\s*([^\)]+)\)",
        flags=re.S,
    )
    repl = rf'outer = ttk.Frame(self._make_scrollable_page_body({window_var}, "{key}"), padding=\1)'
    new_src, count = pattern.subn(repl, src, count=1)
    if count != 1:
        raise RuntimeError(f"Frame externo de {method_name} não encontrado")
    return _replace_app_method(text, method_name, new_src)


def _enhanced_scroll_method() -> str:
    return '''    def _make_scrollable_page_body(self, parent, key):
        """Área vertical rolável: roda funciona sob qualquer filho e a barra só aparece quando necessária."""
        host = ttk.Frame(parent)
        host.pack(fill="both", expand=True)
        canvas = tk.Canvas(
            host, highlightthickness=0, borderwidth=0, bg=self.colors["bg"]
        )
        bar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

        body = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas._gph_smart_scroll = True
        if not hasattr(self, "_smart_scroll_canvases"):
            self._smart_scroll_canvases = {}
        self._smart_scroll_canvases[key] = canvas

        def update_bar():
            try:
                bbox = canvas.bbox("all")
                content_h = (bbox[3] - bbox[1]) if bbox else 0
                need = content_h > max(1, canvas.winfo_height()) + 2
                managed = bool(bar.winfo_manager())
                if need and not managed:
                    bar.pack(side="right", fill="y")
                elif not need and managed:
                    bar.pack_forget()
            except tk.TclError:
                pass

        def update_region(_event=None):
            try:
                bbox = canvas.bbox("all")
                if bbox:
                    canvas.configure(scrollregion=bbox)
                update_bar()
            except tk.TclError:
                pass

        def resize_body(event):
            try:
                canvas.itemconfigure(window, width=max(1, int(event.width)))
                self.after_idle(update_region)
            except tk.TclError:
                pass

        body.bind("<Configure>", update_region, add="+")
        canvas.bind("<Configure>", resize_body, add="+")

        tag = f"GPHScroll_{key}"

        def route_wheel(event):
            units = self._wheel_units(event)
            if not units:
                return
            if self._play_scroll_child_if_possible(event.widget, units):
                return "break"
            try:
                first, last = canvas.yview()
                can_scroll = (units < 0 and first > 0.0) or (units > 0 and last < 1.0)
                if can_scroll:
                    canvas.yview_scroll(units, "units")
                # Sempre consome a roda dentro da página para não alterar Combobox/Spinbox por acidente.
                return "break"
            except tk.TclError:
                return

        self.bind_class(tag, "<MouseWheel>", route_wheel)
        self.bind_class(tag, "<Button-4>", route_wheel)
        self.bind_class(tag, "<Button-5>", route_wheel)

        def install_tags():
            try:
                stack = [host]
                while stack:
                    widget = stack.pop()
                    tags = list(widget.bindtags())
                    if tag not in tags:
                        tags.insert(1 if len(tags) > 1 else 0, tag)
                        widget.bindtags(tuple(tags))
                    stack.extend(widget.winfo_children())
            except tk.TclError:
                pass
            update_region()

        self.after_idle(install_tags)
        return body
'''


def _global_scroll_methods() -> str:
    return '''    def _install_smart_scroll_policy(self):
        """Padrão global: toda tela/janela atual ou futura recebe roteamento inteligente da roda."""
        tag = "GPHSmartWheel"
        self._smart_scroll_tag = tag
        if not getattr(self, "_smart_scroll_policy_installed", False):
            self.bind_class(tag, "<MouseWheel>", self._smart_scroll_route, add="+")
            self.bind_class(tag, "<Button-4>", self._smart_scroll_route, add="+")
            self.bind_class(tag, "<Button-5>", self._smart_scroll_route, add="+")
            self.bind_all("<Map>", self._smart_scroll_on_map, add="+")
            self._smart_scroll_policy_installed = True
        self.after_idle(lambda: self._smart_scroll_install_tags(self))

    def _smart_scroll_install_tags(self, root):
        tag = getattr(self, "_smart_scroll_tag", "GPHSmartWheel")
        try:
            stack = [root]
            while stack:
                widget = stack.pop()
                try:
                    tags = list(widget.bindtags())
                    if tag not in tags:
                        tags.insert(1 if len(tags) > 1 else 0, tag)
                        widget.bindtags(tuple(tags))
                    stack.extend(widget.winfo_children())
                except tk.TclError:
                    continue
        except Exception:
            pass

    def _smart_scroll_on_map(self, event):
        try:
            self._smart_scroll_install_tags(event.widget)
        except Exception:
            pass

    @staticmethod
    def _smart_scroll_can_move(widget, units):
        try:
            first, last = widget.yview()
            return (units < 0 and first > 0.0) or (units > 0 and last < 1.0)
        except Exception:
            return False

    def _smart_scroll_find_candidate(self, root, units, skip=None):
        candidates = []
        try:
            stack = list(root.winfo_children())
            while stack:
                widget = stack.pop()
                try:
                    stack.extend(widget.winfo_children())
                    if widget is skip or not widget.winfo_ismapped():
                        continue
                    cls = widget.winfo_class()
                    if cls not in {"Treeview", "Text", "Listbox", "Canvas"}:
                        continue
                    if not self._smart_scroll_can_move(widget, units):
                        continue
                    priority = {"Treeview": 4, "Text": 3, "Listbox": 3, "Canvas": 2}.get(cls, 1)
                    area = max(1, widget.winfo_width()) * max(1, widget.winfo_height())
                    candidates.append((priority, area, widget))
                except Exception:
                    continue
        except Exception:
            return None
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][2]

    def _smart_scroll_route(self, event):
        units = self._wheel_units(event)
        if not units:
            return
        widget = getattr(event, "widget", None)
        if widget is None:
            return

        # Controles que têm conteúdo próprio rolável recebem prioridade.
        if self._play_scroll_child_if_possible(widget, units):
            return "break"

        # Depois procura um Canvas rolável na cadeia de pais: é a página/janela atual.
        current = widget
        visited = set()
        while current is not None and current not in visited:
            visited.add(current)
            try:
                if current.winfo_class() == "Canvas" and self._smart_scroll_can_move(current, units):
                    current.yview_scroll(units, "units")
                    return "break"
                parent_name = current.winfo_parent()
                if not parent_name:
                    break
                current = current._nametowidget(parent_name)
            except Exception:
                break

        # Em diálogos antigos sem Canvas externo, rola o principal Text/Tree/Listbox disponível.
        try:
            top = widget.winfo_toplevel()
        except Exception:
            top = None
        if top is not None:
            candidate = self._smart_scroll_find_candidate(top, units, skip=widget)
            if candidate is not None:
                try:
                    candidate.yview_scroll(units, "units")
                    return "break"
                except Exception:
                    pass

        # Evita que a roda altere valores de seleção quando não há conteúdo para rolar.
        try:
            if widget.winfo_class() in {"TCombobox", "TSpinbox", "Spinbox"}:
                return "break"
        except Exception:
            pass
        return
'''


def _refactor_shadow_lab(text: str) -> str:
    _start, _end, src = _app_method_span(text, "show_shadow_lab_page")
    lines = src.splitlines(keepends=True)
    body_idx = None
    for i, line in enumerate(lines):
        if 'body = self._make_scrollable_page_body(self.content, "shadow_lab")' in line:
            body_idx = i
            break
    if body_idx is None:
        raise RuntimeError("Ponto de extração do Laboratório não encontrado")
    tail = "".join(lines[body_idx + 1:])
    header = '''    def _build_shadow_lab_section(self, body):
        """Laboratório Sombra incorporado à Central de Decisão."""
        try:
            self.db.audit_shadow_snapshots()
            self.db.ensure_shadow_snapshot(trigger="ABRIR_DECISAO")
        except Exception:
            pass

        lab_intro = ttk.Frame(body, style="Card.TFrame", padding=11)
        lab_intro.pack(fill="x", pady=(4, 8))
        ttk.Label(lab_intro, text="LABORATÓRIO SOMBRA", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            lab_intro,
            text=(
                "Área experimental da própria Decisão: leituras congeladas antes do resultado, "
                "comparação prospectiva de Centenas/Puxadas e Seca exclusiva do 1º prêmio. "
                "Nada aqui promove método automaticamente."
            ),
            style="CardMuted.TLabel", wraplength=1080, justify="left",
        ).pack(anchor="w", pady=(3, 0))

'''
    alias = '''
    def show_shadow_lab_page(self):
        """Compatibilidade: o antigo Laboratório agora abre a tela única de Decisão."""
        self.show_decision_page(open_lab=True)
'''
    return _replace_app_method(text, "show_shadow_lab_page", header + tail + alias)


def _merge_lab_into_decision(text: str) -> str:
    _start, _end, src = _app_method_span(text, "show_decision_page")
    src = src.replace("    def show_decision_page(self):", "    def show_decision_page(self, open_lab=False):", 1)
    src = src.replace(
        "Convergência dos métodos, confiança dos sinais e desempenho prospectivo. O índice não é probabilidade de prêmio.",
        "Visão da rodada, convergência, desempenho prospectivo e Laboratório Sombra em uma única tela. O índice não é probabilidade de prêmio.",
        1,
    )
    anchor = "        self._decision_build_stage3(body)\n"
    if anchor not in src:
        raise RuntimeError("Âncora da Etapa 3 não encontrada em Decisão")
    insert = anchor + '''
        # v0.36.0 — Laboratório deixa de ser página paralela e vira seção da Decisão.
        self._build_shadow_lab_section(body)
        if open_lab:
            canvas = getattr(self, "_smart_scroll_canvases", {}).get("decision")
            if canvas is not None:
                self.after_idle(lambda c=canvas: c.yview_moveto(1.0))
'''
    src = src.replace(anchor, insert, 1)
    return _replace_app_method(text, "show_decision_page", src)


def _patch_notes(text: str) -> str:
    if "• v0.36.0 — Decisão incorpora o Laboratório Sombra" not in text:
        marker = "• v0.35.3 — Recomendação da Rodada explica desempenho do horário, convergência atual e Seca do 1º."
        pos = text.find(marker)
        if pos >= 0:
            text = text[:pos] + (
                "• v0.36.0 — Decisão incorpora o Laboratório Sombra e o rolamento inteligente vira padrão global de interface.\\n\"\n            \""
            ) + text[pos:]
    return text


def _validate(text: str):
    ast.parse(text)
    required = [
        'APP_VERSION = "0.36.0"',
        'def _install_smart_scroll_policy(self):',
        'def _build_shadow_lab_section(self, body):',
        'def show_decision_page(self, open_lab=False):',
    ]
    for item in required:
        if item not in text:
            raise RuntimeError(f"Validação falhou: {item}")
    if '("Laboratório", self.show_shadow_lab_page' in text:
        raise RuntimeError("Laboratório ainda aparece como item separado do menu")
    for method, key in [
        ("show_home", "home"),
        ("show_home_animals", "home_animals"),
        ("show_search", "search"),
        ("show_results", "results"),
        ("show_statistics_page", "statistics"),
        ("show_pulls_page", "pulls"),
        ("show_methods_page", "methods"),
        ("show_generator_page", "generator"),
    ]:
        _s, _e, src = _app_method_span(text, method)
        if f'_make_scrollable_page_body(self.content, "{key}")' not in src:
            raise RuntimeError(f"Rolamento inteligente ausente em {method}")
    _s, _e, play_src = _app_method_span(text, "show_play_page")
    if "play_body_canvas" not in play_src:
        raise RuntimeError("Rolamento próprio da tela Jogar foi perdido")


def main():
    text = CENTRAL.read_text(encoding="utf-8")
    if 'APP_VERSION = "0.35.3"' not in text and 'APP_VERSION = "0.36.0"' not in text:
        raise RuntimeError("Base esperada v0.35.3 não encontrada")

    text = text.replace("GP-H Central Histórica v0.35.3", "GP-H Central Histórica v0.36.0", 1)
    text = text.replace('APP_VERSION = "0.35.3"', 'APP_VERSION = "0.36.0"', 1)

    # Menu único: Laboratório deixa de disputar espaço com Decisão.
    text = text.replace('            ("Laboratório", self.show_shadow_lab_page, "methods"),\n', "", 1)

    # Padrão de rolagem de páginas antigas.
    for method, key, after_title in [
        ("show_home", "home", False),
        ("show_home_animals", "home_animals", False),
        ("show_search", "search", True),
        ("show_results", "results", True),
        ("show_statistics_page", "statistics", True),
        ("show_pulls_page", "pulls", True),
        ("show_methods_page", "methods", True),
        ("show_generator_page", "generator", True),
    ]:
        text = _wrap_main_page(text, method, key, after_title=after_title)

    # Atualiza o helper e adiciona a política global que também alcança diálogos futuros.
    text = _replace_app_method(text, "_make_scrollable_page_body", _enhanced_scroll_method())
    if "def _install_smart_scroll_policy(self):" not in text:
        text = _insert_after_app_method(text, "_make_scrollable_page_body", _global_scroll_methods())

    # Ativa a política uma única vez; rebuild de tema apenas reinstala tags nos novos widgets.
    _s, _e, build_ui = _app_method_span(text, "_build_ui")
    if "self._install_smart_scroll_policy()" not in build_ui:
        needle = "        self._hover_after_id = None\n"
        if needle not in build_ui:
            raise RuntimeError("Âncora de _build_ui não encontrada")
        build_ui = build_ui.replace(needle, needle + "        self._install_smart_scroll_policy()\n", 1)
        text = _replace_app_method(text, "_build_ui", build_ui)

    # Grandes janelas construídas diretamente pelo App também recebem Canvas externo.
    for method, winvar, key in [
        ("_show_profile_dialog", "win", "profile_dialog"),
        ("_show_animal_pack_preview", "pop", "animal_pack_preview"),
        ("play_show_daily_closing", "dialog", "daily_closing"),
        ("_show_method_guide", "win", "method_guide"),
    ]:
        text = _wrap_app_toplevel_outer(text, method, winvar, key)

    # Unificação Decisão + Laboratório.
    text = _refactor_shadow_lab(text)
    text = _merge_lab_into_decision(text)
    text = _patch_notes(text)

    _validate(text)
    CENTRAL.write_text(text, encoding="utf-8")

    doc = DOC.read_text(encoding="utf-8")
    doc = doc.replace("VERSÃO ATUAL: v0.35.3", "VERSÃO ATUAL: v0.36.0", 1)
    block = '''REVISÃO v0.36.0 — DECISÃO ÚNICA / ROLAMENTO INTELIGENTE GLOBAL
- Decisão e Laboratório Sombra deixam de ser páginas paralelas: o Laboratório passa a ser uma seção da Central de Decisão.
- O item Laboratório é removido do menu lateral para eliminar duplicidade e dúvida sobre onde analisar a rodada.
- A Central de Decisão mantém índice de consistência, sinais, desempenho, Campeão × Desafiante, tendência, concentração e Walk-Forward, e passa a incluir também a leitura atual congelada, Centenas sombra, Puxadas/Bichos e Seca do 1º prêmio.
- O antigo caminho interno do Laboratório permanece como compatibilidade e redireciona para Decisão.
- Início, painel dos 25 bichos, Pesquisa, Resultados, Estatísticas, Puxadas, Métodos e Gerador passam a usar a mesma área vertical rolável inteligente já aplicada em telas mais novas.
- Jogar preserva seu mecanismo próprio de rolagem, inclusive prioridade de Treeview/Text/Listbox e fallback para a página.
- Grandes janelas abertas diretamente pela Central recebem área externa rolável quando aplicável.
- Uma política global de roda do mouse passa a alcançar também diálogos e widgets atuais/futuros: controles com rolagem própria têm prioridade, depois a página/janela assume; Combobox/Spinbox não mudam valor acidentalmente quando a intenção é rolar.
- Nenhum método, fórmula, histórico, financeiro ou jogo oficial foi alterado.

PADRÃO PERMANENTE DE INTERFACE — ROLAMENTO INTELIGENTE
- Toda nova aba, tela, seção extensa ou janela criada no GP-H deve prever rolagem vertical desde a implementação inicial.
- A roda do mouse deve funcionar mesmo quando o ponteiro estiver sobre labels, botões, entradas, comboboxes ou cartões; não deve exigir clicar na barra de rolagem.
- Treeview, Text e Listbox rolam primeiro enquanto ainda tiverem conteúdo na direção pedida; ao chegar ao limite, a página/janela externa assume quando houver continuação.
- Combobox e Spinbox não devem trocar valores apenas porque o usuário girou a roda tentando mover a tela.
- A barra vertical pode ficar oculta quando todo o conteúdo couber e reaparecer quando houver overflow.
- Esta regra vale para telas já existentes e para qualquer tela/janela futura; exceção apenas para elementos efêmeros sem conteúdo rolável, como tooltips pequenos.

'''
    if not doc.startswith("REVISÃO v0.36.0"):
        doc = block + doc
    DOC.write_text(doc, encoding="utf-8")

    upd = UPDATES.read_text(encoding="utf-8")
    upd = upd.replace("GP-H CENTRAL HISTÓRICA v0.35.3", "GP-H CENTRAL HISTÓRICA v0.36.0", 1)
    ublock = '''Novidades v0.36.0:
- Decisão e Laboratório Sombra passam a ser uma única tela de análise.
- Laboratório sai do menu lateral e vira seção interna de Decisão, sem perder os dados prospectivos.
- Rolamento inteligente vira padrão global da interface e alcança as principais abas antigas, janelas e widgets futuros.
- A roda prioriza controles roláveis e depois a página; Combobox/Spinbox ficam protegidos contra alterações acidentais pela roda.
- Nenhum método, fórmula ou jogo oficial foi alterado.

'''
    if "Novidades v0.36.0:" not in upd:
        anchor = "Novidades v0.35.3:\n"
        if anchor not in upd:
            raise RuntimeError("Âncora de atualizações não encontrada")
        upd = upd.replace(anchor, ublock + anchor, 1)
    UPDATES.write_text(upd, encoding="utf-8")

    bat = BAT.read_text(encoding="utf-8")
    bat = re.sub(r"v0\.35\.1", "v0.36.0", bat)
    BAT.write_text(bat, encoding="utf-8")

    print("v0.36.0 aplicada e validada estaticamente.")


if __name__ == "__main__":
    main()
