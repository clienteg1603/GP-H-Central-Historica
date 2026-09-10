from pathlib import Path

SRC = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')
s = SRC.read_text(encoding='utf-8')

# Versão.
assert 'APP_VERSION = "0.47.4"' in s, 'versão-base 0.47.4 não encontrada'
s = s.replace('APP_VERSION = "0.47.4"', 'APP_VERSION = "0.47.5"', 1)

# A montagem manual agora vive somente dentro de Nova aposta.
nav_line = '            ("manual_builder", "Jogo manual", self.play_show_manual_builder),\n'
assert nav_line in s, 'aba Jogo manual não encontrada'
s = s.replace(nav_line, '', 1)

# Função pura/testável de acumulação para entradas manuais consecutivas.
anchor = '    def play_manual_input(self):\n'
assert anchor in s, 'play_manual_input não encontrada'
helper = '''    @staticmethod\n    def _merge_manual_generation(existing, incoming):\n        """Acumula palpites manuais compatíveis sem substituir os anteriores."""\n        incoming = copy.deepcopy(incoming or {})\n        incoming_rows = list(incoming.get("rows") or [])\n        if not existing or str(existing.get("strategy") or "") != "Manual":\n            return incoming, len(incoming_rows), False\n        if str(incoming.get("strategy") or "") != "Manual":\n            return incoming, len(incoming_rows), False\n\n        def target_key(generation):\n            target = generation.get("intended_target") or {}\n            return (target.get("data"), target.get("sorteio"), target.get("hora"))\n\n        compatible = (\n            str(existing.get("kind") or "") == str(incoming.get("kind") or "")\n            and str(existing.get("scope") or "") == str(incoming.get("scope") or "")\n            and str(existing.get("submodalidade") or "") == str(incoming.get("submodalidade") or "")\n            and target_key(existing) == target_key(incoming)\n        )\n        if not compatible:\n            return incoming, len(incoming_rows), False\n\n        merged = copy.deepcopy(existing)\n        merged_rows = list(merged.get("rows") or [])\n        seen = {\n            (str(row.get("numero") or ""), str(row.get("modalidade") or ""))\n            for row in merged_rows\n        }\n        added = 0\n        for row in incoming_rows:\n            key = (str(row.get("numero") or ""), str(row.get("modalidade") or ""))\n            if key in seen:\n                continue\n            merged_rows.append(copy.deepcopy(row))\n            seen.add(key)\n            added += 1\n        merged["rows"] = merged_rows\n        return merged, added, True\n\n'''
if '    def _merge_manual_generation(existing, incoming):\n' not in s:
    s = s.replace(anchor, helper + anchor, 1)

# Em vez de substituir self.play_generation, acumula quando alvo/modalidade/escopo coincidem.
old = '''            self.play_generation = generation\n            self.play_total.set(\n                str(len(generation["rows"]))\n            )\n            self.play_render_generation()\n            self.play_financial_refresh()\n'''
new = '''            generation, added, accumulated = self._merge_manual_generation(\n                self.play_generation, generation\n            )\n            self.play_generation = generation\n            self.play_total.set(str(len(generation.get("rows") or [])))\n            self.play_render_generation()\n            self.play_financial_refresh()\n\n            if accumulated:\n                status = getattr(self, "status", None)\n                if status is not None:\n                    if added:\n                        status.configure(\n                            text=(\n                                f"Manual: {added} novo(s) palpite(s) adicionado(s) • "\n                                f"{len(generation.get('rows') or [])} na lista atual."\n                            )\n                        )\n                    else:\n                        status.configure(text="Manual: esse palpite já estava na lista atual.")\n'''
# Limita a troca ao corpo de play_manual_input.
start = s.index('    def play_manual_input(self):')
end = s.find('\n    def ', start + 10)
segment = s[start:end if end != -1 else len(s)]
assert old in segment, 'bloco de substituição manual não encontrado'
segment = segment.replace(old, new, 1)
s = s[:start] + segment + s[end if end != -1 else len(s):]

SRC.write_text(s, encoding='utf-8', newline='\n')

entry = '''REVISÃO v0.47.5 — MANUAL MULTIJOGO / ABA REDUNDANTE\n\n- Em Jogar > Nova aposta > Método Manual, novas entradas compatíveis passam a ser somadas aos palpites já exibidos em vez de substituir a entrada anterior.\n- A acumulação ocorre somente quando rodada, modalidade, colocação e submodalidade são as mesmas; ao mudar esse contexto, a nova entrada inicia uma geração compatível com o novo contexto, preservando o comportamento seguro anterior.\n- Palpites repetidos não são duplicados na lista. A quantidade e os cálculos de valor acompanham automaticamente o total acumulado.\n- A aba superior redundante "Jogo manual" foi removida; toda a montagem manual fica concentrada em Nova aposta > Método Manual.\n- Bilhetes, Financeiro, Cotações e registro de múltiplas modalidades permanecem inalterados.\n- O Database e os cérebros Meta v0.2, Reset, Puxada, Similaridade, Histórico, Decisão e Lei de Geração GP-H não foram alterados.\n\n'''
d = DOC.read_text(encoding='utf-8')
if not d.startswith('REVISÃO v0.47.5'):
    d = entry + d
DOC.write_text(d, encoding='utf-8', newline='\n')
