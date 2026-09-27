# conversao-sei

Conversor de documentos Word (`.docx`), PDF (`.pdf`), LibreOffice (`.odt`), Markdown (`.md`) e texto (`.txt`) para o padrão institucional do editor do **SEI** (Sistema Eletrônico de Informações / CKEditor / SEI Pro). Confira o resultado antes de colar, especialmente imagens, tabelas e documentos com formatação complexa.

> **Versão web online (sem instalação, e o documento não sai do navegador)**:  
> Acesse: **[https://ramson.com.br/conversorsei/](https://ramson.com.br/conversorsei/)** (o endereço antigo, `/conversao_sei/`, redireciona para cá)
> *Arraste seus arquivos e converta direto pelo navegador. Todo o processamento ocorre localmente na sua máquina via WebAssembly (Pyodide): nenhum documento é enviado para a internet, o que atende à LGPD e ao sigilo.*
>
> Encontrou um problema? O link **Relatar problema** (no rodapé, no quadro de avisos e na mensagem de erro) abre o seu programa de e-mail com um modelo preenchido: versão da página, navegador, formato do arquivo e avisos da conversão. O documento e o nome do arquivo não vão no e-mail.
>
> O conversor é gratuito. Quem quiser apoiar o projeto encontra no rodapé o link **Apoie este projeto**, com o QR Code do Pix, o código copia e cola e a chave (conversorsei@gmail.com).
>
> A página conta visitas e conversões de forma anônima pelo GoatCounter, sem cookies. De cada conversão vão só a extensão do arquivo e o resultado (sucesso ou falha), nunca o nome nem o conteúdo do documento.
>
> A página é um **aplicativo instalável (PWA)**: o navegador oferece instalá-la como programa e, depois da primeira visita, ela **abre e converte sem internet**. Vários arquivos podem ser arrastados de uma vez, e o resultado sai num **ZIP único**, com uma pasta por documento de origem.

---

## O que esta ferramenta faz

Ao colar conteúdo no editor do SEI ou importá-lo via extensão SEI Pro, a formatação costuma quebrar caso não sejam utilizadas as classes CSS institucionais do órgão.

O **`conversao-sei`**:
1. Converte os formatos aceitos para **HTML com as classes de parágrafo do SEI**.
2. **Remove números digitados manualmente** em títulos e listas com contadores automáticos (`Item_Nivel1..4`, `Item_Inciso_Romano`, `Item_Alinea_Letra`), evitando números duplicados (`1. 1. ASSUNTO`).
3. Formata **tabelas** centralizadas (`align="center"`), com a largura que têm no Word em porcentagem da página (`width="80%"`, por exemplo), larguras percentuais nas colunas, cabeçalhos em cinza (`#e6e6e6`) e parágrafos `Tabela_Texto_*`.
4. **Embute imagens em Base64** no próprio HTML. No `.odt` e nas imagens indicadas no Markdown, a imagem não é incorporada, e a conversão avisa para inseri-la no SEI.
5. **Auto-divisão inteligente de partes**: divide documentos com corpo maior que ~22 KB em `documento_SEI_parte01.html`, `documento_SEI_parte02.html` etc., evitando o defeito do plugin SEI Pro que achata estilos acima de 27 KB.
6. **Limpeza de PDFs**: remove carimbos de autenticidade, assinaturas eletrônicas e o rodapé de página dos PDFs exportados pelo SEI. O PDF precisa ter camada de texto: documento apenas digitalizado exige OCR antes da conversão (a página web indica duas opções: uma online e outra local, para documentos restritos). A extração usa o `pdftotext` quando ele está instalado e o arquivo vem do disco; a partir de conteúdo em memória (a interface web e a função `converter_bytes`) o trabalho fica com o `pypdf`, que respeita menos o layout original. Para um mesmo PDF, a linha de comando pode produzir um texto melhor que a web.
7. **Gera todas as 34 classes do menu Estilo do SEI.** O caminho garantido é o nome do estilo: um estilo do Word ou do LibreOffice com o nome exato de uma classe do SEI (`Texto_Ementa`, `Citação`, `Texto_Mono_Espaçado` etc.) é usado sem alteração. Além disso, algumas marcas feitas de propósito escolhem a classe sozinhas:

   | Formatação no documento | Classe no SEI |
   |---|---|
   | Parágrafo inteiro riscado | `Tachado` |
   | Sombreamento cinza e negrito (com ou sem caixa alta) | `Texto_Fundo_Cinza_Negrito`, `Texto_Fundo_Cinza_Maiusculas_Negrito` |
   | Negrito com espaçamento entre letras | `Texto_Espaco_Duplo_Recuo_Primeira_Linha` |
   | Centralizado em caixa alta (com ou sem negrito) | `Texto_Centralizado_Maiusculas_Negrito`, `Texto_Centralizado_Maiusculas` |
   | Célula de tabela com fonte até 10 pt (centralizada) ou até 8 pt | `Tabela_Texto_10`, `Tabela_Texto_8` |
   | Estilo "Quote" ou "Citação" do Word | `Citação` |

   Recuo, fonte e espaçamento não escolhem classe: uma ementa recuada, uma citação em fonte menor ou um trecho em Courier saem como texto comum, a menos que usem o estilo com o nome da classe. Regras desse tipo erravam em documentos comuns (assinatura recuada virava ementa, documento todo em Courier virava bloco de código). Parágrafo que começa com número de item (`1. ASSUNTO`) segue a numeração do SEI, inclusive quando está todo riscado.

   No Markdown (`.md`), a classe vem da marcação:

   | Markdown | Classe no SEI |
   |---|---|
   | `# Título` (sem número) | `Texto_Centralizado_Maiusculas_Negrito` |
   | `> texto` (um ou mais níveis) | `Citação` |
   | bloco entre ` ``` ` (com ou sem linguagem: ` ``` python`) | `Texto_Mono_Espaçado`, com o conteúdo literal; cerca sem fechamento fica como texto |
   | `~~linha inteira~~` | `Tachado` (um trecho riscado vira `<s>`; item numerado riscado continua item) |
   | `<p class="Texto_Ementa">texto</p>` | a classe indicada, qualquer uma das 34 (outro nome é ignorado) |

   No `.txt`, que não é Markdown, `>`, ` ``` ` e `~~` ficam como texto.
8. **Omite o cabeçalho, a pedido.** O SEI gera título, número e dados do processo pelo modelo do documento. Com o botão "Omitir cabeçalho" na web (ou `--sem-cabecalho` na CLI), o HTML começa no item 1 (`1. ASSUNTO`, ou o primeiro parágrafo numerado). A conversão sempre mostra o que vem antes do item 1, para quem converte decidir: na web, em "Revisar ajustes do documento", onde "Restaurar cabeçalho" desfaz a escolha.
9. **Avisa o que não foi convertido**: notas de rodapé e caixas de texto do Word, imagens do ODT e do Markdown, células mescladas entre linhas no ODT e caracteres ilegíveis no `.txt` aparecem como "Pontos a conferir antes de colar".

---

## Instalação e requisitos

Requer Python >= 3.11.

```bash
# Com uv (recomendado)
uv sync

# Ou com pip
pip install -e .
```

---

## Estrutura de pastas recomendada

Para manter tudo organizado sem poluir a raiz do projeto, utilize a estrutura padrão de pastas:

```
conversao_SEI/
├── dados/
│   ├── entrada/                      # Coloque seus arquivos e subpastas aqui
│   │   ├── minuta_avulsa.docx
│   │   ├── 80000.001234_2026-10/     # Subpasta temática/processo
│   │   │   ├── nota_tecnica.docx
│   │   │   └── despacho.pdf
│   └── saida/                        # Arquivos HTML gerados automaticamente
│       ├── minuta_avulsa_SEI.html
│       └── 80000.001234_2026-10/
│           ├── nota_tecnica_SEI.html
│           └── despacho_SEI.html
```

> **Documentos de trabalho ficam fora do controle de versão.** O `.gitignore` cobre todo o conteúdo de `dados/entrada/` e `dados/saida/`, exceto os arquivos `.gitkeep` que preservam as pastas.
>
> A regra vale para arquivo ainda não rastreado: se um documento já entrou em algum commit, o `.gitignore` não o remove. Confira com `git ls-files dados/` e, aparecendo algum documento, tire-o do índice com `git rm --cached <arquivo>`.

Para um exemplo pronto, use o documento sintético de `exemplos/`:

```bash
conversao-sei exemplos/nota_tecnica_exemplo.md -o dados/saida/
```

---

## Uso via linha de comando (CLI)

### 1. Conversão automática de toda a pasta de entrada
Basta colocar os arquivos/subpastas em `dados/entrada/` e rodar:
```bash
conversao-sei
```
*(Ele varre `dados/entrada/` recursivamente e salva os HTMLs gerados em `dados/saida/`, preservando a estrutura de subpastas).*

### 2. Converter um arquivo ou pasta específica
```bash
# Converte DOCX específico
conversao-sei documento.docx

# Converte Markdown para pasta de saída específica
conversao-sei nota_tecnica.md -o ./minha_saida/

# Converte PDF (com extração e limpeza automática)
conversao-sei processo.pdf

# Observa dados/entrada/ e converte a cada arquivo salvo ou alterado
conversao-sei -w
```

### 3. Opções e flags
- `-o, --outdir <DIR>`: Diretório onde serão gravados os arquivos HTML.
- `--saida <ARQUIVO>`: Nome exato do arquivo de saída, quando há um só arquivo de entrada (não combina com `--watch`).
- `--unico`: Força a geração de um arquivo único, desativando a auto-divisão de partes.
- `--partes`: Usa o nome `_parte01.html` mesmo quando o documento cabe numa parte só.
- `--corpo`: Gera apenas o fragmento HTML do corpo (sem `<head>`/`<style>`), pronto para o plugin "inserir HTML" do SEI Pro.
- `--max-kb <N>`: Define o tamanho-alvo de cada parte (padrão: 22 KB).
- `--max-nivel <N>`: Profundidade máxima de `Item_Nivel` para números digitados (padrão: 4). Níveis mais profundos viram alíneas.
- `-r, --recursivo`: Processa subpastas recursivamente.
- `-w, --watch`: Fica em execução e converte a cada arquivo novo ou alterado no alvo. `Ctrl+C` encerra.
- `--intervalo <SEG>`: Tempo entre as varreduras do modo `--watch` (padrão: 2 segundos).
- `--citacao-por-recuo`: Converte como Citação o parágrafo recuado (2 cm ou mais) e em fonte menor que a do texto, em `.docx` e `.odt`. Sem a flag, esses parágrafos saem como texto comum e o relatório diz quantos são. Na interface web, o botão "Converter como citação", em "Revisar ajustes do documento", faz o mesmo.
- `--sem-cabecalho`: Começa a saída no item 1 (`1. ASSUNTO`, ou o primeiro parágrafo numerado) e omite o que vem antes, como título, número e dados do processo, que o SEI já gera pelo modelo. Sem item 1 no documento, nada é omitido e o relatório avisa. Na interface web, o botão "Omitir cabeçalho" do resultado faz o mesmo.
- `--no-validar`: Desliga a validação das regras do SEI e do limite de tamanho (sem os avisos no relatório).
- `--json`: Retorna a saída estruturada em JSON (ideal para pipelines e automações).

---

## Uso via API Python

```python
from conversao_sei import converter_documento, converter_diretorio

# Converter um arquivo DOCX/PDF/MD
resultado = converter_documento(
    caminho_entrada="documento.docx",
    outdir="./saida_sei",
    max_kb=22,
    validar=True,
)

print(f"Sucesso: {resultado.sucesso}")
for arq in resultado.arquivos_gerados:
    print(f"Gerado: {arq}")

# Converter uma pasta inteira
resultados = converter_diretorio(
    diretorio="./documentos",
    outdir="./saida_sei",
    recursivo=True,
)
```

---

## Instruções de inserção no SEI

### Método 1: copiar e colar pelo navegador (recomendado)
1. Abra o arquivo `*_SEI.html` gerado no Chrome / Edge.
2. Pressione `Cmd+A` (Mac) ou `Ctrl+A` (Windows/Linux) e depois `Cmd+C` / `Ctrl+C`.
3. No editor do SEI, clique no corpo do documento e pressione `Cmd+V` / `Ctrl+V`.
4. Confira a numeração e tabelas, depois clique em **Salvar**.
*(Caso o documento tenha sido dividido em partes, repita o processo para cada parte em sequência no mesmo documento).*

### Método 2 (reserva): plugin "Inserir HTML" do SEI Pro
Pouco útil com este conversor, que já entrega o HTML nas classes do SEI. Fica como alternativa para quando a colagem falhar. A interface web não oferece a opção de gerar só o corpo; ela está disponível apenas na CLI.
1. No SEI Pro, utilize a função de importar HTML selecionando o arquivo `*_SEI.html` (ou utilize a flag `--corpo`).
2. Se o documento gerou múltiplas partes (`_parte01.html`, `_parte02.html`), insira-as em ordem.

---

## Testes automatizados

Para executar os testes de validação, integridade e regressão:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy
```

O teste no navegador abre a página no Chromium e no WebKit (o motor do Safari): converte, omite o cabeçalho, copia o HTML e converte de novo sem rede. Ele fica fora do `pytest -q` padrão, porque precisa do Playwright e de rede:

```bash
uv sync --group e2e
uv run playwright install chromium webkit
uv run pytest -m e2e
```

O corpus em `tests/corpus/` guarda documentos reais **anonimizados** e a saída revisada de cada um. Um documento novo, ou uma mudança de saída intencional, é gravado com `ATUALIZAR_CORPUS=1 uv run pytest tests/test_corpus.py`, e o diff é revisado antes do commit. As regras de anonimização estão em [tests/corpus/README.md](tests/corpus/README.md).

No GitHub Actions, com as versões do `uv.lock`, rodam os testes, o lint, a verificação de tipos, a sincronia do pacote web, a cobertura do CSS e o teste no navegador. Todos precisam passar antes de qualquer publicação no GitHub Pages. O mypy cobre `conversao_sei/` e `scripts/`.

---

## Interface web: como alterar

A pasta `docs/` é o que vai ao ar no GitHub Pages:

- `index.html` e `app.js`: a interface.
- A conversão pela web acontece **inteiramente em memória**: os bytes vêm do navegador e o HTML volta como texto, sem gravar nada no sistema de arquivos emulado do WebAssembly.
- `estilos.css`: o CSS compilado do Tailwind (fora de `vendor/`, porque o nome não muda a cada compilação).
- `vendor/`: Lucide, JSZip, as fontes e os wheels Python puros (`typing_extensions`, `python-docx` e `pypdf`), todos com versão fixa e servidos pelo próprio site. O Pyodide e suas bibliotecas compiladas continuam vindo do jsDelivr, com versão fixa e verificação de integridade SRI para o script inicial.
- `sw.js`: o service worker, que faz a página abrir e converter sem rede depois da primeira visita.
- `conversao_sei.zip`: o pacote Python que o Pyodide descompacta no navegador.

**Ao alterar qualquer arquivo de `conversao_sei/`, regenere o bundle e inclua o ZIP no commit:**

```bash
uv run python scripts/bundle_web.py
```

O bundle é determinístico (mesmo conteúdo gera sempre os mesmos bytes). O CI confere a sincronia com `python scripts/bundle_web.py --verificar` e falha se o ZIP estiver defasado em relação ao código-fonte.

**Ao mudar a chave, o nome ou a cidade do Pix de apoio**, edite `scripts/gerar_pix.py`, rode `uv run python scripts/gerar_pix.py` (regrava `docs/pix.svg`) e copie o código exibido para `PIX_COPIA_E_COLA` em `docs/app.js`. O `tests/test_pix.py` falha se o QR Code e o código da página não forem o mesmo Pix.

**Ao acrescentar classes do Tailwind em `index.html` ou `app.js`, recompile o CSS:**

```bash
npx tailwindcss@3.4.16 -c tailwind.config.js -i tailwind-input.css -o docs/estilos.css --minify
```

O CI roda `python scripts/verificar_css.py`, que falha se alguma classe usada na interface não tiver regra no CSS compilado. A verificação é por classe, e não por bytes, porque a saída do Tailwind varia conforme o browserslist do ambiente.

---

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE).
