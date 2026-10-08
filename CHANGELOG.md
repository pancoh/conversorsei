# Histórico de versões

O que mudou no Conversor SEI em cada versão, da mais recente para a mais antiga. A
numeração segue o padrão 0.X.Y: X sobe com recurso novo, e Y com correção.

## Em desenvolvimento

## 0.7.0 (2026-10-08)

- **Travessões preservados.** O travessão e a meia-risca ficam no texto em todos os formatos,
  como já ficavam no Word. Antes, nos outros formatos, o travessão virava vírgula e a
  meia-risca sumia: "2020–2023" saía "20202023".
- **Títulos do LibreOffice como os do Word.** O título sem número de um .odt passa a sair
  como item numerado do SEI, no nível do título, como o Título 1 do Word.
- **Listas do LibreOffice.** A lista numerada de um .odt sai com o número escrito no texto
  ("1.", "a)"), como a lista numerada colada, e a lista com marcadores mantém os subníveis.
- **Notas de rodapé do Word.** As notas passam para o fim do texto, numa seção Notas, com a
  chamada entre colchetes ([1], [2]), como já acontecia no .odt. Antes, elas se perdiam.
- **Parágrafo sem numeração no Word.** O parágrafo em que a numeração foi desligada deixa de
  sair como item numerado.
- **Links.** O link sai sem cor e sublinhado embutidos, como o do Word, e o endereço com
  parênteses fica inteiro. Link que executaria código (javascript:) sai como texto.
- **Linha de comando.** `--max-nivel` aceita só de 1 a 4, os níveis do SEI. `--saida` com
  mais de um arquivo passa a dar erro, em vez de ser ignorada. O `--json` traz os trechos de
  citação e de cabeçalho.
- **Privacidade.** A página, o rodapé e o README descrevem do mesmo jeito o que a contagem
  de acessos registra.

## 0.6.1 (2026-10-08)

- **Imagens do Word no tamanho da página.** A imagem passa a sair com a largura que tem no
  Word, proporcional à página: a foto na largura toda fica com cerca de 800 px no SEI, e a
  altura acompanha. Antes, a foto aparecia no tamanho original, muito maior que a página, e
  precisava ser reduzida à mão. A imagem nunca é ampliada além do tamanho original.
- **Colunas de tabela pelo conteúdo.** Quando todas as colunas têm a mesma largura (o padrão
  do Word e de toda tabela vinda de Markdown, ODT, HTML ou PDF), a largura de cada uma passa
  a ser calculada pelo texto: uma coluna só com os números 1, 2, 3 fica estreita, e as de
  texto longo ficam largas. Larguras ajustadas no Word continuam como estão.
- **Assinatura no meio do documento.** A assinatura que vem antes de um despacho, como a do
  coordenador antes do "De acordo." da diretora, passa a sair como bloco de assinatura, e não
  só a que fecha o documento. O bloco do meio começa na marca "[assinado eletronicamente]".

## 0.6.0 (2026-10-08)

- **Documento inteiro num arquivo só.** O documento longo deixa de ser dividido em partes:
  a cópia e a colagem direto no editor do SEI levam o documento inteiro com a formatação.
  A divisão servia ao limite do plugin SEI Pro. Saem também o painel "Opções de conversão",
  o tamanho do arquivo e o aviso de limite. Na linha de comando, saem `--unico`, `--partes`
  e `--max-kb`, e as partes de conversões anteriores são apagadas da pasta de saída.
- **Rodapé.** A versão passa a ocupar uma linha própria, e o rodapé deixa de quebrar o texto
  e os botões em telas médias.
- **Assinatura colada de um chat.** A assinatura escrita num parágrafo só, com a marca, o
  nome e o cargo em linhas quebradas, passa a sair como bloco de assinatura, uma linha por
  parágrafo.
- **Privacidade explicada na página.** Abaixo da área de envio, o quadro "Seus documentos
  não saem do seu computador" explica que o documento não é enviado a servidores nem a
  serviços de inteligência artificial, que nada fica guardado e como conferir isso
  desligando a internet.

## 0.5.0 (2026-10-07)

- **Citação entre aspas.** O parágrafo inteiro entre aspas que passa de uma linha, e a
  transcrição entre aspas que ocupa vários parágrafos, passam a ser sugeridos como citação,
  em todos os formatos. Como na citação recuada, eles saem como texto comum, e o botão
  "Converter como citação" faz a troca. Dentro da citação, "a)" e "1." ficam no texto, sem
  virar alínea ou item.
- **Lista numerada colada.** A lista numerada que vem em HTML, como a copiada de um chat de
  IA, sai com o número escrito no texto ("1.", "a)"), e não mais com marcadores. O número
  não entra na numeração do documento.
- **Assinatura sem centralização.** A marca "[assinado eletronicamente]" no fim do
  documento, seguida de nome e cargo, abre o bloco de assinatura mesmo sem centralização,
  como no texto colado e no .txt.
- **Versão e novidades.** O rodapé mostra a versão da página, e o quadro Novidades traz o
  histórico de cada versão.

## 0.4.0 (2026-09-30)

- **HTML como entrada.** O conversor aceita arquivos .html. O HTML do próprio SEI chega com
  as mesmas classes, e a assinatura eletrônica e a nota de autenticidade saem, com aviso.
- **Texto colado.** Ctrl+V em qualquer ponto da página, o botão "Colar texto" e o texto
  arrastado para a área de envio são convertidos como um arquivo. O texto copiado de um chat
  de IA, com as marcas do Markdown, sai com títulos, listas e negrito.
- **Leitura direta da área de transferência.** O botão "Colar texto" lê o que foi copiado e
  converte na hora. Sem permissão do navegador, ele abre um campo para colar.

## 0.3.0 (2026-09-28)

- **Tela do resultado mais simples.** A parte copiada ganha a marca "Copiada" até a próxima
  conversão, e o limite do SEI Pro só aparece na parte que não cabe. Com o resultado na tela,
  a área de envio vira uma faixa baixa.
- **Andamento do OCR.** Uma barra mostra o avanço do reconhecimento no documento inteiro, com
  a página e a porcentagem.
- **Avisos do OCR.** O aviso do resultado foi dividido em dois itens curtos, com link para o
  PDF24.

## 0.2.0 (2026-09-27)

Primeira versão publicada neste repositório.

- **Conversão para o padrão do SEI.** Converte .docx, .odt, .md, .txt e .pdf em HTML com as
  classes de parágrafo do editor do SEI, e divide em partes o documento que passa do limite
  do SEI Pro.
- **Na página ou no computador.** A conversão roda no navegador, sem enviar o documento, e
  funciona sem rede depois da primeira visita. O comando conversorsei faz o mesmo na linha de
  comando.
- **Ajustes a pedido.** O resultado oferece omitir o cabeçalho antes do item 1 e converter
  como citação os parágrafos recuados e em fonte menor.
- **OCR de PDF digitalizado.** No PDF sem camada de texto, o botão "Reconhecer texto (OCR)"
  reconhece as páginas em português no próprio navegador.
- **Endereço próprio.** A página passa a conversorsei.com.br, e os endereços antigos
  redirecionam para ela.
- **Numeração no Chrome.** A prévia deixou de numerar 2.3 logo depois de 2.
- **Rodapé.** Links para relatar problema, enviar sugestão e apoiar o projeto por Pix, e o
  aviso de que o projeto é independente.
