from pathlib import Path

src = Path("source/gph_central.py")
text = src.read_text(encoding="utf-8")

if 'APP_VERSION = "0.36.6"' in text:
    raise SystemExit("v0.36.6 ja aplicada")
if 'APP_VERSION = "0.36.5"' not in text:
    raise SystemExit("Base esperada v0.36.5 nao encontrada")

text = text.replace("GP-H Central Histórica v0.36.5", "GP-H Central Histórica v0.36.6", 1)
text = text.replace('APP_VERSION = "0.36.5"', 'APP_VERSION = "0.36.6"', 1)

# Ctrl+G deixa de abrir a tela antiga e passa a levar para Jogar.
old = '''        self.bind_all(
            "<Control-g>",
            lambda _e: self.show_generator_page(),
        )'''
new = '''        self.bind_all(
            "<Control-g>",
            lambda _e: self.show_play_page(),
        )'''
if old not in text:
    raise SystemExit("Atalho Ctrl+G esperado nao encontrado")
text = text.replace(old, new, 1)

# O icone do Gerador deixa de ser carregado pelo menu principal.
old_icons = '("home","ticket","results","search","statistics","pulls","methods","generator","database","animals")'
new_icons = '("home","ticket","results","search","statistics","pulls","methods","database","animals")'
if old_icons not in text:
    raise SystemExit("Lista de icones esperada nao encontrada")
text = text.replace(old_icons, new_icons, 1)

# Remove a entrada visual Gerador do menu lateral.
nav_line = '            ("Gerador", self.show_generator_page, "generator"),\n'
if nav_line not in text:
    raise SystemExit("Entrada Gerador do menu nao encontrada")
text = text.replace(nav_line, '', 1)

# Botao da Home que preparava o jogo na tela legada agora usa Jogar.
old_home = '''            self.show_generator_page()
            self.gen_source.set("Método oficial — Reset")
            self.gen_num_animals.set("5")
            self.gen_kind.set("Centena")
            self.gen_strategy.set("Oficial 3+1")
            self.gen_scope.set("1º–5º")
            self.gen_total.set("20")

            self.generator_refresh_control_states()
            self.generator_generate()
'''
new_home = '''            self.show_play_page()
            self.play_generate()
'''
if old_home not in text:
    raise SystemExit("Fluxo Home -> Gerador esperado nao encontrado")
text = text.replace(old_home, new_home, 1)
text = text.replace(
    '"Confira e congele quando estiver satisfeito."',
    '"Confira os palpites e adicione ao bilhete quando estiver satisfeito."',
    1,
)

# Rota antiga permanece por compatibilidade, mas redireciona imediatamente para Jogar.
old_route = '''    def show_generator_page(self):
        self._set_active_nav("Gerador")
'''
new_route = '''    def show_generator_page(self):
        """Compatibilidade: a antiga tela Gerador foi absorvida por Jogar."""
        return self.show_play_page()

        # Implementação legada preservada internamente por segurança do motor.
        self._set_active_nav("Gerador")
'''
if old_route not in text:
    raise SystemExit("Inicio de show_generator_page nao encontrado")
text = text.replace(old_route, new_route, 1)

# Atualizacao de pagina antiga e API interna antiga tambem desembocam em Jogar.
old_refresh = '''        elif self._page == "generator":
            self.show_generator_page()
'''
new_refresh = '''        elif self._page == "generator":
            self.show_play_page()
'''
if old_refresh not in text:
    raise SystemExit("Rota generator em refresh nao encontrada")
text = text.replace(old_refresh, new_refresh, 1)

old_open = '''    def open_game_generator(self):
        self.show_generator_page()
'''
new_open = '''    def open_game_generator(self):
        # Compatibilidade com chamadas antigas: geração oficial vive em Jogar.
        self.show_play_page()
'''
if old_open not in text:
    raise SystemExit("open_game_generator esperado nao encontrado")
text = text.replace(old_open, new_open, 1)

src.write_text(text, encoding="utf-8")

# Documentacao consolidada.
doc = Path("source/DOCUMENTACAO_GP-H.txt")
if doc.exists():
    d = doc.read_text(encoding="utf-8")
    revision = '''REVISÃO v0.36.6 — GERADOR ABSORVIDO POR JOGAR\n- A aba Gerador é removida do menu lateral por ter se tornado redundante.\n- Jogar passa a ser o ponto oficial e único da interface para gerar, revisar e registrar apostas.\n- Ctrl+G, a rota interna antiga do Gerador e open_game_generator redirecionam para Jogar, preservando compatibilidade.\n- O atalho da tela Início para preparar o próximo jogo agora abre Jogar e gera o Reset + 3+1 diretamente ali.\n- O motor e as rotinas internas de geração permanecem preservados; foi removida apenas a porta de entrada visual obsoleta.\n- Nenhuma fórmula, ranking, seleção dos 5 bichos, congelamento, histórico, bilhete ou financeiro foi alterado.\n\n'''
    if not d.startswith("REVISÃO v0.36.6"):
        d = revision + d
    d = d.replace("VERSÃO ATUAL: v0.36.5", "VERSÃO ATUAL: v0.36.6", 1)
    doc.write_text(d, encoding="utf-8")

upd = Path("source/ATUALIZACOES_PROGRAMA_v0.35.txt")
if upd.exists():
    u = upd.read_text(encoding="utf-8")
    u = u.replace("GP-H CENTRAL HISTÓRICA v0.36.5", "GP-H CENTRAL HISTÓRICA v0.36.6", 1)
    note = '''\nNovidades v0.36.6:\n- Gerador removido do menu lateral; a geração de apostas fica concentrada em Jogar.\n- Rotas/atalhos antigos do Gerador redirecionam para Jogar.\n- Preparar próximo jogo na Início agora usa diretamente o fluxo de Jogar.\n- Motor interno preservado e nenhuma fórmula alterada.\n'''
    if "Novidades v0.36.6:" not in u:
        u += note
    upd.write_text(u, encoding="utf-8")

print("Patch v0.36.6 aplicado")
