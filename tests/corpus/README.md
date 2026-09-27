# Corpus de documentos reais

Documentos como eles chegam de fato ao conversor, com a saída revisada de cada um. O teste
`tests/test_corpus.py` converte todos e falha se a saída de algum mudar.

## Regra de privacidade

**Só entram documentos anonimizados.** O repositório não guarda documento institucional
(veja `tests/test_higiene_repositorio.py`). Antes de acrescentar um documento, troque:

- nomes de pessoas, cargos com titular identificável e assinaturas;
- CPF, matrícula, e-mail, telefone e endereço;
- número de processo SEI, número de documento e de protocolo;
- qualquer dado de terceiros ou informação restrita.

Mantenha a **forma** do documento: estilos, numeração, tabelas, recuos, listas, bloco de
assinatura. É a forma que o corpus testa, e não o conteúdo. Troque o texto por outro de
tamanho parecido, sem apagar parágrafos nem desfazer a formatação.

## Como acrescentar um documento

1. Anonimize o documento e salve em `documentos/`, no formato original (`.docx`, `.odt`,
   `.pdf`, `.md` ou `.txt`).
2. Gere a saída: `ATUALIZAR_CORPUS=1 uv run pytest tests/test_corpus.py`.
3. Abra `esperado/<nome>.html` e confira as classes de cada parágrafo, a numeração, as
   tabelas e os avisos no topo. Se algo estiver errado, o problema é do conversor: corrija
   antes de gravar a saída.
4. Faça o commit do documento junto com a saída revisada.

## Quando a saída muda

Se uma mudança no conversor altera a saída de propósito, rode o passo 2 de novo e revise o
diff de `esperado/` antes do commit. Um diff que não era esperado é regressão.

## O que vale ter aqui

Documentos variados valem mais que muitos documentos iguais: nota técnica, ofício,
despacho e parecer; feitos no Word e no LibreOffice; com tabela mesclada, lista aninhada,
citação recuada, controle de conteúdo e revisão controlada; e um PDF exportado do SEI.
