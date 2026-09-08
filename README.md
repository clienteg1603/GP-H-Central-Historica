# GP-H Central Histórica

Repositório oficial de publicação das atualizações da **GP-H Central Histórica**.

## Primeira publicação de teste

1. Envie para a raiz deste repositório o arquivo:
   `GP-H_Central_Historica_v0.34.1_Teste_GitHub.zip`
2. Abra a aba **Actions**.
3. Abra **Publicar atualização GP-H**.
4. Clique em **Run workflow / Executar fluxo de trabalho**.
5. Selecione o canal **test** e execute.

O GitHub irá automaticamente:

- extrair o pacote-fonte;
- validar o Python;
- gerar `GP-H Central Historica.exe` sem console;
- gerar `GP-H_Updater.exe` sem console;
- criar o pacote de atualização;
- calcular SHA-256;
- publicar a GitHub Release;
- atualizar `update_manifest.json` na raiz do repositório.

Depois da primeira execução bem-sucedida, a Central poderá consultar o manifesto público em:

`https://raw.githubusercontent.com/clienteg1603/GP-H-Central-Historica/main/update_manifest.json`

Os dados locais da Central permanecem fora da instalação, em `%LOCALAPPDATA%`, e não são substituídos pelo atualizador.
