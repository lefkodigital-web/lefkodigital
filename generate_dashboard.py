#!/usr/bin/env python3
"""Generate encrypted, password-gated, non-indexable leads dashboard (index.html).
Two tabs: Genuine Leads (forms + calls) and All Calls. AES-256-GCM client-side."""
import os, json, base64, datetime
from zoneinfo import ZoneInfo
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = os.path.dirname(os.path.abspath(__file__))
LEADS_PATH = os.path.join(ROOT, "leads.json")
if not os.path.exists(LEADS_PATH):
    print("No leads.json - keeping existing index.html."); raise SystemExit(0)
DATA = json.load(open(LEADS_PATH))
PW = os.environ.get("DASH_PASSWORD", "ChangeMe-Grizzly2026").encode()
ITER = 250000
MT = ZoneInfo("America/Denver"); IST = ZoneInfo("Asia/Kolkata")
now = datetime.datetime.now(datetime.timezone.utc)
DATA["generated_display"] = f"{now.astimezone(MT):%b %d, %Y %I:%M %p} MT ({now.astimezone(IST):%b %d, %Y %I:%M %p} IST)"

plaintext = json.dumps(DATA, ensure_ascii=False).encode()
salt = os.urandom(16); iv = os.urandom(12)
key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(PW)
ct = AESGCM(key).encrypt(iv, plaintext, None)
b64 = lambda b: base64.b64encode(b).decode()
BLOB = json.dumps({"salt": b64(salt), "iv": b64(iv), "ct": b64(ct), "iter": ITER})

HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive, nosnippet, noimageindex, notranslate">
<meta name="googlebot" content="noindex, nofollow, noarchive, nosnippet">
<meta name="robots" content="noai, noimageai"><meta name="referrer" content="no-referrer">
<title>Lefko Digital — Private Leads Dashboard</title>
<style>
:root{--navy:#1F3B4D;--orange:#E8792B;--green:#1E8449;--red:#C0392B;--ink:#1a2530;--muted:#6b7a86;--line:#e3e8ec;--bg:#f4f6f8;}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--ink)}
.lock{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.06)}
.lockbox{width:360px;padding:34px 30px;text-align:center}
.brand{font-weight:800;font-size:22px;color:var(--navy)}.brand span{color:var(--orange)}
.sub{color:var(--muted);font-size:13px;margin:6px 0 22px}
input[type=password]{width:100%;padding:12px 14px;border:1px solid var(--line);border-radius:9px;font-size:15px;margin-bottom:12px}
button.unlock{background:var(--navy);color:#fff;border:0;border-radius:9px;padding:12px 16px;font-size:15px;font-weight:600;width:100%;cursor:pointer}
.err{color:var(--red);font-size:13px;height:18px;margin-top:8px}
.wrap{max-width:1240px;margin:0 auto;padding:22px 18px 60px;display:none}
header.top{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:10px;border-bottom:3px solid var(--orange);padding-bottom:14px;margin-bottom:16px}
h1{margin:0;font-size:22px;color:var(--navy)}.tzline{font-size:11.5px;color:var(--muted);margin-top:2px}
.updated{font-size:12.5px;color:var(--muted);text-align:right}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:11px;margin-bottom:16px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:13px 15px}
.kpi .n{font-size:24px;font-weight:800;color:var(--navy)}.kpi .l{font-size:11.5px;color:var(--muted);margin-top:3px}
.kpi.g .n{color:var(--green)}.kpi.o .n{color:var(--orange)}.kpi.r .n{color:var(--red)}
.note{background:#fff8f2;border:1px solid #f6d9c2;border-radius:10px;padding:11px 14px;font-size:12.5px;color:#7a4a22;margin-bottom:16px}
.tabs{display:flex;gap:8px;margin-bottom:12px}
.tab{padding:9px 16px;border:1px solid var(--line);background:#fff;border-radius:9px;cursor:pointer;font-weight:600;font-size:13.5px;color:var(--muted)}
.tab.active{background:var(--navy);color:#fff;border-color:var(--navy)}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:13px}
th{background:var(--navy);color:#fff;text-align:left;padding:9px 11px;font-weight:600;font-size:12px}
td{padding:9px 11px;border-top:1px solid var(--line);vertical-align:top}tr:nth-child(even) td{background:#fafbfc}
.pill{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
.pill.form{background:#e8f0fe;color:#1a56b0}.pill.call{background:#e7f7ee;color:#1E8449}
.badge{font-size:11px;font-weight:700}
.cat-Lead{color:#1E8449;font-weight:700}.cat-Spam{color:#C0392B}.cat-Voicemail{color:#b7791f}
.hide{display:none}.foot{margin-top:22px;font-size:11.5px;color:var(--muted);line-height:1.6}
</style></head><body>
<div class="lock" id="lock"><div class="card lockbox">
<div class="brand">Lefko<span>Digital</span></div><div class="sub">Private Leads Dashboard · Grizzly Insulation Co.</div>
<input type="password" id="pw" placeholder="Enter access password" autocomplete="off" autofocus>
<button class="unlock" onclick="unlock()">Unlock</button><div class="err" id="err"></div></div></div>
<div class="wrap" id="app">
<header class="top"><div><h1>Grizzly Insulation — Leads Dashboard</h1><div class="tzline" id="tz"></div></div><div class="updated" id="updated"></div></header>
<div class="note" id="metanote"></div><div class="kpis" id="kpis"></div>
<div class="tabs"><div class="tab active" id="t1" onclick="showTab(1)">Genuine Leads</div><div class="tab" id="t2" onclick="showTab(2)">All Calls (raw)</div></div>
<div id="pane1"></div><div id="pane2" class="hide"></div>
<div class="foot" id="foot"></div></div>
<script>
const BLOB=__BLOB__;
function b(s){return Uint8Array.from(atob(s),c=>c.charCodeAt(0));}
async function unlock(){const pw=document.getElementById('pw').value,err=document.getElementById('err');err.textContent='';
 try{const enc=new TextEncoder();const km=await crypto.subtle.importKey('raw',enc.encode(pw),'PBKDF2',false,['deriveKey']);
 const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:b(BLOB.salt),iterations:BLOB.iter,hash:'SHA-256'},km,{name:'AES-GCM',length:256},false,['decrypt']);
 const p=await crypto.subtle.decrypt({name:'AES-GCM',iv:b(BLOB.iv)},key,b(BLOB.ct));render(JSON.parse(new TextDecoder().decode(p)));}
 catch(e){err.textContent='Incorrect password.';}}
document.getElementById('pw').addEventListener('keydown',e=>{if(e.key==='Enter')unlock();});
function esc(s){return(s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function showTab(n){document.getElementById('t1').classList.toggle('active',n==1);document.getElementById('t2').classList.toggle('active',n==2);
 document.getElementById('pane1').classList.toggle('hide',n!=1);document.getElementById('pane2').classList.toggle('hide',n!=2);}
function render(d){document.getElementById('lock').style.display='none';document.getElementById('app').style.display='block';
 document.getElementById('tz').textContent='Times in '+d.meta.source_timezone_label+' · IST in brackets · '+d.meta.period;
 document.getElementById('updated').innerHTML='<b>Last updated:</b><br>'+esc(d.generated_display);
 document.getElementById('metanote').textContent=d.meta.note;
 const s=d.summary;
 const k=[['Unique genuine leads',s.unique_genuine,'g'],['Form leads (paid)',s.form_leads,''],['Phone leads',s.call_leads,'o'],
   ['Booked inspections',s.booked_inspections,'g'],['Google Ads counted',d.spend.reported_conversions,'r'],['Spam calls filtered',s.spam_calls,'r']];
 document.getElementById('kpis').innerHTML=k.map(x=>`<div class="kpi ${x[2]}"><div class="n">${esc(x[1])}</div><div class="l">${esc(x[0])}</div></div>`).join('');
 // Pane 1: genuine leads
 let r1=d.genuine_leads.map(l=>`<tr><td>${esc(l.received)}</td><td><span class="pill ${l.channel.toLowerCase()}">${esc(l.channel)}</span></td><td><b>${esc(l.name)}</b></td><td>${esc(l.contact)}</td><td>${esc(l.need)}</td><td>${esc(l.source)}</td><td><span class="badge cat-Lead">${esc(l.status)}</span></td></tr>`).join('');
 document.getElementById('pane1').innerHTML=`<table><thead><tr><th>Received (MT / IST)</th><th>Type</th><th>Name</th><th>Contact</th><th>Need</th><th>Source</th><th>Status</th></tr></thead><tbody>${r1}</tbody></table>`;
 // Pane 2: all calls
 let r2=d.all_calls.map(c=>`<tr><td>${esc(c.received)}</td><td><b>${esc(c.name)}</b><br><span style="color:#6b7a86">${esc(c.contact)}</span></td><td>${esc(c.summary)}</td><td>${esc(c.source)}</td><td>${esc(c.duration)}<br>${esc(c.answered)}</td><td class="cat-${esc((c.category||'').split(' ')[0])}">${esc(c.category)}</td></tr>`).join('');
 document.getElementById('pane2').innerHTML=`<table><thead><tr><th>Received (MT / IST)</th><th>Caller</th><th>Summary</th><th>Source / Number</th><th>Call</th><th>Category</th></tr></thead><tbody>${r2}</tbody></table>`;
 document.getElementById('foot').innerHTML='Ad spend (period): <b>$'+d.spend.period_spend_usd.toLocaleString()+'</b>. '+esc(d.spend.note)+'<br><br>'+esc(d.excluded.note)+'<br>Account '+esc(d.meta.ads_account_id)+' · AES-256 encrypted · noindex/noai enabled.';}
</script></body></html>"""
open(os.path.join(ROOT,"index.html"),"w",encoding="utf-8").write(HTML.replace("__BLOB__",BLOB))
print("index.html generated — genuine:",len(DATA["genuine_leads"]),"calls:",len(DATA["all_calls"]))
