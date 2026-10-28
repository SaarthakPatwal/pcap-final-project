/* Plain JavaScript: a flat index is row * N + column, exactly as in C++. */
const $ = id => document.getElementById(id);
const canvas = $('heatmap'), ctx = canvas.getContext('2d');
const pixels = document.createElement('canvas'), pixelCtx = pixels.getContext('2d');
let frame = null, selected = new Set(), running = false, generation = 0;
let dragStart = null, history = null, queue = Promise.resolve();
let resetting = false;

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed: ${response.status}`);
  return result;
}
function message(text, error = false) {
  $('message').textContent = text;
  $('message').hidden = !text;
  $('message').classList.toggle('error', error);
}
// Serialize UI requests. A slow frame cannot arrive after a reset and replace it.
function enqueue(action) {
  queue = queue.then(action).catch(error => { pause(); message(error.message, true); });
  return queue;
}
function pause() {
  running = false; ++generation;
  $('start').disabled = false; $('pause').disabled = true;
  $('run-status').innerHTML = '<i></i> Paused';
  $('run-status').classList.remove('running');
}
async function tick(token) {
  if (!running || token !== generation) return;
  await enqueue(async () => {
    if (!running || token !== generation) return;
    await api('/step', {n: Number($('speed').value)});
    await getFrame();
  });
  // No overlapping requests; request/JSON/render time limits the actual rate.
  if (running && token === generation) setTimeout(() => tick(token), 100);
}
$('start').onclick = () => {
  if (running) return;
  message(''); running = true; const token = ++generation;
  $('start').disabled = true; $('pause').disabled = false;
  $('run-status').innerHTML = '<i></i> Running'; $('run-status').classList.add('running');
  tick(token);
};
$('pause').onclick = pause;
$('step').onclick = () => { pause(); enqueue(async () => { await api('/step', {n: 1}); await getFrame(); }); };
window.addEventListener('pagehide', pause);

function reset() {
  if (resetting) return;
  pause();
  resetting = true;
  // A selection from the old grid must not be applied to the replacement grid.
  const controls = ['start', 'step', 'reset', 'size', 'backend', 'select-all', 'clear-selection'];
  controls.forEach(id => $(id).disabled = true);
  document.querySelectorAll('[data-selection], [data-preset]').forEach(b => b.disabled = true);
  const options = {size: Number($('size').value), backend: $('backend').value,
    ambient: Number($('ambient').value), threshold: Number($('threshold').value), tiled: $('tiled').checked};
  enqueue(async () => {
    try {
      await api('/init', options);
      selected.clear();
      if (history) { history.data.labels = []; history.data.datasets.forEach(d => d.data = []); }
      await getFrame(); message('Grid reset to 25 °C, deterministic workloads and 50% cooling.');
    } catch (error) {
      if (frame) { $('backend').value = frame.backend; $('size').value = frame.size; }
      throw error;
    } finally {
      resetting = false;
      controls.forEach(id => $(id).disabled = false);
      document.querySelectorAll('[data-preset]').forEach(b => b.disabled = false);
      selectionChanged();
    }
  });
}
$('reset').onclick = reset;
$('size').onchange = reset;
$('backend').onchange = reset;

function setupChart() {
  if (typeof Chart === 'undefined') { message('Chart.js is missing. Heatmap and controls still work.', true); return; }
  Chart.defaults.font.family = 'Segoe UI, Arial, sans-serif';
  Chart.defaults.color = '#7a8785';
  history = new Chart($('history-chart'), {
    type: 'line', data: {labels: [], datasets: [
      {label: 'Max temperature (°C)', data: [], borderColor: '#e36b49', backgroundColor: '#e36b4915', yAxisID: 'temp', borderWidth: 2, pointRadius: 0, tension: .2},
      {label: 'Throughput', data: [], borderColor: '#087f73', yAxisID: 'through', borderWidth: 2, pointRadius: 0, tension: .2}
    ]}, options: {responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {mode: 'index', intersect: false},
      plugins: {legend: {position: 'bottom', labels: {boxWidth: 12, usePointStyle: true, font: {size: 11}}}},
      scales: {x: {title: {display: true, text: 'Simulation step'}, grid: {display: false}, ticks: {maxTicksLimit: 10}},
        temp: {type: 'linear', position: 'left', title: {display: true, text: '°C'}, grid: {color: '#edf0ec'}},
        through: {type: 'linear', position: 'right', title: {display: true, text: 'Workload units'}, grid: {drawOnChartArea: false}}}
    }
  });
}
async function getFrame() {
  frame = await api('/frame');
  const s = frame.stats;
  $('max-stat').textContent = s.maximum.toFixed(1);
  $('avg-stat').textContent = s.average.toFixed(1);
  $('hot-stat').textContent = s.hotspots.toLocaleString();
  $('through-stat').textContent = new Intl.NumberFormat('en', {notation: 'compact', maximumFractionDigits: 2}).format(s.throughput);
  $('through-stat').title = s.throughput.toLocaleString(undefined, {maximumFractionDigits: 2});
  $('step-stat').textContent = s.step.toLocaleString();
  $('ms-stat').textContent = s.milliseconds.toFixed(3);
  $('hot-label').textContent = `racks above ${frame.threshold} °C`;
  $('rack-count').textContent = `${(frame.size ** 2).toLocaleString()} racks`;
  if (history) {
    const labels = history.data.labels, data = history.data.datasets;
    if (labels.length && s.step < labels[labels.length - 1]) { labels.length = 0; data.forEach(d => d.data = []); }
    if (labels.length && labels[labels.length - 1] === s.step) {
      data[0].data[labels.length - 1] = s.maximum; data[1].data[labels.length - 1] = s.throughput;
    } else {
      labels.push(s.step); data[0].data.push(s.maximum); data[1].data.push(s.throughput);
      if (labels.length > 120) { labels.shift(); data.forEach(d => d.data.shift()); }
    }
    history.update('none');
  }
  draw();
}

// Fixed color scale: a changing maximum never recolors an unchanged rack.
const stops = [[36,74,213], [33,165,200], [99,197,167], [237,201,86], [236,105,66], [157,35,75]];
function color(t) {
  const x = Math.max(0, Math.min(4.9999, (t - 20) / 90 * 5));
  const k = Math.floor(x), f = x - k;
  return stops[k].map((v, c) => Math.round(v + (stops[k + 1][c] - v) * f));
}
function draw() {
  if (!frame) return;
  const n = frame.size, cell = canvas.width / n;
  pixels.width = n; pixels.height = n;
  const image = pixelCtx.createImageData(n, n);
  for (let i = 0; i < n * n; ++i) {
    const rgb = color(frame.temperature[i]);
    image.data[i * 4] = rgb[0]; image.data[i * 4 + 1] = rgb[1]; image.data[i * 4 + 2] = rgb[2]; image.data[i * 4 + 3] = 255;
  }
  pixelCtx.putImageData(image, 0, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(pixels, 0, 0, canvas.width, canvas.height);
  if (n <= 128) {
    ctx.beginPath(); ctx.strokeStyle = '#102d4522'; ctx.lineWidth = .6;
    for (let i = 1; i < n; ++i) {
      ctx.moveTo(i * cell, 0); ctx.lineTo(i * cell, canvas.height);
      ctx.moveTo(0, i * cell); ctx.lineTo(canvas.width, i * cell);
    }
    ctx.stroke();
  }
  ctx.beginPath(); ctx.strokeStyle = '#ffdf79'; ctx.lineWidth = Math.max(.5, cell / 11);
  for (let i = 0; i < n * n; ++i) if (frame.temperature[i] > frame.threshold)
    ctx.rect((i % n) * cell + .5, Math.floor(i / n) * cell + .5, cell - 1, cell - 1);
  ctx.stroke();
  ctx.beginPath(); ctx.strokeStyle = '#fff'; ctx.lineWidth = Math.max(.5, cell / 9);
  for (const i of selected) ctx.rect((i % n) * cell, Math.floor(i / n) * cell, cell, cell);
  ctx.stroke();
}
function selectionChanged() {
  $('selection-count').textContent = selected.size.toLocaleString();
  document.querySelectorAll('[data-selection]').forEach(b => b.disabled = !selected.size);
  draw();
}
function cellAt(event) {
  const rect = canvas.getBoundingClientRect(), n = frame.size;
  const col = Math.max(0, Math.min(n - 1, Math.floor((event.clientX - rect.left) / rect.width * n)));
  const row = Math.max(0, Math.min(n - 1, Math.floor((event.clientY - rect.top) / rect.height * n)));
  return {row, col, index: row * n + col};
}
canvas.onpointerdown = event => {
  if (!frame || resetting || event.button !== 0) return;
  event.preventDefault(); canvas.setPointerCapture(event.pointerId);
  const cell = cellAt(event);
  if (event.shiftKey) {
    if (selected.has(cell.index)) selected.delete(cell.index); else selected.add(cell.index);
    dragStart = null;
  } else { dragStart = cell; selected = new Set([cell.index]); }
  selectionChanged();
};
canvas.onpointermove = event => {
  if (!frame) return;
  const cell = cellAt(event);
  if (dragStart) {
    selected.clear();
    for (let r = Math.min(cell.row, dragStart.row); r <= Math.max(cell.row, dragStart.row); ++r)
      for (let c = Math.min(cell.col, dragStart.col); c <= Math.max(cell.col, dragStart.col); ++c)
        selected.add(r * frame.size + c);
    selectionChanged();
  }
  const tooltip = $('tooltip'), i = cell.index, box = canvas.parentElement.getBoundingClientRect();
  tooltip.textContent = `Rack [${cell.row}, ${cell.col}] · #${i}\nTemperature  ${frame.temperature[i].toFixed(2)} °C\nWorkload     ${frame.workload[i].toFixed(0)}%\nCooling      ${frame.cooling[i].toFixed(0)}%`;
  tooltip.hidden = false;
  tooltip.style.left = `${Math.max(4, Math.min(event.clientX - box.left + 14, box.width - tooltip.offsetWidth - 5))}px`;
  tooltip.style.top = `${Math.max(4, Math.min(event.clientY - box.top + 14, box.height - tooltip.offsetHeight - 5))}px`;
};
canvas.onpointerup = canvas.onpointercancel = () => { dragStart = null; };
canvas.onpointerleave = () => { $('tooltip').hidden = true; };
$('select-all').onclick = () => { if (frame) { selected = new Set(Array.from({length: frame.size ** 2}, (_, i) => i)); selectionChanged(); } };
$('clear-selection').onclick = () => { selected.clear(); selectionChanged(); };

function modify(values) {
  if (!selected.size) return;
  const indices = [...selected];
  enqueue(async () => { const result = await api('/modify', {indices, values}); await getFrame(); message(`Updated ${result.updated.toLocaleString()} selected racks.`); });
}
$('apply').onclick = () => modify({temperature: Number($('temperature-number').value), workload: Number($('workload').value), cooling: Number($('cooling').value)});
const actions = {heat: {delta: 10}, cool: {delta: -10}, max: {workload: 100}, off: {workload: 0}};
document.querySelectorAll('[data-action]').forEach(b => b.onclick = () => modify(actions[b.dataset.action]));
document.querySelectorAll('[data-preset]').forEach(b => b.onclick = () => {
  const data = {name: b.dataset.preset};
  if (selected.size) data.indices = [...selected];
  enqueue(async () => {
    const result = await api('/preset', data);
    selected = new Set(result.indices); selectionChanged(); await getFrame();
    message(`${b.textContent.replace('↗', '').trim()} applied to ${result.indices.length.toLocaleString()} racks.`);
  });
});
$('temperature').oninput = () => { $('temperature-number').value = $('temperature').value; };
$('temperature-number').oninput = () => { $('temperature').value = $('temperature-number').value; };
for (const id of ['workload', 'cooling', 'speed', 'ambient', 'threshold']) {
  $(id).oninput = () => { $(id + '-value').textContent = $(id).value + (['ambient', 'threshold'].includes(id) ? ' °C' : id === 'speed' ? '' : '%'); };
}
for (const id of ['ambient', 'threshold', 'tiled']) $(id).onchange = () => {
  const config = {n: 0, ambient: Number($('ambient').value), threshold: Number($('threshold').value), tiled: $('tiled').checked};
  enqueue(async () => { await api('/step', config); await getFrame(); });
};

setupChart();
enqueue(async () => {
  const info = await api('/info');
  $('hardware').textContent = `OpenMP: ${info.openmp_threads} threads · CUDA blocks: 16 × 16 · ${info.gpu} · Changing backend or grid size resets the simulation.`;
  $('backend').querySelector('[value=cuda]').disabled = !info.cuda_available;
  $('tiled').disabled = !info.cuda_available;
  await getFrame();
  $('backend').value = frame.backend; $('size').value = frame.size;
  $('ambient').value = frame.ambient; $('threshold').value = frame.threshold; $('tiled').checked = frame.tiled;
  $('ambient').oninput(); $('threshold').oninput();
});
