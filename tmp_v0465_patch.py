from pathlib import Path
import ast

SRC = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')
text = SRC.read_text(encoding='utf-8')
doc = DOC.read_text(encoding='utf-8')

# Guarda o Database inteiro: esta correção é 100% de janela/layout.
tree_before = ast.parse(text)
def class_dump(tree, name):
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(name)
db_before = class_dump(tree_before, 'Database')

assert 'APP_VERSION = "0.46.4"' in text
text = text.replace('GP-H Central Histórica v0.46.4', 'GP-H Central Histórica v0.46.5', 1)
text = text.replace('APP_VERSION = "0.46.4"', 'APP_VERSION = "0.46.5"', 1)

# O tamanho mínimo antigo permitia um estado que a Home não comportava bem no
# Windows real. 700 px é o piso visual seguro observado no próprio Windows.
assert text.count('self.minsize(1050, 650)') == 1
text = text.replace('self.minsize(1050, 650)', 'self.minsize(1050, 700)', 1)

# Desativa a animação DWM de maximizar/restaurar para esta janela. O Tk redesenha
# todos os filhos a cada frame da animação nativa; sem a transição a troca ocorre
# em um único salto visual. Falha silenciosamente fora do Windows ou se a API não
# estiver disponível.
anchor = '''    def _maximize_main_window(self):\n        """Inicia a janela principal maximizada sem depender de resolução fixa."""\n'''
assert text.count(anchor) == 1
replacement = '''    def _disable_windows_window_transitions(self):\n        """Desliga animações DWM desta janela para maximizar/restaurar sem tremor."""\n        if os.name != "nt":\n            return False\n        try:\n            import ctypes\n            hwnd = int(self.winfo_id())\n            # Em algumas builds do Tk, winfo_id aponta para a janela cliente; o\n            # HWND pai é a moldura de topo que o DWM realmente anima.\n            parent = int(ctypes.windll.user32.GetParent(hwnd) or 0)\n            if parent:\n                hwnd = parent\n            disabled = ctypes.c_int(1)\n            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(\n                ctypes.c_void_p(hwnd),\n                ctypes.c_uint(3),  # DWMWA_TRANSITIONS_FORCEDISABLED\n                ctypes.byref(disabled),\n                ctypes.sizeof(disabled),\n            )\n            return int(result) == 0\n        except Exception:\n            return False\n\n    def _maximize_main_window(self):\n        """Inicia a janela principal maximizada sem depender de resolução fixa."""\n        self._disable_windows_window_transitions()\n'''
text = text.replace(anchor, replacement, 1)

# compact=True agora significa de fato uma imagem compacta e ESTÁVEL. Na v0.46.4
# o cartão nascia large e só depois trocava de imagem via <Configure>.
old_image = '''        image = (\n            self.animal_images_large.get(info["grupo"])\n            if compact\n            else self.animal_images_large.get(info["grupo"])\n        )\n'''
new_image = '''        image = (\n            self.animal_images_medium.get(info["grupo"])\n            if compact\n            else self.animal_images_large.get(info["grupo"])\n        )\n'''
assert text.count(old_image) == 1
text = text.replace(old_image, new_image, 1)

# Remover completamente o resize adaptativo introduzido na v0.46.4. A Home fica
# com os mesmos widgets/imagens enquanto o Windows muda a geometria.
start_marker = '''        # HOME RESPONSIVA: maximizada mantém as imagens grandes; em alturas\n'''
end_marker = '''\n\n    def show_home_animals(self):\n'''
start = text.find(start_marker)
end = text.find(end_marker, start)
assert start >= 0 and end > start
static_tail = '''        # Home estática: nada é reconstruído ou troca de densidade em <Configure>.\n        # O Canvas continua cuidando apenas da rolagem de segurança.\n        if home_canvas is not None:\n            def _home_refresh_region_once():\n                try:\n                    body.update_idletasks()\n                    bbox = home_canvas.bbox("all")\n                    home_canvas.configure(scrollregion=bbox or (0, 0, 0, 0))\n                except (tk.TclError, ValueError, TypeError):\n                    pass\n            self.after_idle(_home_refresh_region_once)\n'''
text = text[:start] + static_tail + text[end:]

revision = '''REVISÃO v0.46.5 — HOME ESTÁVEL NO WINDOWS\n- Abandonada a troca dinâmica de densidade da v0.46.4: a grade não reage mais a <Configure> trocando imagens durante Maximizar/Restaurar.\n- Os cartões compactos da Home passam a nascer diretamente com a imagem média e permanecem nesse tamanho; não há reconstrução nem troca large/medium durante resize.\n- Altura mínima da janela principal ajustada de 650 para 700 px, impedindo o estado de janela em que a quinta linha ficava espremida/cortada.\n- No Windows, a Central solicita ao DWM a desativação das transições animadas da janela (DWMWA_TRANSITIONS_FORCEDISABLED), tornando Maximizar/Restaurar um salto visual em vez de vários frames de redesenho do Tk.\n- A barra/Canvas da Home continuam oferecendo rolagem de segurança para DPI ou ambientes excepcionais, mas não controlam mais densidade dos bichos.\n- Database e todo o cérebro estatístico permanecem estruturalmente idênticos à v0.46.4.\n\n'''
assert not doc.startswith('REVISÃO v0.46.5')
doc = revision + doc

ast.parse(text)
tree_after = ast.parse(text)
assert db_before == class_dump(tree_after, 'Database'), 'Database foi alterado'
assert '_home_responsive_state' not in text
assert 'home_canvas.bind("<Configure>", _home_schedule_density' not in text
assert 'self.animal_images_medium.get(info["grupo"])\n            if compact' in text
assert 'self.minsize(1050, 700)' in text
assert 'DWMWA_TRANSITIONS_FORCEDISABLED' in text

SRC.write_text(text, encoding='utf-8')
DOC.write_text(doc, encoding='utf-8')
print('Patch v0.46.5 aplicado: Home estática, minheight 700 e DWM sem transição.')
