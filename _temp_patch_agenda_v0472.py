from pathlib import Path
import ast

SRC=Path('source/gph_central.py')
DOC=Path('source/DOCUMENTACAO_GP-H.txt')
s=SRC.read_text(encoding='utf-8')

assert 'APP_VERSION = "0.47.1"' in s, 'base esperada v0.47.1 não encontrada'
s=s.replace('APP_VERSION = "0.47.1"','APP_VERSION = "0.47.2"',1)

def replace_method(source, method_name, new_text):
    tree=ast.parse(source)
    matches=[]
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name==method_name:
            matches.append(node)
    if len(matches)!=1:
        raise AssertionError(f'{method_name}: esperado 1 método, achei {len(matches)}')
    node=matches[0]
    lines=source.splitlines(keepends=True)
    start=node.lineno-1
    end=node.end_lineno
    # preserva a indentação original do def
    indent=lines[start][:len(lines[start])-len(lines[start].lstrip())]
    formatted='\n'.join((indent+line if line else '') for line in new_text.split('\n'))+'\n'
    return ''.join(lines[:start])+formatted+''.join(lines[end:])

s=replace_method(s,'_is_operational_draw','''def _is_operational_draw(self, draw):
    weekday = datetime.strptime(draw["data"], "%Y-%m-%d").weekday()
    name = draw["sorteio"]

    # v0.47.2 — a grade operacional depende do dia da semana.
    # Domingo começa na Federal 11h; quarta troca a PTN 18h pela Federal 20h.
    if weekday == 6:  # domingo
        return name in ("FEDERAL", "PT", "PTV")

    if weekday == 5:  # sábado
        return name in ("PPT", "PTM", "PT", "PTV", "CORUJA")

    if weekday == 2:  # quarta-feira
        return name in ("PPT", "PTM", "PT", "PTV", "FEDERAL", "CORUJA")

    return name in ("PPT", "PTM", "PT", "PTV", "PTN", "CORUJA")''')

s=replace_method(s,'_operational_schedule_for_date','''def _operational_schedule_for_date(self, iso_date):
    weekday = datetime.strptime(iso_date, "%Y-%m-%d").weekday()

    if weekday == 6:  # domingo
        return [
            ("FEDERAL", "11:00"),
            ("PT", "14:00"),
            ("PTV", "16:00"),
        ]

    if weekday == 5:  # sábado
        return [
            ("PPT", "09:00"),
            ("PTM", "11:00"),
            ("PT", "14:00"),
            ("PTV", "16:00"),
            ("CORUJA", "21:00"),
        ]

    if weekday == 2:  # quarta-feira
        return [
            ("PPT", "09:00"),
            ("PTM", "11:00"),
            ("PT", "14:00"),
            ("PTV", "16:00"),
            ("FEDERAL", "20:00"),
            ("CORUJA", "21:00"),
        ]

    return [
        ("PPT", "09:00"),
        ("PTM", "11:00"),
        ("PT", "14:00"),
        ("PTV", "16:00"),
        ("PTN", "18:00"),
        ("CORUJA", "21:00"),
    ]''')

s=replace_method(s,'_reset_expected_target','''def _reset_expected_target(self, source_draw):
    day = datetime.strptime(source_draw["data"], "%Y-%m-%d")
    source_sort = str(source_draw.get("sorteio") or "")
    source_hour = str(source_draw.get("hora") or "")

    # Uma única agenda passa a governar Reset, próxima rodada e diagnóstico
    # de lacunas. Isso evita divergência entre quarta, sábado e domingo.
    sequence = self._operational_schedule_for_date(source_draw["data"])

    source_index = next(
        (
            i for i, (name, hour) in enumerate(sequence)
            if name == source_sort and (not source_hour or hour == source_hour)
        ),
        None,
    )
    if source_index is None:
        # Compatibilidade com bases antigas em que a hora possa ter sido
        # armazenada com pequena diferença: tenta identificar pelo sorteio.
        source_index = next(
            (i for i, (name, _hour) in enumerate(sequence) if name == source_sort),
            None,
        )

    if source_index is not None and source_index + 1 < len(sequence):
        next_sort, next_hour = sequence[source_index + 1]
        return {
            "data": source_draw["data"],
            "sorteio": next_sort,
            "hora": next_hour,
            "derived": True,
        }

    # Se a fonte não pertence à grade daquele dia (registro legado) ou já é
    # a última extração, avança para a primeira rodada operacional do dia seguinte.
    next_day = day + timedelta(days=1)
    for _ in range(8):
        next_date = next_day.strftime("%Y-%m-%d")
        next_sequence = self._operational_schedule_for_date(next_date)
        if next_sequence:
            next_sort, next_hour = next_sequence[0]
            return {
                "data": next_date,
                "sorteio": next_sort,
                "hora": next_hour,
                "derived": True,
            }
        next_day += timedelta(days=1)

    return None''')

# Atualiza a explicação visual do Reset para o novo salto real de domingo.
s=s.replace(
    'no salto sábado Coruja → domingo PT esse peso de contexto é desligado.',
    'no salto sábado Coruja → domingo Federal esse peso de contexto é desligado.',
)

SRC.write_text(s,encoding='utf-8',newline='\n')

d=DOC.read_text(encoding='utf-8')
entry='''REVISÃO v0.47.2 — AGENDA SEMANAL / PRÓXIMA RODADA\n\n- A próxima rodada deixou de usar uma sequência única de segunda a sexta e agora respeita a grade operacional por dia da semana.\n- Quarta-feira: PPT 09h → PTM 11h → PT 14h → PTV 16h → FEDERAL 20h → CORUJA 21h; não existe PTN 18h na grade operacional de quarta.\n- Domingo: FEDERAL 11h → PT 14h → PTV 16h.\n- Sábado permanece PPT 09h → PTM 11h → PT 14h → PTV 16h → CORUJA 21h, sem PTN 18h.\n- Segunda, terça, quinta e sexta permanecem PPT 09h → PTM 11h → PT 14h → PTV 16h → PTN 18h → CORUJA 21h.\n- A mesma agenda é usada para próxima rodada, validação operacional e detecção de lacunas, evitando divergências entre telas.\n- Nenhuma fórmula de Meta, Reset, Puxada, Similaridade, Histórico Concentrado, 3+1 ou Decisão foi recalibrada; a mudança é exclusivamente de calendário/encadeamento operacional.\n\n'''
if not d.startswith('REVISÃO v0.47.2'):
    d=entry+d
DOC.write_text(d,encoding='utf-8',newline='\n')
