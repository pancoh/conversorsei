// Recursos de JavaScript que o PDF.js usa e que a versão legacy dele não traz. É
// importado pela página, antes do PDF.js, e pelo worker de entrada
// (pdfjs-worker-<versão>.js, com a versão de VERSAO_PDFJS no app.js).
// Promise.withResolvers chegou no Chrome 119 e no Safari 17.4: sem ele, o OCR falhava no
// Samsung Internet e no Chrome de celulares Android mais antigos
if (typeof Promise.withResolvers !== 'function') {
  Promise.withResolvers = function withResolvers() {
    let resolve;
    let reject;
    const promise = new this((resolver, rejeitar) => {
      resolve = resolver;
      reject = rejeitar;
    });
    return { promise, resolve, reject };
  };
}
