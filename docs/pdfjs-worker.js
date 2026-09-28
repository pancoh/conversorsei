// Worker do PDF.js: completa os recursos que faltam ao navegador e só então carrega o
// original. Os import rodam na ordem em que aparecem. A pasta tem de ser a mesma de
// OCR.pdfjs em app.js: página e worker de versões diferentes se recusam a trabalhar juntos
import './pdfjs-compativel.js';
import './vendor/pdfjs-legacy-6.3.289/pdf.worker.min.js';
