// app.js: controlador da aplicação web do Conversor SEI no Pyodide

let pyodideInstance = null;
let isPyodideReady = false;
let currentResultFiles = [];
let currentOriginalName = '';
// O resultado na tela veio de um texto colado, e não de um arquivo
let origemColada = false;
let emLote = false;
// Arquivos da última seleção, para converter de novo quando a opção de citação muda
let ultimosArquivos = [];
// Citação pela forma (recuo ou aspas): desligada a cada seleção nova, ligada só pelo botão do resultado
let citacaoPorRecuo = false;
// Cabeçalho antes do item 1: mantido a cada seleção nova, omitido só pelo botão do resultado
let omitirCabecalho = false;
// Só uma chamada usa os globais do Python por vez. O número da seleção impede que uma
// conversão antiga, ainda na fila, substitua o resultado mais recente na tela.
let filaPyodide = Promise.resolve();
let numeroDaSelecao = 0;

function executarNoPyodide(tarefa) {
  const execucao = filaPyodide.then(tarefa, tarefa);
  filaPyodide = execucao.catch(() => {});
  return execucao;
}

// Elementos do DOM
const pyodideStatusCard = document.getElementById('pyodide-status-card');
const statusSpinner = document.getElementById('status-spinner');
const statusTitle = document.getElementById('status-title');
const statusDesc = document.getElementById('status-desc');
const statusRelato = document.getElementById('status-relato');
const statusOcrIniciar = document.getElementById('status-ocr-iniciar');
const statusProgresso = document.getElementById('status-progresso');
const statusProgressoTrilho = document.getElementById('status-progresso-trilho');
const statusProgressoBarra = document.getElementById('status-progresso-barra');
const statusProgressoEtapa = document.getElementById('status-progresso-etapa');
const statusProgressoPorcento = document.getElementById('status-progresso-porcento');

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const dropTitulo = document.getElementById('drop-titulo');
// Somem no estado compacto. A privacidade já foi dita na primeira tela
const dropDetalhes = ['drop-icone', 'drop-formatos', 'drop-ajuda'].map(id => document.getElementById(id));
const btnSelecionar = document.getElementById('btn-selecionar');
const btnSelecionarTexto = document.getElementById('btn-selecionar-texto');
const dropConteudo = document.getElementById('drop-conteudo');
const btnColar = document.getElementById('btn-colar');
const colarPainel = document.getElementById('colar-painel');
const colarCampo = document.getElementById('colar-campo');
const btnColarConverter = document.getElementById('btn-colar-converter');

const toggleOptionsBtn = document.getElementById('toggle-options-btn');
const optionsPanel = document.getElementById('options-panel');
const optionsChevron = document.getElementById('options-chevron');

const optMaxKb = document.getElementById('opt-max-kb');
const optForcarUnico = document.getElementById('opt-forcar-unico');

const resultsSection = document.getElementById('results-section');
const resFilename = document.getElementById('res-filename');
const resMeta = document.getElementById('res-meta');
const resPartsCount = document.getElementById('res-parts-count');
const resActionsTop = document.getElementById('res-actions-top');
const btnDownloadTop = document.getElementById('btn-download-top');
const btnDownloadTopText = document.getElementById('btn-download-top-text');
const resWarningsCard = document.getElementById('res-warnings-card');
const resWarningsList = document.getElementById('res-warnings-list');
const resAjustes = document.getElementById('res-ajustes');
const resCitacaoCard = document.getElementById('res-citacao-card');
const resCitacaoTexto = document.getElementById('res-citacao-texto');
const resCitacaoTrechos = document.getElementById('res-citacao-trechos');
const resCitacaoResumo = document.getElementById('res-citacao-resumo');
const btnCitacao = document.getElementById('btn-citacao');
const resCabecalhoCard = document.getElementById('res-cabecalho-card');
const resCabecalhoTexto = document.getElementById('res-cabecalho-texto');
const resCabecalhoTrechos = document.getElementById('res-cabecalho-trechos');
const resCabecalhoResumo = document.getElementById('res-cabecalho-resumo');
const btnCabecalho = document.getElementById('btn-cabecalho');
const resPartsList = document.getElementById('res-parts-list');
const guiaPassos = document.getElementById('guia-passos');
const guiaPartes = document.getElementById('guia-partes');

const previewModal = document.getElementById('preview-modal');
const previewTitle = document.getElementById('preview-title');
const previewIframe = document.getElementById('preview-iframe');
const closePreviewBtn = document.getElementById('close-preview-btn');
const modalCloseBtn2 = document.getElementById('modal-close-btn2');

const toast = document.getElementById('toast');
const toastMessage = document.getElementById('toast-message');
const toastIcone = document.getElementById('toast-icone');
const anuncio = document.getElementById('anuncio');

// Números no formato brasileiro. Sem isso, "21.36 KB" (ponto decimal) aparecia ao lado
// de "20.884" (ponto de milhar), e o primeiro podia ser lido como vinte e um mil
function formatarNumero(valor, casas = 0) {
  return Number(valor).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

function formatarSegundos(segundos) {
  return `${formatarNumero(segundos, 2)} s`;
}

function plural(n, singular, varios) {
  return `${formatarNumero(n)} ${n === 1 ? singular : varios}`;
}

// Inicialização de Ícones
function refreshIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

// A cópia bem-sucedida se confirma no próprio botão ("Copiado" por dois segundos), onde a
// pessoa está olhando. O aviso no canto da tela fica para os alertas.
//
// Os dois rótulos ficam prontos dentro do botão, sobrepostos na mesma célula da grade, e
// só a visibilidade muda: o botão mantém a largura do rótulo maior, sem medida em px. O
// nome acessível é fixo (aria-label), e quem fala a confirmação é a região de anúncio,
// com o rótulo do cartão, para quem usa leitor de tela saber qual parte copiou
const temporizadoresDaCopia = new WeakMap();

// O "Copiado" do botão dura dois segundos. Num documento em várias partes, a pessoa
// perdia a conta de quais já tinha colado: a marca no quadro da parte fica até a
// próxima conversão
function marcarComoCopiada(card) {
  if (!card) return;
  card.classList.replace('border-slate-200', 'border-emerald-400/60');
  const marca = card.querySelector('[data-marca-copiada]');
  marca.classList.replace('hidden', 'inline-flex');
}

function mostrarCopiado(botao, copiado) {
  clearTimeout(temporizadoresDaCopia.get(botao));
  botao.querySelector('.rotulo-copiar').classList.toggle('invisible', copiado);
  botao.querySelector('.rotulo-copiado').classList.toggle('invisible', !copiado);
  if (!copiado) return;
  temporizadoresDaCopia.set(botao, setTimeout(() => mostrarCopiado(botao, false), 2000));
  anunciar(`Copiado: ${botao.dataset.rotulo}. Cole no editor do SEI.`);
}

// A região é esvaziada e preenchida em tarefas separadas: na mesma tarefa, o navegador
// junta as duas mudanças, e uma segunda cópia com o mesmo texto não seria anunciada.
// Um anúncio novo cancela o pendente: sem isso, duas cópias seguidas deixavam o texto
// antigo chegar à região depois de esvaziada para o novo
let temporizadorDoAnuncio = null;

function anunciar(texto) {
  clearTimeout(temporizadorDoAnuncio);
  anuncio.textContent = '';
  temporizadorDoAnuncio = setTimeout(() => { anuncio.textContent = texto; }, 100);
}

// Aviso rápido. O de alerta fica mais tempo na tela, porque pede uma ação. Um aviso novo
// substitui o anterior: sem cancelar o temporizador, o antigo esconderia o novo
let temporizadorDoAviso = null;

function showToast(msg, tipo = 'ok') {
  const alerta = tipo === 'alerta';
  toastMessage.textContent = msg;
  toastIcone.innerHTML = alerta
    ? '<i data-lucide="alert-triangle" class="w-4 h-4 text-amber-400"></i>'
    : '<i data-lucide="check-circle" class="w-4 h-4 text-emerald-400"></i>';
  refreshIcons();
  toast.classList.remove('hidden', 'opacity-0');
  toast.classList.add('flex', 'opacity-100');
  clearTimeout(temporizadorDoAviso);
  temporizadorDoAviso = setTimeout(() => {
    toast.classList.remove('opacity-100');
    toast.classList.add('opacity-0');
    temporizadorDoAviso = setTimeout(() => {
      toast.classList.add('hidden');
      toast.classList.remove('flex');
    }, 300);
  }, alerta ? 9000 : 2500);
}

// Relato de problema e apoio ao projeto. O canal do relato é o e-mail: não exige conta em
// nenhum serviço, e o modelo chega preenchido com os dados técnicos da última tentativa.
const EMAIL_RELATO = 'conversorsei@gmail.com';
// Apoio por Pix. O código copia e cola é o mesmo do QR Code (docs/pix.svg): os dois saem de
// scripts/gerar_pix.py, e tests/test_pix.py confere que batem
const PIX_CHAVE = 'conversorsei@gmail.com';
const PIX_COPIA_E_COLA = '00020126440014br.gov.bcb.pix0122conversorsei@gmail.com5204000053039865802BR5913CONVERSOR SEI6008BRASILIA62070503***6304583E';
// Um mailto muito longo é cortado por alguns programas de e-mail
const MAXIMO_LINHAS_DO_RELATO = 10;

// O que a última tentativa deixou: o relato leva a situação e os avisos, nunca o documento
let contextoDoRelato = { situacao: 'Nenhuma conversão nesta visita.', detalhes: [] };

function registrarParaRelato(situacao, detalhes = []) {
  contextoDoRelato = { situacao, detalhes: detalhes.filter(Boolean) };
}

// Tira o nome dos arquivos do texto. O nome de um documento de trabalho pode identificar o
// processo, e o relato sai da página por e-mail. Primeiro os nomes enviados (com e sem a
// extensão, os mais longos antes), depois qualquer palavra com extensão de documento
function semNomesDeArquivo(texto) {
  let limpo = String(texto);
  const nomes = ultimosArquivos
    .flatMap(f => [f.name, f.name.replace(/\.[^.]+$/, '')])
    .filter(nome => nome.length > 2)
    .sort((a, b) => b.length - a.length);
  for (const nome of nomes) limpo = limpo.split(nome).join('<arquivo>');
  return limpo.replace(/[^\s[\]:|"'()]+\.(docx?|odt|pdf|md|txt|rtf|html)\b/gi, '<arquivo>');
}

// A marca de versão do app.js, gravada pelo bundle_web.py, identifica a publicação
function versaoDaPagina() {
  const script = document.querySelector('script[src*="app.js?v="]');
  return script ? new URL(script.src).searchParams.get('v') : 'desconhecida';
}

function linkDoRelato() {
  const formatos = [...new Set(ultimosArquivos.map(f => {
    const extensao = (f.name.match(/\.[^.]+$/) || ['sem extensão'])[0].toLowerCase();
    return f.colado ? `colado (${extensao})` : extensao;
  }))];
  const { situacao, detalhes } = contextoDoRelato;
  const linhas = detalhes.slice(0, MAXIMO_LINHAS_DO_RELATO).map(d => `- ${semNomesDeArquivo(d)}`);
  if (detalhes.length > MAXIMO_LINHAS_DO_RELATO) linhas.push(`- e mais ${detalhes.length - MAXIMO_LINHAS_DO_RELATO}.`);
  const corpo = [
    'Descreva o problema:',
    '',
    '',
    'O que você esperava:',
    '',
    '',
    'Não anexe documento com informação restrita. Se puder, envie um exemplo anonimizado.',
    '',
    '--- Dados técnicos (o documento não é enviado) ---',
    `Versão da página: ${versaoDaPagina()}`,
    `Navegador: ${navigator.userAgent}`,
    `Formato: ${formatos.join(', ') || 'nenhum'}`,
    `Situação: ${semNomesDeArquivo(situacao)}`,
    ...linhas,
  ].join('\n');
  const assunto = encodeURIComponent('Conversor SEI: relato de problema');
  return `mailto:${EMAIL_RELATO}?subject=${assunto}&body=${encodeURIComponent(corpo)}`;
}

// O endereço é montado no clique, com a situação daquele momento
document.querySelectorAll('[data-relato]').forEach(link => {
  link.href = `mailto:${EMAIL_RELATO}`;
  link.addEventListener('click', () => { link.href = linkDoRelato(); });
});

// A sugestão vai para o mesmo e-mail, com assunto próprio e sem dados técnicos: ela não
// depende de uma conversão, e a versão e o navegador só atrapalhariam a leitura
function linkDaSugestao() {
  const corpo = [
    'Sua sugestão:',
    '',
    '',
    'Em que situação ela ajudaria:',
    '',
    '',
    'Não anexe documento com informação restrita.',
  ].join('\n');
  const assunto = encodeURIComponent('Conversor SEI: sugestão');
  return `mailto:${EMAIL_RELATO}?subject=${assunto}&body=${encodeURIComponent(corpo)}`;
}

document.querySelectorAll('[data-sugestao]').forEach(link => { link.href = linkDaSugestao(); });

// Janela do Pix: abre pelo rodapé, fecha no X, no Esc ou no fundo, e devolve o foco ao botão
const pixModal = document.getElementById('pix-modal');
const btnApoio = document.getElementById('btn-apoio');
const pixFechar = document.getElementById('pix-fechar');
const pixCopiarCodigo = document.getElementById('pix-copiar-codigo');
const pixCopiarChave = document.getElementById('pix-copiar-chave');
document.getElementById('pix-chave').textContent = PIX_CHAVE;

function abrirPix() {
  pixModal.classList.remove('hidden');
  pixFechar.focus();
}

function fecharPix() {
  if (pixModal.classList.contains('hidden')) return;
  pixModal.classList.add('hidden');
  btnApoio.focus();
}

// Texto puro: o código Pix e a chave são colados no aplicativo do banco, e não no SEI
async function copiarTexto(texto) {
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch {
    const campo = document.createElement('textarea');
    campo.value = texto;
    document.body.appendChild(campo);
    campo.select();
    const copiou = document.execCommand('copy');
    document.body.removeChild(campo);
    return copiou;
  }
}

async function copiarDoPix(texto, confirmacao) {
  if (await copiarTexto(texto)) {
    showToast(confirmacao);
  } else {
    showToast('Não foi possível copiar. Selecione e copie o texto manualmente.', 'alerta');
  }
}

btnApoio.addEventListener('click', abrirPix);
pixFechar.addEventListener('click', fecharPix);
pixModal.addEventListener('click', (e) => {
  if (e.target === pixModal) fecharPix();
});
pixCopiarCodigo.addEventListener('click', () => copiarDoPix(PIX_COPIA_E_COLA, 'Código Pix copiado. Cole no aplicativo do banco.'));
pixCopiarChave.addEventListener('click', () => copiarDoPix(PIX_CHAVE, 'Chave Pix copiada.'));
document.addEventListener('keydown', (e) => {
  if (pixModal.classList.contains('hidden')) return;
  if (e.key === 'Escape') {
    fecharPix();
    return;
  }
  if (e.key !== 'Tab') return;
  const focaveis = [pixFechar, pixCopiarCodigo, pixCopiarChave];
  const indice = focaveis.indexOf(document.activeElement);
  if (indice === -1 || (e.shiftKey && indice === 0) || (!e.shiftKey && indice === focaveis.length - 1)) {
    e.preventDefault();
    focaveis[e.shiftKey ? focaveis.length - 1 : 0].focus();
  }
});

// Inicializar Pyodide
const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
const PYODIDE_SRI = 'sha384-i3R37b3tF+HWudsUf1VSEOY2YxwSNMqY8DQa9Z0O3xh+NkJ9o+yjcGyIi5huj+nB';
// Tempo máximo de espera pelo service worker na primeira visita. Esgotado, o conversor
// carrega assim mesmo: só o uso sem rede fica para depois da visita seguinte
const PRAZO_SERVICE_WORKER_MS = 15000;

// Na primeira visita, o service worker só atende a página depois de ativado. O que a página
// baixava antes disso (o Pyodide inteiro) não entrava no cache dele, e a página não abria
// sem rede na visita seguinte, ao contrário do que promete. Por isso o motor espera o
// controle. Nas visitas seguintes o controle já existe, e não há espera.
function aguardarServiceWorker(prazoMs) {
  if (!('serviceWorker' in navigator) || navigator.serviceWorker.controller) return Promise.resolve();
  if (location.protocol !== 'http:' && location.protocol !== 'https:') return Promise.resolve();
  return new Promise((resolve) => {
    let temporizador = null;
    const concluir = () => {
      clearTimeout(temporizador);
      resolve();
    };
    temporizador = setTimeout(concluir, prazoMs);
    navigator.serviceWorker.addEventListener('controllerchange', concluir, { once: true });
  });
}

function solicitarReparoDoCache() {
  if (!('serviceWorker' in navigator)) return;
  const avisar = () => navigator.serviceWorker.controller?.postMessage({ tipo: 'reparar-cache-essencial' });
  // O controlador atual pode ser a versão anterior, ainda sem o reparo. Avisa de novo
  // quando a versão nova assumir a página.
  navigator.serviceWorker.addEventListener('controllerchange', avisar, { once: true });
  avisar();
}

// Carrega um script externo com SRI. O crossOrigin faz a resposta ser CORS, e não opaca:
// resposta opaca não informa o status, e o service worker não a guarda
function carregarScript(src, integrity) {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.integrity = integrity;
    script.crossOrigin = 'anonymous';
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Falha ao carregar ${src}`));
    document.head.appendChild(script);
  });
}
// Avisa a demora sem interromper o carregamento. Um prazo que rejeitasse declarava a
// página indisponível numa rede lenta, com o download ainda em andamento e sem falha real.
function comAvisoDeDemora(promessa, milissegundos) {
  const temporizador = setTimeout(() => {
    statusDesc.textContent = 'A rede está lenta e o carregamento continua. Aguarde sem fechar a página.';
  }, milissegundos);
  return promessa.finally(() => clearTimeout(temporizador));
}

async function initPyodide() {
  let enderecoEmCarga = PYODIDE_URL;
  try {
    statusTitle.textContent = 'Preparando o conversor (1 de 4)...';
    statusDesc.textContent = 'Baixando os componentes. Na primeira visita, isso leva alguns segundos.';

    await aguardarServiceWorker(PRAZO_SERVICE_WORKER_MS);
    pyodideInstance = await comAvisoDeDemora(
      carregarScript(`${PYODIDE_URL}pyodide.js`, PYODIDE_SRI).then(() => loadPyodide({ indexURL: PYODIDE_URL })),
      20000
    );

    statusTitle.textContent = 'Preparando o conversor (2 de 4)...';
    statusDesc.textContent = 'Carregando as bibliotecas de leitura de documentos.';
    
    // O lxml DEVE ser carregado via loadPackage pois é uma extensão C pré-compilada no Pyodide
    enderecoEmCarga = PYODIDE_URL;
    await comAvisoDeDemora(pyodideInstance.loadPackage(['micropip', 'lxml']), 20000);
    
    statusTitle.textContent = 'Preparando o conversor (3 de 4)...';
    statusDesc.textContent = 'Instalando os leitores de Word e PDF.';
    
    const micropip = pyodideInstance.pyimport('micropip');
    // Wheels puros servidos pelo próprio site, com versões fixas. Redes que bloqueiam
    // PyPI continuam precisando liberar só o CDN do Pyodide.
    const wheels = [
      'typing_extensions-4.16.0-py3-none-any.whl',
      'python_docx-1.2.0-py3-none-any.whl',
      'pypdf-6.16.1-py3-none-any.whl'
    ];
    for (const wheel of wheels) {
      enderecoEmCarga = new URL(`vendor/${wheel}`, window.location.href).href;
      await comAvisoDeDemora(micropip.install(enderecoEmCarga), 20000);
    }

    statusTitle.textContent = 'Preparando o conversor (4 de 4)...';
    statusDesc.textContent = 'Carregando as regras e os estilos do SEI.';

    // Baixa o ZIP do conversorsei e descompacta no sistema de arquivos virtual do Pyodide.
    // Sem sufixo de versão na URL: cada valor novo seria um endereço que o service worker
    // nunca tem em cache, e a página deixaria de abrir sem rede. O 'no-cache' revalida
    // com o servidor quando há rede, e o service worker responde quando não há.
    enderecoEmCarga = new URL('conversorsei.zip', window.location.href).href;
    const response = await comAvisoDeDemora(fetch('conversorsei.zip', { cache: 'no-cache' }), 20000);
    if (!response.ok) {
      throw new Error('Falha ao baixar conversorsei.zip: ' + response.statusText);
    }
    const zipArrayBuffer = await response.arrayBuffer();
    pyodideInstance.unpackArchive(zipArrayBuffer, 'zip');

    // Executa import de teste
    enderecoEmCarga = null;
    await pyodideInstance.runPythonAsync(`
import sys
import conversorsei
from conversorsei.web import converter_memoria_json
print("conversorsei pronto versão:", conversorsei.__version__)
`);

    isPyodideReady = true;
    
    mostrarStatusDiscreto('Pronto para converter.');
    definirEnvioDisponivel(true);
    solicitarReparoDoCache();
  } catch (err) {
    console.error('Erro na inicialização do Pyodide:', err);
    pyodideStatusCard.className = CLASSE_QUADRO_ERRO;
    statusSpinner.innerHTML = '<i data-lucide="alert-circle" class="w-5 h-5 text-rose-600"></i>';
    statusSpinner.className = 'self-start';
    statusTitle.className = 'text-sm font-semibold text-rose-900';
    statusTitle.textContent = 'Não foi possível carregar o conversor';
    statusDesc.className = `${CLASSE_DESCRICAO_ERRO} break-all`;
    statusDesc.textContent = enderecoEmCarga
      ? `Não foi possível carregar um componente de ${enderecoEmCarga}. Informe esse endereço à TI ou tente outra rede.`
      : 'Os componentes foram carregados, mas o conversor não iniciou. Recarregue a página e tente novamente.';
    registrarParaRelato('O conversor não carregou', [statusDesc.textContent, err.message || String(err)]);
    statusRelato.classList.remove('hidden');
    btnSelecionarTexto.textContent = 'Conversor indisponível';
    btnSelecionar.classList.replace('cursor-wait', 'cursor-not-allowed');
    refreshIcons();
  }
}

// O botão de envio fica desativado enquanto o conversor carrega. Antes, ele parecia
// ativo e só respondia com um aviso rápido, que passava despercebido
function definirEnvioDisponivel(disponivel) {
  fileInput.disabled = !disponivel;
  btnColar.disabled = !disponivel;
  [btnSelecionar, btnColar].forEach(botao => {
    botao.classList.toggle('opacity-60', !disponivel);
    botao.classList.toggle('cursor-wait', !disponivel);
  });
  btnSelecionarTexto.textContent = disponivel ? 'Selecionar arquivos' : 'Carregando o conversor...';
}

// Alternar Painel de Opções
toggleOptionsBtn.addEventListener('click', () => {
  const abrir = optionsPanel.classList.contains('hidden');
  optionsPanel.classList.toggle('hidden', !abrir);
  optionsChevron.classList.toggle('rotate-180', abrir);
  toggleOptionsBtn.setAttribute('aria-expanded', String(abrir));
});

// Eventos de Seleção de Arquivo e Drag & Drop
fileInput.addEventListener('click', (e) => {
  if (!isPyodideReady) {
    e.preventDefault();
    showToast('Aguarde o conversor terminar de carregar.');
  }
});

['dragenter', 'dragover'].forEach(eventName => {
  dropZone.addEventListener(eventName, (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isPyodideReady) {
      dropZone.classList.add('drop-active');
    }
  }, false);
});

['dragleave', 'drop'].forEach(eventName => {
  dropZone.addEventListener(eventName, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove('drop-active');
  }, false);
});

dropZone.addEventListener('drop', (e) => {
  if (!isPyodideReady) {
    showToast('Aguarde o conversor terminar de carregar.');
    return;
  }
  const dt = e.dataTransfer;
  const files = dt.files;
  if (files.length > 0) {
    novaSelecao(Array.from(files));
    return;
  }
  // Texto selecionado e arrastado de outra janela segue o caminho do texto colado
  const colado = arquivoDoConteudoColado(dt);
  if (colado) novaSelecao([colado]);
});

// Texto colado. A área de transferência traz o mesmo conteúdo em mais de uma forma: o
// HTML formatado (Word, Google Docs, LibreOffice, o SEI, texto selecionado num chat) vai
// ao leitor de HTML; o texto simples com marcas de Markdown (o botão Copiar dos chats de
// IA), ao de Markdown; o resto, ao de texto. O conteúdo vira um arquivo e segue o caminho
// de qualquer outro, com a marca `colado`, que tira os avisos próprios de arquivo
const ESTRUTURA_HTML = /<(p|h[1-6]|li|table|blockquote|pre)[\s>]/i;
const MARCAS_MARKDOWN = /^\s{0,3}(#{1,6}\s|[-*+]\s|>|\|.*\|\s*$|```)|\*\*\S|\[[^\]]+\]\([^)\s]+\)/m;

function arquivoDoConteudoColado(dados) {
  const html = dados.getData('text/html') || '';
  const texto = dados.getData('text/plain') || '';
  let nome, conteudo, tipo;
  if (html && ESTRUTURA_HTML.test(html)) {
    [nome, conteudo, tipo] = ['texto_colado.html', html, 'text/html'];
  } else if (texto.trim()) {
    const markdown = MARCAS_MARKDOWN.test(texto);
    [nome, conteudo, tipo] = [markdown ? 'texto_colado.md' : 'texto_colado.txt', texto, 'text/plain'];
  } else if (html.trim()) {
    [nome, conteudo, tipo] = ['texto_colado.html', html, 'text/html'];
  } else {
    return null;
  }
  const arquivo = new File([conteudo], nome, { type: tipo });
  arquivo.colado = true;
  return arquivo;
}

// Ctrl+V em qualquer ponto da página converte o que foi colado. Num campo de texto da
// página (as opções), colar é colar, menos no campo feito para isso
document.addEventListener('paste', (e) => {
  const alvo = e.target;
  const editavel = alvo instanceof HTMLElement && (alvo.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(alvo.tagName));
  if (editavel && alvo !== colarCampo) return;
  e.preventDefault();
  if (!isPyodideReady) {
    showToast('Aguarde o conversor terminar de carregar.');
    return;
  }
  const colado = e.clipboardData && arquivoDoConteudoColado(e.clipboardData);
  if (!colado) {
    showToast('A área de transferência não tem texto para converter.');
    return;
  }
  novaSelecao([colado]);
});

// O botão lê a área de transferência direto. Cada navegador pede uma confirmação: o
// Chrome, a permissão na primeira vez; o Safari e o Firefox, um toque em "Colar" a cada
// leitura. Recusada ou sem o recurso, o botão abre um campo, e colar nele (Ctrl+V, ou
// tocar e segurar no celular) converte na hora. O Converter do campo é para o texto digitado
btnColar.addEventListener('click', async (e) => {
  e.preventDefault();
  if (!isPyodideReady) {
    showToast('Aguarde o conversor terminar de carregar.');
    return;
  }
  if (!colarPainel.classList.contains('hidden')) {
    mostrarCampoDeColar(false);
    return;
  }
  let colado;
  try {
    colado = await lerAreaDeTransferencia();
  } catch {
    // Permissão negada, bolha "Colar" dispensada ou navegador sem o recurso
    mostrarCampoDeColar(true);
    return;
  }
  if (colado) {
    novaSelecao([colado]);
  } else {
    showToast('A área de transferência não tem texto para converter.');
  }
});

// As formas de texto do que foi copiado, no formato que arquivoDoConteudoColado lê
async function lerAreaDeTransferencia() {
  const valores = {};
  if (navigator.clipboard && navigator.clipboard.read) {
    for (const item of await navigator.clipboard.read()) {
      for (const tipo of ['text/html', 'text/plain']) {
        if (item.types.includes(tipo) && !valores[tipo]) valores[tipo] = await (await item.getType(tipo)).text();
      }
    }
  } else if (navigator.clipboard && navigator.clipboard.readText) {
    valores['text/plain'] = await navigator.clipboard.readText();
  } else {
    throw new Error('Leitura da área de transferência indisponível.');
  }
  return arquivoDoConteudoColado(comoDadosColados(valores));
}

function comoDadosColados(valores) {
  return { getData: tipo => valores[tipo] || '' };
}

function mostrarCampoDeColar(mostrar) {
  colarPainel.classList.toggle('hidden', !mostrar);
  btnColar.setAttribute('aria-expanded', String(mostrar));
  colarCampo.value = '';
  btnColarConverter.classList.add('hidden');
  if (mostrar) colarCampo.focus();
}

colarCampo.addEventListener('input', () => {
  btnColarConverter.classList.toggle('hidden', !colarCampo.value.trim());
});

btnColarConverter.addEventListener('click', () => {
  const colado = arquivoDoConteudoColado(comoDadosColados({ 'text/plain': colarCampo.value }));
  if (colado) novaSelecao([colado]);
});

// No Mac, o atalho é Cmd+V
if (/Mac/.test(navigator.platform || navigator.userAgent)) {
  document.querySelectorAll('[data-atalho-colar]').forEach(el => { el.textContent = 'Cmd+V'; });
}

fileInput.addEventListener('change', (e) => {
  if (e.target.files.length > 0) {
    novaSelecao(Array.from(e.target.files));
    // Reseta o input para permitir selecionar o mesmo arquivo novamente se desejar
    e.target.value = '';
  }
});

// Documentos escolhidos agora começam sem a citação pela forma e com o cabeçalho: as
// opções valem para a seleção em que a pessoa clicou no botão, e não para as seguintes
function novaSelecao(files) {
  citacaoPorRecuo = false;
  omitirCabecalho = false;
  resAjustes.open = false;
  mostrarCampoDeColar(false);
  processFiles(files);
}

// Liga ou desliga a citação pela forma e converte de novo os mesmos arquivos
btnCitacao.addEventListener('click', () => {
  if (ultimosArquivos.length === 0) return;
  citacaoPorRecuo = !citacaoPorRecuo;
  processFiles(ultimosArquivos);
});

// Omite ou devolve o cabeçalho e converte de novo os mesmos arquivos. A conversão é
// refeita, e não só recortada na tela, porque a divisão em partes muda sem o cabeçalho
btnCabecalho.addEventListener('click', () => {
  if (ultimosArquivos.length === 0) return;
  omitirCabecalho = !omitirCabecalho;
  processFiles(ultimosArquivos);
});

// Mudar uma opção com o resultado na tela converte de novo os mesmos arquivos. Sem isso,
// a opção só valia no próximo envio, e nada na página avisava. O campo numérico dispara
// 'change' ao sair dele ou com Enter, e não a cada tecla
[optMaxKb, optForcarUnico].forEach(opcao => {
  opcao.addEventListener('change', () => {
    if (ultimosArquivos.length === 0 || !isPyodideReady) return;
    processFiles(ultimosArquivos).then((convertido) => {
      if (convertido) showToast('Convertido de novo com as opções novas.');
    });
  });
});

// Converte um ou vários documentos. Com mais de um, os arquivos gerados por todos eles
// são reunidos numa lista só, e o ZIP do topo leva o conjunto inteiro.
async function processFiles(files) {
  if (!isPyodideReady) {
    showToast('Aguarde o conversor terminar de carregar.');
    return;
  }
  const selecao = ++numeroDaSelecao;
  const maxKb = Math.min(27, Math.max(5, parseInt(optMaxKb.value, 10) || 22));
  optMaxKb.value = String(maxKb);
  const opcoes = {
    maxKb,
    forcarUnico: optForcarUnico.checked,
    citacaoPorRecuo,
    omitirCabecalho,
  };
  // O resultado anterior não pode ficar ativo durante outra conversão, nem depois de uma
  // falha: a pessoa copiaria o HTML do documento errado. Numa seleção nova, ele sai da
  // tela. Ao converter de novo os mesmos arquivos (opção ou citação), fica esmaecido e
  // inativo até o novo resultado chegar, para a tela não piscar
  if (files === ultimosArquivos) {
    suspenderResultado();
  } else {
    ocultarResultado();
  }
  ultimosArquivos = files;
  if (files.length === 1) {
    return processFile(files[0], selecao, opcoes);
  }

  const startTime = performance.now();
  emLote = true;
  origemColada = false;
  currentOriginalName = `${files.length} documentos`;

  const gerados = [];
  const avisos = [];
  const falhas = [];
  let citacoes = 0;
  let citacoesEntreAspas = 0;
  let documentosComCitacao = 0;
  const trechos = [];
  let cabecalhos = 0;
  let documentosComCabecalho = 0;
  const trechosCabecalho = [];
  let limiteKb = null;

  for (let i = 0; i < files.length; i++) {
    if (selecao !== numeroDaSelecao) return false;
    const file = files[i];
    mostrarStatusProcessando(`Convertendo ${i + 1} de ${files.length}: ${file.name}...`);
    try {
      const resultado = await converterArquivo(file, opcoes);
      if (selecao !== numeroDaSelecao) return false;
      if (!resultado.sucesso) {
        falhas.push(`${file.name}: ${resultado.erros.join(' ')}`);
        continue;
      }
      // A origem acompanha o arquivo: dois documentos podem gerar o mesmo nome de
      // saída (nota.odt e nota.docx viram nota_SEI.html), e sem separá-los um
      // sobrescreveria o outro dentro do ZIP
      const origem = resultado.nome_origem || file.name;
      resultado.arquivos.forEach(arq => gerados.push({ ...arq, origem }));
      limiteKb = resultado.limite_kb ?? limiteKb;
      (resultado.avisos || []).forEach(a => avisos.push(`${file.name}: ${a}`));
      if (resultado.citacoes_por_recuo || resultado.citacoes_entre_aspas) {
        citacoes += resultado.citacoes_por_recuo || 0;
        citacoesEntreAspas += resultado.citacoes_entre_aspas || 0;
        documentosComCitacao += 1;
        (resultado.citacoes_trechos || []).forEach(t => trechos.push(`${file.name}: ${t}`));
      }
      if (resultado.cabecalho_paragrafos) {
        cabecalhos += resultado.cabecalho_paragrafos;
        documentosComCabecalho += 1;
        (resultado.cabecalho_trechos || []).forEach(t => trechosCabecalho.push(`${file.name}: ${t}`));
      }
    } catch (err) {
      if (selecao !== numeroDaSelecao) return false;
      falhas.push(`${file.name}: ${err.message || err}`);
    }
  }

  const elapsedSeconds = (performance.now() - startTime) / 1000;

  if (gerados.length === 0) {
    ocultarResultado();
    mostrarStatusErro('Nenhum documento pôde ser convertido', falhas.join(' | '));
    return false;
  }

  currentResultFiles = gerados;
  renderResults(
    {
      arquivos: gerados,
      avisos: avisos.concat(falhas),
      citacoes_por_recuo: citacoes,
      citacoes_entre_aspas: citacoesEntreAspas,
      citacoes_trechos: trechos,
      documentos_com_citacao: documentosComCitacao,
      cabecalho_paragrafos: cabecalhos,
      cabecalho_trechos: trechosCabecalho,
      documentos_com_cabecalho: documentosComCabecalho,
      limite_kb: limiteKb,
    },
    elapsedSeconds
  );

  const resumo = falhas.length
    ? `${files.length - falhas.length} de ${files.length} documentos convertidos em ${formatarSegundos(elapsedSeconds)}. ${plural(falhas.length, 'falhou', 'falharam')}.`
    : `${files.length} documentos convertidos em ${formatarSegundos(elapsedSeconds)}, com ${plural(gerados.length, 'arquivo gerado', 'arquivos gerados')}.`;
  mostrarStatusSoParaLeitorDeTela(resumo);
  return true;
}

// Resultado fora de uso: escondido (seleção nova ou falha) ou suspenso (conversão dos
// mesmos arquivos em andamento). O inert tira os botões do alcance do teclado também
function ocultarResultado() {
  destacarEnvio(true);
  reativarResultado();
  resultsSection.classList.add('hidden');
  currentResultFiles = [];
}

function suspenderResultado() {
  resultsSection.classList.add('opacity-50');
  resultsSection.inert = true;
  resultsSection.setAttribute('aria-busy', 'true');
}

function reativarResultado() {
  resultsSection.classList.remove('opacity-50');
  resultsSection.inert = false;
  resultsSection.removeAttribute('aria-busy');
}

// Estados do cartão de status. No erro, o vermelho fica no ícone e no título: com a
// explicação também em vermelho, o quadro inteiro pesava e cansava a leitura. O ícone
// acompanha a primeira linha, e não o meio do quadro, quando o texto ocupa várias
const CLASSE_QUADRO_ERRO = 'bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-center justify-between transition-all duration-300';
const CLASSE_DESCRICAO_ERRO = 'text-sm text-slate-700';

function mostrarStatusProcessando(titulo) {
  statusRelato.classList.add('hidden');
  statusOcrIniciar.classList.add('hidden');
  statusProgresso.classList.add('hidden');
  pyodideStatusCard.className = 'bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-center justify-between transition-all duration-300';
  statusSpinner.className = 'animate-spin text-blue-600 self-start';
  statusSpinner.innerHTML = '<i data-lucide="loader-2" class="w-5 h-5"></i>';
  statusTitle.className = 'text-sm font-semibold text-blue-900';
  statusTitle.textContent = titulo;
  statusDesc.className = 'text-sm text-blue-700';
  statusDesc.textContent = 'Aplicando os estilos do SEI aos parágrafos e tabelas.';
  refreshIcons();
}

// Com tudo certo, a situação cabe numa linha sem cor de fundo. O quadro colorido fica
// para carregamento, conversão e erro: antes, o "pronto" aparecia no título, num selo e
// na descrição ao mesmo tempo
function mostrarStatusDiscreto(texto) {
  statusRelato.classList.add('hidden');
  statusOcrIniciar.classList.add('hidden');
  statusProgresso.classList.add('hidden');
  pyodideStatusCard.className = 'flex items-center px-1';
  statusSpinner.innerHTML = '<i data-lucide="check" class="w-4 h-4 text-emerald-700"></i>';
  statusSpinner.className = '';
  statusTitle.className = 'text-sm text-slate-600';
  statusTitle.textContent = texto;
  statusDesc.className = 'hidden';
  refreshIcons();
}

// Com o resultado na tela, o resumo da conversão fica só para o leitor de tela: visível,
// repetia o nome e o número de partes que o quadro do resultado mostra logo abaixo. O
// tempo passa para o quadro do resultado
function mostrarStatusSoParaLeitorDeTela(texto) {
  mostrarStatusDiscreto(texto);
  pyodideStatusCard.className = 'sr-only';
}

// Trecho da mensagem do pdf_converter para o PDF sem camada de texto. O teste
// test_mensagem_do_pdf_sem_texto_oferece_o_ocr confere que os dois batem
const MARCA_PDF_SEM_TEXTO = 'não tem camada de texto';

function mostrarStatusErro(titulo, descricao) {
  registrarParaRelato(titulo, [descricao]);
  statusRelato.classList.remove('hidden');
  statusProgresso.classList.add('hidden');
  const semTexto = String(descricao || '').includes(MARCA_PDF_SEM_TEXTO);
  // O reconhecimento é de um documento por vez: no lote, a falha fica na lista
  statusOcrIniciar.classList.toggle('hidden', !(semTexto && ultimosArquivos.length === 1));
  pyodideStatusCard.className = CLASSE_QUADRO_ERRO;
  statusSpinner.innerHTML = '<i data-lucide="alert-circle" class="w-5 h-5 text-rose-600"></i>';
  statusSpinner.className = 'self-start';
  statusTitle.className = 'text-sm font-semibold text-rose-900';
  statusTitle.textContent = titulo;
  statusDesc.className = CLASSE_DESCRICAO_ERRO;
  statusDesc.textContent = descricao || 'Verifique o formato do documento.';
  refreshIcons();
}

// Andamento do OCR: a barra mede o documento inteiro, e não a página, para não voltar
// ao zero a cada página. Antes das páginas (download e preparo do motor), a barra some e
// só a etapa aparece, porque a porcentagem ali é da etapa. O aviso vai em letra menor,
// abaixo: antes, etapa, porcentagem e aviso vinham emendados na mesma frase
function mostrarAndamentoOcr({ etapa, pagina, total, fracao }) {
  statusProgresso.classList.remove('hidden');
  statusProgressoTrilho.classList.toggle('hidden', !pagina);
  // Com três linhas, o ícone fica na altura do título, e não no meio do quadro
  statusSpinner.className = 'animate-spin text-blue-600 self-start mt-px';
  let porcento = null;
  if (pagina) {
    statusTitle.textContent = 'Reconhecendo o texto';
    statusProgressoEtapa.textContent = `Página ${pagina} de ${total}`;
    porcento = Math.round(((pagina - 1 + (fracao || 0)) / total) * 100);
  } else {
    statusTitle.textContent = 'Preparando o reconhecimento de texto';
    statusProgressoEtapa.textContent = etapa;
    if (typeof fracao === 'number') porcento = Math.round(fracao * 100);
  }
  statusProgressoPorcento.textContent = porcento === null ? '' : `${porcento}%`;
  if (pagina) statusProgressoBarra.style.width = `${porcento}%`;
  const aviso = 'O documento não sai do computador. O texto reconhecido pode conter erros.'
    + (pagina ? '' : ' Na primeira vez, a página baixa cerca de 7 MB.');
  // O Tesseract informa o andamento dezenas de vezes por página: o aviso e o ícone só
  // são refeitos quando o texto muda
  if (statusDesc.lastElementChild?.textContent === aviso) return;
  statusDesc.className = 'flex items-start gap-1.5 text-xs text-blue-700/80';
  statusDesc.innerHTML = '<i data-lucide="lock" class="w-3.5 h-3.5 mt-px shrink-0"></i><span></span>';
  statusDesc.lastElementChild.textContent = aviso;
  refreshIcons();
}

// OCR no navegador para o PDF sem camada de texto. O PDF.js desenha cada página numa
// imagem e o Tesseract reconhece o texto em português. Tudo vem de vendor/ e só é
// baixado quando alguém pede o reconhecimento: são cerca de 7 MB, e a maioria dos
// documentos não precisa deles. O documento não sai do navegador
// A versão legacy do PDF.js traz quase todos os recursos novos de JavaScript que ele usa
// (Map.getOrInsertComputed): sem eles, o OCR falhava no Samsung Internet do Android. O
// que ela não traz vem de pdfjs-compativel.js, na página e no worker
const VERSAO_PDFJS = 'legacy-6.3.289';
const PASTA_PDFJS = `vendor/pdfjs-${VERSAO_PDFJS}/`;
const OCR = {
  pdfjsCompativel: 'pdfjs-compativel.js',
  pdfjs: `${PASTA_PDFJS}pdf.min.js`,
  // Importa o worker da PASTA_PDFJS depois de completar os recursos
  pdfjsWorker: `pdfjs-worker-${VERSAO_PDFJS}.js`,
  // Decodificadores de imagem (JBIG2 e JPEG 2000), comuns em documento digitalizado
  pdfjsWasm: `${PASTA_PDFJS}wasm/`,
  tesseract: 'vendor/tesseract-7.0.0/tesseract.min.js',
  tesseractWorker: 'vendor/tesseract-7.0.0/worker.min.js',
  // O Tesseract escolhe a variante do motor que o navegador suporta (com ou sem SIMD)
  tesseractCore: 'vendor/tesseract-core-7.0.0',
  // Modelo de português compacto (best_int): 1,3 MB, com a precisão do modelo completo
  tessdata: 'vendor/tessdata-4.0.0-best-int',
};
// A página vira imagem a 216 dpi (3 x 72). Menos que isso, o Tesseract erra letras
// pequenas; mais, a imagem de uma página A4 passa do limite de canvas do Safari no iPhone
const ESCALA_OCR = 3;

// O texto reconhecido fica guardado por arquivo: mudar uma opção converte de novo os
// mesmos arquivos, e sem isso o PDF voltaria a falhar por falta de texto
const textosReconhecidos = new WeakMap();

function enderecoLocal(caminho) {
  return new URL(caminho, window.location.href).href;
}

function carregarScriptLocal(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Falha ao carregar ${src}`));
    document.head.appendChild(script);
  });
}

// Etapas do Tesseract, na língua da página. O andamento aparece no quadro de situação:
// num celular lento, o reconhecimento leva minutos, e sem ele a página parecia parada
const ETAPAS_DO_TESSERACT = {
  'loading tesseract core': 'Carregando o motor de OCR',
  'initializing tesseract': 'Iniciando o motor de OCR',
  'loading language traineddata': 'Carregando o modelo de português',
  'initializing api': 'Iniciando o reconhecimento',
  'recognizing text': 'Reconhecendo',
};

// `informar({ etapa, pagina, total, fracao })` recebe cada passo: antes das páginas, a
// etapa e o andamento dela; depois, a página e o andamento dentro dela
async function reconhecerTextoDoPdf(file, informar) {
  informar({ etapa: 'Carregando o OCR' });
  // O Tesseract baixa junto com o PDF.js: numa rede de celular, em sequência a espera
  // seria a soma das duas. Só o PDF.js precisa esperar os recursos que completam o navegador
  const [pdfjs] = await Promise.all([
    import(enderecoLocal(OCR.pdfjsCompativel)).then(() => import(enderecoLocal(OCR.pdfjs))),
    window.Tesseract ? null : carregarScriptLocal(enderecoLocal(OCR.tesseract)),
  ]);

  // O worker do PDF.js é criado aqui, e não pelo PDF.js, para a página ouvir os erros
  // dele: um erro dentro do worker não rejeita a promessa do PDF.js, e o OCR ficava
  // parado em "Abrindo o PDF..." sem dizer nada. `comOWorker` encerra a espera no erro
  const workerDoPdf = new Worker(enderecoLocal(OCR.pdfjsWorker), { type: 'module' });
  const falhaDoWorker = new Promise((_, rejeitar) => {
    workerDoPdf.addEventListener('error', (evento) => {
      // Sem mensagem, o arquivo do worker não carregou (sem rede ou fora do site), e
      // atualizar o navegador não resolveria
      rejeitar(new Error(evento.message
        ? `O leitor de PDF parou com um erro (${evento.message}). Atualize o navegador ou tente em outro.`
        : 'Não foi possível carregar o leitor de PDF. Confira a conexão e tente de novo.'));
    });
  });
  // Sem isto, a rejeição ficaria sem tratamento quando o erro chega entre duas esperas
  falhaDoWorker.catch(() => {});
  const comOWorker = (promessa) => Promise.race([promessa, falhaDoWorker]);
  let leitor = null;
  let carregamento = null;
  try {
    leitor = pdfjs.PDFWorker.create({ port: workerDoPdf });
    informar({ etapa: 'Abrindo o PDF' });
    carregamento = pdfjs.getDocument({
      worker: leitor,
      data: new Uint8Array(await file.arrayBuffer()),
      wasmUrl: enderecoLocal(OCR.pdfjsWasm),
      isEvalSupported: false,
      // JPEG pelo decodificador do próprio PDF.js, e não pelo ImageDecoder do navegador:
      // no WebKit de Linux, a página em JPEG (o formato comum da digitalização) saía em
      // branco, sem erro, e o OCR não achava texto
      isImageDecoderSupported: false,
    });
    const pdf = await comOWorker(carregamento.promise);
    return await reconhecerPaginas(pdf, comOWorker, informar);
  } finally {
    // No PDF.js 6, quem libera o documento é a tarefa de carregamento. Ela espera a
    // resposta do worker, que não vem se ele parou com erro. O worker criado pela página
    // não é encerrado pelo PDF.js: fica por conta dela
    try {
      await comOWorker(carregamento?.destroy());
    } catch {
      // O erro que importa é o do reconhecimento, que segue adiante
    }
    leitor?.destroy();
    workerDoPdf.terminate();
  }
}

async function reconhecerPaginas(pdf, comOWorker, informar) {
  let paginaAtual = 0;
  informar({ etapa: 'Preparando o motor de OCR' });
  // O worker vem do próprio site, e não de um blob: assim o service worker o controla e
  // guarda o motor e o modelo para uso sem rede. O cache do Tesseract (IndexedDB) seria
  // uma segunda cópia do modelo
  const reconhecedor = await window.Tesseract.createWorker('por', window.Tesseract.OEM.LSTM_ONLY, {
    workerPath: enderecoLocal(OCR.tesseractWorker),
    corePath: enderecoLocal(OCR.tesseractCore),
    langPath: enderecoLocal(OCR.tessdata),
    workerBlobURL: false,
    cacheMethod: 'none',
    logger: (m) => {
      const fracao = typeof m.progress === 'number' ? m.progress : undefined;
      if (paginaAtual) {
        if (m.status === 'recognizing text') informar({ pagina: paginaAtual, total: pdf.numPages, fracao });
      } else {
        informar({ etapa: ETAPAS_DO_TESSERACT[m.status] || m.status, fracao });
      }
    },
  });
  try {
    const paginas = [];
    for (let numero = 1; numero <= pdf.numPages; numero++) {
      paginaAtual = numero;
      informar({ pagina: numero, total: pdf.numPages, fracao: 0 });
      const pagina = await comOWorker(pdf.getPage(numero));
      const viewport = pagina.getViewport({ scale: ESCALA_OCR });
      const canvas = document.createElement('canvas');
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      await comOWorker(pagina.render({ canvas, viewport }).promise);
      const { data } = await reconhecedor.recognize(canvas);
      paginas.push(data.text);
      pagina.cleanup();
      // Devolve a memória da imagem antes da próxima página
      canvas.width = 0;
      canvas.height = 0;
    }
    return paginas.join('\n\n');
  } finally {
    await reconhecedor.terminate();
  }
}

statusOcrIniciar.addEventListener('click', async () => {
  const file = ultimosArquivos[0];
  if (!file || ultimosArquivos.length !== 1) return;
  const selecao = numeroDaSelecao;
  mostrarStatusProcessando('Preparando o reconhecimento de texto');
  try {
    const texto = await reconhecerTextoDoPdf(file, (andamento) => {
      if (selecao !== numeroDaSelecao) return;
      mostrarAndamentoOcr(andamento);
    });
    textosReconhecidos.set(file, texto);
  } catch (err) {
    if (selecao !== numeroDaSelecao) return;
    console.error('Erro no OCR:', err);
    mostrarStatusErro('Não foi possível reconhecer o texto', err.message || String(err));
    return;
  }
  // Outra seleção durante o reconhecimento: o texto fica guardado, mas a tela é dela
  if (selecao !== numeroDaSelecao) return;
  processFiles(ultimosArquivos);
});

// Converte um arquivo e devolve o resultado já decodificado do Python
async function converterArquivo(file, opcoes) {
  const arrayBuffer = await file.arrayBuffer();
  const bytes = new Uint8Array(arrayBuffer);
  const textoReconhecido = textosReconhecidos.get(file);

  return executarNoPyodide(async () => {
    pyodideInstance.globals.set('temp_filename', file.name);
    pyodideInstance.globals.set('temp_bytes', bytes);
    pyodideInstance.globals.set('temp_max_kb', opcoes.maxKb);
    pyodideInstance.globals.set('temp_forcar_unico', opcoes.forcarUnico);
    // O argumento só vai quando ligado: um pacote ainda em cache, anterior à opção,
    // continua convertendo normalmente
    const argCitacao = opcoes.citacaoPorRecuo ? '\n    citacao_por_recuo=True,' : '';
    const argCabecalho = opcoes.omitirCabecalho ? '\n    omitir_cabecalho=True,' : '';
    if (textoReconhecido !== undefined) pyodideInstance.globals.set('temp_texto_reconhecido', textoReconhecido);
    const argOcr = textoReconhecido !== undefined ? '\n    texto_reconhecido=temp_texto_reconhecido,' : '';
    const argColado = file.colado ? '\n    colado=True,' : '';

    const jsonStr = await pyodideInstance.runPythonAsync(`
import conversorsei.web

res_json = conversorsei.web.converter_memoria_json(
    nome_arquivo=temp_filename,
    conteudo_bytes=bytes(temp_bytes.to_py()),
    # Sempre o HTML completo: "só o corpo" servia apenas ao Inserir HTML do SEI Pro e saiu
    # da tela. O parâmetro so_corpo continua no pacote e na CLI (--corpo), como reserva
    so_corpo=False,
    forcar_unico=bool(temp_forcar_unico),
    max_kb=int(temp_max_kb),
    validar=True,${argCitacao}${argCabecalho}${argOcr}${argColado}
)
# Sem isto o documento inteiro fica preso no dicionário global do Python até a
# conversão seguinte, o que pesa no modo em lote
del temp_bytes
globals().pop('temp_texto_reconhecido', None)
res_json
`);

    const resultado = JSON.parse(jsonStr);
    registrarConversao(file, resultado.sucesso);
    return resultado;
  });
}

// Conta a conversão no GoatCounter como evento. Vai só a extensão e o desfecho, nunca o
// nome do arquivo, que pode identificar o processo. Sem rede ou com o contador bloqueado,
// window.goatcounter não existe e a conversão segue sem contar.
function registrarConversao(file, sucesso) {
  if (!window.goatcounter || typeof window.goatcounter.count !== 'function') return;
  const ponto = file.name.lastIndexOf('.');
  let extensao = ponto >= 0 ? file.name.slice(ponto + 1).toLowerCase() : 'sem-extensao';
  // O texto colado conta à parte, pela forma em que chegou
  if (file.colado) extensao = `colado-${extensao}`;
  try {
    window.goatcounter.count({
      path: `conversao-${extensao}${sucesso ? '' : '-falha'}`,
      title: file.colado ? `Conversão de texto colado (${extensao.slice(7)})` : `Conversão de .${extensao}`,
      event: true,
    });
  } catch {
    // A contagem nunca pode interromper a conversão
  }
}

// Processamento do Arquivo
async function processFile(file, selecao, opcoes) {
  if (!isPyodideReady) {
    showToast('Aguarde o conversor terminar de carregar.');
    return;
  }

  emLote = false;
  origemColada = Boolean(file.colado);
  currentOriginalName = file.name;
  const nomeNaTela = origemColada ? 'Texto colado' : file.name;
  const startTime = performance.now();
  mostrarStatusProcessando(origemColada ? 'Convertendo o texto colado...' : `Convertendo ${file.name}...`);

  try {
    const result = await converterArquivo(file, opcoes);
    if (selecao !== numeroDaSelecao) return false;
    const elapsedSeconds = (performance.now() - startTime) / 1000;

    if (!result.sucesso) {
      throw new Error(result.erros.join('\n') || 'Falha ao converter documento.');
    }

    currentResultFiles = result.arquivos;
    renderResults(result, elapsedSeconds);
    const partes = result.arquivos.length === 1 ? 'em arquivo único' : `em ${result.arquivos.length} partes`;
    mostrarStatusSoParaLeitorDeTela(`${nomeNaTela} convertido em ${formatarSegundos(elapsedSeconds)}, ${partes}.`);
  } catch (err) {
    if (selecao !== numeroDaSelecao) return false;
    console.error('Erro na conversão:', err);
    ocultarResultado();
    mostrarStatusErro(origemColada ? 'Erro ao converter o texto colado' : 'Erro ao converter documento', err.message);
    return false;
  }
  return true;
}

// Quantos trechos o quadro da citação mostra. Acima disso, a lista empurraria o
// resultado para longe, e o começo já basta para reconhecer o tipo de parágrafo
const MAXIMO_TRECHOS = 5;

// Quadro da citação pela forma: diz quantos parágrafos têm forma de citação (recuados
// em fonte menor, ou inteiros entre aspas), mostra o começo deles e oferece a troca (ou
// o desfazer), já que a conversão não aplica as regras sozinha
function renderCitacao(recuo, aspas, documentos, trechos) {
  const total = recuo + aspas;
  if (total === 0) {
    resCitacaoCard.classList.add('hidden');
    resCitacaoResumo.classList.add('hidden');
    return;
  }
  const um = total === 1;
  const onde = emLote && documentos > 1 ? ` em ${documentos} documentos` : '';
  const partes = `${recuo} ${recuo === 1 ? 'recuado' : 'recuados'} e em fonte menor que a do texto e ` +
    `${aspas} ${aspas === 1 ? 'inteiro' : 'inteiros'} entre aspas`;
  if (citacaoPorRecuo) {
    if (recuo && aspas) {
      resCitacaoTexto.textContent = `${total} parágrafos${onde} foram convertidos como Citação: ${partes}.`;
    } else {
      const forma = recuo
        ? (um ? 'recuado e em fonte menor que a do texto' : 'recuados e em fonte menor que a do texto')
        : (um ? 'inteiro entre aspas' : 'inteiros entre aspas');
      resCitacaoTexto.textContent = um
        ? `1 parágrafo ${forma}${onde} foi convertido como Citação.`
        : `${total} parágrafos ${forma}${onde} foram convertidos como Citação.`;
    }
    btnCitacao.textContent = 'Manter citações como texto';
    resCitacaoResumo.textContent = `Citações: ${total} convertidas`;
  } else {
    if (recuo && aspas) {
      resCitacaoTexto.textContent =
        `${total} parágrafos${onde} parecem citações: ${partes}. Eles saíram como texto comum.`;
    } else if (recuo) {
      resCitacaoTexto.textContent = um
        ? `1 parágrafo${onde} está recuado e em fonte menor que a do texto, como uma citação. Ele saiu como texto comum.`
        : `${total} parágrafos${onde} estão recuados e em fonte menor que a do texto, como citações. Eles saíram como texto comum.`;
    } else {
      resCitacaoTexto.textContent = um
        ? `1 parágrafo${onde} está inteiro entre aspas e passa de uma linha, como uma citação. Ele saiu como texto comum.`
        : `${total} parágrafos${onde} estão inteiros entre aspas e passam de uma linha, como citações. Eles saíram como texto comum.`;
    }
    btnCitacao.textContent = 'Converter como citação';
    resCitacaoResumo.textContent = `Citações: ${total} possíveis`;
  }
  const itens = trechos.slice(0, MAXIMO_TRECHOS).map(t => `<li>${escapeHtml(t)}</li>`);
  if (trechos.length > MAXIMO_TRECHOS) {
    itens.push(`<li class="list-none not-italic">e mais ${trechos.length - MAXIMO_TRECHOS}.</li>`);
  }
  resCitacaoTrechos.innerHTML = itens.join('');
  resCitacaoCard.classList.remove('hidden');
  resCitacaoResumo.classList.remove('hidden');
}

// Quadro do cabeçalho: diz quantos parágrafos vêm antes do item 1, mostra o começo deles
// e oferece omiti-los (ou o desfazer). Sem item 1, a conversão não acha cabeçalho, e o
// quadro não aparece
function renderCabecalho(total, documentos, trechos) {
  if (total === 0) {
    resCabecalhoCard.classList.add('hidden');
    resCabecalhoResumo.classList.add('hidden');
    return;
  }
  const um = total === 1;
  const onde = emLote && documentos > 1 ? ` em ${documentos} documentos` : '';
  if (omitirCabecalho) {
    resCabecalhoTexto.textContent = um
      ? `1 parágrafo antes do item 1${onde} foi omitido. O HTML copiado começa no item 1.`
      : `${total} parágrafos antes do item 1${onde} foram omitidos. O HTML copiado começa no item 1.`;
    btnCabecalho.textContent = 'Restaurar cabeçalho';
    resCabecalhoResumo.textContent = `Cabeçalho: ${total} ${um ? 'parágrafo omitido' : 'parágrafos omitidos'}`;
  } else {
    resCabecalhoTexto.textContent = um
      ? `1 parágrafo vem antes do item 1${onde}. Ele entra no HTML copiado. Se o SEI já gera o título e o número, omita.`
      : `${total} parágrafos vêm antes do item 1${onde}. Eles entram no HTML copiado. Se o SEI já gera o título e o número, omita.`;
    btnCabecalho.textContent = 'Omitir cabeçalho';
    resCabecalhoResumo.textContent = `Cabeçalho: ${total} ${um ? 'parágrafo incluído' : 'parágrafos incluídos'}`;
  }
  const itens = trechos.slice(0, MAXIMO_TRECHOS).map(t => `<li>${escapeHtml(t)}</li>`);
  if (trechos.length > MAXIMO_TRECHOS) {
    itens.push(`<li class="list-none not-italic">e mais ${trechos.length - MAXIMO_TRECHOS}.</li>`);
  }
  resCabecalhoTrechos.innerHTML = itens.join('');
  resCabecalhoCard.classList.remove('hidden');
  resCabecalhoResumo.classList.remove('hidden');
}

// Avisa quando o arquivo não cabe numa colagem no SEI Pro. Caber é o normal: repetido
// em verde em cada parte, o "cabe no limite" virava ruído. Um pacote antigo, ainda no
// cache, não manda a informação, e o cartão mostra só o tamanho
function situacaoDoLimite(arq, limiteKb) {
  if (arq.cabe_no_limite !== false || !limiteKb) return '';
  return `<span class="inline-flex items-center gap-1 text-amber-700">
    <i data-lucide="alert-triangle" class="w-3.5 h-3.5"></i>Acima do limite do SEI Pro (${limiteKb} KB): a formatação pode se perder ao colar</span>`;
}

// Depois da primeira conversão, o resultado é o que importa: a área de envio encolhe para
// uma faixa e deixa de empurrar o resultado para baixo. Arrastar continua valendo
function compactarAreaDeEnvio() {
  dropDetalhes.forEach(el => el.classList.add('hidden'));
  // Sem o limite de largura: título e os dois botões cabem numa linha só
  dropConteudo.classList.add('sm:flex', 'sm:items-center', 'sm:justify-center', 'sm:gap-4', 'sm:space-y-0', 'sm:max-w-none');
  dropZone.classList.remove('p-6', 'sm:p-8');
  dropZone.classList.add('p-4');
  dropTitulo.textContent = 'Converter outro documento';
  dropTitulo.classList.remove('hidden');
}

// O passo de colar as partes só aparece quando algum documento foi dividido. No lote,
// cada documento é uma origem, e é dividido quando gerou mais de um arquivo
function ajustarGuia(arquivos) {
  const porOrigem = {};
  arquivos.forEach(arq => { porOrigem[arq.origem || ''] = (porOrigem[arq.origem || ''] || 0) + 1; });
  const dividido = Object.values(porOrigem).some(n => n > 1);
  guiaPartes.classList.toggle('hidden', !dividido);
  guiaPassos.classList.toggle('md:grid-cols-2', !dividido);
  guiaPassos.classList.toggle('md:grid-cols-3', dividido);
}

// Com o resultado na tela, a ação principal é copiar: o botão de enviar outro arquivo
// passa a ter contorno, como Baixar, e deixa de disputar a atenção com Copiar. Sem
// resultado (erro ou seleção nova), volta a ser o botão principal
const CLASSES_BOTAO_PRINCIPAL = ['bg-blue-700', 'hover:bg-blue-800', 'active:bg-blue-800', 'text-white'];
const CLASSES_BOTAO_SECUNDARIO = ['bg-white', 'hover:bg-slate-50', 'active:bg-slate-100', 'text-slate-700', 'border', 'border-slate-300'];

function destacarEnvio(principal) {
  btnSelecionar.classList.remove(...(principal ? CLASSES_BOTAO_SECUNDARIO : CLASSES_BOTAO_PRINCIPAL));
  btnSelecionar.classList.add(...(principal ? CLASSES_BOTAO_PRINCIPAL : CLASSES_BOTAO_SECUNDARIO));
}

// Renderização dos Resultados
function renderResults(result, segundos) {
  registrarParaRelato(
    `Conversão concluída, ${plural(result.arquivos.length, 'arquivo gerado', 'arquivos gerados')}`,
    result.avisos || []
  );
  compactarAreaDeEnvio();
  destacarEnvio(false);
  reativarResultado();
  // Depois da conversão, o arquivo pronto aparece antes da área de novo envio.
  if (resultsSection.previousElementSibling !== pyodideStatusCard) {
    pyodideStatusCard.after(resultsSection);
  }
  resultsSection.classList.remove('hidden');
  resFilename.textContent = origemColada ? 'Texto colado' : currentOriginalName;
  
  const totalPartes = result.arquivos.length;
  if (totalPartes === 1) {
    resPartsCount.textContent = '1 arquivo gerado';
  } else {
    resPartsCount.textContent = emLote ? `${totalPartes} arquivos gerados` : `${totalPartes} partes geradas`;
  }
  if (typeof segundos === 'number') resPartsCount.textContent += ` em ${formatarSegundos(segundos)}`;

  // Exibir botão de download no topo apenas quando for particionado (Download do ZIP com tudo)
  if (totalPartes > 1) {
    resActionsTop.classList.remove('hidden');
    btnDownloadTopText.textContent = emLote ? 'Baixar todos os arquivos (ZIP)' : 'Baixar todas as partes (ZIP)';
    btnDownloadTop.onclick = downloadAllZip;
  } else {
    // Para arquivo único, oculta o botão do topo para não duplicar com os botões do card logo abaixo
    resActionsTop.classList.add('hidden');
  }

  // Avisos de validação
  if (result.avisos && result.avisos.length > 0) {
    resWarningsCard.classList.remove('hidden');
    resWarningsList.innerHTML = result.avisos.map(a => `<li>${formatarAviso(a)}</li>`).join('');
  } else {
    resWarningsCard.classList.add('hidden');
    resWarningsList.innerHTML = '';
  }

  renderCabecalho(result.cabecalho_paragrafos || 0, result.documentos_com_cabecalho || 0, result.cabecalho_trechos || []);
  renderCitacao(
    result.citacoes_por_recuo || 0,
    result.citacoes_entre_aspas || 0,
    result.documentos_com_citacao || 0,
    result.citacoes_trechos || []
  );
  resAjustes.classList.toggle('hidden', resCabecalhoCard.classList.contains('hidden') && resCitacaoCard.classList.contains('hidden'));
  ajustarGuia(result.arquivos);

  // No lote, cada documento pode ter várias partes, e elas saem em sequência. O rótulo
  // diz a qual documento a parte pertence e qual é a posição dela, para colar na ordem
  const partesPorOrigem = {};
  result.arquivos.forEach(arq => {
    if (arq.origem) partesPorOrigem[arq.origem] = (partesPorOrigem[arq.origem] || 0) + 1;
  });
  const posicaoNaOrigem = {};

  // Cards das partes
  resPartsList.innerHTML = '';
  result.arquivos.forEach((arq, index) => {
    const card = document.createElement('div');
    // Informações em cima e botões embaixo: na coluna estreita da página, lado a lado, o
    // nome, o tamanho e o limite quebravam em três linhas
    card.className = 'bg-white border border-slate-200 rounded-xl p-4 sm:p-5 flex flex-col gap-3 transition-colors';
    card.dataset.parte = String(index);
    
    // O rótulo diz o que o arquivo é. O nome do arquivo vai em segundo plano: no
    // documento único, ele só repetia o nome já exibido no cabeçalho do resultado
    let rotulo = 'Arquivo pronto para o SEI';
    if (arq.origem) {
      posicaoNaOrigem[arq.origem] = (posicaoNaOrigem[arq.origem] || 0) + 1;
      const total = partesPorOrigem[arq.origem];
      rotulo = total > 1 ? `${arq.origem}, parte ${posicaoNaOrigem[arq.origem]} de ${total}` : arq.origem;
    } else if (totalPartes > 1) {
      rotulo = `Parte ${index + 1} de ${totalPartes}`;
    }

    card.innerHTML = `
      <div class="space-y-1 min-w-0 flex-1">
        <div class="flex items-start justify-between gap-3">
          <p class="font-semibold text-sm text-slate-800 break-all">${escapeHtml(rotulo)}</p>
          <span data-marca-copiada class="hidden shrink-0 items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-400/15 text-xs font-semibold text-emerald-700">
            <i data-lucide="check" class="w-3.5 h-3.5"></i>Copiada
          </span>
        </div>
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500">
          <span class="break-all">${escapeHtml(arq.nome)}</span>
          <span>•</span>
          <span>${formatarNumero(arq.tamanho_kb, 1)} KB</span>
          ${situacaoDoLimite(arq, result.limite_kb)}
        </div>
      </div>

      <!-- No celular, Copiar ocupa a linha e os outros dois dividem a de baixo: com três
           botões empilhados, um documento em três partes virava nove botões na tela -->
      <div class="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        <!-- Copiar vem primeiro e em destaque: é o caminho do guia, colar no editor do SEI -->
        <button 
          data-copy-idx="${index}"
          data-rotulo="${escapeHtml(rotulo)}"
          aria-label="Copiar para o SEI: ${escapeHtml(rotulo)}"
          class="btn-copy rotulos-sobrepostos col-span-2 sm:col-span-1 inline-grid place-items-center px-4 py-2.5 bg-blue-700 hover:bg-blue-800 active:bg-blue-800 text-white text-sm font-semibold rounded-lg transition-colors"
          title="Copiar o conteúdo formatado para colar no editor do SEI"
        >
          <span class="rotulo-copiar inline-flex items-center gap-2"><i data-lucide="copy" class="w-4 h-4"></i>Copiar para o SEI</span>
          <span class="rotulo-copiado invisible inline-flex items-center gap-2"><i data-lucide="check" class="w-4 h-4"></i>Copiado</span>
        </button>

        <button 
          data-download-idx="${index}"
          class="btn-download inline-flex items-center justify-center gap-2 px-3 py-2 bg-white hover:bg-slate-50 active:bg-slate-100 text-slate-700 text-sm font-medium rounded-lg border border-slate-300 transition-colors"
          title="Baixar o arquivo HTML"
        >
          <i data-lucide="download" class="w-4 h-4 text-slate-500"></i>
          Baixar
        </button>

        <button 
          data-preview-idx="${index}"
          class="btn-preview inline-flex items-center justify-center gap-2 px-3 py-2 bg-white hover:bg-slate-50 active:bg-slate-100 text-slate-700 text-sm font-medium rounded-lg border border-slate-300 transition-colors"
          title="Ver como o documento vai ficar"
        >
          <i data-lucide="eye" class="w-4 h-4 text-slate-500"></i>
          Ver prévia
        </button>
      </div>
    `;

    resPartsList.appendChild(card);
  });

  // Conectar eventos dos botões dos cards
  document.querySelectorAll('.btn-copy').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const botao = e.currentTarget;
      const idx = parseInt(botao.getAttribute('data-copy-idx'), 10);
      const arq = currentResultFiles[idx];
      const copiado = await copiarHtml(arq.conteudo);
      // Sem o HTML, o botão sai do "Copiado" de uma cópia anterior, para não contradizer o alerta
      mostrarCopiado(botao, copiado === 'html');
      if (copiado === 'html') marcarComoCopiada(botao.closest('[data-parte]'));
      if (copiado === 'texto') {
        showToast(
          'Este navegador copiou só o texto, sem a formatação: colado no SEI, ele mostraria as tags. '
          + 'Clique em Baixar, abra o arquivo no navegador e copie de lá (Ctrl+A e Ctrl+C).',
          'alerta'
        );
      } else if (copiado !== 'html') {
        showToast('Não foi possível copiar. Clique em Baixar, abra o arquivo no navegador e copie de lá.', 'alerta');
      }
    });
  });

  document.querySelectorAll('.btn-preview').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const idx = parseInt(e.currentTarget.getAttribute('data-preview-idx'), 10);
      const arq = currentResultFiles[idx];
      abrirPrevia(arq);
    });
  });

  document.querySelectorAll('.btn-download').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const idx = parseInt(e.currentTarget.getAttribute('data-download-idx'), 10);
      const arq = currentResultFiles[idx];
      triggerDownload(arq.nome, arq.conteudo);
    });
  });

  refreshIcons();

  // Rola até o resultado; sem animação para quem pediu movimento reduzido
  const semMovimento = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  resultsSection.scrollIntoView({ behavior: semMovimento ? 'auto' : 'smooth', block: 'nearest' });
}

// O editor do SEI é um CKEditor: ele só interpreta a marcação quando ela chega no
// clipboard como text/html. Copiado como texto puro, o HTML é colado como texto visível,
// com as tags à mostra. O text/plain vai junto para quem cola num editor de código.
//
// Devolve o que conseguiu: 'html', 'texto' (a formatação se perdeu) ou 'falhou'. Antes,
// os três casos davam a mesma mensagem de sucesso, e a colagem no SEI mostrava as tags.
async function copiarHtml(html) {
  if (navigator.clipboard && window.ClipboardItem) {
    try {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([html], { type: 'text/html' }),
          'text/plain': new Blob([html], { type: 'text/plain' }),
        }),
      ]);
      return 'html';
    } catch (err) {
      // Navegador sem suporte ou sem permissão: cai para os modos abaixo
    }
  }

  // Segundo caminho que ainda leva o text/html: o evento de cópia, que navegadores sem
  // ClipboardItem (como o Firefox antes da versão 127) aceitam
  if (copiarPorEventoDeCopia(html)) return 'html';

  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(html);
      return 'texto';
    } catch (err) {
      // Segue para o modo síncrono
    }
  }

  const textarea = document.createElement('textarea');
  textarea.value = html;
  document.body.appendChild(textarea);
  textarea.select();
  const copiou = document.execCommand('copy');
  document.body.removeChild(textarea);
  return copiou ? 'texto' : 'falhou';
}

// Cópia pelo evento 'copy', gravando o text/html diretamente. O Safari só dispara o
// evento quando há algo selecionado, daí a seleção de um trecho escondido
function copiarPorEventoDeCopia(html) {
  let gravou = false;
  const aoCopiar = (e) => {
    e.clipboardData.setData('text/html', html);
    e.clipboardData.setData('text/plain', html);
    e.preventDefault();
    gravou = true;
  };
  const alvo = document.createElement('span');
  alvo.textContent = 'copia';
  alvo.style.cssText = 'position:fixed;left:-9999px;';
  document.body.appendChild(alvo);
  const faixa = document.createRange();
  faixa.selectNodeContents(alvo);
  const selecao = window.getSelection();
  selecao.removeAllRanges();
  selecao.addRange(faixa);
  document.addEventListener('copy', aoCopiar, { once: true });
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch (err) {
    ok = false;
  }
  document.removeEventListener('copy', aoCopiar);
  selecao.removeAllRanges();
  alvo.remove();
  return ok && gravou;
}

// Download em ZIP

async function downloadAllZip() {
  if (!currentResultFiles || currentResultFiles.length === 0) return;

  const zip = new JSZip();
  currentResultFiles.forEach(arq => {
    // No lote, o nome do documento de origem vira pasta, o que também evita que dois
    // documentos com o mesmo nome de saída se sobrescrevam
    zip.file(arq.origem ? `${arq.origem}/${arq.nome}` : arq.nome, arq.conteudo);
  });

  const baseName = currentOriginalName.replace(/\.[^/.]+$/, '');
  const zipFilename = emLote ? 'conversorsei_lote.zip' : `${baseName}_SEI_partes.zip`;

  const blob = await zip.generateAsync({ type: 'blob' });
  triggerBlobDownload(zipFilename, blob);
  showToast(`${zipFilename} baixado.`);
}

// Helper de Download de Arquivo Único
function triggerDownload(filename, content) {
  const blob = new Blob([content], { type: 'text/html;charset=utf-8' });
  triggerBlobDownload(filename, blob);
  showToast(`Download de ${filename} iniciado.`);
}

function triggerBlobDownload(filename, blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 1500);
}

// Prévia. O foco vai para o botão de fechar ao abrir e volta ao botão de origem ao fechar,
// para quem usa teclado ou leitor de tela não se perder na página
let focoAntesDaPrevia = null;

function abrirPrevia(arq) {
  focoAntesDaPrevia = document.activeElement;
  previewTitle.textContent = `Prévia: ${arq.nome}`;
  previewIframe.srcdoc = arq.conteudo;
  previewModal.classList.remove('hidden');
  refreshIcons();
  closePreviewBtn.focus();
}

function fecharPrevia() {
  if (previewModal.classList.contains('hidden')) return;
  previewModal.classList.add('hidden');
  previewIframe.srcdoc = '';
  if (focoAntesDaPrevia && document.contains(focoAntesDaPrevia)) focoAntesDaPrevia.focus();
}

[closePreviewBtn, modalCloseBtn2].forEach(btn => btn.addEventListener('click', fecharPrevia));

previewModal.addEventListener('click', (e) => {
  if (e.target === previewModal) fecharPrevia();
});

document.addEventListener('keydown', (e) => {
  if (previewModal.classList.contains('hidden')) return;
  if (e.key === 'Escape') {
    fecharPrevia();
    return;
  }
  if (e.key !== 'Tab') return;
  // A prévia entra no ciclo para rolar pelo teclado. Com o foco dentro dela, as teclas
  // ficam no iframe (Esc inclusive), e o Tab do navegador leva de volta aos botões
  const focaveis = [closePreviewBtn, previewIframe, modalCloseBtn2];
  const indice = focaveis.indexOf(document.activeElement);
  if (indice === -1 || (e.shiftKey && indice === 0) || (!e.shiftKey && indice === focaveis.length - 1)) {
    e.preventDefault();
    focaveis[e.shiftKey ? focaveis.length - 1 : 0].focus();
  }
});

// Marcas do aviso, aplicadas depois de o texto ser escapado: `[texto](https://...)` e
// endereço https solto viram link, e `**...**`, negrito. O aviso do OCR indica um serviço
// online, e a pessoa teria de copiar o endereço à mão. No endereço solto, a pontuação que
// fecha a frase fica fora do link
function formatarAviso(texto) {
  const link = (url, rotulo) =>
    `<a href="${url}" target="_blank" rel="noopener noreferrer" class="font-semibold underline">${rotulo}</a>`;
  // Uma expressão só para as duas formas de link: em duas passadas, a segunda acharia o
  // endereço dentro do href que a primeira acabou de gerar
  return escapeHtml(texto)
    .replace(/\[([^\]]+)\]\((https:\/\/[^\s)]+)\)|https:\/\/[^\s<]*[^\s<.,;:)]/g,
      (trecho, rotulo, url) => (url ? link(url, rotulo) : link(trecho, trecho)))
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}

// Service worker: faz a página abrir e converter sem rede depois da primeira visita.
// Só é registrado quando servido por http(s): aberto direto do disco (file://) o
// navegador recusa o registro, e o erro no console pareceria defeito da página.
function registrarServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  if (location.protocol !== 'http:' && location.protocol !== 'https:') return;

  navigator.serviceWorker.register('./sw.js').catch((err) => {
    console.warn('Service worker não registrado:', err);
  });
}

// Iniciar quando o DOM estiver pronto
document.addEventListener('DOMContentLoaded', () => {
  refreshIcons();
  registrarServiceWorker();
  initPyodide();
});
