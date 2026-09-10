from __future__ import annotations

import ast
from pathlib import Path

SRC=Path('source/gph_central.py')
DOC=Path('source/DOCUMENTACAO_GP-H.txt')
s=SRC.read_text(encoding='utf-8')

# A versão do aplicativo já foi elevada pela Lei GP-H nesta mesma release.
assert 'APP_VERSION = "0.47.4"' in s

# Tabela 1 / Puxada Antiga: sinal admitido somente após o walk-forward pré-declarado.
TABLE_BLOCK='''META_TABLE1_PULLS = {\n    1: (25, 2, 13, 19, 20),\n    2: (10, 1, 13, 19, 20),\n    3: (11, 12, 21, 24, 10, 9),\n    4: (6, 12, 14, 16, 5, 13),\n    5: (13, 14, 8, 17, 18, 19),\n    6: (7, 17, 12, 21, 22, 23),\n    7: (6, 10, 25),\n    8: (5, 12, 23),\n    9: (15, 18, 3, 14),\n    10: (7, 2, 3),\n    11: (3, 6, 21),\n    12: (6, 23, 22, 16, 3),\n    13: (5, 1, 2, 19, 20),\n    14: (5, 16, 22, 9),\n    15: (9, 18, 4, 17),\n    16: (12, 14, 22, 23),\n    17: (5, 6, 20, 15),\n    18: (9, 20, 15, 5),\n    19: (1, 2, 13, 20),\n    20: (1, 2, 13, 19, 24),\n    21: (25, 3, 6),\n    22: (14, 16, 6),\n    23: (16, 12, 8, 6),\n    24: (20, 3, 6),\n    25: (21, 1, 7),\n}\n\n'''
if 'META_TABLE1_PULLS = {' not in s:
    anchor='class Database:'
    assert anchor in s
    s=s.replace(anchor,TABLE_BLOCK+anchor,1)

# Mantém as 20 características anteriores byte-a-byte no início do vetor e
# acrescenta somente a 21ª: força normalizada das puxadas da Tabela 1 a partir
# dos cinco grupos da extração-base. Repetições da base contam como no estudo.
old_tail='''        count=base_groups.count(group)\n        features += [float(count>0), min(1.0,max(0,count-1)/2.0)]\n        return [float(v) for v in features]'''
new_tail='''        count=base_groups.count(group)\n        features += [float(count>0), min(1.0,max(0,count-1)/2.0)]\n\n        table1_votes = sum(\n            1 for source_group in base_groups\n            if group in META_TABLE1_PULLS.get(int(source_group), ())\n        )\n        table1_strength = float(table1_votes) / float(max(1, len(base_groups)))\n        features += [table1_strength]\n        return [float(v) for v in features]'''
assert old_tail in s, 'cauda das 20 características Meta não encontrada'
s=s.replace(old_tail,new_tail,1)

# A arquitetura muda de 20 para 21 características; o novo cérebro passa a v0.2.
# Os registros históricos v0.41/v0.42 no changelog embutido permanecem v0.1.
lines=s.splitlines()
for i,line in enumerate(lines):
    if '# GP-H META v0.1 — v0.41.0' in line:
        lines[i]=line.replace('# GP-H META v0.1 — v0.41.0', '# GP-H META v0.2 — v0.47.4 (Tabela 1 admitida como 21ª característica)')
        continue
    if '• v0.42.0 —' in line or '• v0.41.0 —' in line or '# v0.41.0 — GP-H Meta v0.1 em SOMBRA' in line:
        continue
    lines[i]=line.replace('GP-H Meta v0.1','GP-H Meta v0.2').replace('GP-H META v0.1','GP-H META v0.2')
s='\n'.join(lines)+'\n'

# Identificador interno do modelo: snapshots novos distinguem claramente 20f de 21f.
count=s.count('META_LOGIT_NATIVE_V1')
assert count >= 5, f'quantidade inesperada de model_version V1: {count}'
s=s.replace('META_LOGIT_NATIVE_V1','META_LOGIT_NATIVE_V2_TABLE1')

# Texto operacional explicita a nova característica; não promete ganho futuro.
s=s.replace(
    'GP-H Meta v0.2 usa o ranking aprendido com snapshots auditados. ',
    'GP-H Meta v0.2 usa 21 características; a Tabela 1 entrou como sinal adicional após passar no walk-forward de admissão. ',
    1,
)

SRC.write_text(s,encoding='utf-8',newline='\n')

# Registra a decisão científica na documentação consolidada.
d=DOC.read_text(encoding='utf-8')
marker='- O cérebro dos seletores não é recalibrado por esta mudança; a alteração é de geração operacional.\n'
assert marker in d
admission='''- Tabela 1 / Puxada Antiga: o teste de admissão foi definido antes do resultado e comparou o Meta de 20 características com um candidato de 21 características em 180 rodadas walk-forward, sem lookahead.\n- Resultado do teste: Meta 20f = 155 acertos de bicho no Top 5; Meta 21f + Tabela 1 = 165, ganho líquido +10. No confronto por rodada, o candidato venceu 50, perdeu 42 e empatou 88.\n- Nas três janelas temporais contíguas: 47→52 (+5), 56→51 (-5), 52→62 (+10). Duas das três janelas melhoraram.\n- Como os três critérios pré-declarados foram cumpridos — ganho líquido positivo, melhora em pelo menos 2/3 janelas e mais vitórias que derrotas — a Tabela 1 foi ADMITIDA como 21ª característica do GP-H Meta v0.2.\n- A 21ª característica usa somente a extração-base já conhecida: cada bicho da base vota nos grupos listados na Tabela 1, repetição conta novamente e a força é normalizada pela quantidade de prêmios da base. O resultado-alvo nunca entra no cálculo da previsão.\n- Reset, Puxada, Similaridade, Histórico Concentrado e Decisão permanecem com seus cérebros inalterados; somente o Meta muda de 20 para 21 características por autorização condicionada ao teste.\n'''
d=d.replace(marker,marker+admission,1)
DOC.write_text(d,encoding='utf-8',newline='\n')
