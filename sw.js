/* ============================================================
   SERVICE WORKER — Meu Dia (Agenda)
   Faz três coisas:
   1. Guarda o app em cache para funcionar offline
   2. Tenta enviar o resumo matinal mesmo com o app fechado
      (via sincronização periódica, quando o aparelho permite)
   3. Ao tocar na notificação, abre a agenda direto em "Hoje"
   ============================================================ */

const CACHE_APP = 'agenda-app-v1';
const ARQUIVOS = ['./', './index.html', './manifest.json'];

self.addEventListener('install', (evento) => {
  evento.waitUntil(
    caches.open(CACHE_APP).then(cache => cache.addAll(ARQUIVOS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (evento) => {
  evento.waitUntil(self.clients.claim());
});

/* Offline: tenta a rede, cai para o cache */
self.addEventListener('fetch', (evento) => {
  if (evento.request.method !== 'GET') return;
  evento.respondWith(
    fetch(evento.request)
      .then(resposta => {
        const copia = resposta.clone();
        caches.open(CACHE_APP).then(cache => cache.put(evento.request, copia)).catch(()=>{});
        return resposta;
      })
      .catch(() => caches.match(evento.request))
  );
});

/* ---------- Resumo matinal em segundo plano ----------
   A página espelha os dados da agenda no cache "agenda-dados".
   Quando o sistema acorda o service worker, lemos esses dados
   e, se for depois do horário configurado e o resumo de hoje
   ainda não foi enviado, mostramos a notificação. */
function dataHoje() {
  const d = new Date();
  return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');
}

function ocorreEm(ev, dataStr) {
  if (dataStr < ev.data) return false;
  if (ev.repete === 'diario') return true;
  if (ev.repete === 'semanal') {
    const dia = (s) => { const [a, m, d] = s.split('-').map(Number); return new Date(a, m - 1, d).getDay(); };
    return dia(dataStr) === dia(ev.data);
  }
  return ev.data === dataStr;
}

async function enviarResumoSePrecisar() {
  try {
    const cache = await caches.open('agenda-dados');
    const resposta = await cache.match('dados-agenda');
    if (!resposta) return;
    const dados = await resposta.json();

    const agora = new Date();
    const [h, m] = (dados.horaResumo || '07:00').split(':').map(Number);
    const jaPassou = agora.getHours() > h || (agora.getHours() === h && agora.getMinutes() >= m);
    if (!jaPassou || dados.ultimoResumo === dataHoje()) return;

    const evs = (dados.eventos || [])
      .filter(ev => ocorreEm(ev, dataHoje()))
      .sort((a, b) => (a.hora || '99:99').localeCompare(b.hora || '99:99'));

    const corpo = evs.length === 0
      ? 'Nenhum compromisso agendado. Dia livre! ✦'
      : evs.slice(0, 5).map(e => (e.hora ? e.hora + ' — ' : '') + e.titulo).join('\n') +
        (evs.length > 5 ? '\n…e mais ' + (evs.length - 5) + '.' : '');

    await self.registration.showNotification('🌅 Seu dia de hoje', {
      body: corpo,
      icon: 'icone-192.png',
      badge: 'icone-192.png',
      tag: 'resumo-matinal'
    });

    dados.ultimoResumo = dataHoje();
    await cache.put('dados-agenda', new Response(JSON.stringify(dados), { headers: { 'Content-Type': 'application/json' } }));
  } catch (e) { /* silencioso — o resumo também roda ao abrir o app */ }
}

self.addEventListener('periodicsync', (evento) => {
  if (evento.tag === 'resumo-matinal') {
    evento.waitUntil(enviarResumoSePrecisar());
  }
});

/* Tocar na notificação abre (ou foca) a agenda */
self.addEventListener('notificationclick', (evento) => {
  evento.notification.close();
  evento.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(janelas => {
      for (const j of janelas) { if ('focus' in j) return j.focus(); }
      return self.clients.openWindow('./');
    })
  );
});
