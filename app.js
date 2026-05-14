/* =============================================
   W1 Gestão à Vista – SP1  |  Dashboard Logic
   ============================================= */

const CACHE_BUST = () => '?t=' + Date.now();

// ── Elementos DOM ──────────────────────────────
const tableBody    = document.getElementById('table-body');
const tableFoot    = document.getElementById('table-footer');
const rankingAside = document.getElementById('ranking-aside-body');
const ranking7dias = document.getElementById('ranking-aside-body-7dias');
const syncTime     = document.getElementById('sync-time');

// ── Estado ─────────────────────────────────────
let metaAPMes = 0;
let metaPPMes = 0;
let totalAPRealizadoAtual = 0;
let dadosEquipes = [];   // para o gráfico de barras
let apChart    = null;
let barChart   = null;

// ── Metas semanais ─────────────────────────────
function semanaDoMes() {
  const dia = new Date().getDate();
  if (dia <= 7)  return 1;
  if (dia <= 14) return 2;
  if (dia <= 21) return 3;
  return 4;
}

function calcularMetaSemana(metaMes, realizado) {
  const semana = semanaDoMes();
  const falta  = Math.max(0, metaMes - realizado);
  if (semana === 1) return metaMes / 4;
  if (semana === 2) return falta / 3;
  if (semana === 3) return falta / 2;
  return falta;
}

function atualizarMetasSemana(totalAPValor, totalPP) {
  if (metaAPMes > 0) {
    const metaAPSemana = calcularMetaSemana(metaAPMes, totalAPValor);
    document.getElementById('meta-ap-semana').textContent = formatarBRL(metaAPSemana);
  }
  if (metaPPMes > 0) {
    const metaPPSemana = calcularMetaSemana(metaPPMes, totalPP);
    document.getElementById('meta-pp-semana').textContent = formatarPP(metaPPSemana);
  }
}

// ── Formatação ─────────────────────────────────
function formatarBRL(valor) {
  const num = typeof valor === 'number'
    ? valor
    : parseFloat(String(valor).replace(/R\$\s*/g, '').replace(/\./g, '').replace(',', '.'));
  if (isNaN(num)) return String(valor);
  return 'R$ ' + num.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatarPP(valor) {
  const num = typeof valor === 'number'
    ? valor
    : parseFloat(String(valor).replace(/\./g, '').replace(',', '.'));
  if (isNaN(num)) return String(valor);
  return num.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 2 }) + ' PPs';
}

function parseBRL(str) {
  if (!str) return 0;
  return parseFloat(String(str).replace(/[R$\s.]/g, '').replace(',', '.')) || 0;
}

function parseNum(str) {
  if (!str) return 0;
  return parseFloat(String(str).replace(',', '.')) || 0;
}

// ── Metas ──────────────────────────────────────
async function carregarMetas() {
  try {
    const res  = await fetch('metas.json' + CACHE_BUST());
    const meta = await res.json();
    metaAPMes = parseFloat(meta.meta_ap_mes) || 0;
    metaPPMes = parseFloat(meta.meta_pp_mes) || 0;
    const set = (id, val, fmt) => {
      const el = document.getElementById(id);
      if (el && val) el.textContent = fmt(val);
    };
    set('meta-ap-mes', meta.meta_ap_mes, formatarBRL);
    set('meta-pp-mes', meta.meta_pp_mes, formatarPP);
  } catch {
    console.warn('metas.json não encontrado');
  }
}

// ── Tabela de resultados ───────────────────────
function renderizarTabela(rows) {
  const dados = rows
    .filter(r => r['Equipe'] || r['Consultor/Nível'])
    .sort((a, b) => parseBRL(b['AP Valor'] || '0') - parseBRL(a['AP Valor'] || '0'));

  let totalAA = 0, totalAF = 0, totalAP = 0;
  let totalAPValor = 0, totalREC = 0, totalPP = 0;

  tableBody.innerHTML = dados.map(row => {
    const equipe  = row['Equipe']   || row['Consultor/Nível'] || '–';
    const aa      = row['AA']       || '0';
    const af      = row['AF']       || '0';
    const ap      = row['AP']       || '0';
    const apValor = row['AP Valor'] || row['AP [R$]'] || 'R$ 0,00';
    const rec     = row['REC']      || row['Recs']    || '0';
    const pp      = row['PP Total'] || row['Total']   || '0,00';

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

  totalAPRealizadoAtual = totalAPValor;
  dadosEquipes = dados;
  atualizarMetasSemana(totalAPValor, totalPP);
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

function renderizarListaRanking(container, rows) {
  const dados = rows.filter(r => r['Consultor'] || r['Consultor/Nível']);
  container.innerHTML = dados.map((row, i) => {
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
}

function renderizarRanking(rows) {
  renderizarListaRanking(rankingAside, rows);
}

function carregarRanking() {
  Papa.parse('ranking_muapd.csv' + CACHE_BUST(), {
    download: true, header: true, skipEmptyLines: true,
    complete: r => renderizarListaRanking(rankingAside, r.data),
    error:    () => console.warn('ranking_muapd.csv não encontrado'),
  });
  Papa.parse('ranking_7dias.csv' + CACHE_BUST(), {
    download: true, header: true, skipEmptyLines: true,
    complete: r => renderizarListaRanking(ranking7dias, r.data),
    error:    () => console.warn('ranking_7dias.csv não encontrado'),
  });
}

function trocarAbaRanking(aba, btn) {
  document.querySelectorAll('.ranking-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (aba === 'hoje') {
    rankingAside.style.display = '';
    ranking7dias.style.display = 'none';
  } else {
    rankingAside.style.display = 'none';
    ranking7dias.style.display = '';
  }
}

// ── Timestamp ──────────────────────────────────
function atualizarSyncTime() {
  const agora = new Date();
  syncTime.textContent = 'Sincronizado: ' +
    agora.toLocaleDateString('pt-BR') + ', ' +
    agora.toLocaleTimeString('pt-BR');
}

// ── Recarregar ─────────────────────────────────
function recarregarDados() {
  carregarMetas();
  carregarDados();
  carregarRanking();
  atualizarSyncTime();
}

// ── Gráfico de pizza AP do Mês ─────────────────
function abrirGrafico() {
  document.getElementById('chart-modal').classList.add('active');
  const realizado = totalAPRealizadoAtual;
  const faltante  = Math.max(0, metaAPMes - realizado);
  const pct       = metaAPMes > 0 ? ((realizado / metaAPMes) * 100).toFixed(1) : 0;
  const ctx = document.getElementById('ap-chart').getContext('2d');
  if (apChart) apChart.destroy();
  apChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Realizado', 'Faltante'],
      datasets: [{
        data: realizado + faltante > 0 ? [realizado, faltante] : [0, 1],
        backgroundColor: ['#00C2B8', '#1e2a3a'],
        borderColor:     ['#00C2B8', '#2d3f55'],
        borderWidth: 2,
      }],
    },
    options: {
      cutout: '70%',
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => ' ' + formatarBRL(c.raw) } },
      },
    },
    plugins: [{
      id: 'centerText',
      beforeDraw(chart) {
        const { ctx, width, height } = chart;
        ctx.save();
        ctx.font = `bold ${Math.round(width / 8)}px Segoe UI, sans-serif`;
        ctx.fillStyle = '#00C2B8';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`${pct}%`, width / 2, height / 2);
        ctx.restore();
      },
    }],
  });
  document.getElementById('chart-legend').innerHTML = `
    <div class="legend-item"><span class="legend-dot" style="background:#00C2B8"></span>
      Realizado: <strong>${formatarBRL(realizado)}</strong></div>
    <div class="legend-item"><span class="legend-dot" style="background:#1e2a3a"></span>
      Faltante: <strong>${formatarBRL(faltante)}</strong></div>
    <div class="legend-item">Meta: <strong>${formatarBRL(metaAPMes)}</strong></div>
  `;
}

function fecharGrafico(event) {
  if (event && event.target !== document.getElementById('chart-modal')) return;
  document.getElementById('chart-modal').classList.remove('active');
}

// ── Gráfico de barras AP por Equipe ────────────
function abrirGraficoBarras() {
  document.getElementById('bar-chart-modal').classList.add('active');
  const dados = dadosEquipes.filter(r => r['Equipe']);
  const labels    = dados.map(r => r['Equipe']);
  const realizado = dados.map(r => parseBRL(r['AP Valor'] || '0'));
  const meta      = dados.map(r => parseBRL(r['Meta AP']  || '0'));

  const ctx = document.getElementById('bar-chart').getContext('2d');
  if (barChart) barChart.destroy();

  const pcts = realizado.map((r, i) => meta[i] > 0 ? Math.round((r / meta[i]) * 100) : 0);

  barChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Realizado',
          data: realizado,
          backgroundColor: '#00C2B8',
          borderRadius: 4,
        },
        {
          label: 'Meta',
          data: meta,
          backgroundColor: 'rgba(255,255,255,0.10)',
          borderColor: 'rgba(255,255,255,0.25)',
          borderWidth: 1,
          borderRadius: 4,
        },
      ],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      layout: { padding: { right: 52 } },
      plugins: {
        legend: {
          labels: { color: 'rgba(255,255,255,0.7)', font: { size: 11 } },
        },
        tooltip: {
          callbacks: {
            label: c => {
              const base = ` ${c.dataset.label}: ${formatarBRL(c.raw)}`;
              if (c.datasetIndex === 0) return base + `  (${pcts[c.dataIndex]}% da meta)`;
              return base;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: 'rgba(255,255,255,0.5)',
            callback: v => 'R$' + (v / 1000).toFixed(0) + 'k',
          },
          grid: { color: 'rgba(255,255,255,0.06)' },
        },
        y: {
          ticks: { color: '#fff', font: { size: 11 } },
          grid: { display: false },
        },
      },
    },
    plugins: [{
      id: 'pctLabels',
      afterDatasetsDraw(chart) {
        const ctx = chart.ctx;
        const meta0 = chart.getDatasetMeta(0);
        meta0.data.forEach((bar, i) => {
          const pct = pcts[i];
          const color = pct >= 100 ? '#4ade80' : pct >= 60 ? '#00C2B8' : pct >= 30 ? '#fbbf24' : '#f87171';
          ctx.save();
          ctx.font = 'bold 11px Segoe UI, sans-serif';
          ctx.fillStyle = color;
          ctx.textAlign = 'left';
          ctx.textBaseline = 'middle';
          ctx.fillText(`${pct}%`, bar.x + 6, bar.y);
          ctx.restore();
        });
      },
    }],
  });
}

function fecharGraficoBarras(event) {
  if (event && event.target !== document.getElementById('bar-chart-modal')) return;
  document.getElementById('bar-chart-modal').classList.remove('active');
}

// ── Init ───────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  recarregarDados();
  setInterval(recarregarDados, 30 * 60 * 1000);
});
