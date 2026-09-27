# Nota Técnica nº 1/2026/EXEMPLO

Processo nº 00000.000000/2026-00

Interessado: Unidade de Exemplo

<p class="Texto_Ementa">Ementa: documento fictício que reúne, num só arquivo, todos os elementos que o conversor transforma para o editor do SEI. Não tem valor administrativo.</p>

# 1. ASSUNTO

1.1. Este documento serve para testar o conversor e para mostrar o resultado de cada elemento no SEI. Todos os nomes, números e datas são fictícios.

1.2. O texto antes do item 1 (título, processo e interessado) é o cabeçalho. Na página, o botão "Omitir cabeçalho" o retira, porque o SEI já o gera pelo modelo.

# 2. NUMERAÇÃO AUTOMÁTICA

2.1. Os itens usam os contadores do SEI. O número digitado no texto é retirado, e o SEI o recria, sem repetir.

2.1.1. Item de terceiro nível.

2.1.1.1. Item de quarto nível.

2.1.2. Outro item de terceiro nível, que continua a contagem.

2.2. Um item pode ter incisos e alíneas. No Markdown, eles vêm pelo nome da classe; no Word, por uma lista numerada em romanos ou em letras. O número digitado é retirado, e o SEI o recria:

<p class="Item_Inciso_Romano">I - primeiro inciso;</p>

<p class="Item_Inciso_Romano">II - segundo inciso, que pode ter alíneas:</p>

<p class="Item_Alinea_Letra">a) primeira alínea;</p>

<p class="Item_Alinea_Letra">b) segunda alínea; e</p>

<p class="Item_Inciso_Romano">III - terceiro inciso.</p>

2.3. Parágrafos numerados, independentes dos itens:

<p class="Paragrafo_Numerado_Nivel1">Parágrafo numerado de primeiro nível.</p>

<p class="Paragrafo_Numerado_Nivel2">Parágrafo numerado de segundo nível.</p>

<p class="Paragrafo_Numerado_Nivel3">Parágrafo numerado de terceiro nível.</p>

# 3. TEXTO E FORMATAÇÃO

3.1. Dentro do parágrafo, o texto pode ter **negrito**, *itálico*, ***negrito e itálico***, ~~um trecho riscado~~ e um link: [www.gov.br](https://www.gov.br).

3.2. Listas com marcadores:

- primeiro marcador;
- segundo marcador, com subitens:
  - subitem do segundo marcador;
    - subitem de terceiro nível;
- [x] tarefa concluída;
- [ ] tarefa pendente.

3.3. Citação de um trecho de norma:

> Art. 1º Este é um trecho citado, que o SEI mostra com recuo e fonte menor.
>
> Parágrafo único. A citação pode ter mais de um parágrafo.

3.4. Trecho de código, que mantém os espaços e a fonte de largura fixa:

```python
def saudacao(nome):
    return f"Olá, {nome}"
```

3.5. Parágrafo inteiro riscado, como numa alteração de texto normativo:

~~Este parágrafo foi revogado e aparece riscado.~~

# 4. TABELAS

4.1. A tabela sai centralizada, com a primeira linha em cinza:

| Formato | Extensão | Observação |
| --- | --- | --- |
| Word | .docx | Mantém negrito, itálico, tabelas e imagens |
| LibreOffice | .odt | Mantém os estilos com nome de classe |
| PDF | .pdf | Retira carimbos e assinaturas do SEI |
| Markdown | .md | Usa a marcação para escolher a classe |
| Texto | .txt | Organiza os parágrafos automaticamente |

4.2. Uma tabela de valores:

| Ano | Valor previsto (R$) | Valor executado (R$) |
| --- | --- | --- |
| 2024 | 1.000.000,00 | 850.000,00 |
| 2025 | 1.200.000,00 | 1.100.000,00 |
| **Total** | **2.200.000,00** | **1.950.000,00** |

# 5. CLASSES DO SEI

5.1. Qualquer classe do menu Estilo do SEI pode ser escolhida pelo nome. Os parágrafos abaixo usam cada uma delas.

<p class="Texto_Justificado">Texto_Justificado: parágrafo justificado, sem recuo.</p>

<p class="Texto_Justificado_Recuo_Primeira_Linha">Texto_Justificado_Recuo_Primeira_Linha: parágrafo justificado, com recuo na primeira linha. É a classe padrão do corpo do texto.</p>

<p class="Texto_Justificado_Recuo_Primeira_Linha2">Texto_Justificado_Recuo_Primeira_Linha2: variação com recuo maior na primeira linha.</p>

<p class="Texto_Justificado_Maiusculas">Texto_Justificado_Maiusculas: parágrafo justificado em caixa alta.</p>

<p class="Texto_Espaco_Duplo_Recuo_Primeira_Linha">Texto_Espaco_Duplo_Recuo_Primeira_Linha: espaço duplo entre as linhas.</p>

<p class="Texto_Alinhado_Esquerda">Texto_Alinhado_Esquerda: parágrafo alinhado à esquerda.</p>

<p class="Texto_Alinhado_Esquerda_Espaçamento_Simples">Texto_Alinhado_Esquerda_Espaçamento_Simples: à esquerda, com espaçamento simples.</p>

<p class="Texto_Alinhado_Esquerda_Espacamento_Simples_Maiusc">Texto_Alinhado_Esquerda_Espacamento_Simples_Maiusc: à esquerda, espaçamento simples e caixa alta.</p>

<p class="Texto_Alinhado_Direita">Texto_Alinhado_Direita: parágrafo alinhado à direita.</p>

<p class="Texto_Centralizado">Texto_Centralizado: parágrafo centralizado.</p>

<p class="Texto_Centralizado_Maiusculas">Texto_Centralizado_Maiusculas: centralizado em caixa alta.</p>

<p class="Texto_Centralizado_Maiusculas_Negrito">Texto_Centralizado_Maiusculas_Negrito: centralizado, caixa alta e negrito.</p>

<p class="Texto_Fundo_Cinza_Negrito">Texto_Fundo_Cinza_Negrito: fundo cinza com negrito.</p>

<p class="Texto_Fundo_Cinza_Maiusculas_Negrito">Texto_Fundo_Cinza_Maiusculas_Negrito: fundo cinza, caixa alta e negrito.</p>

<p class="Texto_Citação">Texto_Citação: citação curta, dentro do corpo do texto.</p>

<p class="Citação">Citação: citação longa, com recuo e fonte menor.</p>

<p class="Texto_Mono_Espaçado">Texto_Mono_Espaçado: fonte de largura fixa.</p>

<p class="Tachado">Tachado: parágrafo inteiro riscado.</p>

<p class="Fonte_Calibri">Fonte_Calibri: parágrafo na fonte Calibri.</p>

<p class="Tabela_Texto_Alinhado_Esquerda">Tabela_Texto_Alinhado_Esquerda: texto de tabela à esquerda.</p>

<p class="Tabela_Texto_Alinhado_Direita">Tabela_Texto_Alinhado_Direita: texto de tabela à direita.</p>

<p class="Tabela_Texto_Centralizado">Tabela_Texto_Centralizado: texto de tabela centralizado.</p>

<p class="Tabela_Texto_10">Tabela_Texto_10: texto de tabela em fonte 10.</p>

<p class="Tabela_Texto_8">Tabela_Texto_8: texto de tabela em fonte 8.</p>

# 6. PONTOS A CONFERIR

6.1. Alguns elementos não passam para o SEI e aparecem na lista "Pontos a conferir antes de colar". Uma imagem indicada no Markdown precisa ser inserida à mão no SEI:

![Gráfico de execução](grafico_execucao.png)

6.2. Uma nota de rodapé também precisa ser revista.[^1]

[^1]: O SEI não tem notas de rodapé. O texto da nota deve ir para o corpo do documento.

# 7. CONCLUSÃO

7.1. Documento de exemplo, sem valor administrativo, mantido para testes e demonstração do conversor.

<p class="Texto_Alinhado_Direita">Brasília, 27 de setembro de 2026.</p>

<p class="Tabela_Texto_Centralizado">[Assinado eletronicamente]</p>

<p class="Tabela_Texto_Centralizado">**MARIA DA SILVA**</p>

<p class="Tabela_Texto_Centralizado">Analista de Exemplo</p>

<p class="Tabela_Texto_Centralizado">(assinado eletronicamente)</p>

<p class="Tabela_Texto_Centralizado">**JOÃO DOS SANTOS**</p>

<p class="Tabela_Texto_Centralizado">Coordenador de Exemplo</p>
