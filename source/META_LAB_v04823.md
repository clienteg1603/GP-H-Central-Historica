# GP-H Meta Lab — v0.48.23

## Objetivo
Investigar a fronteira do Top 5 do GP-H Meta sem alterar o cérebro oficial.

## Protocolo congelado
- As primeiras 21 rodadas válidas permanecem como baseline diagnóstico.
- A partir da 22ª rodada, as variantes são avaliadas prospectivamente.
- Nenhuma variante gera aposta, muda pesos, scores, confiança ou o Top 5 oficial.
- Nenhuma variante pode ser promovida automaticamente.
- O primeiro checkpoint forte permanece em 30 rodadas totais.

## Variantes
1. A · Consenso protegido — no máximo uma troca: candidato em rank até 10 com 2+ sinais pode substituir um bicho de fronteira do Top 5 com no máximo um sinal.
2. B · Fronteira 4–8 — preserva os ranks 1–3 e reordena apenas os ranks 4–8 por convergência entre métodos.
3. C · Consenso 3–10 — preserva os ranks 1–2 e escolhe as três vagas restantes entre os ranks 3–10 por convergência.

Todas as escolhas usam somente informações já congeladas antes do resultado. O resultado real é usado somente depois, para auditoria de desempenho.
