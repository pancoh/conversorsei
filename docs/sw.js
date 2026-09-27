// sw.js: service worker do Conversor SEI.
//
// Objetivo: depois da primeira visita, a página abre e converte documentos sem rede.
// O que é servido pelo próprio site entra no cache já na instalação. O que vem de fora
// (o Pyodide no jsDelivr) é grande e entra no cache de execução, na
// primeira vez que o motor de conversão é carregado.
//
// Com rede, a página, o app.js, o CSS e o pacote Python vêm sempre do servidor: mudam
// juntos a cada deploy e precisam ser da mesma versão. O CSS compilado do Tailwind já
// esteve em vendor/, servido do cache: como o nome não muda a cada recompilação, a
// página nova abria com o CSS antigo. Servidos do cache e atualizados em
// segundo plano, o navegador ficava com a página nova e o app.js antigo por várias
// visitas (o GitHub Pages ainda deixa o cache HTTP guardá-los por 10 minutos).

const VERSAO = 'v8';
const CACHE_ESTATICO = `conversao-sei-estatico-${VERSAO}`;
const CACHE_EXECUCAO = `conversao-sei-execucao-${VERSAO}`;

// Só o essencial para a página abrir. Fontes e ícones entram sozinhos no primeiro uso,
// o que evita manter aqui uma lista que sai de sincronia com a pasta vendor.
const ARQUIVOS_ESSENCIAIS = [
  './',
  './index.html',
  './app.js',
  './manifest.webmanifest',
  './icons/marca-conversor.svg',
  './icons/conversor-sei-192-v2.png',
  './icons/conversor-sei-512-v2.png',
  './conversorsei.zip',
  './estilos.css',
  './vendor/fonts.css',
  './vendor/jszip-3.10.1.min.js',
  './vendor/lucide-1.33.0.min.js',
  './vendor/typing_extensions-4.16.0-py3-none-any.whl',
  './vendor/python_docx-1.2.0-py3-none-any.whl',
  './vendor/pypdf-6.16.1-py3-none-any.whl',
];

// Hospeda o Pyodide e as bibliotecas compiladas que ele carrega
const ORIGENS_EXTERNAS = ['cdn.jsdelivr.net'];
// Núcleo do Pyodide, sem o qual a página não converte sem rede. Entra no cache de execução
// quando a página o baixa, mas o reparo confere: no WebKit (Safari), o pyodide.asm.js
// carregado pelo <script> do Pyodide não chegava ao cache, e a página não abria sem rede
const PYODIDE_ESSENCIAL = ['pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']
  .map((nome) => `https://cdn.jsdelivr.net/pyodide/v0.26.4/full/${nome}`);

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_ESTATICO)
      // Um arquivo ausente não pode impedir a instalação inteira do service worker.
      // 'reload' pula o cache HTTP, que ainda pode ter a versão anterior ao deploy
      .then((cache) => Promise.allSettled(
        ARQUIVOS_ESSENCIAIS.map((url) => cache.add(new Request(url, { cache: 'reload' })))
      ))
      .then(() => self.skipWaiting())
  );
});

// Apaga só as versões antigas dos próprios caches. O domínio (ramson.com.br) é compartilhado
// com outros sites, e o cache é por domínio: sem o prefixo, a ativação apagava o cache de
// qualquer outro site ali, e o da própria página quando ela mudou de caminho
const PREFIXO_CACHE = 'conversao-sei-';
// Ligado quando a página muda de endereço (desligar): daí em diante nada entra no cache
let desligado = false;

self.addEventListener('activate', (event) => {
  const atuais = [CACHE_ESTATICO, CACHE_EXECUCAO];
  event.waitUntil(
    caches.keys()
      .then((nomes) => Promise.all(
        nomes.filter((n) => n.startsWith(PREFIXO_CACHE) && !atuais.includes(n)).map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

// Uma falha isolada no pré-cache não impede a instalação. Quando a página termina de
// preparar o conversor, tenta completar as entradas ausentes enquanto há rede: os
// arquivos do site e o núcleo do Pyodide.
async function completar(nomeCache, urls, opcoes) {
  if (desligado) return;
  const cache = await caches.open(nomeCache);
  await Promise.allSettled(urls.map(async (url) => {
    if (await cache.match(url)) return;
    await cache.add(new Request(url, opcoes));
  }));
}

async function repararCacheEssencial() {
  await Promise.all([
    completar(CACHE_ESTATICO, ARQUIVOS_ESSENCIAIS, { cache: 'reload' }),
    // O endereço do CDN leva a versão: o cache HTTP do navegador serve, sem baixar de novo
    completar(CACHE_EXECUCAO, PYODIDE_ESSENCIAL, { mode: 'cors', credentials: 'omit' }),
  ]);
}

self.addEventListener('message', (event) => {
  if (event.data?.tipo !== 'reparar-cache-essencial') return;
  event.waitUntil(repararCacheEssencial());
});

// Guarda no cache apenas resposta utilizável: erro e resposta parcial ficam de fora
async function guardar(nomeCache, requisicao, resposta) {
  if (desligado || !resposta || !resposta.ok || resposta.status === 206) return resposta;
  const cache = await caches.open(nomeCache);
  await cache.put(requisicao, resposta.clone());
  return resposta;
}

// Chave sem a marca de versão (?v=): cada deploy troca a marca, e guardar cada uma como
// entrada nova acumularia cópias do app.js e do CSS no cache
function semBusca(requisicao) {
  const url = new URL(requisicao.url);
  return url.origin + url.pathname;
}

// Cache primeiro: serve o que já está guardado e busca na rede só o que falta.
// É a estratégia para os arquivos externos, que são grandes e têm versão fixa na URL.
async function cachePrimeiro(requisicao, nomeCache) {
  const guardado = await caches.match(requisicao);
  if (guardado) return guardado;
  const resposta = await fetch(requisicao);
  return guardar(nomeCache, requisicao, resposta);
}

// A página mudou de endereço: o servidor redireciona toda a pasta para o domínio novo.
// Este service worker apaga o próprio cache e sai do caminho, e o endereço antigo passa a
// ir direto ao redirecionamento. Depois dele o navegador nunca mais o atualizaria: não
// aceita buscar sw.js por um redirecionamento.
// A página antiga ainda pode ter buscas em andamento, e cada uma, ao terminar, abria o
// cache de novo (caches.open recria o que foi apagado). Por isso a marca vem antes, e a
// limpeza se repete depois do unregister, para pegar o que já tinha passado pela marca
async function apagarCaches() {
  const nomes = await caches.keys();
  await Promise.all(nomes.filter((n) => n.startsWith(PREFIXO_CACHE)).map((n) => caches.delete(n)));
}

async function desligar() {
  desligado = true;
  await apagarCaches();
  await self.registration.unregister();
  await apagarCaches();
}

// Rede primeiro, confirmando com o servidor e não com o cache HTTP ('no-cache': quando
// nada mudou, a resposta é um 304 curto). Sem rede, serve o que está guardado.
async function redePrimeiro(requisicao, reserva) {
  // Na navegação, o redirecionamento volta ao navegador como veio ('manual'), e é ele quem
  // o segue. Seguido aqui, a resposta chegava à navegação já redirecionada, e o navegador
  // a recusa: a página não abria
  const navegacao = requisicao.mode === 'navigate';
  let resposta = null;
  try {
    resposta = await fetch(requisicao.url, {
      cache: 'no-cache',
      credentials: 'same-origin',
      redirect: navegacao ? 'manual' : 'follow',
    });
    if (resposta.type === 'opaqueredirect') {
      await desligar();
      return resposta;
    }
    if (resposta.ok) return guardar(CACHE_ESTATICO, semBusca(requisicao), resposta);
  } catch {
    // Sem rede: segue para o que está guardado
  }
  // ignoreSearch pelo mesmo motivo de cacheERevalida
  const guardado = (await caches.match(requisicao, { ignoreSearch: true }))
    || (reserva && (await caches.match(reserva)));
  // Um erro do servidor sem cópia guardada chega como é, e não como falha de rede
  return guardado || resposta || Response.error();
}

// Serve do cache e atualiza em segundo plano. Só para a pasta vendor, cujos arquivos
// levam a versão no nome e não mudam depois de publicados.
async function cacheERevalida(requisicao) {
  // ignoreSearch: um sufixo de versão na URL ("?v=123") não pode transformar um arquivo
  // já guardado em endereço desconhecido, ou a página deixaria de abrir sem rede
  const guardado = await caches.match(requisicao, { ignoreSearch: true });
  const naRede = fetch(requisicao)
    .then((resposta) => guardar(CACHE_ESTATICO, requisicao, resposta))
    .catch(() => null);
  return guardado || naRede.then((r) => r || Response.error());
}

self.addEventListener('fetch', (event) => {
  const requisicao = event.request;
  if (requisicao.method !== 'GET') return;

  const url = new URL(requisicao.url);

  // Navegação: a página vem da rede e, sem rede, do index.html guardado
  if (requisicao.mode === 'navigate') {
    event.respondWith(redePrimeiro(requisicao, './index.html'));
    return;
  }

  if (ORIGENS_EXTERNAS.includes(url.hostname)) {
    event.respondWith(cachePrimeiro(requisicao, CACHE_EXECUCAO));
    return;
  }

  if (url.origin === self.location.origin) {
    const versionado = url.pathname.includes('/vendor/');
    event.respondWith(versionado ? cacheERevalida(requisicao) : redePrimeiro(requisicao));
  }
});
