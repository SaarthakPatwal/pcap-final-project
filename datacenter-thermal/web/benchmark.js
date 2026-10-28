const $ = id => document.getElementById(id);
const colors = {cpu: '#9ba7b5', openmp: '#087f73', cuda: '#e36b49'};
const names = {cpu: 'Sequential CPU', openmp: 'OpenMP', cuda: 'CUDA'};
let timeChart, speedChart, latest = null, pollTimer;

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}
function showError(error) { $('message').textContent = error.message; $('message').hidden = false; $('message').classList.add('error'); }
function createChart(id, type, title) {
  if (typeof Chart === 'undefined') { showError(new Error('Chart.js is missing. The results table remains available.')); return null; }
  return new Chart($(id), {type, data: {labels: [], datasets: []}, options: {
    responsive: true, maintainAspectRatio: false, animation: false,
    plugins: {legend: {position: 'bottom', labels: {boxWidth: 12, font: {size: 11}}}},
    scales: {x: {grid: {display: false}, title: {display: true, text: 'Grid dimensions'}},
      y: {beginAtZero: true, title: {display: true, text: title}, grid: {color: '#edf0ec'}}}
  }});
}
function render(job) {
  latest = job;
  const busy = job.status === 'running', rows = job.rows;
  $('run-benchmark').disabled = busy;
  $('bench-steps').disabled = busy; $('bench-tiled').disabled = busy || !$('bench-tiled').dataset.available;
  $('run-benchmark').textContent = busy ? 'Running…' : '▶ Run Benchmark';
  $('progress').value = job.progress; $('progress-percent').textContent = `${job.progress}%`;
  $('progress-title').textContent = job.message;
  if (job.steps) $('progress-detail').textContent = `${job.steps} measured steps · 5 warm-up steps · ${job.tiled ? 'Shared-memory' : 'Global-memory'} CUDA kernel · setup and transfers excluded`;
  if (job.status === 'error') showError(new Error(job.message));
  $('download').disabled = !rows.length;
  if (rows.length) {
    $('results-body').replaceChildren();
    for (const row of rows) {
      const tr = document.createElement('tr');
      const values = [`${row.size} × ${row.size}`,
        ...['cpu', 'openmp', 'cuda'].map(b => row.runs[b] ? row.runs[b].ms.toFixed(4) : 'Skipped'),
        ...['openmp', 'cuda'].map(b => row.runs[b] ? `${row.speedups[b].toFixed(2)}×` : '—'),
        row.verified ? '✓ ≤ 0.001 °C' : '✕ Mismatch'];
      values.forEach(value => { const td = document.createElement('td'); td.textContent = value; tr.appendChild(td); });
      if (row.runs.cuda) tr.title = `CUDA event time: ${row.runs.cuda.compute_ms.toFixed(4)} ms/step. Table uses wall-clock time.`;
      $('results-body').appendChild(tr);
    }
  } else $('results-body').innerHTML = '<tr><td colspan="7" class="empty-state">Measurements will appear here as each grid size finishes.</td></tr>';
  for (const [chart, speedup] of [[timeChart, false], [speedChart, true]]) {
    if (!chart) continue;
    chart.data.labels = rows.map(r => `${r.size}²`);
    const backends = ['cpu', 'openmp', 'cuda'].filter(b => rows.some(r => r.runs[b]));
    chart.data.datasets = backends.map(b => ({label: names[b], data: rows.map(r => r.runs[b] ? speedup ? r.speedups[b] : r.runs[b].ms : null),
      backgroundColor: colors[b], borderColor: colors[b], borderWidth: speedup ? 2 : 0,
      borderRadius: speedup ? 0 : 3, pointRadius: speedup ? 3 : 0, tension: .15}));
    chart.update('none');
  }
  const verified = rows.length > 0 && rows.every(r => r.verified);
  const done = job.status === 'done';
  $('verification').className = `verification ${done ? verified ? 'ok' : 'fail' : ''}`;
  const scope = job.info?.cuda_available ? 'CPU, OpenMP and CUDA' : 'CPU and OpenMP; CUDA skipped';
  $('verification').textContent = done ? `${verified ? '✓ Results verified' : '✕ Results differ'} — ${scope}. Final max temperature tolerance: 0.001 °C.` : '○ Results verification pending';
}
async function poll() {
  clearTimeout(pollTimer);
  try { const job = await api('/benchmark'); render(job); if (job.status === 'running') pollTimer = setTimeout(poll, 700); }
  catch (error) { showError(error); $('run-benchmark').disabled = false; }
}
$('run-benchmark').onclick = async () => {
  const steps = Number($('bench-steps').value);
  if (!Number.isInteger(steps) || steps < 1 || steps > 1000) { showError(new Error('Steps must be an integer from 1 to 1000.')); return; }
  $('run-benchmark').disabled = true; $('message').hidden = true;
  try {
    const job = await api('/benchmark', {steps, tiled: $('bench-tiled').checked});
    render(job); poll();
  } catch (error) { showError(error); $('run-benchmark').disabled = false; }
};
$('download').onclick = () => {
  if (!latest?.rows.length) return;
  const lines = ['grid_size,steps,cpu_ms,openmp_ms,cuda_ms,openmp_speedup,cuda_speedup,verified,cuda_tiled,cuda_event_ms'];
  for (const r of latest.rows) lines.push([r.size, latest.steps, r.runs.cpu.ms, r.runs.openmp.ms,
    r.runs.cuda?.ms ?? '', r.speedups.openmp, r.speedups.cuda ?? '', r.verified, latest.tiled, r.runs.cuda?.compute_ms ?? ''].join(','));
  const url = URL.createObjectURL(new Blob([lines.join('\n')], {type: 'text/csv'}));
  const link = document.createElement('a'); link.href = url; link.download = 'thermal-benchmark.csv'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
timeChart = createChart('time-chart', 'bar', 'Milliseconds per step');
speedChart = createChart('speedup-chart', 'line', 'Speedup (×)');
(async () => {
  try {
    const info = await api('/info');
    $('threads').textContent = `${info.openmp_threads} threads`; $('gpu-name').textContent = info.gpu;
    $('bench-tiled').dataset.available = info.cuda_available ? 'yes' : '';
    $('bench-tiled').disabled = !info.cuda_available;
    await poll();
  } catch (error) { showError(error); }
})();
window.addEventListener('pagehide', () => clearTimeout(pollTimer));
