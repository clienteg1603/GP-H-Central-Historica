# GP-H Central Histórica

Repositório oficial de desenvolvimento e publicação da **GP-H Central Histórica**.

## Estrutura atual

- `source/` — código-fonte oficial da Central, Updater, assets, documentação e arquivos de build.
- `.github/workflows/publicar-atualizacao.yml` — valida, compila e publica as novas versões.
- `update_manifest.json` — manifesto público consultado pela Central para encontrar atualizações.
- **GitHub Releases** — armazena os pacotes de atualização e os ZIPs Windows prontos.

## Fluxo de atualização

Não é mais necessário enviar manualmente um ZIP-fonte para o repositório.

Quando arquivos dentro de `source/` são alterados na branch `main`, o GitHub executa automaticamente o fluxo de publicação no canal **Teste**. O processo:

1. valida o código Python;
2. gera `GP-H Central Historica.exe` sem console;
3. gera `GP-H_Updater.exe` sem console;
4. cria o pacote de atualização;
5. calcula o SHA-256;
6. publica ou atualiza a GitHub Release;
7. atualiza o canal **Teste** em `update_manifest.json`.

Depois que uma versão de teste for aprovada, o mesmo workflow pode ser executado manualmente escolhendo o canal **Estável**.

## Manifesto público

`https://raw.githubusercontent.com/clienteg1603/GP-H-Central-Historica/main/update_manifest.json`

Os dados locais da Central permanecem fora da instalação, em `%LOCALAPPDATA%`, e não são substituídos durante atualização ou rollback.
