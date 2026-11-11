"""
FW20 - analiza screenów wykresów przez AI (Claude vision) - wersja z nowym wyglądem.

Lokalnie:  pip install flask anthropic
           set ANTHROPIC_API_KEY=sk-ant-...
           python screen_analyzer.py   ->  http://localhost:5000
Render:    Start Command: gunicorn screen_analyzer:app
           (w requirements.txt: flask, anthropic, gunicorn)
NIE wgrywaj klucza API na GitHub - tylko zmienna środowiskowa.
"""
import os, base64, json, re
from flask import Flask, request, jsonify
import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")
client = anthropic.Anthropic()
app = Flask(__name__)

PROMPT = """Jesteś asystentem analizy technicznej. Dostajesz 1-2 screeny wykresów
(jeśli 2: pierwszy = wyższy interwał, drugi = niższy interwał wejścia).
Odczytaj instrument, interwał i poziomy cen z obrazu. Nie zgaduj - jeśli czegoś
nie widać, wpisz null. Odpowiedz WYŁĄCZNIE JSON-em:
{
 "kierunek": "LONG" | "SHORT" | "BRAK",
 "instrument": "...", "interwal": "...",
 "entry": liczba|null, "sl": liczba|null, "tp": liczba|null, "rr": liczba|null,
 "pewnosc": "niska"|"srednia"|"wysoka",
 "wyzszy_interwal": "wzrostowy"|"spadkowy"|"boczny"|null,
 "opis_htf": "krótko, po polsku",
 "opis": "krótko, po polsku - struktura, poziomy, scenariusz",
 "uniewaznia": "warunek unieważnienia setupu"
}
Jeśli brak czytelnego setupu, daj kierunek BRAK. To analiza techniczna z obrazu,
nie rekomendacja inwestycyjna."""

HTML = r"""<!doctype html>
<html lang="pl"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0c1220">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>FW20 sygnały</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0c1220; --surface:#141c2f; --raised:#1b2540; --line:#26324f;
  --text:#e8edf7; --muted:#8b98b3;
  --long:#2dd4a7; --short:#ff6b6b; --accent:#6ea8ff; --warn:#f5b94a;
  --r-lg:22px; --r-md:14px; --r-sm:10px;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:'Manrope',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-variant-numeric:tabular-nums;line-height:1.45;
  padding:calc(env(safe-area-inset-top,0px) + 18px) 16px calc(env(safe-area-inset-bottom,0px) + 28px);
  max-width:560px;margin-inline:auto}
button{font:inherit;color:inherit;cursor:pointer}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* nagłówek */
.top{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:16px}
.top h1{margin:0;font-size:30px;font-weight:800;letter-spacing:-.02em}
.top p{margin:2px 0 0;color:var(--muted);font-size:14px}
.clock{font-size:15px;font-weight:700;color:var(--muted)}

/* statystyki */
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);padding:12px 8px;text-align:center}
.stat b{display:block;font-size:24px;font-weight:800;line-height:1.1}
.stat span{font-size:12px;color:var(--muted)}
.stat.long b{color:var(--long)} .stat.short b{color:var(--short)}
.pos{color:var(--long)} .neg{color:var(--short)}

/* przycisk analizy */
.go{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;
  background:var(--accent);color:#06101f;border:0;border-radius:var(--r-lg);
  padding:18px;font-size:17px;font-weight:800;transition:transform .12s ease}
.go:active{transform:scale(.98)}
.go svg{flex:none}
.hint{margin:10px 2px 0;color:var(--muted);font-size:13px}

/* ładowanie */
.loading{display:flex;gap:12px;align-items:center;background:var(--surface);
  border:1px solid var(--line);border-radius:var(--r-lg);padding:14px;margin-top:16px}
.loading .th{display:flex;gap:6px}
.loading img{width:54px;height:54px;object-fit:cover;border-radius:var(--r-sm);border:1px solid var(--line)}
.spin{width:20px;height:20px;border:3px solid var(--line);border-top-color:var(--accent);
  border-radius:50%;animation:sp .8s linear infinite;margin-left:auto}
@keyframes sp{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.spin{animation-duration:2.4s}.go{transition:none}}

.err{margin-top:16px;border:1px solid var(--short);background:rgba(255,107,107,.08);
  border-radius:var(--r-lg);padding:14px;font-size:14px}

h2{font-size:18px;margin:26px 2px 10px;font-weight:800}
.empty{background:var(--surface);border:1px dashed var(--line);border-radius:var(--r-lg);
  padding:22px;color:var(--muted);text-align:center;font-size:14px}

/* karta sygnału */
.card{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--muted);
  border-radius:var(--r-lg);padding:16px;margin-bottom:14px}
.card.LONG{border-left-color:var(--long)} .card.SHORT{border-left-color:var(--short)}
.card.done{opacity:.72}
.hd{display:flex;gap:12px;align-items:center}
.badge{font-weight:800;font-size:20px;letter-spacing:-.01em}
.LONG .badge{color:var(--long)} .SHORT .badge{color:var(--short)} .BRAK .badge{color:var(--muted)}
.meta{display:flex;flex-direction:column;min-width:0;font-size:13px;color:var(--muted)}
.meta b{color:var(--text);font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.x{margin-left:auto;background:none;border:0;color:var(--muted);font-size:22px;line-height:1;padding:4px 8px}

/* drabinka cen */
.ladder{margin:16px 2px 6px}
.bar{display:flex;height:12px;border-radius:99px;overflow:hidden;background:var(--raised)}
.bar i{display:block;height:100%}
.bar .risk{background:var(--short)} .bar .win{background:var(--long)}
.lab{position:relative;height:42px;margin-top:6px;font-size:12px;color:var(--muted)}
.lab div{position:absolute;top:0;display:flex;flex-direction:column;line-height:1.25}
.lab b{font-size:16px;color:var(--text);font-weight:800}
.lab .l{left:0;align-items:flex-start} .lab .r{right:0;align-items:flex-end}
.lab .m{transform:translateX(-50%);align-items:center}
.dot{position:relative;height:0}
.dot u{position:absolute;top:-19px;width:4px;height:26px;background:#fff;border-radius:2px;transform:translateX(-50%)}

.facts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0 4px}
.facts div{background:var(--raised);border-radius:var(--r-sm);padding:9px 10px;font-size:12px;color:var(--muted)}
.facts b{display:block;font-size:15px;color:var(--text);font-weight:700;text-transform:none}

details{margin-top:10px}
summary{cursor:pointer;color:var(--accent);font-weight:700;font-size:14px;padding:6px 0}
details p{margin:6px 0;font-size:14px;color:#c6cfe2}
.inv{margin:10px 0 0;font-size:13px;color:var(--warn)}

/* przyciski statusu */
.seg{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:14px}
.seg button{background:var(--raised);border:1px solid var(--line);border-radius:var(--r-sm);
  padding:11px 2px;font-size:13px;font-weight:700;transition:background .15s,border-color .15s}
.seg button.on.in{background:rgba(110,168,255,.18);border-color:var(--accent);color:var(--accent)}
.seg button.on.skip{background:rgba(139,152,179,.18);border-color:var(--muted)}
.seg button.on.tp{background:rgba(45,212,167,.18);border-color:var(--long);color:var(--long)}
.seg button.on.sl{background:rgba(255,107,107,.18);border-color:var(--short);color:var(--short)}

.foot{margin-top:22px;color:var(--muted);font-size:12px;text-align:center}
.foot button{background:none;border:0;color:var(--muted);text-decoration:underline;font-size:12px;margin-top:6px}
</style></head>
<body>
<div class="top">
  <div><h1>FW20</h1><p>Sygnały z wykresów</p></div>
  <div class="clock" id="clock"></div>
</div>

<section class="stats" id="stats" aria-label="Statystyki"></section>

<label class="go" role="button" tabindex="0" id="pick">
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>
  Wybierz 1–2 screeny i analizuj
  <input id="f" type="file" accept="image/*" multiple hidden>
</label>
<p class="hint">Zaznacz wykres wyższego interwału (np. 1H), a potem niższego (np. 15m). Wyższy daje kierunek, niższy wejście.</p>

<div id="status"></div>

<h2>Wyniki</h2>
<div id="list"></div>

<p class="foot">Analiza techniczna z obrazu, nie rekomendacja inwestycyjna. Sprawdzaj poziomy na żywym wykresie.<br>
<button id="clear">Wyczyść historię</button></p>

<script>
const KEY='fw20_items_v2';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>{const v=parseFloat(n);return isNaN(v)?null:v};
const fmt=n=>n==null?'–':n.toLocaleString('pl-PL',{maximumFractionDigits:2});
let items=[];
try{items=JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){items=[]}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(items))}catch(e){}};

function tick(){$('clock').textContent=new Date().toLocaleTimeString('pl-PL',{hour:'2-digit',minute:'2-digit'})}
tick();setInterval(tick,30000);

function stats(){
  const real=items.filter(i=>i.d.kierunek==='LONG'||i.d.kierunek==='SHORT');
  const open=items.filter(i=>i.st==='in').length;
  const tp=items.filter(i=>i.st==='tp'), sl=items.filter(i=>i.st==='sl');
  const pl=tp.reduce((a,i)=>a+(num(i.d.rr)||0),0)-sl.length;
  const closed=tp.length+sl.length;
  const acc=closed?Math.round(tp.length/closed*100)+'%':'–';
  const plTxt=(pl>0?'+':'')+fmt(Math.round(pl*100)/100)+'R';
  const plCls=closed?(pl>=0?'pos':'neg'):'';
  $('stats').innerHTML=
    `<div class="stat"><b>${open}</b><span>Otwarte</span></div>`+
    `<div class="stat"><b class="${plCls}">${closed?plTxt:'–'}</b><span>P/L zamknięte</span></div>`+
    `<div class="stat"><b>${acc}</b><span>Trafność</span></div>`+
    `<div class="stat"><b>${real.length}</b><span>Ważne</span></div>`+
    `<div class="stat long"><b>${real.filter(i=>i.d.kierunek==='LONG').length}</b><span>LONG</span></div>`+
    `<div class="stat short"><b>${real.filter(i=>i.d.kierunek==='SHORT').length}</b><span>SHORT</span></div>`;
}

function ladder(d){
  const e=num(d.entry),s=num(d.sl),t=num(d.tp);
  if(e==null||s==null||t==null||(d.kierunek!=='LONG'&&d.kierunek!=='SHORT')) return '';
  const short=d.kierunek==='SHORT';
  const L=short?t:s, R=short?s:t;           // od najniższej do najwyższej ceny
  if(L===R) return '';
  let pos=(e-L)/(R-L)*100; pos=Math.max(22,Math.min(78,pos));
  const lc=short?'win':'risk', rc=short?'risk':'win';
  const ln=short?'TP':'SL', rn=short?'SL':'TP';
  return `<div class="ladder">
    <div class="bar"><i class="${lc}" style="width:${pos}%"></i><i class="${rc}" style="width:${100-pos}%"></i></div>
    <div class="dot"><u style="left:${pos}%"></u></div>
    <div class="lab">
      <div class="l"><b>${fmt(L)}</b>${ln}</div>
      <div class="m" style="left:${pos}%"><b>${fmt(e)}</b>Entry</div>
      <div class="r"><b>${fmt(R)}</b>${rn}</div>
    </div></div>`;
}

const SEG=[['in','Wszedłem'],['skip','Bez wejścia'],['tp','TP'],['sl','SL']];

function card(it){
  const d=it.d, k=(d.kierunek==='LONG'||d.kierunek==='SHORT')?d.kierunek:'BRAK';
  const done=(it.st==='tp'||it.st==='sl'||it.st==='skip')?' done':'';
  const seg=k==='BRAK'?'':`<div class="seg">${SEG.map(([v,l])=>
     `<button class="${v}${it.st===v?' on':''}" data-act="st" data-v="${v}" data-id="${it.id}">${l}</button>`).join('')}</div>`;
  const rr=num(d.rr);
  return `<article class="card ${k}${done}">
    <div class="hd">
      <span class="badge">${k}</span>
      <div class="meta"><b>${esc(d.instrument||'Instrument?')}</b><span>${esc(d.interwal||'')} ${esc(it.time)}</span></div>
      <button class="x" data-act="del" data-id="${it.id}" aria-label="Usuń sygnał">×</button>
    </div>
    ${ladder(d)}
    <div class="facts">
      <div>RR<b>${rr==null?'–':fmt(rr)}</b></div>
      <div>Pewność<b>${esc(d.pewnosc||'–')}</b></div>
      <div>Wyższy int.<b>${esc(d.wyzszy_interwal||'–')}</b></div>
    </div>
    <details><summary>Opis analizy</summary>
      ${d.opis_htf?`<p>${esc(d.opis_htf)}</p>`:''}
      ${d.opis?`<p>${esc(d.opis)}</p>`:''}
    </details>
    ${d.uniewaznia?`<p class="inv">Unieważnia: ${esc(d.uniewaznia)}</p>`:''}
    ${seg}
  </article>`;
}

function render(){
  stats();
  $('list').innerHTML=items.length?items.map(card).join('')
    :'<div class="empty">Brak sygnałów. Wybierz screeny wykresu, a wynik pojawi się tutaj.</div>';
}

$('list').addEventListener('click',e=>{
  const b=e.target.closest('[data-act]'); if(!b) return;
  const it=items.find(i=>i.id===b.dataset.id); if(!it) return;
  if(b.dataset.act==='del'){items=items.filter(i=>i!==it)}
  else{it.st=(it.st===b.dataset.v)?'new':b.dataset.v}
  save();render();
});
$('clear').onclick=()=>{if(confirm('Usunąć całą historię sygnałów?')){items=[];save();render()}};
$('pick').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('f').click()}});

$('f').onchange=async e=>{
  const files=[...e.target.files].slice(0,2); e.target.value='';
  if(!files.length) return;
  const th=files.map(f=>`<img alt="Podgląd screena" src="${URL.createObjectURL(f)}">`).join('');
  $('status').innerHTML=`<div class="loading"><div class="th">${th}</div><div>Analizuję wykres…</div><div class="spin"></div></div>`;
  const fd=new FormData(); files.forEach(f=>fd.append('img',f));
  try{
    const r=await fetch('/analyze',{method:'POST',body:fd}); const d=await r.json();
    if(d.error){$('status').innerHTML=`<div class="err">${esc(d.error)}<br>Spróbuj ponownie lub wybierz wyraźniejszy screen.</div>`;return}
    items.unshift({id:Date.now().toString(36),time:new Date().toLocaleString('pl-PL',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}),st:'new',d});
    items=items.slice(0,60); save(); $('status').innerHTML=''; render();
  }catch(err){
    $('status').innerHTML=`<div class="err">Brak połączenia z serwerem. Sprawdź, czy aplikacja działa, i spróbuj ponownie.</div>`;
  }
};
render();
</script></body></html>"""


@app.get("/")
def index():
    return HTML


@app.post("/analyze")
def analyze():
    files = request.files.getlist("img")[:2]
    if not files:
        return jsonify(error="Brak obrazów")
    content = []
    for i, f in enumerate(files, 1):
        data = base64.standard_b64encode(f.read()).decode()
        mt = f.mimetype if f.mimetype in ("image/png", "image/jpeg", "image/webp") else "image/png"
        content.append({"type": "text", "text": f"Screen {i}:"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}})
    content.append({"type": "text", "text": PROMPT})
    try:
        msg = client.messages.create(model=MODEL, max_tokens=1000,
                                     messages=[{"role": "user", "content": content}])
        m = re.search(r"\{.*\}", msg.content[0].text, re.S)
        return jsonify(json.loads(m.group(0)))
    except Exception as e:
        return jsonify(error=f"Błąd analizy: {e}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
