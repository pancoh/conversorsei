// Worker do PDF.js: completa os recursos que faltam ao navegador e só então carrega o
// original. Os import rodam na ordem em que aparecem. A versão vai no nome, como a da
// pasta: uma aba aberta antes de uma troca de versão continua pedindo este arquivo, e
// página e worker de versões diferentes se recusam a trabalhar juntos
import './pdfjs-compativel.js';
import './vendor/pdfjs-legacy-6.3.289/pdf.worker.min.js';
