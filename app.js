/* =============================================
   W1 Gestão à Vista – SP1  |  Dashboard Logic
   ============================================= */

const SWITCH_TIME = 30; // segundos entre views (resultados ↔ ranking)
const CACHE_BUST  = () => '?t=' + Date.now();

let timeLeft      = SWITCH_TIME;
let showingRanking = false;
let cicloAtivo    = false;

// ── Elementos DOM ──────────────────────────────
const viewResults  = document.getElementById('view-results');
const viewRanking  = document.getElementById('view-ranking');
const progressBar  = document.getElementById('progress-bar');
const tableBody    = document.getElementById('table-body');
const tableFoot    = document.getElementById('table-footer');
const rankingGrid  = document.getElementById('ranking-grid');
const rankingAside = document.getElementById('ranking-aside-body');
const syncTime     = document.getElementById('sync-time');

// ── Metas ──────────────────────────────────────
function formatarBRL(valor) {
  const num = parseFloat(String(valor).replace(/\./g, '').replace(',', '.'));
  if (isNaN(num)) return valor;
  return 'R$ ' + num.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatarPP(valor) {
  const num = parseFloat(String(valor).replace(/\./g, '').replace(',', '.'));
  if (isNaN(num)) return valor;
  return num.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 2 }) + ' PPs';
}

async function carregarMetas() {
  try {
    const res  = await fetch('metas.json' + CACHE_BUST());
    const meta = await res.json();

    const set = (id, val, fmt) => {
      const el = document.getElementById(id);
      if (el && val) el.textContent = fmt(val);
    };

    set('meta-ap-semana', meta.meta_ap_semana, formatarBRL);
    set('meta-pp-semana', meta.meta_pp_semana, formatarPP);
    set('meta-ap-mes',    meta.meta_ap_mes,    formatarBRL);
    set('meta-pp-mes',    meta.meta_pp_mes,    formatarPP);
  } catch {
    console.warn('metas.json não encontrado — usando valores padrão');
  }
}

// ── Tabela de resultados ───────────────────────
function parseBRL(str) {
  if (!str) return 0;
  return parseFloat(String(str).replace(/[R$\s.]/g, '').replace(',', '.')) || 0;
}

function parseNum(str) {
  if (!str) return 0;
  return parseFloat(String(str).replace(',', '.')) || 0;
}

function renderizarTabela(rows) {
  // Filtra linhas vazias
  const dados = rows.filter(r => r['Equipe'] || r['Consultor/Nível']);

  let totalAA = 0, totalAF = 0, totalAP = 0;
  let totalAPValor = 0, totalREC = 0, totalPP = 0;

  tableBody.innerHTML = dados.map(row => {
    const equipe  = row['Equipe']    || row['Consultor/Nível'] || '–';
    const aa      = row['AA']        || '0';
    const af      = row['AF']        || '0';
    const ap      = row['AP']        || '0';
    const apValor = row['AP Valor']  || row['AP [R$]'] || 'R$ 0,00';
    const rec     = row['REC']       || row['Recs']    || '0';
    const pp      = row['PP Total']  || row['Total']   || '0,00';

    totalAA      += parseNum(aa);
    totalAF      += parseNum(af);
    totalAP      += parseNum(ap);
    totalAPValor += parseBRL(apValor);
    totalREC     += parseNum(rec);
    totalPP      += parseNum(pp);

    return `<tr>
      <td>${equipe}</td>
      <td>${aa}</td>
      <td>${af}</td>
      <td>${ap}</td>
      <td class="td-ap-valor">${apValor}</td>
      <td>${rec}</td>
      <td class="td-pp">${pp}</td>
    </tr>`;
  }).join('');

  tableFoot.innerHTML = `<tr>
    <td><strong>TOTAL</strong></td>
    <td>${totalAA}</td>
    <td>${totalAF}</td>
    <td>${totalAP}</td>
    <td class="tfoot-ap-valor">${formatarBRL(totalAPValor)}</td>
    <td>${totalREC}</td>
    <td class="tfoot-pp">${totalPP.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
  </tr>`;
}

function carregarDados() {
  Papa.parse('dados_extraidos.csv' + CACHE_BUST(), {
    download: true, header: true, skipEmptyLines: true,
    complete: r  => renderizarTabela(r.data),
    error:    ()  => console.warn('dados_extraidos.csv não encontrado'),
  });
}

// ── Ranking MUAPD ──────────────────────────────
const MEDALHAS = ['🥇', '🥈', '🥉'];

function renderizarRanking(rows) {
  const dados = rows.filter(r => r['Consultor'] || r['Consultor/Nível']);

  // Painel lateral (aside)
  rankingAside.innerHTML = dados.map((row, i) => {
    const nome = row['Consultor'] || row['Consultor/Nível'] || '–';
    const aa   = row['AA'] || '0';
    const pos  = i < 3 ? `<span class="rank-pos medal">${MEDALHAS[i]}</span>`
                       : `<span class="rank-pos">${i + 1}</span>`;
    const cls  = i === 0 ? 'top1' : i === 1 ? 'top2' : i === 2 ? 'top3' : '';
    return `<div class="ranking-row ${cls}">
      ${pos}
      <span class="rank-name">${nome}</span>
      <span class="rank-aa">${aa}</span>
    </div>`;
  }).join('');

  // View tela cheia (alternado)
  rankingGrid.innerHTML = dados.map((row, i) => {
    const nome = row['Consultor'] || row['Consultor/Nível'] || '–';
    const aa   = row['AA'] || '0';
    const pos  = i < 3 ? `<span class="rank-pos medal">${MEDALHAS[i]}</span>`
                       : `<span class="rank-pos">${i + 1}</span>`;
    return `<div class="ranking-card">
      ${pos}
      <span class="rank-name">${nome}</span>
      <span class="rank-aa">${aa}</span>
    </div>`;
  }).join('');
}

function carregarRanking() {
  Papa.parse('ranking_muapd.csv' + CACHE_BUST(), {
    download: true, header: true, skipEmptyLines: true,
    complete: r  => renderizarRanking(r.data),
    error:    ()  => console.warn('ranking_muapd.csv não encontrado'),
  });
}

// ── Ciclo automático resultados ↔ ranking ─────
function alternarView() {
  showingRanking = !showingRanking;
  if (showingRanking) {
    viewResults.classList.remove('active');
    viewRanking.classList.add('active');
  } else {
    viewRanking.classList.remove('active');
    viewResults.classList.add('active');
  }
}

function iniciarCiclo() {
  if (cicloAtivo) return;
  cicloAtivo = true;

  setInterval(() => {
    timeLeft -= 0.1;
    const pct = ((SWITCH_TIME - timeLeft) / SWITCH_TIME) * 100;
    progressBar.style.width = pct + '%';

    if (timeLeft <= 0) {
      timeLeft = SWITCH_TIME;
      alternarView();
    }
  }, 100);
}

// ── Timestamp de sincronização ─────────────────
function atualizarSyncTime() {
  const agora = new Date();
  syncTime.textContent = 'Sincronizado: ' +
    agora.toLocaleDateString('pt-BR') + ', ' +
    agora.toLocaleTimeString('pt-BR');
}

// ── Recarregar (botão Atualizar) ───────────────
function recarregarDados() {
  carregarMetas();
  carregarDados();
  carregarRanking();
  atualizarSyncTime();
}

// ── Init ───────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  recarregarDados();
  iniciarCiclo();
});
