// Entrada anterior do worker do PDF.js, sem a versão no nome. Fica para as abas abertas
// antes de ela ganhar a versão (2026-09-27), que ainda pedem este arquivo. Aponta para a
// versão legacy, a atual; pode sair junto com a pasta vendor/pdfjs-6.3.289/, que só essas
// abas antigas ainda usam
import './pdfjs-compativel.js';
import './vendor/pdfjs-legacy-6.3.289/pdf.worker.min.js';
