from fastapi import APIRouter, Response

router = APIRouter()

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>AI Governance Demo – Live</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    html,body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Helvetica,Arial,sans-serif;background:#0f1216;color:#e6edf3;margin:0;padding:0}
    .wrap{max-width:1200px;margin:24px auto;padding:0 16px}
    h1{font-size:22px;margin:0 0 16px}
    .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
    .card{background:#171a21;border:1px solid #2a2f3a;border-radius:10px;padding:16px}
    .metric{font-size:13px;color:#9fb0c3;margin-bottom:6px}
    .value{font-size:28px;font-weight:700}
    .row{display:flex;gap:12px}
    canvas{background:#0f1216;border-radius:6px}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th,td{border-bottom:1px solid #2a2f3a;padding:8px;text-align:left}
    th{color:#9fb0c3;font-weight:600}
    .pill{padding:2px 8px;border-radius:999px;font-size:12px;background:#22314a}
    .ok{color:#66e089}.warn{color:#ffcc66}.bad{color:#ff8d8d}
    .muted{color:#9fb0c3}
    .bar{height:4px;background:#2a2f3a;border-radius:999px;overflow:hidden}
    .bar>span{display:block;height:100%;background:#6aa4ff}
    .footer{margin-top:14px;font-size:12px;color:#9fb0c3}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
<div class="wrap">
  <h1>AI Governance Demo – Live</h1>

  <div class="grid">
    <div class="card"><div class="metric">Raw events</div><div id="raw_total" class="value">0</div></div>
    <div class="card"><div class="metric">Canonical events</div><div id="canonical_total" class="value">0</div></div>
    <div class="card"><div class="metric">Agents</div><div id="agents_total" class="value">0</div></div>
  </div>

  <div class="row" style="margin-top:12px">
    <div class="card" style="flex:1">
      <div class="metric">Events by source</div>
      <canvas id="bySource" height="140"></canvas>
    </div>
    <div class="card" style="flex:1">
      <div class="metric">Agents by data class</div>
      <canvas id="byDataClass" height="140"></canvas>
    </div>
    <div class="card" style="flex:1">
      <div class="metric">Autonomy</div>
      <canvas id="autonomy" height="140"></canvas>
    </div>
  </div>

  <div class="card" style="margin-top:12px">
    <div class="row" style="justify-content:space-between;align-items:center">
      <div class="metric">Violations: confidential + external egress without DLP</div>
      <div class="pill"><span id="violations_count">0</span> open</div>
    </div>
    <div style="overflow:auto; max-height:320px; margin-top:8px">
      <table>
        <thead><tr>
          <th>Agent</th><th>Data class</th><th>Output scope</th><th>DLP</th>
        </tr></thead>
        <tbody id="violations_rows"><tr><td class="muted" colspan="4">No violations</td></tr></tbody>
      </table>
    </div>
  </div>

  <div class="footer muted">Auto-refresh every 5s. Uses /admin/metrics.</div>
</div>

<script>
let srcChart, dcChart, autChart;

function upsertBar(el, labels, data){
  const ctx = document.getElementById(el).getContext('2d');
  const cfg = {
    type: 'bar',
    data: { labels: labels, datasets: [{ label: '', data: data }] },
    options: { plugins:{legend:{display:false}}, responsive:true, scales:{y:{beginAtZero:true}} }
  };
  if(el==='bySource'){ if(srcChart) srcChart.destroy(); srcChart = new Chart(ctx, cfg); }
  if(el==='byDataClass'){ if(dcChart) dcChart.destroy(); dcChart = new Chart(ctx, cfg); }
  if(el==='autonomy'){ if(autChart) autChart.destroy(); autChart = new Chart(ctx, cfg); }
}

async function refresh(){
  try{
    const r = await fetch('/admin/metrics');
    const m = await r.json();
    document.getElementById('raw_total').textContent = m.raw_total;
    document.getElementById('canonical_total').textContent = m.canonical_total;
    document.getElementById('agents_total').textContent = m.agents_total;

    upsertBar('bySource', m.by_source.map(x=>x.source), m.by_source.map(x=>x.count));
    upsertBar('byDataClass', m.by_data_class.map(x=>x.data_class), m.by_data_class.map(x=>x.count));
    upsertBar('autonomy', m.autonomy.map(x=>x.autonomy), m.autonomy.map(x=>x.count));

    const vcnt = m.violations_count || 0;
    document.getElementById('violations_count').textContent = vcnt;
    const tbody = document.getElementById('violations_rows');
    tbody.innerHTML = '';
    if(vcnt===0){
      const tr = document.createElement('tr');
      tr.innerHTML = '<td class="muted" colspan="4">No violations</td>';
      tbody.appendChild(tr);
    } else {
      m.violations.forEach(v=>{
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><code>${v.agent_id}</code></td>
          <td>${v.data_class}</td>
          <td><code>${v.output_scope}</code></td>
          <td>${v.dlp_template || ''}</td>`;
        tbody.appendChild(tr);
      });
    }
  }catch(e){ /* ignore */ }
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""

@router.get("/ui")
def ui():
    return Response(content=HTML, media_type="text/html")