GP-H CONSULTA HISTÓRICA v0.1.12
================================

Esta revisão mantém a lógica da v0.1.11 e adiciona a distribuição Windows compilada.

- Executável próprio, sem necessidade de Python instalado.
- Build em modo windowed/no-console.
- Continua lendo por padrão o banco compartilhado da Central em:
  %LOCALAPPDATA%\GP-H_Central_Historica\dados\gph_historico.db
- Continua podendo buscar resultados novos/corrigidos com backup antes da gravação.
- Não altera métodos, apostas, Bilhetes ou Financeiro.

O código-fonte da Consulta fica armazenado comprimido em gph_consulta.py.gz apenas para reduzir o tamanho no repositório. O workflow descompacta antes de validar e compilar.
