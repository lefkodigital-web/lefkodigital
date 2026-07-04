#!/usr/bin/env python3
"""Generate an encrypted, password-gated, non-indexable leads dashboard (index.html).
Data is AES-256-GCM encrypted client-side (Web Crypto compatible). The page only ever
contains ciphertext; without the password nothing readable is exposed to visitors,
crawlers, or LLMs.
Usage: DASH_PASSWORD=yourpass python3 generate_dashboard.py
"""
import os, json, base64, datetime
from zoneinfo import ZoneInfo
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = os.path.dirname(os.path.abspath(__file__))
LEADS_PATH = os.path.join(ROOT, "leads.json")
if not os.path.exists(LEADS_PATH):
    print("No leads.json present (APIs not yet connected) - keeping existing index.html unchanged.")
    raise SystemExit(0)
DATA = json.load(open(LEADS_PATH))
if not DATA.get("leads"):
    print("leads.json has 0 leads (fetch returned nothing) - keeping existing index.html unchanged.")
    raise SystemExit(0)
PW = os.environ.get("DASH_PASSWORD", "ChangeMe-Grizzly2026").encode()
ITER = 250000
MT = ZoneInfo("America/Denver"); IST = ZoneInfo("Asia/Kolkata")

def fmt_both(dt):
    mt = dt.astimezone(MT); ist = dt.astimezone(IST)
    return f"{mt:%b %d, %Y %I:%M %p} MT  ({ist:%b %d, %Y %I:%M %p} IST)"

# Stamp display strings for each lead + last-updated
now = datetime.datetime.now(datetime.timezone.utc)
DATA["generated_display"] = fmt_both(now)
for L in DATA["leads"]:
    if L.get("received_iso"):
        dt = datetime.datetime.fromisoformat(L["received_iso"]).replace(tzinfo=MT)
        L["received_display"] = fmt_both(dt)
    else:
        L["received_display"] = "Pending first automated sync"

plaintext = json.dumps(DATA, ensure_ascii=False).encode()

# Encrypt (matches browser Web Crypto: PBKDF2-SHA256 -> AES-256-GCM, tag appended)
salt = os.urandom(16); iv = os.urandom(12)
kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER)
key = kdf.derive(PW)
ct = AESGCM(key).encrypt(iv, plaintext, None)
b64 = lambda b: base64.b64encode(b).decode()
BLOB = json.dumps({"salt": b64(salt), "iv": b64(iv), "ct": b64(ct), "iter": ITER})

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive, nosnippet, noimageindex, notranslate">
<meta name="googlebot" content="noindex, nofollow, noarchive, nosnippet">
<meta name="robots" content="noai, noimageai">
<meta name="referrer" content="no-referrer">
<title>Lefko Digital — Private Leads Dashboard</title>
<style>
  :root{--navy:#1F3B4D;--orange:#E8792B;--green:#1E8449;--red:#C0392B;--ink:#1a2530;--muted:#6b7a86;--line:#e3e8ec;--bg:#f4f6f8;}
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--ink)}
  .lock{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
  .card{background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.06)}
  .lockbox{width:360px;padding:34px 30px;text-align:center}
  .brand{font-weight:800;font-size:22px;color:var(--navy)}
  .brand span{color:var(--orange)}
  .sub{color:var(--muted);font-size:13px;margin:6px 0 22px}
  input[type=password]{width:100%;padding:12px 14px;border:1px solid var(--line);border-radius:9px;font-size:15px;margin-bottom:12px}
  button{background:var(--navy);color:#fff;border:0;border-radius:9px;padding:12px 16px;font-size:15px;font-weight:600;width:100%;cursor:pointer}
  button:hover{background:#16303f}
  .err{color:var(--red);font-size:13px;height:18px;margin-top:8px}
  .wrap{max-width:1180px;margin:0 auto;padding:22px 18px 60px;display:none}
  header.top{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:10px;border-bottom:3px solid var(--orange);padding-bottom:14px;margin-bottom:18px}
  h1{margin:0;font-size:22px;color:var(--navy)}
  .updated{font-size:12.5px;color:var(--muted);text-align:right}
  .tzline{font-size:11.5px;color:var(--muted);margin-top:2px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
  .kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px}
  .kpi .n{font-size:26px;font-weight:800;color:var(--navy)}
  .kpi .l{font-size:12px;color:var(--muted);margin-top:3px}
  .kpi.g .n{color:var(--green)} .kpi.o .n{color:var(--orange)} .kpi.r .n{color:var(--red)}
  .sec{font-size:13px;font-weight:700;color:var(--navy);text-transform:uppercase;letter-spacing:.04em;margin:22px 0 10px}
  table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:13px}
  th{background:var(--navy);color:#fff;text-align:left;padding:9px 11px;font-weight:600;font-size:12px}
  td{padding:9px 11px;border-top:1px solid var(--line);vertical-align:top}
  tr:nth-child(even) td{background:#fafbfc}
  .pill{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
  .pill.form{background:#e8f0fe;color:#1a56b0} .pill.call{background:#e7f7ee;color:#1E8449}
  .badge{font-size:11px;font-weight:700;color:var(--green)}
  .foot{margin-top:26px;font-size:11.5px;color:var(--muted);line-height:1.6}
  a{color:var(--orange)}
  .note{background:#fff8f2;border:1px solid #f6d9c2;border-radius:10px;padding:12px 14px;font-size:12.5px;color:#7a4a22;margin-bottom:18px}
</style>
</head>
<body>
  <div class="lock" id="lock">
    <div class="card lockbox">
      <div class="brand">Lefko<span>Digital</span></div>
      <div class="sub">Private Leads Dashboard · Grizzly Insulation Co.</div>
      <input type="password" id="pw" placeholder="Enter access password" autocomplete="off" autofocus>
      <button onclick="unlock()">Unlock</button>
      <div class="err" id="err"></div>
    </div>
  </div>

  <div class="wrap" id="app">
    <header class="top">
      <div>
        <h1>Grizzly Insulation — Leads Dashboard</h1>
        <div class="tzline" id="tz"></div>
      </div>
      <div class="updated" id="updated"></div>
    </header>
    <div class="note" id="metanote"></div>
    <div class="kpis" id="kpis"></div>
    <div class="sec">All Leads (genuine — spam &amp; test entries excluded)</div>
    <div id="leadtable"></div>
    <div class="sec">Excluded / Filtered</div>
    <div id="exctable"></div>
    <div class="foot" id="foot"></div>
  </div>

<script>
const BLOB = __BLOB__;
function b(s){return Uint8Array.from(atob(s),c=>c.charCodeAt(0));}
async function unlock(){
  const pw=document.getElementById('pw').value, err=document.getElementById('err');
  err.textContent='';
  try{
    const enc=new TextEncoder();
    const km=await crypto.subtle.importKey('raw',enc.encode(pw),'PBKDF2',false,['deriveKey']);
    const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:b(BLOB.salt),iterations:BLOB.iter,hash:'SHA-256'},km,{name:'AES-GCM',length:256},false,['decrypt']);
    const pt=await crypto.subtle.decrypt({name:'AES-GCM',iv:b(BLOB.iv)},key,b(BLOB.ct));
    render(JSON.parse(new TextDecoder().decode(pt)));
  }catch(e){err.textContent='Incorrect password.';}
}
document.getElementById('pw').addEventListener('keydown',e=>{if(e.key==='Enter')unlock();});
function esc(s){return (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function render(d){
  document.getElementById('lock').style.display='none';
  document.getElementById('app').style.display='block';
  document.getElementById('tz').textContent='Times shown in '+d.meta.source_timezone_label+'  ·  IST shown in brackets for team reference';
  document.getElementById('updated').innerHTML='<b>Last updated:</b><br>'+esc(d.generated_display);
  document.getElementById('metanote').textContent=d.meta.note;
  const leads=d.leads, forms=leads.filter(l=>l.channel==='Form').length, calls=leads.filter(l=>l.channel==='Call').length;
  const svc={},kw={};
  leads.forEach(l=>{svc[l.service]=(svc[l.service]||0)+1;kw[l.keyword]=(kw[l.keyword]||0)+1;});
  const top=o=>Object.entries(o).sort((a,b)=>b[1]-a[1])[0]||['—',0];
  const cpl=d.spend&&leads.length?('$'+(d.spend.period_spend_usd/leads.length).toFixed(0)):'—';
  const k=[['Total genuine leads',leads.length,''],['Form leads',forms,'g'],['Phone-call leads',calls,'o'],
    ['Top service',top(svc)[0]+' ('+top(svc)[1]+')',''],['Top keyword',top(kw)[0],''],
    ['Spam / test filtered',(d.excluded.form_test_entries+d.excluded.form_spam),'r'],['Cost / lead (real)',cpl,'']];
  document.getElementById('kpis').innerHTML=k.map(x=>`<div class="kpi ${x[2]}"><div class="n">${esc(x[1])}</div><div class="l">${esc(x[0])}</div></div>`).join('');
  let rows=leads.map(l=>`<tr><td>${esc(l.received_display)}</td><td><span class="pill ${l.channel.toLowerCase()}">${esc(l.channel)}</span></td><td><b>${esc(l.name)}</b></td><td>${esc(l.phone)}<br><span style="color:#6b7a86">${esc(l.email)}</span></td><td>${esc(l.service)}</td><td>${esc(l.keyword)}</td><td>${esc(l.landing_page||'')}</td><td><span class="badge">${esc(l.status)}</span></td></tr>`).join('');
  document.getElementById('leadtable').innerHTML=`<table><thead><tr><th>Received (MT / IST)</th><th>Type</th><th>Name</th><th>Contact</th><th>Service</th><th>Keyword</th><th>Landing page</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
  document.getElementById('exctable').innerHTML=`<table><thead><tr><th>Category</th><th>Count</th><th>Note</th></tr></thead><tbody><tr><td>Form test/QA entries</td><td>${d.excluded.form_test_entries}</td><td>test@test.com placeholder submissions</td></tr><tr><td>Form spam</td><td>${d.excluded.form_spam}</td><td>Caught by Gravity spam filter</td></tr></tbody></table>`;
  document.getElementById('foot').innerHTML='Ad spend (period): <b>$'+d.spend.period_spend_usd.toLocaleString()+'</b> · Google Ads reported conversions: <b>'+d.spend.reported_conversions+'</b><br>'+esc(d.spend.note)+'<br><br>Account '+esc(d.meta.ads_account_id)+' · Data is AES-256 encrypted at rest in this page · noindex/noai enabled.';
}
</script>
</body>
</html>"""

out = HTML.replace("__BLOB__", BLOB)
open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(out)
print("index.html generated (", len(out), "bytes ) — leads:", len(DATA["leads"]))
