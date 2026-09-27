# Conversor SEI

Converte documentos `.docx`, `.odt`, `.pdf`, `.md` e `.txt` em HTML com os estilos do editor do
**SEI**. O texto colado no SEI mantém a numeração automática, as tabelas, as imagens e as
classes de parágrafo do padrão institucional.

**Use pelo navegador: [ramson.com.br/conversorsei](https://ramson.com.br/conversorsei/)**

- Não precisa instalar nada.
- O documento não sai do seu computador: a conversão roda no próprio navegador.
- Depois da primeira visita, a página funciona sem internet e pode ser instalada como aplicativo.

Confira sempre o resultado antes de salvar no SEI, principalmente imagens e tabelas.

## O que o conversor faz

- Aplica as classes de parágrafo do SEI, inclusive a numeração automática de itens, incisos e
  alíneas, sem repetir o número digitado no documento.
- Centraliza as tabelas e mantém a largura que elas têm no Word.
- Incorpora as imagens do Word no próprio HTML.
- Divide documentos grandes em partes, para evitar o defeito do SEI Pro que desfaz os estilos
  acima de 27 KB.
- Limpa os PDFs exportados pelo SEI (carimbos, assinaturas e rodapés). O PDF precisa ter texto
  selecionável; documento só digitalizado exige OCR antes.
- A pedido, omite o cabeçalho (título, número, processo), que o SEI já gera pelo modelo.
- Lista o que precisa de conferência manual, como notas de rodapé e imagens do `.odt`.

Para escolher uma classe específica, use no Word ou no LibreOffice um estilo com o nome exato
da classe do SEI (por exemplo, `Texto_Ementa` ou `Citação`).

## Como colar no SEI

1. Converta o documento e clique em **Copiar para o SEI** (na linha de comando, abra o arquivo
   `*_SEI.html` no navegador e copie tudo com `Ctrl+A` e `Ctrl+C`).
2. No editor do SEI, clique no corpo do documento e cole com `Ctrl+V`.
3. Confira a numeração e as tabelas e salve.

Se o documento foi dividido em partes, cole uma de cada vez, na ordem.

## Linha de comando

Requer Python 3.11 ou mais recente.

```bash
uv sync                                   # ou: pip install -e .

conversorsei documento.docx               # converte um arquivo
conversorsei pasta/ -o saida/ -r          # converte uma pasta e as subpastas
conversorsei                              # converte dados/entrada/ para dados/saida/
conversorsei -w                           # converte a cada arquivo salvo em dados/entrada/
conversorsei --help                       # todas as opções
```

Para testar, use o documento de exemplo:

```bash
conversorsei exemplos/nota_tecnica_exemplo.md -o dados/saida/
```

Na linha de comando, o PDF pode sair melhor que na web: quando o `pdftotext` está instalado, ele
é usado no lugar do `pypdf`.

## Para quem desenvolve

```bash
uv run pytest -q                          # testes
uv run ruff check . && uv run mypy        # lint e tipos
uv sync --group e2e && uv run playwright install chromium webkit
uv run pytest -m e2e                      # teste no navegador (Chromium e WebKit)
```

A página publicada fica em `docs/` e roda o mesmo pacote Python no navegador, pelo Pyodide.

- Mudou algo em `conversao_sei/`, `docs/app.js` ou `docs/estilos.css`: rode
  `uv run python scripts/bundle_web.py` e inclua o resultado no commit.
- Usou uma classe nova do Tailwind: recompile o CSS e rode o `bundle_web.py` de novo.

  ```bash
  npx tailwindcss@3.4.16 -c tailwind.config.js -i tailwind-input.css -o docs/estilos.css --minify
  ```

O GitHub Actions roda todas as verificações e só publica a página se elas passarem.

## Privacidade, problemas e apoio

- A página conta visitas e conversões pelo GoatCounter, sem cookies. De cada conversão vão só a
  extensão do arquivo e o resultado, nunca o nome ou o conteúdo do documento.
- Para relatar um problema, use o link **Relatar problema** da página. Ele abre um e-mail com a
  versão e o navegador preenchidos, sem o documento e sem o nome do arquivo.
- O conversor é gratuito. Para apoiar o projeto, use o link **Apoie este projeto**, no rodapé
  da página (Pix).

## Licença

MIT. Veja [LICENSE](LICENSE).
