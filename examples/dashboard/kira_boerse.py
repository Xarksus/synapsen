#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# KIRA Bio-Sync Börsen-Dashboard — ECHTE Daten, Börsen-Look.
# Liest hormones.json + synapsen.db, baut ein schönes HTML mit ECharts.
# Aufruf: python3 kira_boerse.py  →  öffnet /tmp/kira_boerse.html im Browser.
# ─────────────────────────────────────────────────────────────────────────────
import json, sqlite3, html, webbrowser
from pathlib import Path
from datetime import datetime

HORM = Path.home() / ".config/kira/hormones.json"
DB   = Path.home() / ".kira/synapsen.db"
OUT  = Path("/tmp/kira_boerse.html")

# ── Daten laden ──────────────────────────────────────────────────────────────
def load_hormones():
    try:
        return json.loads(HORM.read_text())
    except Exception:
        return {"hormones": {}, "mood": "?", "state": "?"}

def q(sql, params=()):
    try:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        rows = c.execute(sql, params).fetchall()
        c.close()
        return rows
    except Exception:
        return []

h = load_hormones()
horm = h.get("hormones", {})

# Verlauf: emotional_log, gleichmäßig auf ~300 Punkte verdünnt
total = q("SELECT COUNT(*) FROM emotional_log")
n = total[0][0] if total else 0
step = max(1, n // 300)
series = q(f"""SELECT timestamp, oxytocin, serotonin, dopamine, cortisol, noradrenalin
              FROM (SELECT *, ROW_NUMBER() OVER (ORDER BY id) rn FROM emotional_log)
              WHERE rn % {step} = 0 ORDER BY id""")
times = [r[0][:16].replace("T", " ") for r in series]
def col(i): return [round(r[i], 1) if r[i] is not None else None for r in series]
ox, se, do, co, no = col(1), col(2), col(3), col(4), col(5)

# Selbstbild
selbst = q("SELECT merkmal, ROUND(staerke,2), belege FROM selbstbild ORDER BY staerke DESC")
# Erfahrungen (letzte 12)
erf = q("""SELECT substr(timestamp,1,16), situation, meine_reaktion, was_ich_gelernt_habe, gewicht
           FROM charakter_erfahrungen ORDER BY id DESC LIMIT 12""")
# Zähler
def cnt(t):
    r = q(f"SELECT COUNT(*) FROM {t}")
    return r[0][0] if r else 0
c_emo, c_erf, c_ent, c_gew = cnt("emotional_log"), cnt("charakter_erfahrungen"), cnt("entscheidungen"), cnt("gewichte")

# 24h-Veränderung je Hormon (jetzt vs. ~24h zurück)
def change(colname, cur):
    r = q(f"SELECT {colname} FROM emotional_log WHERE timestamp <= datetime('now','-1 day') ORDER BY id DESC LIMIT 1")
    if r and r[0][0] is not None and cur is not None:
        return round(cur - r[0][0], 1)
    return 0.0

cards = [
    ("VERBUNDEN",  "Oxytocin",   horm.get("oxytocin"),    "#5dcaa5"),
    ("RUHIG",      "Serotonin",  horm.get("serotonin"),   "#4fb6e0"),
    ("ANTRIEB",    "Dopamin",    horm.get("dopamine"),    "#e0c24f"),
    ("STRESS",     "Cortisol",   horm.get("cortisol"),    "#e08a8a"),
    ("WACHHEIT",   "Noradrenalin", horm.get("noradrenalin"), "#b48fe0"),
]

now = datetime.now().strftime("%Y-%m-%d %H:%M")

# ── HTML bauen ───────────────────────────────────────────────────────────────
def card_html(name, sub, val, color):
    val = 0 if val is None else val
    ch = change(sub.lower() if sub.lower()!="dopamin" else "dopamine", val)
    arrow = "▲" if ch > 0 else ("▼" if ch < 0 else "▬")
    chcol = "#5dcaa5" if ch > 0 else ("#e08a8a" if ch < 0 else "#7a8a90")
    return f"""<div class="card">
      <div class="card-h"><span class="dot" style="background:{color}"></span>{name}<span class="sub">{sub}</span></div>
      <div class="card-v" style="color:{color}">{val:.0f}</div>
      <div class="card-ch" style="color:{chcol}">{arrow} {ch:+.1f} <span class="sub">24h</span></div>
    </div>"""

cards_html = "".join(card_html(*c) for c in cards)

selbst_labels = json.dumps([s[0] for s in selbst])
selbst_vals   = json.dumps([s[1] for s in selbst])
selbst_belege = json.dumps([s[2] for s in selbst])

erf_html = "".join(
    f"""<div class="erf"><div class="erf-t">{html.escape(t)}</div>
        <div class="erf-s">{html.escape(sit or '')}</div>
        <div class="erf-r">↳ {html.escape((reak or '')[:60])}</div>
        <div class="erf-l">{html.escape((lern or '')[:70])} <span class="g">g={g}</span></div></div>"""
    for (t, sit, reak, lern, g) in erf)

page = f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="60">
<title>KIRA Bio-Sync Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0;font-family:'JetBrainsMono Nerd Font','Segoe UI',sans-serif}}
  body{{background:#0a0d12;color:#c6d3d8;padding:18px;background-image:radial-gradient(circle at 20% 0%,rgba(93,202,165,.06),transparent 60%)}}
  .top{{display:flex;align-items:center;gap:16px;border-bottom:1px solid rgba(93,202,165,.2);padding-bottom:14px;margin-bottom:18px}}
  .logo{{font-size:30px;filter:drop-shadow(0 0 8px #5dcaa5)}}
  .title{{font-size:22px;font-weight:700;letter-spacing:1px}}
  .title span{{color:#5dcaa5}}
  .subt{{font-size:11px;color:#6b7a80;letter-spacing:3px}}
  .ticker{{margin-left:auto;display:flex;gap:18px;font-size:13px}}
  .ti b{{color:#9fb0b6}} .up{{color:#5dcaa5}} .dn{{color:#e08a8a}}
  .grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:16px}}
  .card{{background:linear-gradient(160deg,rgba(20,26,33,.9),rgba(14,18,23,.9));border:1px solid rgba(93,202,165,.14);border-radius:14px;padding:14px 16px}}
  .card-h{{font-size:12px;color:#8b9aa0;letter-spacing:1px;display:flex;align-items:center;gap:7px}}
  .card-h .sub{{margin-left:auto;font-size:10px;color:#5b6a70}}
  .dot{{width:9px;height:9px;border-radius:50%;display:inline-block;box-shadow:0 0 8px currentColor}}
  .card-v{{font-size:38px;font-weight:700;margin:4px 0;text-shadow:0 0 18px rgba(93,202,165,.25)}}
  .card-ch{{font-size:13px}} .card-ch .sub{{color:#5b6a70;font-size:10px}}
  .row{{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:16px}}
  .panel{{background:rgba(16,21,27,.85);border:1px solid rgba(93,202,165,.14);border-radius:14px;padding:16px}}
  .panel h2{{font-size:13px;color:#5dcaa5;letter-spacing:2px;margin-bottom:10px;font-weight:600}}
  .row2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
  #chart{{height:340px}} #bars{{height:300px}} #donut{{height:300px}}
  .erfbox{{max-height:300px;overflow-y:auto}}
  .erf{{border-left:2px solid rgba(93,202,165,.4);padding:6px 10px;margin-bottom:8px}}
  .erf-t{{font-size:10px;color:#5b6a70}} .erf-s{{font-size:12px;color:#aebbc0}}
  .erf-r{{font-size:11px;color:#7e8d93}} .erf-l{{font-size:11px;color:#5dcaa5;margin-top:2px}}
  .g{{color:#6b7a80}}
  .stats{{display:flex;gap:26px;font-size:13px;color:#9fb0b6;margin-top:8px}}
  .stats b{{color:#5dcaa5;font-size:20px;display:block}}
  .foot{{font-size:11px;color:#5b6a70;margin-top:14px;display:flex;justify-content:space-between}}
</style></head><body>

<div class="top">
  <div class="logo">🧠</div>
  <div><div class="title">KIRA <span>BIO-SYNC</span> DASHBOARD</div><div class="subt">ECHTE DATEN · LIVE · {now}</div></div>
  <div class="ticker">
    <div class="ti"><b>VERB</b> <span class="up">{horm.get('oxytocin',0):.0f}</span></div>
    <div class="ti"><b>RUHIG</b> <span class="up">{horm.get('serotonin',0):.0f}</span></div>
    <div class="ti"><b>STRESS</b> <span class="{ 'dn' if horm.get('cortisol',0)>50 else 'up'}">{horm.get('cortisol',0):.0f}</span></div>
    <div class="ti"><b>STIMMUNG</b> <span class="up">{html.escape(str(h.get('mood','?')))}</span></div>
    <div class="ti"><b>ZUSTAND</b> <span class="up">{html.escape(str(h.get('state','?')))}</span></div>
  </div>
</div>

<div class="grid">{cards_html}</div>

<div class="row">
  <div class="panel"><h2>📈 BIO-SYNC VERLAUF — HORMONE ÜBER ZEIT ({c_emo} Messpunkte)</h2><div id="chart"></div></div>
  <div class="panel"><h2>🧬 SELBSTBILD / CHARAKTER-STÄRKEN</h2><div id="bars"></div></div>
</div>

<div class="row2">
  <div class="panel"><h2>✨ LETZTE CHARAKTER-ERFAHRUNGEN</h2><div class="erfbox">{erf_html}</div>
    <div class="stats"><div><b>{c_erf}</b>Erfahrungen</div><div><b>{c_emo}</b>Emotions-Log</div><div><b>{c_ent}</b>Entscheidungen</div><div><b>{c_gew}</b>Gewichte</div></div>
  </div>
  <div class="panel"><h2>🍩 SELBSTBILD-VERTEILUNG</h2><div id="donut"></div></div>
</div>

<div class="foot"><span>DATENSTAND: {now}</span><span>KIRA Bio-Sync · echte synapsen.db + hormones.json</span></div>

<script>
const T={json.dumps(times)};
const mk=(name,data,color)=>({{name,type:'line',smooth:true,showSymbol:false,data,lineStyle:{{width:2,color}},areaStyle:{{color:'rgba(0,0,0,0)'}}}});
echarts.init(document.getElementById('chart'),'dark').setOption({{
  backgroundColor:'transparent',
  tooltip:{{trigger:'axis'}}, legend:{{textStyle:{{color:'#9fb0b6'}},top:0}},
  grid:{{left:48,right:16,top:34,bottom:54}},
  xAxis:{{type:'category',data:T,axisLabel:{{color:'#5b6a70',fontSize:9}},axisLine:{{lineStyle:{{color:'#2a343b'}}}}}},
  yAxis:{{type:'value',axisLabel:{{color:'#5b6a70'}},splitLine:{{lineStyle:{{color:'rgba(93,202,165,.06)'}}}}}},
  dataZoom:[{{type:'inside'}},{{type:'slider',height:16,bottom:18,borderColor:'#2a343b',textStyle:{{color:'#5b6a70'}}}}],
  series:[mk('Oxytocin',{json.dumps(ox)},'#5dcaa5'),mk('Serotonin',{json.dumps(se)},'#4fb6e0'),
          mk('Dopamin',{json.dumps(do)},'#e0c24f'),mk('Cortisol',{json.dumps(co)},'#e08a8a'),
          mk('Noradrenalin',{json.dumps(no)},'#b48fe0')]
}});
echarts.init(document.getElementById('bars'),'dark').setOption({{
  backgroundColor:'transparent', grid:{{left:90,right:24,top:10,bottom:20}},
  tooltip:{{trigger:'axis',formatter:p=>p[0].name+': '+p[0].value+' Stärke'}},
  xAxis:{{type:'value',axisLabel:{{color:'#5b6a70'}},splitLine:{{lineStyle:{{color:'rgba(93,202,165,.06)'}}}}}},
  yAxis:{{type:'category',data:{selbst_labels},axisLabel:{{color:'#aebbc0'}},inverse:true}},
  series:[{{type:'bar',data:{selbst_vals},itemStyle:{{color:'#5dcaa5',borderRadius:[0,6,6,0]}},barWidth:'55%'}}]
}});
echarts.init(document.getElementById('donut'),'dark').setOption({{
  backgroundColor:'transparent',
  tooltip:{{trigger:'item'}}, legend:{{bottom:0,textStyle:{{color:'#9fb0b6'}}}},
  series:[{{type:'pie',radius:['45%','70%'],center:['50%','44%'],
    data:{selbst_labels}.map((l,i)=>({{name:l,value:{selbst_vals}[i]}})),
    label:{{color:'#aebbc0'}},itemStyle:{{borderColor:'#0a0d12',borderWidth:2}}}}]
}});
</script>
</body></html>"""

OUT.write_text(page, encoding="utf-8")
print(f"✅ Dashboard-HTML erzeugt: {OUT}")
