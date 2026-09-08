from pathlib import Path

src = Path("source/gph_central.py")
text = src.read_text(encoding="utf-8")

if 'APP_VERSION = "0.36.3"' in text:
    raise SystemExit("v0.36.3 ja aplicada")
if 'APP_VERSION = "0.36.2"' not in text:
    raise SystemExit("Base esperada v0.36.2 nao encontrada")

text = text.replace("GP-H Central Histórica v0.36.2", "GP-H Central Histórica v0.36.3", 1)
text = text.replace('APP_VERSION = "0.36.2"', 'APP_VERSION = "0.36.3"', 1)

# Guia do método oficial.
text = text.replace(
    '"base": "O Reset escolhe exatamente 5 bichos. O sorteio imediatamente anterior é usado para a regra de congelamento da dezena principal.",',
    '"base": "O Reset escolhe exatamente 5 bichos. O congelamento da dezena principal é um estado persistente do bicho, reconstruído até a extração-base sem olhar o futuro.",',
)
text = text.replace(
    '"does": "Para cada bicho: normalmente usa 3 Centenas da dezena principal + 1 da segunda. Se a principal apareceu no sorteio anterior, ela descansa uma rodada e passa a usar 3 da segunda + 1 da terceira.",',
    '"does": "Para cada bicho: normalmente usa 3 Centenas da dezena principal + 1 da segunda. Quando a principal aparece enquanto está livre, ela congela. Enquanto congelada, usa 3 da segunda + 1 da terceira e permanece assim até o mesmo bicho aparecer novamente; essa nova aparição descongela a principal.",',
)
text = text.replace(
    '"note": "A colocação do bilhete agora é livre; isso não muda silenciosamente a fórmula interna do 3+1.",',
    '"note": "Estado oficial: principal saiu → congela; congelada + mesmo bicho saiu novamente → descongela. A colocação do bilhete continua livre e não altera a fórmula interna.",',
)

marker = '''    def generate_centenas_3plus1(\n        self,\n        groups: list[int],\n        previous_draw=None,\n    ):\n'''
if marker not in text:
    raise SystemExit("generate_centenas_3plus1 nao encontrado")

helper = r'''    def centena_31_freeze_state(self, group: int, principal_dezena: str, previous_draw=None):
        """Reconstrói o estado oficial de congelamento do 3+1 até a extração-base.

        Máquina de estado por bicho/dezena principal:
        - livre + principal aparece -> congela;
        - congelada + o mesmo bicho aparece novamente -> descongela;
        - congelada + o bicho não aparece -> continua congelada.

        Cada extração conta como um único evento, mesmo que o bicho apareça mais
        de uma vez entre os cinco prêmios. Se o bicho reaparecer enquanto já
        estava congelado, a reaparição apenas libera o estado; mesmo que a
        principal esteja entre os prêmios dessa extração, ela não recongela no
        mesmo evento.
        """
        group = int(group)
        principal_dezena = str(principal_dezena).zfill(2)

        if previous_draw is None:
            previous_draw = self.latest_operational_draw()
        if previous_draw is None:
            raise ValueError("Não há extração-base para reconstruir o congelamento 3+1.")

        cutoff = (
            previous_draw.get("data"),
            previous_draw.get("sorteio"),
            previous_draw.get("hora"),
        )
        draws = self._draws_in_order()
        cutoff_idx = next(
            (
                i for i, draw in enumerate(draws)
                if (draw.get("data"), draw.get("sorteio"), draw.get("hora")) == cutoff
            ),
            None,
        )
        if cutoff_idx is None:
            raise ValueError("A extração-base não foi encontrada para reconstruir o congelamento 3+1.")

        frozen = False
        trigger = None
        released_by = None

        for draw in draws[:cutoff_idx + 1]:
            group_prizes = [
                p for p in draw.get("prizes", [])
                if int(p.get("grupo") or 0) == group
            ]
            if not group_prizes:
                continue

            event = {
                "data": draw.get("data"),
                "sorteio": draw.get("sorteio"),
                "hora": draw.get("hora"),
                "dezenas": [str(p.get("dezena") or "").zfill(2) for p in group_prizes],
            }

            if frozen:
                frozen = False
                released_by = event
                trigger = None
                continue

            if any(str(p.get("dezena") or "").zfill(2) == principal_dezena for p in group_prizes):
                frozen = True
                trigger = event
                released_by = None

        return {
            "grupo": group,
            "principal": principal_dezena,
            "frozen": frozen,
            "trigger": trigger,
            "released_by": released_by,
            "cutoff": {
                "data": cutoff[0],
                "sorteio": cutoff[1],
                "hora": cutoff[2],
            },
        }

'''
text = text.replace(marker, helper + marker, 1)

old_doc = '''        Para cada um dos 5 bichos:\n        - ordena as 4 dezenas pela frequência histórica 1º–5º;\n        - normal: 3 Centenas na dezena principal + 1 na segunda;\n        - se a dezena principal apareceu em qualquer prêmio do sorteio\n          imediatamente anterior, ela fica congelada por uma rodada:\n          3 Centenas na segunda + 1 na terceira;\n        - dentro da dezena escolhida, usa as Centenas historicamente mais fortes.\n'''
new_doc = '''        Para cada um dos 5 bichos:\n        - ordena as 4 dezenas pela frequência histórica 1º–5º;\n        - normal: 3 Centenas na dezena principal + 1 na segunda;\n        - quando a principal aparece enquanto está livre, ela congela;\n        - enquanto congelada: 3 Centenas na segunda + 1 na terceira;\n        - o congelamento persiste até o mesmo bicho aparecer novamente;\n        - essa nova aparição do bicho descongela a principal;\n        - dentro da dezena escolhida, usa as Centenas historicamente mais fortes.\n'''
if old_doc not in text:
    raise SystemExit("Docstring antiga do 3+1 nao encontrada")
text = text.replace(old_doc, new_doc, 1)

old_frozen = '            frozen = principal["numero"] in previous_dezenas\n\n            if frozen:\n'
new_frozen = '''            freeze_state = self.centena_31_freeze_state(\n                g,\n                principal["numero"],\n                previous_draw=previous_draw,\n            )\n            frozen = bool(freeze_state.get("frozen"))\n\n            if frozen:\n'''
if old_frozen not in text:
    raise SystemExit("Regra antiga de frozen nao encontrada")
text = text.replace(old_frozen, new_frozen, 1)

old_meta = '''                "principal_tied": principal_tied,\n                "frozen": frozen,\n                "main_dezena": main_dez,\n                "extra_dezena": extra_dez,\n'''
new_meta = '''                "principal_tied": principal_tied,\n                "frozen": frozen,\n                "freeze_trigger": freeze_state.get("trigger"),\n                "freeze_released_by": freeze_state.get("released_by"),\n                "freeze_rule": "persistente_ate_reaparicao_do_bicho",\n                "main_dezena": main_dez,\n                "extra_dezena": extra_dez,\n'''
if old_meta not in text:
    raise SystemExit("animal_meta do 3+1 nao encontrado")
text = text.replace(old_meta, new_meta, 1)

# Metadado das linhas para auditoria visual/técnica.
text = text.replace(
    '                    "frozen": frozen,\n                    "principal": principal["numero"],',
    '                    "frozen": frozen,\n                    "freeze_rule": "persistente_ate_reaparicao_do_bicho",\n                    "principal": principal["numero"],',
    2,
)

text = text.replace(
    '            "previous_dezenas": sorted(previous_dezenas),\n        }\n\n\n\n    def method_similarity_day(',
    '            "previous_dezenas": sorted(previous_dezenas),\n            "freeze_rule": "principal_sai_congela__mesmo_bicho_reaparece_descongela",\n        }\n\n\n\n    def method_similarity_day(',
    1,
)

src.write_text(text, encoding="utf-8")

# Documentação consolidada.
doc = Path("source/DOCUMENTACAO_GP-H.txt")
if doc.exists():
    d = doc.read_text(encoding="utf-8")
    revision = '''REVISÃO v0.36.3 — RESET + 3+1 / CONGELAMENTO PERSISTENTE\n- Regra oficial corrigida: a dezena principal não descansa apenas uma rodada; o congelamento passa a ser um estado persistente.\n- Estado livre + dezena principal aparece em qualquer prêmio da extração: congela.\n- Enquanto congelada, o gerador usa 3 Centenas da 2ª dezena mais forte + 1 da 3ª.\n- O congelamento permanece mesmo que passem outras extrações sem o bicho aparecer.\n- Quando o mesmo bicho aparece novamente em uma extração, a principal é descongelada, independentemente de qual das quatro dezenas do bicho saiu.\n- Se a principal reaparece enquanto já estava congelada, essa reaparição também descongela; não recongela no mesmo evento.\n- Quando livre, o gerador volta a 3 Centenas da principal + 1 da 2ª.\n- A reconstrução respeita a extração-base e não olha resultados posteriores, preservando o uso prospectivo/sombra.\n- Nenhum seletor de bicho ou outro método foi alterado.\n\n'''
    if not d.startswith("REVISÃO v0.36.3"):
        d = revision + d
    d = d.replace("VERSÃO ATUAL: v0.36.0", "VERSÃO ATUAL: v0.36.3", 1)
    doc.write_text(d, encoding="utf-8")

upd = Path("source/ATUALIZACOES_PROGRAMA_v0.35.txt")
if upd.exists():
    u = upd.read_text(encoding="utf-8")
    u = u.replace("GP-H CENTRAL HISTÓRICA v0.36.0", "GP-H CENTRAL HISTÓRICA v0.36.3", 1)
    note = '''\nNovidades v0.36.3:\n- Reset + 3+1 passa a usar congelamento persistente da dezena principal.\n- Principal sai livre: congela; enquanto congelada, 3 da segunda + 1 da terceira.\n- O mesmo bicho reaparece: descongela, mesmo que a principal seja a dezena que reapareceu.\n'''
    if "Novidades v0.36.3:" not in u:
        u += note
    upd.write_text(u, encoding="utf-8")

print("Patch v0.36.3 aplicado")
