from pathlib import Path

SRC = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')
text = SRC.read_text(encoding='utf-8')

assert 'APP_VERSION = "0.47.6"' in text
text = text.replace('APP_VERSION = "0.47.6"', 'APP_VERSION = "0.47.7"', 1)

helper_anchor = '''    @staticmethod\n    def _coverage_evolution_summary(records, window, target_pct=50.0):\n'''
assert helper_anchor in text
helper = '''    @staticmethod\n    def _coverage_frozen_audit(meta, result_groups_json):\n        \"\"\"\n        Audita um Top 5 Meta JÁ CONGELADO contra o resultado já conhecido.\n\n        Não recalcula previsão, ranking, peso ou confiança. Serve somente para\n        reaproveitar snapshots prospectivos antigos que ainda não possuíam\n        meta_audit_json quando o painel Evolução de Cobertura foi criado.\n        \"\"\"\n        meta = meta or {}\n        core_groups = []\n        for raw_group in (meta.get(\"groups\") or [])[:5]:\n            try:\n                group = int(raw_group)\n            except Exception:\n                continue\n            if 1 <= group <= 25 and group not in core_groups:\n                core_groups.append(group)\n\n        decoded = result_groups_json\n        if isinstance(decoded, str):\n            try:\n                decoded = json.loads(decoded or \"[]\")\n            except Exception:\n                decoded = []\n        if not isinstance(decoded, (list, tuple)):\n            decoded = []\n\n        result_groups = []\n        for raw_group in decoded:\n            try:\n                group = int(raw_group)\n            except Exception:\n                continue\n            if 1 <= group <= 25:\n                result_groups.append(group)\n\n        if not core_groups or not result_groups:\n            return {\"available\": False, \"source\": \"frozen_history\"}\n\n        coverage_hits = len(set(core_groups) & set(result_groups))\n        return {\n            \"available\": True,\n            \"source\": \"frozen_history\",\n            \"groups\": core_groups,\n            \"result_groups\": result_groups,\n            \"coverage_hits\": coverage_hits,\n        }\n\n'''
text = text.replace(helper_anchor, helper + helper_anchor, 1)

old_audit = '''                meta = row.get(\"meta\") or {}\n                audit = row.get(\"meta_audit\") or {}\n                if not audit.get(\"available\"):\n                    continue\n                core_groups = []\n'''
new_audit = '''                meta = row.get(\"meta\") or {}\n                audit = row.get(\"meta_audit\") or {}\n                audit_source = \"saved_audit\"\n                if not audit.get(\"available\"):\n                    try:\n                        frozen_result_json = raw[\"result_groups_json\"]\n                    except Exception:\n                        frozen_result_json = row.get(\"result_groups_json\") or \"[]\"\n                    audit = self._coverage_frozen_audit(meta, frozen_result_json)\n                    if not audit.get(\"available\"):\n                        continue\n                    audit_source = \"frozen_history\"\n                core_groups = []\n'''
assert old_audit in text
text = text.replace(old_audit, new_audit, 1)

record_anchor = '''                    \"core_terno_count\": core_terno_count,\n                    \"diagnostic\": diagnostic,\n'''
record_new = '''                    \"core_terno_count\": core_terno_count,\n                    \"audit_source\": audit_source,\n                    \"diagnostic\": diagnostic,\n'''
assert record_anchor in text
text = text.replace(record_anchor, record_new, 1)

return_anchor = '''            \"recent\": records[:recent_limit],\n            \"eligible_rounds\": len(records),\n            \"note\": (\n                \"Cobertura usa o Top 5 Meta congelado. Conversão 3→3 só usa Ternos Meta registrados, \"\n                \"da mesma base prospectiva e formados integralmente pelo Top 5; ausência de Terno não vira falha de conversão.\"\n            ),\n'''
return_new = '''            \"recent\": records[:recent_limit],\n            \"eligible_rounds\": len(records),\n            \"historical_bootstrap_rounds\": sum(r.get(\"audit_source\") == \"frozen_history\" for r in records),\n            \"note\": (\n                \"Cobertura e Taxa 2+ reaproveitam também Top 5 Meta que já estavam congelados antes dos resultados, \"\n                \"mesmo quando a auditoria Meta ainda não existia. Conversão 3→3 continua usando somente Ternos Meta \"\n                \"realmente registrados, da mesma base prospectiva e formados integralmente pelo Top 5; ausência de Terno não vira falha.\"\n            ),\n'''
assert return_anchor in text
text = text.replace(return_anchor, return_new, 1)

ui_old = 'text=\"diagnóstico • janelas 20 / 30 / 60\", style=\"CardMuted.TLabel\"'
ui_new = 'text=\"histórico congelado + novas rodadas • janelas 20 / 30 / 60\", style=\"CardMuted.TLabel\"'
assert ui_old in text
text = text.replace(ui_old, ui_new, 1)

empty_old = 'text=\"A coleta ainda não possui snapshots Meta auditados suficientes para formar este painel.\"'
empty_new = 'text=\"Ainda não há Top 5 Meta congelados com resultado disponível suficientes para formar este painel.\"'
assert empty_old in text
text = text.replace(empty_old, empty_new, 1)

SRC.write_text(text, encoding='utf-8')

doc = DOC.read_text(encoding='utf-8')
anchor = 'REVISÃO v0.47.6 — EVOLUÇÃO DE COBERTURA / META DIAGNÓSTICA\n'
assert anchor in doc
entry = '''REVISÃO v0.47.7 — BOOTSTRAP HISTÓRICO DA EVOLUÇÃO DE COBERTURA\n\n- O painel Decisão > Auditoria > Evolução de Cobertura deixa de depender exclusivamente de meta_audit_json criado nas versões mais recentes.\n- Rodadas antigas passam a entrar em Cobertura do Núcleo e Taxa 2+ quando já possuíam Top 5 do GP-H Meta congelado antes do sorteio e o resultado posterior está registrado.\n- Esse bootstrap é somente de auditoria: o Meta antigo NÃO é recalculado com dados futuros, nenhum ranking histórico é recriado e nenhum peso/confiança/decisão é alterado.\n- Melhor Terno e Conversão 3→3 continuam exigindo Ternos Meta realmente registrados para aquela mesma base prospectiva; Ternos ausentes não são reconstruídos retrospectivamente.\n- O objetivo é iniciar as janelas 20/30/60 com o máximo de histórico prospectivo legítimo já existente, reduzindo o tempo de formação do diagnóstico sem contaminar a avaliação.\n\n'''
doc = doc.replace(anchor, entry + anchor, 1)
DOC.write_text(doc, encoding='utf-8')
print('PATCH v0.47.7 aplicado')
