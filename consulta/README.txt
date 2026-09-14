GP-H CONSULTA HISTÓRICA v0.1.14
================================

Esta revisão mantém tudo o que já existia na v0.1.13 e acrescenta o atraso do bicho especificamente no 1º prêmio na tela Início.

- Atrasos atuais agora mostram quatro indicadores: Bicho 1º–5º, Cabeça 1º, Centena e Dezena.
- Bicho 1º–5º continua medindo a última aparição do animal em qualquer um dos cinco prêmios.
- Cabeça 1º mede quantas extrações se passaram desde a última vez em que o animal saiu especificamente no 1º prêmio.
- Uma aparição no 2º, 3º, 4º ou 5º prêmio não zera o atraso de Cabeça 1º.
- O cartão de Cabeça 1º preserva a consulta por Bicho e mostra a última ocorrência no tooltip.
- Mantém a opção lateral Jogos do dia, com todas as extrações de uma data em cartões separados.
- Navegação por dia anterior/próximo, botão Hoje, calendário e atualização de resultados na própria tela.
- Usa o mesmo banco compartilhado da Central em:
  %LOCALAPPDATA%\GP-H_Central_Historica\dados\gph_historico.db
- Executável próprio, sem necessidade de Python instalado.
- Build em modo windowed/no-console.
- Não altera métodos, apostas, Bilhetes ou Financeiro.

O código-fonte base da Consulta permanece armazenado comprimido, é verificado por SHA-256 e recebe o patch controlado da v0.1.14 antes da build.
