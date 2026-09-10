from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

SRC = Path('source/gph_central.py')
DOC = Path('source/DOCUMENTACAO_GP-H.txt')


def replace_function(source: str, name: str, block: str) -> str:
    tree = ast.parse(source)
    nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(nodes) != 1:
        raise AssertionError(f'{name}: esperado 1 método, encontrados {len(nodes)}')
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    start = sum(len(x) for x in lines[:node.lineno - 1])
    end = sum(len(x) for x in lines[:node.end_lineno])
    indent = ' ' * node.col_offset
    raw = textwrap.dedent(block).strip('\n')
    replacement = '\n'.join((indent + line if line else '') for line in raw.splitlines()) + '\n'
    return source[:start] + replacement + source[end:]


s = SRC.read_text(encoding='utf-8')

# Versão do programa.
m = re.search(r'^APP_VERSION\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', s, flags=re.M)
assert m, 'APP_VERSION não encontrado'
assert m.group(1) == '0.47.3', f'base inesperada: {m.group(1)}'
s = s[:m.start(1)] + '0.47.4' + s[m.end(1):]

# ---------------------------------------------------------------------------
# LEI DE GERAÇÃO GP-H
# O antigo gerador Meta 2:1 vira compatibilidade sobre uma camada universal.
# ---------------------------------------------------------------------------
s = replace_function(s, 'generate_centenas_meta_21', r'''
def generate_gph_law_numbers(
    self,
    groups: list[int],
    kind="Centena",
    total=20,
    previous_draw=None,
    scope="1º–5º",
    date_to=None,
):
    """Lei de Geração GP-H para Centena e Milhar.

    O método seletor entrega apenas o ranking dos bichos. Esta camada única
    transforma o ranking em números, independentemente de ele vir de Meta,
    Reset, Puxada, Similaridade, Seca ou de seletores futuros.

    Regras estruturais:
    - quantidade total distribuída por round-robin; sobras favorecem líderes;
    - aproximadamente 2/3 na dezena principal ativa e 1/3 na segunda ativa;
    - 4 números por bicho => 3+1; 5=>3+2; 6=>4+2; 7=>5+2;
      8=>5+3; 9=>6+3; 10=>7+3;
    - a máquina persistente de congelamento do 3+1 é reutilizada sem mudança:
      principal livre -> principal+segunda; congelada -> segunda+terceira;
    - dentro de cada dezena ativa usa os números historicamente mais fortes.
    """
    if kind not in ("Centena", "Milhar"):
        raise ValueError("A Lei de Geração GP-H numérica aceita Centena ou Milhar.")

    unique_groups = []
    for value in groups:
        g = int(value)
        if 1 <= g <= 25 and g not in unique_groups:
            unique_groups.append(g)
    if not unique_groups:
        raise ValueError("O método não forneceu bichos para a Lei de Geração GP-H.")

    total = max(1, int(total))
    if total < len(unique_groups):
        raise ValueError(
            f"Com {len(unique_groups)} bichos, informe pelo menos {len(unique_groups)} {kind.lower()}s "
            "para que cada bicho receba ao menos um número."
        )

    counts = self.distribute_game_counts(total, unique_groups, kind=kind)
    if sum(counts.values()) != total:
        raise ValueError("Não foi possível distribuir a quantidade pedida entre os bichos.")

    # Com exatamente duas dezenas ativas, cada dezena comporta 10 Centenas ou
    # 100 Milhares. 15/150 é o maior total por bicho que preserva 2:1 sem
    # repetir número ou abrir uma terceira dezena fora da lei.
    per_group_limit = 15 if kind == "Centena" else 150
    overloaded = [(g, qty) for g, qty in counts.items() if int(qty) > per_group_limit]
    if overloaded:
        worst = max(qty for _g, qty in overloaded)
        raise ValueError(
            f"A Lei GP-H 2/3 + 1/3 suporta até {per_group_limit} {kind.lower()}s por bicho; "
            f"a configuração atual chegaria a {worst}. Aumente a quantidade de bichos ou reduza os números."
        )

    if previous_draw is None:
        previous_draw = self.latest_operational_draw()
    if previous_draw is None:
        raise ValueError("Não há extração-base para aplicar o congelamento das dezenas.")

    rows = []
    animals = []
    for rank_group, g in enumerate(unique_groups, start=1):
        qty = int(counts[g])
        dez_rank = self.number_rankings_for_group(
            g, kind="Dezena", scope=scope, date_to=date_to
        )
        if len(dez_rank) < 3:
            raise ValueError(f"Ranking de dezenas insuficiente para o grupo {g:02d}.")

        principal, segunda, terceira = dez_rank[:3]
        freeze_state = self.centena_31_freeze_state(
            g, principal["numero"], previous_draw=previous_draw
        )
        frozen = bool(freeze_state.get("frozen"))
        if frozen:
            main_dez = segunda["numero"]
            extra_dez = terceira["numero"]
            main_name = "2/3 na 2ª dezena (principal congelada)"
            extra_name = "1/3 na 3ª dezena"
        else:
            main_dez = principal["numero"]
            extra_dez = segunda["numero"]
            main_name = "2/3 na principal"
            extra_name = "1/3 na 2ª dezena"

        # Mesmo arredondamento já validado no Meta: 3->2+1, 4->3+1,
        # 5->3+2, 6->4+2, 7->5+2, 8->5+3, 9->6+3, 10->7+3.
        main_count = (2 * qty + 1) // 3
        extra_count = qty - main_count

        number_rank = self.number_rankings_for_group(
            g, kind=kind, scope=scope, date_to=date_to
        )
        main_rank = [r for r in number_rank if str(r["numero"])[-2:] == str(main_dez).zfill(2)]
        extra_rank = [r for r in number_rank if str(r["numero"])[-2:] == str(extra_dez).zfill(2)]
        if len(main_rank) < main_count or len(extra_rank) < extra_count:
            raise ValueError(f"{kind}s insuficientes nas dezenas ativas do grupo {g:02d}.")

        animals.append({
            "grupo": g,
            "bicho": BICHOS[g],
            "rank_bicho": rank_group,
            "principal": principal["numero"],
            "segunda": segunda["numero"],
            "terceira": terceira["numero"],
            "principal_tied": principal["ocorrencias"] == segunda["ocorrencias"],
            "frozen": frozen,
            "freeze_trigger": freeze_state.get("trigger"),
            "freeze_released_by": freeze_state.get("released_by"),
            "freeze_rule": "persistente_ate_reaparicao_do_bicho",
            "main_dezena": main_dez,
            "extra_dezena": extra_dez,
            "main_count": main_count,
            "extra_count": extra_count,
            "total_count": qty,
        })

        for pos, num in enumerate(main_rank[:main_count], start=1):
            rows.append({
                "grupo": g, "bicho": BICHOS[g], "numero": num["numero"],
                "dezena_base": main_dez, "regra": main_name,
                "ocorrencias": num["ocorrencias"], "ultima": num["ultima"],
                "rank_no_bicho": pos, "rank_bicho": rank_group,
                "frozen": frozen, "principal": principal["numero"],
                "segunda": segunda["numero"], "terceira": terceira["numero"],
            })
        for pos, num in enumerate(extra_rank[:extra_count], start=1):
            rows.append({
                "grupo": g, "bicho": BICHOS[g], "numero": num["numero"],
                "dezena_base": extra_dez, "regra": extra_name,
                "ocorrencias": num["ocorrencias"], "ultima": num["ultima"],
                "rank_no_bicho": main_count + pos, "rank_bicho": rank_group,
                "frozen": frozen, "principal": principal["numero"],
                "segunda": segunda["numero"], "terceira": terceira["numero"],
            })

    return {
        "kind": kind,
        "strategy": "Lei de Geração GP-H",
        "scope": scope,
        "groups": unique_groups,
        "counts": counts,
        "requested_total": total,
        "generated_total": len(rows),
        "rows": rows,
        "animals": animals,
        "previous_draw": previous_draw,
        "freeze_rule": "mesma_maquina_persistente_do_3plus1",
        "distribution_rule": "aprox_2_tercos_mais_1_terco",
        "generation_law": "GP-H v1",
    }


def generate_centenas_meta_21(
    self,
    groups: list[int],
    total=20,
    previous_draw=None,
):
    """Compatibilidade: o antigo Meta 2:1 agora usa a Lei de Geração GP-H."""
    result = self.generate_gph_law_numbers(
        groups=groups,
        kind="Centena",
        total=total,
        previous_draw=previous_draw,
        scope="1º–5º",
    )
    result["strategy"] = "Meta • Lei de Geração GP-H"
    return result
''')

# A Seca preserva seu seletor 1º-prêmio, mas passa pela mesma lei numérica.
s = replace_function(s, 'generate_dry_day_numbers', r'''
def generate_dry_day_numbers(
    self,
    base_date,
    kind="Centena",
    total=2,
    top_animals=2,
    targets_per_source=3,
    min_support=3,
    count_repeats=True,
    previous_draw=None,
):
    """Seca do Dia: seletor próprio, geração numérica pela Lei GP-H."""
    if kind not in ("Centena", "Milhar"):
        raise ValueError("A Seca do Dia gera apenas Centena ou Milhar.")

    total = max(1, int(total))
    top_animals = max(1, min(10, int(top_animals), total))
    method = self.method_dry_day_first_prize(
        base_date=base_date,
        top_n=top_animals,
        targets_per_source=targets_per_source,
        min_support=min_support,
        count_repeats=count_repeats,
    )
    groups = [int(r["grupo"]) for r in method["selected"]]
    if not groups:
        raise ValueError("Nenhum bicho alcançou o suporte mínimo da Seca do Dia.")

    generation = self.generate_gph_law_numbers(
        groups=groups,
        kind=kind,
        total=total,
        previous_draw=previous_draw,
        scope="1º",
        date_to=base_date,
    )
    generation["strategy"] = "Seca do Dia 1º • Lei GP-H"
    generation["base_date"] = str(base_date)
    generation["method"] = method
    generation["selector_scope"] = "1º"
    return generation
''')

# ---------------------------------------------------------------------------
# TELA JOGAR: a quantidade de bichos deixa de ser exclusiva do Meta.
# Mantemos o nome interno play_meta_animals para compatibilidade de UI.
# ---------------------------------------------------------------------------
s = s.replace(
    'self.play_method = tk.StringVar(value="Oficial • Reset + 3+1")',
    'self.play_method = tk.StringVar(value="Oficial • Reset + Lei GP-H")',
    1,
)
s = s.replace(
    'text="Pode jogar desde o primeiro snapshot auditado. Até 20, fica marcado como META EM FORMAÇÃO; a arquitetura do cérebro e o corte anti-lookahead permanecem os mesmos."',
    'text="O método escolhe e ordena os bichos; a Lei GP-H transforma esse ranking em jogo. Em Centena/Milhar usa 2/3 + 1/3 nas dezenas ativas e o mesmo congelamento persistente do 3+1."',
    1,
)
s = s.replace('text="Bichos do ranking Meta"', 'text="Bichos do ranking"', 1)
s = s.replace(
    'text="Escolha quantos bichos do topo do Meta entrarão no jogo."',
    'text="Escolha quantos bichos do topo do método entrarão no jogo."',
    1,
)

# Ajustes apenas dentro de play_controls_changed.
tree = ast.parse(s)
node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'play_controls_changed')
lines = s.splitlines(keepends=True)
start = sum(len(x) for x in lines[:node.lineno - 1]); end = sum(len(x) for x in lines[:node.end_lineno])
fn = s[start:end]

old_centena = '''        elif kind == "Centena":\n            methods = [\n                "Oficial • Reset + 3+1",\n                "★ META • GP-H Meta v0.1",\n                "Oficial • Reset + Histórica",\n                "Especial • Seca do Dia 1º",\n                "Experimental • Puxada Combinada",\n                "Experimental • Similaridade do Dia",\n                "Manual",\n            ]'''
new_centena = '''        elif kind == "Centena":\n            methods = [\n                "Oficial • Reset + Lei GP-H",\n                "★ META • GP-H Meta v0.1",\n                "Especial • Seca do Dia 1º",\n                "Experimental • Puxada Combinada",\n                "Experimental • Similaridade do Dia",\n                "Manual",\n            ]'''
assert old_centena in fn, 'bloco Centena não encontrado'
fn = fn.replace(old_centena, new_centena, 1)

old_milhar = '''        elif kind == "Milhar":\n            methods = [\n                "Oficial • Reset + Histórica",\n                "★ META • GP-H Meta v0.1",\n                "Especial • Seca do Dia 1º",\n                "Experimental • Puxada Combinada",\n                "Experimental • Similaridade do Dia",\n                "Manual",\n            ]'''
new_milhar = '''        elif kind == "Milhar":\n            methods = [\n                "Oficial • Reset + Lei GP-H",\n                "★ META • GP-H Meta v0.1",\n                "Especial • Seca do Dia 1º",\n                "Experimental • Puxada Combinada",\n                "Experimental • Similaridade do Dia",\n                "Manual",\n            ]'''
assert old_milhar in fn, 'bloco Milhar não encontrado'
fn = fn.replace(old_milhar, new_milhar, 1)

old_lock = '''            if kind == "Centena" and method == "Oficial • Reset + 3+1":\n                self.play_total.set("20")\n                self.play_total_spin.configure(state="disabled")\n            else:\n                self.play_total_spin.configure(state="normal")'''
assert old_lock in fn, 'trava 20 do 3+1 não encontrada'
fn = fn.replace(old_lock, '            self.play_total_spin.configure(state="normal")', 1)

old_meta_controls = '''        is_meta = method.startswith("★ META")\n        if is_meta:\n            self.play_meta_card.pack(fill="x", pady=(0, 6), before=self.play_stake_card)\n            if kind == "Fechamento de Grupo":\n                self.play_meta_animals_label.grid_remove()\n                self.play_meta_animals_spin.grid_remove()\n                self.play_meta_status.configure(\n                    text="No Fechamento, a quantidade de bichos é definida no cartão Fechamento configurável abaixo."\n                )\n            else:\n                self.play_meta_animals_label.grid()\n                self.play_meta_animals_spin.grid()\n                self.play_meta_status.configure(\n                    text="Escolha quantos bichos do topo do Meta entrarão no jogo. Sobras de quantidade favorecem os primeiros do ranking."\n                )\n        else:\n            self.play_meta_card.pack_forget()'''
new_meta_controls = '''        uses_law_controls = method != "Manual" and kind != "Fechamento de Grupo"\n        if uses_law_controls:\n            self.play_meta_card.pack(fill="x", pady=(0, 6), before=self.play_stake_card)\n            self.play_meta_animals_label.grid()\n            self.play_meta_animals_spin.grid()\n            if "Similaridade" in method:\n                law_status = "Bichos do topo dos até 5 slots da Similaridade; repetições podem reduzir os bichos únicos disponíveis."\n            elif method.startswith("Especial"):\n                law_status = "Bichos mais fortes do seletor Seca. A geração numérica segue a Lei GP-H preservando o histórico de 1º prêmio."\n            else:\n                law_status = "Escolha quantos bichos do topo do método entrarão no jogo. Sobras favorecem os primeiros do ranking."\n            self.play_meta_status.configure(text=law_status)\n        else:\n            self.play_meta_card.pack_forget()'''
assert old_meta_controls in fn, 'controles exclusivos do Meta não encontrados'
fn = fn.replace(old_meta_controls, new_meta_controls, 1)

s = s[:start] + fn + s[end:]

# Ajustes dentro de play_generate.
tree = ast.parse(s)
node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'play_generate')
lines = s.splitlines(keepends=True)
start = sum(len(x) for x in lines[:node.lineno - 1]); end = sum(len(x) for x in lines[:node.end_lineno])
fn = s[start:end]

anchor = '            total = max(1, int(self.play_total.get()))\n'
assert anchor in fn
fn = fn.replace(anchor, anchor + '''            try:\n                requested_animals = max(1, min(25, int(str(self.play_meta_animals.get()).strip() or "5")))\n            except Exception:\n                raise ValueError("Informe uma quantidade válida de bichos do ranking.")\n''', 1)

# Seca usa a quantidade escolhida e a mesma máquina de congelamento.
fn = fn.replace('                    top_animals=min(5, max(2, total)),', '                    top_animals=requested_animals,', 1)
needle = '                    top_animals=requested_animals,\n                )'
assert needle in fn, 'chamada Seca não localizada após ajuste'
fn = fn.replace(needle, '                    top_animals=requested_animals,\n                    previous_draw=latest,\n                )', 1)

# Meta: quantidade universal no modo comum; fechamento continua no cartão próprio.
old = '''                else:\n                    try:\n                        top_animals = max(1, min(25, int(self.play_meta_animals.get())))\n                    except Exception:\n                        raise ValueError("Informe uma quantidade válida de bichos do Meta.")'''
assert old in fn, 'quantidade Meta não localizada'
fn = fn.replace(old, '''                else:\n                    top_animals = requested_animals''', 1)

# Os outros seletores recebem a mesma quantidade solicitada sem mudar sua fórmula.
fn = fn.replace('latest["data"], latest["sorteio"], latest["hora"], top_n=5\n                    )',
                'latest["data"], latest["sorteio"], latest["hora"], top_n=requested_animals\n                    )', 1)
fn = fn.replace('                    top_n=5,\n                )', '                    top_n=requested_animals,\n                )', 1)

sim_anchor = '''                    selector = "Sombra Similaridade do Dia"'''
assert sim_anchor in fn
fn = fn.replace(sim_anchor, '''                    groups = groups[:requested_animals]\n                    selector = "Sombra Similaridade do Dia"''', 1)

# Todo Centena/Milhar automático (exceto Seca, que retorna antes) usa a Lei GP-H.
old_numeric = '''            elif kind == "Centena" and method.startswith("★ META"):\n                generation = self.db.generate_centenas_meta_21(\n                    groups=groups,\n                    total=total,\n                    previous_draw=latest,\n                )\n                generation["selector"] = selector\n                generation["strategy"] = "Meta 2:1"\n                generation["meta_ranking"] = copy.deepcopy((meta_payload or {}).get("ranking") or [])\n                generation["meta_training_snapshots"] = int((meta_payload or {}).get("training_snapshots") or 0)\n\n            elif (\n                kind == "Centena"\n                and method == "Oficial • Reset + 3+1"\n            ):\n                generation = self.db.generate_centenas_3plus1(\n                    groups=groups[:5],\n                    previous_draw=latest,\n                )\n                generation["selector"] = selector\n                generation["strategy"] = "Oficial 3+1"\n\n            else:\n                generation = self.db.generate_historical_numbers('''
new_numeric = '''            elif kind in ("Centena", "Milhar"):\n                generation = self.db.generate_gph_law_numbers(\n                    groups=groups,\n                    kind=kind,\n                    total=total,\n                    previous_draw=latest,\n                    scope="1º–5º",\n                )\n                generation["selector"] = selector\n                generation["strategy"] = f"{selector} • Lei GP-H"\n\n            else:\n                generation = self.db.generate_historical_numbers('''
assert old_numeric in fn, 'bloco numérico antigo não encontrado'
fn = fn.replace(old_numeric, new_numeric, 1)

s = s[:start] + fn + s[end:]

# Ajuda textual do Reset deixa claro que o seletor e o gerador são camadas distintas.
s = s.replace(
    'help_text = "Reset é o seletor oficial. Métodos oficiais geram apenas para a próxima rodada operacional."',
    'help_text = "Reset é o seletor oficial; a Lei de Geração GP-H é a camada comum que transforma o ranking em jogo."',
    1,
)

SRC.write_text(s, encoding='utf-8', newline='\n')

# Documentação: a conclusão da Tabela 1 será acrescentada depois do walk-forward.
d = DOC.read_text(encoding='utf-8')
entry = '''REVISÃO v0.47.4 — LEI DE GERAÇÃO GP-H UNIVERSAL\n\n- Cria uma camada única entre seleção de bichos e montagem do jogo: o método escolhe/rankeia; a Lei GP-H gera.\n- Centena e Milhar automáticas passam a usar a mesma distribuição: quantidade livre de bichos, quantidade total dividida de forma equilibrada e sobras priorizando os líderes.\n- Dentro de cada bicho, aproximadamente 2/3 dos números usam a dezena principal ativa e 1/3 a segunda ativa. O caso de 4 números continua sendo 3+1; 5=3+2, 6=4+2, 7=5+2, 8=5+3, 9=6+3 e 10=7+3.\n- A máquina persistente de congelamento do antigo 3+1 é reutilizada sem alteração: principal livre usa principal+segunda; congelada usa segunda+terceira até a reaparição do mesmo bicho.\n- Reset, Meta, Puxada Combinada, Similaridade e Seca do Dia passam pela mesma camada de geração quando a modalidade é Centena/Milhar; seletores futuros devem entregar apenas o ranking para herdar a lei.\n- A quantidade de bichos deixa de ser controle exclusivo do Meta e passa a ser um controle da Lei GP-H para os métodos automáticos.\n- Fechamentos de Grupo preservam o gerador comum concentrado/equilibrado validado na v0.47.3, evitando dependência total do líder quando existe alternativa.\n- O cérebro dos seletores não é recalibrado por esta mudança; a alteração é de geração operacional.\n\n'''
if not d.startswith('REVISÃO v0.47.4'):
    d = entry + d
DOC.write_text(d, encoding='utf-8', newline='\n')
