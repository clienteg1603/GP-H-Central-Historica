from pathlib import Path

SRC = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')
text = SRC.read_text(encoding='utf-8')

assert 'APP_VERSION = "0.47.7"' in text
text = text.replace('APP_VERSION = "0.47.7"', 'APP_VERSION = "0.47.8"', 1)

anchor = '''    def decision_coverage_evolution(self, windows=(20, 30, 60), recent_limit=10):\n'''
assert anchor in text
helper = '''    def _coverage_candidate_rows(self):\n        \"\"\"\n        Retorna snapshots candidatos ao diagnóstico de cobertura sem exigir status AUDITADO.\n\n        A elegibilidade real continua sendo decidida depois: precisa existir Top 5 Meta\n        já congelado e resultado posterior disponível. Esta consulta é exclusiva do\n        painel diagnóstico e não altera status, pesos, ranking ou previsão.\n        \"\"\"\n        with self.connect() as con:\n            rows = con.execute(\n                \"SELECT * FROM decision_snapshots \"\n                \"ORDER BY target_data DESC, target_hora DESC, id DESC\"\n            ).fetchall()\n        return [dict(row) for row in rows]\n\n'''
text = text.replace(anchor, helper + anchor, 1)

old_rows = '''        raw_rows = self._decision_audited_rows(window=\"Todos\")\n'''
new_rows = '''        raw_rows = self._coverage_candidate_rows()\n'''
assert old_rows in text
text = text.replace(old_rows, new_rows, 1)

old_audit = '''                audit = row.get(\"meta_audit\") or {}\n                audit_source = \"saved_audit\"\n                if not audit.get(\"available\"):\n                    try:\n                        frozen_result_json = raw[\"result_groups_json\"]\n                    except Exception:\n                        frozen_result_json = row.get(\"result_groups_json\") or \"[]\"\n                    audit = self._coverage_frozen_audit(meta, frozen_result_json)\n                    if not audit.get(\"available\"):\n                        continue\n                    audit_source = \"frozen_history\"\n'''
new_audit = '''                audit = row.get(\"meta_audit\") or {}\n                audit_source = \"saved_audit\"\n                if not audit.get(\"available\"):\n                    frozen_result_json = raw.get(\"result_groups_json\") or row.get(\"result_groups_json\") or \"[]\"\n                    audit = self._coverage_frozen_audit(meta, frozen_result_json)\n                    if audit.get(\"available\"):\n                        audit_source = \"frozen_history\"\n                    else:\n                        # Snapshots antigos podem nunca ter recebido status AUDITADO/result_groups_json.\n                        # O resultado é apenas consultado AGORA no histórico; o Top 5 permanece aquele\n                        # que já estava congelado no snapshot antes da rodada.\n                        target = self.get_draw(\n                            row.get(\"target_data\"),\n                            row.get(\"target_sorteio\"),\n                            row.get(\"target_hora\"),\n                        )\n                        prizes = (target or {}).get(\"prizes\") or []\n                        if len(prizes) >= 5:\n                            lookup_groups = []\n                            for prize in prizes[:5]:\n                                try:\n                                    lookup_groups.append(int(prize[\"grupo\"]))\n                                except Exception:\n                                    pass\n                            audit = self._coverage_frozen_audit(meta, lookup_groups)\n                        if not audit.get(\"available\"):\n                            continue\n                        audit_source = \"result_lookup\"\n'''
assert old_audit in text
text = text.replace(old_audit, new_audit, 1)

old_count = '''            \"historical_bootstrap_rounds\": sum(r.get(\"audit_source\") == \"frozen_history\" for r in records),\n'''
new_count = '''            \"historical_bootstrap_rounds\": sum(r.get(\"audit_source\") in (\"frozen_history\", \"result_lookup\") for r in records),\n            \"result_lookup_rounds\": sum(r.get(\"audit_source\") == \"result_lookup\" for r in records),\n'''
assert old_count in text
text = text.replace(old_count, new_count, 1)

old_note = '''                \"Cobertura e Taxa 2+ reaproveitam também Top 5 Meta que já estavam congelados antes dos resultados, \"\n                \"mesmo quando a auditoria Meta ainda não existia. Conversão 3→3 continua usando somente Ternos Meta \"\n'''
new_note = '''                \"Cobertura e Taxa 2+ reaproveitam todo Top 5 Meta já congelado que possua resultado correspondente no banco, \"\n                \"mesmo que o snapshot antigo nunca tenha recebido status AUDITADO. Conversão 3→3 continua usando somente Ternos Meta \"\n'''
assert old_note in text
text = text.replace(old_note, new_note, 1)

old_ui = 'text=\"histórico congelado + novas rodadas • janelas 20 / 30 / 60\", style=\"CardMuted.TLabel\"'
new_ui = 'text=\"histórico Meta existente + novas rodadas • janelas 20 / 30 / 60\", style=\"CardMuted.TLabel\"'
assert old_ui in text
text = text.replace(old_ui, new_ui, 1)

SRC.write_text(text, encoding='utf-8')

doc = DOC.read_text(encoding='utf-8')
anchor_doc = 'REVISÃO v0.47.7 — BOOTSTRAP HISTÓRICO DA EVOLUÇÃO DE COBERTURA\n'
assert anchor_doc in doc
entry = '''REVISÃO v0.47.8 — CORREÇÃO DO BOOTSTRAP HISTÓRICO DA COBERTURA\n\n- Corrige a v0.47.7, que ainda iniciava pela função _decision_audited_rows e por isso descartava snapshots antigos antes do bootstrap.\n- Evolução de Cobertura agora lê diretamente os snapshots existentes sem exigir status AUDITADO; uma rodada só entra se já houver Top 5 Meta congelado e resultado correspondente disponível.\n- Quando result_groups_json/meta_audit antigos não existem, o painel consulta o resultado pelo alvo data+sorteio+hora via get_draw e compara esse resultado com o Top 5 que já estava salvo.\n- Essa consulta é somente de auditoria posterior: não recalcula Meta, ranking, pesos, confiança, sinais nem previsões antigas.\n- Ternos continuam sem reconstrução retrospectiva: Melhor Terno/Conversão 3→3 só usam apostas Meta realmente registradas para a mesma base prospectiva.\n\n'''
doc = doc.replace(anchor_doc, entry + anchor_doc, 1)
DOC.write_text(doc, encoding='utf-8')
print('PATCH v0.47.8 aplicado')
