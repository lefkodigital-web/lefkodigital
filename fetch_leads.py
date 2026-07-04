#!/usr/bin/env python3
"""Fetch leads from Gravity Forms REST API v2 (OAuth 1.0a signed) + CallTrackingMetrics,
filter spam/test, and write leads.json for the dashboard generator.

Env (GitHub Secrets): GF_BASE_URL, GF_CONSUMER_KEY, GF_CONSUMER_SECRET, GF_FORM_IDS,
CTM_ACCOUNT_ID, CTM_API_KEY, CTM_API_SECRET, LOOKBACK_DAYS (opt).
"""
import os, json, base64, datetime, hmac, hashlib, time, urllib.request, urllib.error
from urllib.parse import quote, urlparse, parse_qsl
from zoneinfo import ZoneInfo

MT = ZoneInfo("America/Denver"); UTC = datetime.timezone.utc
LOOKBACK = int(os.environ.get("LOOKBACK_DAYS", "30"))
ROOT = os.path.dirname(os.path.abspath(__file__))
TEST_MARKERS = ("test@test.com", "test test", "1234567", "asdf", "example.com", "qwerty")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
enc = lambda s: quote(str(s), safe="~")

def _get(url, headers=None):
    headers = {**(headers or {}), "User-Agent": UA, "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        raise RuntimeError(f"HTTP {e.code} :: {body}")

def oauth_url(method, url, extra, ck, cs):
    """Return a Gravity-Forms-compatible OAuth 1.0a (HMAC-SHA1) signed URL."""
    p = urlparse(url)
    base_url = f"{p.scheme}://{p.netloc}{p.path}"
    params = dict(parse_qsl(p.query))
    params.update(extra or {})
    params.update({
        "oauth_consumer_key": ck,
        "oauth_nonce": os.urandom(16).hex(),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_version": "1.0",
    })
    norm = "&".join(f"{enc(k)}={enc(params[k])}" for k in sorted(params))
    base = "&".join([method.upper(), enc(base_url), enc(norm)])
    sig = base64.b64encode(hmac.new(f"{enc(cs)}&".encode(), base.encode(), hashlib.sha1).digest()).decode()
    params["oauth_signature"] = sig
    return base_url + "?" + "&".join(f"{enc(k)}={enc(params[k])}" for k in params)

def is_junk(name, email, phone):
    blob = f"{name} {email} {phone}".lower()
    return any(m in blob for m in TEST_MARKERS)

def utc_to_mt_iso(s):
    if not s: return None
    s = s.replace("T", " ").split("+")[0].strip()
    try:
        return datetime.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).astimezone(MT).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None

def discover_fields(form):
    roles = {}
    for f in form.get("fields", []):
        fid = str(f.get("id")); label = (f.get("label") or "").lower(); t = f.get("type", "")
        if t == "name" and "name" not in roles: roles["name"] = fid
        elif "name" in label and "user" not in label and "name" not in roles and t in ("text", "name"): roles["name"] = fid
        if "email" in label and "email" not in roles: roles["email"] = fid
        if "phone" in label and "phone" not in roles: roles["phone"] = fid
        if "service" in label and "service" not in roles: roles["service"] = fid
        if "utm" in label and "utm" not in roles: roles["utm"] = fid
    return roles

def get_val(entry, fid):
    if not fid: return ""
    if fid in entry and entry[fid]: return entry[fid]
    parts = [entry.get(f"{fid}.{i}", "") for i in (2, 3, 4, 6, 8)]
    return " ".join(p for p in parts if p).strip()

def fetch_gravity():
    base = os.environ.get("GF_BASE_URL"); ck = os.environ.get("GF_CONSUMER_KEY"); cs = os.environ.get("GF_CONSUMER_SECRET")
    if not (base and ck and cs): return [], "Gravity keys not set"
    base = base.rstrip("/")
    form_ids = [x.strip() for x in (os.environ.get("GF_FORM_IDS") or "6,7").split(",") if x.strip()]
    out = []; notes = []
    for fid in form_ids:
        try:
            form = _get(oauth_url("GET", f"{base}/wp-json/gf/v2/forms/{fid}", {}, ck, cs))
            roles = discover_fields(form if isinstance(form, dict) else {})
            data = _get(oauth_url("GET", f"{base}/wp-json/gf/v2/forms/{fid}/entries", {"paging[page_size]": "200"}, ck, cs))
        except Exception as ex:
            notes.append(f"form {fid}: {ex}"); continue
        ents = data.get("entries", []) if isinstance(data, dict) else []
        print(f"  form {fid}: roles={roles} total_count={data.get('total_count') if isinstance(data,dict) else '?'} entries={len(ents)}")
        for e in ents:
            name = get_val(e, roles.get("name")) or "(no name)"
            email = get_val(e, roles.get("email")); phone = get_val(e, roles.get("phone"))
            if is_junk(name, email, phone): continue
            out.append({"id": f"F-{e.get('id')}", "channel": "Form", "form": form.get("title", f"form {fid}"),
                        "name": name, "email": email, "phone": phone,
                        "service": get_val(e, roles.get("service")), "keyword": get_val(e, roles.get("utm")),
                        "landing_page": e.get("source_url", ""), "received_iso": utc_to_mt_iso(e.get("date_created")),
                        "status": "Genuine"})
    return out, ("; ".join(notes) if notes else None)

def fetch_ctm():
    acct = os.environ.get("CTM_ACCOUNT_ID"); key = os.environ.get("CTM_API_KEY"); sec = os.environ.get("CTM_API_SECRET")
    if not (acct and key and sec): return [], 0, "CTM API keys not set"
    auth = base64.b64encode(f"{key}:{sec}".encode()).decode()
    since = (datetime.datetime.now(MT) - datetime.timedelta(days=LOOKBACK)).strftime("%Y-%m-%d")
    try:
        data = _get(f"https://api.calltrackingmetrics.com/api/v1/accounts/{acct}/calls?start_date={since}&per_page=500", {"Authorization": f"Basic {auth}"})
    except Exception as e:
        return [], 0, f"CTM fetch error: {e}"
    leads, spam = [], 0
    for c in data.get("calls", []):
        dur = c.get("duration", 0) or 0
        tags = " ".join(c.get("tags", [])).lower() if isinstance(c.get("tags"), list) else str(c.get("tags", "")).lower()
        if ("spam" in tags) or ("robocall" in tags) or (dur < 20 and "lead" not in tags):
            spam += 1; continue
        leads.append({"id": f"C-{c.get('id')}", "channel": "Call", "form": "",
                      "name": c.get("name") or c.get("caller_name") or c.get("caller_number", "Caller"),
                      "email": "", "phone": c.get("caller_number", ""), "service": "",
                      "keyword": c.get("keyword", "") or (c.get("utm", {}) or {}).get("term", ""),
                      "landing_page": (c.get("utm", {}) or {}).get("source", ""),
                      "received_iso": utc_to_mt_iso(c.get("called_at") or c.get("created_at")), "status": "Genuine"})
    return leads, spam, None

def main():
    if not any(os.environ.get(k) for k in ("GF_CONSUMER_KEY", "CTM_API_KEY")):
        print("No API keys configured - skipping fetch."); return
    bp = os.path.join(ROOT, "leads.json")
    base = json.load(open(bp)) if os.path.exists(bp) else {
        "meta": {"account": "Grizzly Insulation Co.", "ads_account_id": "403-750-9921",
                 "source_timezone": "America/Denver", "source_timezone_label": "Mountain Time (GMT-06:00)",
                 "display_timezone_secondary": "Asia/Kolkata", "note": ""},
        "spend": {"period_spend_usd": 8590.45, "reported_conversions": 8, "note": "Google Ads Jun 3-Jul 2 2026 (static until Ads API added)."},
        "excluded": {"form_test_entries": 22, "form_spam": 0}, "leads": []}
    gf, gferr = fetch_gravity(); ctm, ctm_spam, ctmerr = fetch_ctm()
    errors = [e for e in (gferr, ctmerr) if e]
    if gf or ctm:
        base["leads"] = gf + ctm; base["excluded"]["call_spam"] = ctm_spam
    base["meta"]["last_fetch_utc"] = datetime.datetime.now(UTC).isoformat()
    base["meta"]["fetch_notes"] = errors or ["ok"]
    json.dump(base, open(bp, "w"), ensure_ascii=False, indent=2)
    print("fetched forms:", len(gf), "calls:", len(ctm), "call-spam:", ctm_spam, "errors:", errors)

if __name__ == "__main__":
    main()
