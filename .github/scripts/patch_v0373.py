from pathlib import Path
import ast, re

SOURCE=Path('source/gph_central.py')
DOC=Path('source/DOCUMENTACAO_GP-H.txt')
text=SOURCE.read_text(encoding='utf-8')

if 'APP_VERSION = "0.37.2"' not in text:
    raise SystemExit('v0.37.3 deve partir exatamente da v0.37.2')

CRITICAL={
    'generate_centenas_3plus1','centena_31_freeze_state','decision_contextual_evidence',
    'method_reset_coverage_v1','play_generate','freeze_generated_game'
}
def critical_ast(src):
    tree=ast.parse(src); out={}
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in CRITICAL:
            out[n.name]=ast.dump(n,include_attributes=False)
    missing=CRITICAL-set(out)
    if missing: raise SystemExit(f'Funções críticas ausentes: {sorted(missing)}')
    return out
critical_before=critical_ast(text)

# ------------------------------------------------------------------
# 1) Regra universal de tamanho/posição para janelas secundárias.
# ------------------------------------------------------------------
helper='''\ndef fit_toplevel_to_screen(window, width=None, height=None, *, min_width=360, min_height=260, parent=None, margin_x=24, margin_y=56):
    """Dimensiona e centraliza uma Toplevel sem ultrapassar a área útil do monitor.

    O tamanho pedido é um alvo, não uma obrigação: em telas menores a janela encolhe.
    O mínimo também é limitado ao espaço realmente disponível. Janelas que usam
    conteúdo rolável continuam acessíveis mesmo quando precisam ser reduzidas.
    """
    try:
        window.update_idletasks()
        screen_w=max(1, int(window.winfo_screenwidth()))
        screen_h=max(1, int(window.winfo_screenheight()))
        max_w=max(320, screen_w - int(margin_x) * 2)
        max_h=max(240, screen_h - int(margin_y) * 2)

        req_w=max(1, int(window.winfo_reqwidth()))
        req_h=max(1, int(window.winfo_reqheight()))
        desired_w=int(width) if width else req_w
        desired_h=int(height) if height else req_h
        w=max(1, min(desired_w, max_w))
        h=max(1, min(desired_h, max_h))
        floor_w=max(1, min(int(min_width), max_w, w))
        floor_h=max(1, min(int(min_height), max_h, h))

        try:
            window.minsize(floor_w, floor_h)
            window.maxsize(max_w, max_h)
        except tk.TclError:
            pass

        owner=parent
        if owner is None:
            try:
                owner=window.master
            except Exception:
                owner=None

        if owner is not None:
            try:
                owner.update_idletasks()
                ox=int(owner.winfo_rootx())
                oy=int(owner.winfo_rooty())
                ow=max(1, int(owner.winfo_width()))
                oh=max(1, int(owner.winfo_height()))
                x=ox + (ow-w)//2
                y=oy + (oh-h)//2
            except Exception:
                x=(screen_w-w)//2
                y=(screen_h-h)//2
        else:
            x=(screen_w-w)//2
            y=(screen_h-h)//2

        x=max(int(margin_x), min(int(x), screen_w-w-int(margin_x)))
        y=max(int(margin_y)//2, min(int(y), screen_h-h-int(margin_y)))
        window.geometry(f"{w}x{h}+{x}+{y}")
        return w, h
    except Exception:
        try:
            if width and height:
                window.geometry(f"{int(width)}x{int(height)}")
        except Exception:
            pass
        return None
\n'''
anchor='class DatePickerDialog(tk.Toplevel):'
if anchor not in text: raise SystemExit('DatePickerDialog não encontrado')
text=text.replace(anchor,helper+anchor,1)

# Janelas de classe com tamanhos antigos fixos.
pairs=[
('720x520','620, 430'),('1080x660','900, 540'),('720x610','650, 560'),
('860x650','780, 590'),('980x620','820, 520'),('1080x650','880, 540'),
('1040x620','860, 520'),('1280x720','1000, 580'),('920x520','760, 430'),
('1180x620','930, 500'),('900x650','760, 540'),('1120x650','900, 520'),
]
for geom, mins in pairs:
    w,h=geom.split('x'); mw,mh=[v.strip() for v in mins.split(',')]
    old=f'        self.geometry("{geom}")\n        self.minsize({mins})'
    new=f'        fit_toplevel_to_screen(self, {w}, {h}, min_width={mw}, min_height={mh}, parent=master)'
    if old not in text:
        raise SystemExit(f'Par geometry/minsize não encontrado: {geom} / {mins}')
    text=text.replace(old,new,1)

# Calendário e cadastro manual não tinham posicionamento/tamanho comum.
old='''        self.render_calendar()\n\n    def render_calendar(self):'''
new='''        self.render_calendar()\n        fit_toplevel_to_screen(self, min_width=390, min_height=330, parent=master)\n\n    def render_calendar(self):'''
if old not in text: raise SystemExit('Âncora DatePicker render não encontrada')
text=text.replace(old,new,1)

old='''        self.bind("<Return>", lambda e: self.save())\n        self.bind("<Escape>", lambda e: self.destroy())\n\n    def update_hour(self, _=None):'''
new='''        self.bind("<Return>", lambda e: self.save())\n        self.bind("<Escape>", lambda e: self.destroy())\n        fit_toplevel_to_screen(self, min_width=470, min_height=430, parent=master)\n\n    def update_hour(self, _=None):'''
if old not in text: raise SystemExit('Âncora ManualDialog não encontrada')
text=text.replace(old,new,1)

# Perfil: substitui centralização manual fixa.
profile_pat=re.compile(r'''        self\.update_idletasks\(\)\n        try:\n            x = self\.winfo_rootx\(\) \+ max\(20, \(self\.winfo_width\(\) - 570\) // 2\)\n            y = self\.winfo_rooty\(\) \+ max\(20, \(self\.winfo_height\(\) - 440\) // 2\)\n            win\.geometry\(f"570x440\+\{x\}\+\{y\}"\)\n        except tk\.TclError:\n            win\.geometry\("570x440"\)''')
text,n=profile_pat.subn('        fit_toplevel_to_screen(win, 570, 440, min_width=500, min_height=390, parent=self)',text,count=1)
if n!=1: raise SystemExit('Bloco de geometry do Perfil não substituído')

# Prévia dos bichos: tamanho adaptativo em vez de 820x700 fixo + cálculo próprio.
preview_pat=re.compile(r'''        pop\.geometry\("820x700"\)\n        pop\.minsize\(720, 620\)\n        try:\n            self\.update_idletasks\(\)\n            px = self\.winfo_rootx\(\) \+ max\(0, \(self\.winfo_width\(\) - 820\) // 2\)\n            py = self\.winfo_rooty\(\) \+ max\(0, \(self\.winfo_height\(\) - 700\) // 2\)\n            pop\.geometry\(f"820x700\+\{px\}\+\{py\}"\)\n        except tk\.TclError:\n            pass''')
text,n=preview_pat.subn('        fit_toplevel_to_screen(pop, 820, 700, min_width=720, min_height=620, parent=self)',text,count=1)
if n!=1: raise SystemExit('Prévia de bichos não adaptada')

# Diálogos criados dentro de App.
repls={
'''        dialog.minsize(510, 390)\n        dialog.geometry("560x470")''':
'''        fit_toplevel_to_screen(dialog, 560, 470, min_width=510, min_height=390, parent=self)''',
'''        dialog.geometry("760x620")\n        dialog.minsize(650,520)''':
'''        fit_toplevel_to_screen(dialog, 760, 620, min_width=650, min_height=520, parent=self)''',
'''        win.geometry("980x650")\n        win.minsize(820, 520)''':
'''        fit_toplevel_to_screen(win, 980, 650, min_width=820, min_height=520, parent=self)''',
}
for old,new in repls.items():
    if old not in text: raise SystemExit('Diálogo interno esperado não encontrado: '+old.splitlines()[0])
    text=text.replace(old,new,1)

# ------------------------------------------------------------------
# 2) Um único motor de rolamento: GPHSmartWheel.
# ------------------------------------------------------------------
def app_function_span(src,name):
    tree=ast.parse(src)
    app=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='App')
    f=next((n for n in app.body if isinstance(n,ast.FunctionDef) and n.name==name),None)
    if f is None: raise SystemExit(f'Função App.{name} ausente')
    return f.lineno,f.end_lineno

def replace_app_function(src,name,new_code):
    a,b=app_function_span(src,name)
    lines=src.splitlines(keepends=True)
    lines[a-1:b]=[new_code if new_code.endswith('\n') else new_code+'\n']
    return ''.join(lines)

new_scrollable='''    def _make_scrollable_page_body(self, parent, key):
        """Cria uma página rolável usando exclusivamente o GPHSmartWheel global."""
        host = ttk.Frame(parent)
        host.pack(fill="both", expand=True)
        canvas = tk.Canvas(
            host, highlightthickness=0, borderwidth=0, bg=self.colors["bg"]
        )
        bar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

        body = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas._gph_smart_scroll = True
        canvas._gph_scrollbar = bar
        body._gph_scroll_canvas = canvas
        if not hasattr(self, "_smart_scroll_canvases"):
            self._smart_scroll_canvases = {}
        self._smart_scroll_canvases[key] = canvas

        def update_bar(first=None, last=None):
            try:
                if first is None or last is None:
                    first, last = canvas.yview()
                need = float(first) > 0.0 or float(last) < 1.0
                managed = bool(bar.winfo_manager())
                if need and not managed:
                    bar.pack(side="right", fill="y")
                elif not need and managed:
                    bar.pack_forget()
            except (tk.TclError, ValueError, TypeError):
                pass

        def on_yview(first, last):
            try:
                bar.set(first, last)
            finally:
                update_bar(first, last)

        canvas.configure(yscrollcommand=on_yview)

        def update_region(_event=None):
            try:
                bbox = canvas.bbox("all")
                canvas.configure(scrollregion=bbox or (0, 0, 0, 0))
                self.after_idle(update_bar)
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

        def install_global_policy():
            self._smart_scroll_install_tags(host)
            update_region()

        self.after_idle(install_global_policy)
        return body

'''
text=replace_app_function(text,'_make_scrollable_page_body',new_scrollable)

# Nomes genéricos: deixam de carregar o legado "play".
text=text.replace('def _wheel_units(event):','def _smart_scroll_units(event):',1)
text=text.replace('self._wheel_units(event)','self._smart_scroll_units(event)')
text=text.replace('def _play_scroll_child_if_possible(self, widget, units):','def _smart_scroll_child_if_possible(self, widget, units):',1)
text=text.replace('self._play_scroll_child_if_possible(', 'self._smart_scroll_child_if_possible(')

# Remove os dois métodos exclusivos do antigo motor de Jogar.
for name in ('_play_install_wheel_bindtag','_play_mousewheel'):
    a,b=app_function_span(text,name)
    lines=text.splitlines(keepends=True)
    del lines[a-1:b]
    text=''.join(lines)

# Retira criação/bind do GPHPlayWheel em show_play_page.
play_block=re.compile(r'''\n        # A roda do mouse é roteada por um bindtag próprio, instalado nos\n        # controles da página\. Isso faz a rolagem responder sob labels,\n        # botões, entradas e comboboxes sem exigir clique/foco prévio\.\n        # Se o ponteiro estiver sobre Treeview/Text/Listbox, o próprio\n        # controle rola enquanto puder; ao chegar ao limite, a página assume\.\n        self\._play_wheel_tag = "GPHPlayWheel"\n        if not getattr\(self, "_play_mousewheel_bound", False\):\n            self\.bind_class\(self\._play_wheel_tag, "<MouseWheel>", self\._play_mousewheel, add="\+"\)\n            self\.bind_class\(self\._play_wheel_tag, "<Button-4>", self\._play_mousewheel, add="\+"\)\n            self\.bind_class\(self\._play_wheel_tag, "<Button-5>", self\._play_mousewheel, add="\+"\)\n            self\._play_mousewheel_bound = True\n''')
text,n=play_block.subn('\n        # Jogar usa o mesmo GPHSmartWheel global de todas as outras telas.\n',text,count=1)
if n!=1: raise SystemExit('Bloco GPHPlayWheel não removido')

# O finalize de Jogar agora só instala o bindtag global nos widgets dinâmicos.
new_finalize='''    def _play_finalize_layout(self):
        if getattr(self, "_page", None) != "play":
            return
        host = getattr(self, "play_scroll_host", None)
        if host is not None:
            self._smart_scroll_install_tags(host)
        self._play_update_scrollregion()

'''
text=replace_app_function(text,'_play_finalize_layout',new_finalize)

# Barra de Jogar também some quando não há overflow.
new_play_region='''    def _play_update_scrollregion(self, _event=None):
        canvas = getattr(self, "play_body_canvas", None)
        if canvas is None:
            return
        try:
            bbox = canvas.bbox("all")
            canvas.configure(scrollregion=bbox or (0, 0, 0, 0))
            bar = getattr(self, "play_body_scrollbar", None)
            if bar is not None:
                first, last = canvas.yview()
                need = float(first) > 0.0 or float(last) < 1.0
                managed = bool(bar.winfo_manager())
                if need and not managed:
                    bar.pack(side="right", fill="y")
                elif not need and managed:
                    bar.pack_forget()
        except (tk.TclError, ValueError, TypeError):
            pass

'''
text=replace_app_function(text,'_play_update_scrollregion',new_play_region)

# Listbox de Vários Horários não captura mais a roda por conta própria.
local_wheel=re.compile(r'''\n        def on_wheel\(event\):\n            delta = int\(-1 \* \(event\.delta / 120\)\) if event\.delta else 0\n            if delta:\n                listbox\.yview_scroll\(delta, "units"\)\n            return "break"\n\n        listbox\.bind\("<MouseWheel>", on_wheel\)\n''')
text,n=local_wheel.subn('\n        self._smart_scroll_install_tags(dialog)\n',text,count=1)
if n!=1: raise SystemExit('MouseWheel local de Vários Horários não removido')

# ------------------------------------------------------------------
# 3) Versão, documentação e validações.
# ------------------------------------------------------------------
text=text.replace('GP-H Central Histórica v0.37.2','GP-H Central Histórica v0.37.3',1)
text=text.replace('APP_VERSION = "0.37.2"','APP_VERSION = "0.37.3"',1)
about='            "• v0.37.2 — padrão global de interface: tipografia, fonte mínima, tabelas, controles, espaçamento e cores semânticas centralizados.\\n"\n'
if about not in text: raise SystemExit('Âncora Sobre v0.37.2 ausente')
text=text.replace(about,'            "• v0.37.3 — um único rolamento inteligente global e janelas secundárias adaptativas ao monitor.\\n"\n'+about,1)

# Lógica crítica deve continuar idêntica.
ast.parse(text)
critical_after=critical_ast(text)
for name in CRITICAL:
    if critical_before[name] != critical_after[name]:
        raise SystemExit(f'LÓGICA CRÍTICA ALTERADA: {name}')

# Invariantes da Etapa 3.
for forbidden in ('GPHPlayWheel','GPHScroll_','_play_mousewheel','_play_install_wheel_bindtag','_play_scroll_child_if_possible','listbox.bind("<MouseWheel>"'):
    if forbidden in text: raise SystemExit(f'Legado de rolamento ainda presente: {forbidden}')
if text.count('"<MouseWheel>"') != 1:
    raise SystemExit(f'Esperado exatamente 1 binding MouseWheel global; encontrados {text.count(chr(34)+"<MouseWheel>"+chr(34))}')
for marker in ('def fit_toplevel_to_screen(', 'def _smart_scroll_units(', 'def _smart_scroll_child_if_possible(', 'tag = "GPHSmartWheel"'):
    if marker not in text: raise SystemExit(f'Marcador v0.37.3 ausente: {marker}')
if text.count('fit_toplevel_to_screen(') < 18:
    raise SystemExit('Poucas janelas foram migradas para tamanho adaptativo')

SOURCE.write_text(text,encoding='utf-8')

doc=DOC.read_text(encoding='utf-8')
revision='''REVISÃO v0.37.3 — ROLAMENTO INTELIGENTE + JANELAS ADAPTATIVAS / ETAPA 3
- Unificado o roteamento da roda do mouse: GPHSmartWheel passa a ser o único motor para páginas, Jogar e diálogos; removidos GPHPlayWheel, GPHScroll_<tela> e bindings locais de MouseWheel.
- Treeview, Text e Listbox continuam rolando primeiro; ao atingir o limite, a página/Canvas assume quando existir.
- Combobox e Spinbox continuam protegidos contra alteração acidental pela roda.
- Scrollbars das páginas genéricas e da tela Jogar passam a ocultar-se automaticamente quando não existe overflow vertical e reaparecem quando necessário.
- Criada fit_toplevel_to_screen(): janelas secundárias recebem tamanho-alvo, mas nunca ultrapassam a área útil disponível; mínimos também são limitados pela resolução real.
- Janelas normais são centralizadas em relação à janela principal e têm maxsize compatível com o monitor; tooltips sem decoração mantêm o posicionamento especial junto ao elemento apontado.
- Migradas para a regra adaptativa as janelas técnicas, detalhes de bicho/jogo, atualização, métodos, exemplos de puxadas, perfil, prévia de bichos, vários horários, fechamento diário, guia de métodos, calendário e cadastro manual.
- Reset + 3+1, congelamento persistente, Reset Cobertura, Decisão Contextual, Similaridade, apostas, banco, financeiro e sincronização permanecem sem alteração de lógica.

'''
DOC.write_text(revision+doc,encoding='utf-8')
print('v0.37.3 preparada com sucesso')
print('MouseWheel bindings:', text.count('"<MouseWheel>"'))
print('fit_toplevel_to_screen refs:', text.count('fit_toplevel_to_screen('))
print('linhas:',len(text.splitlines()))
print('funções críticas preservadas:', ', '.join(sorted(CRITICAL)))
