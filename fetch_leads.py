#!/usr/bin/env python3
"""Fetch leads from Gravity Forms REST API v2 + CallTrackingMetrics API, filter out
spam/test, and write data/leads.json for the dashboard generator.

Required environment variables (set as GitHub Secrets):
  GF_BASE_URL      e.g. https://grizzlyinsulationco.com
  GF_CONSUMER_KEY  Gravity Forms REST API consumer key
  GF_CONSUMER_SECRET
  GF_FORM_IDS      comma list of ad-lead form ids (e.g. "6,7")
  CTM_ACCOUNT_ID   CallTrackingMetrics account id
  CTM_API_KEY      CTM API key
  CTM_API_SECRET   CTM API secret
Optional:
  LOOKBACK_DAYS    default 30
"""
import os, json, datetime, base64, urllib.request, urllib.parse
from zoneinfo import ZoneInfo

MT = ZoneInfo("America/Denver")
LOOKBACK = int(os.environ.get("LOOKBACK_DAYS", "30"))
ROOT = os.path.dirname(os.path.abspath(__file__))

TEST_MARKERS = ("test@test.com", "test test", "1234567", "asdf", "example.com")

def _get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())

def is_junk(name, email, phone):
    blob = f"{name} {email} {phone}".lower()
    return any(m in blob for m in TEST_MARKERS)

def fetch_gravity():
    base = os.environ.get("GF_BASE_URL"); ck = os.environ.get("GF_CONSUMER_KEY"); cs = os.environ.get("GF_CONSUMER_SECRET")
    if not (base and ck and cs):
        return [], "Gravity Forms API keys not set"
    form_ids = [x.strip() for x in os.environ.get("GF_FORM_IDS", "6").split(",") if x.strip()]
    auth = base64.b64encode(f"{ck}:{cs}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    out = []
    for fid in form_ids:
        url = f"{base}/wp-json/gf/v2/forms/{fid}/entries?paging[page_size]=200"
        try:
            data = _get(url, headers)
        except Exception as e:
            return out, f"Gravity fetch error: {e}"
        for e in data.get("entries", []):
            # Field ids vary per form — map by label heuristics if present
            name = e.get("1.3","") and (e.get("1.3","")+" "+e.get("1.6","")).strip() or e.get("name","") or e.get("1","")
            email = e.get("2","") or e.get("email","")
            phone = e.get("3","") or e.get("phone","")
            if is_junk(name, email, phone):
                continue
            out.append({
                "id": f"F-{e.get('id')}", "channel":"Form", "form": f"form {fid}",
                "name": name or "(no name)", "email": email, "phone": phone,
                "service": e.get("4",""), "keyword": e.get("utm_term","") or e.get("5",""),
                "landing_page": e.get("source_url",""),
                "received_iso": (e.get("date_created","") or "").replace(" ","T") or None,
                "status":"Genuine"})
    return out, None

def fetch_ctm():
    acct = os.environ.get("CTM_ACCOUNT_ID"); key = os.environ.get("CTM_API_KEY"); sec = os.environ.get("CTM_API_SECRET")
    if not (acct and key and sec):
        return [], 0, "CTM API keys not set"
    auth = base64.b64encode(f"{key}:{sec}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    since = (datetime.datetime.now(MT) - datetime.timedelta(days=LOOKBACK)).strftime("%Y-%m-%d")
    url = f"https://api.calltrackingmetrics.com/api/v1/accounts/{acct}/calls?start_date={since}&per_page=500"
    try:
        data = _get(url, headers)
    except Exception as e:
        return [], 0, f"CTM fetch error: {e}"
    leads, spam = [], 0
    for c in data.get("calls", []):
        # Treat short/robocall/spam-tagged as spam; genuine = answered & > 30s or tagged lead
        dur = c.get("duration", 0) or 0
        tags = " ".join(c.get("tags", [])).lower() if isinstance(c.get("tags"), list) else str(c.get("tags","")).lower()
        is_spam = ("spam" in tags) or ("robocall" in tags) or (dur < 20 and "lead" not in tags)
        if is_spam:
            spam += 1; continue
        leads.append({
            "id": f"C-{c.get('id')}", "channel":"Call", "form":"",
            "name": c.get("name") or c.get("caller_name") or c.get("caller_number","Caller"),
            "email":"", "phone": c.get("caller_number",""),
            "service":"", "keyword": c.get("keyword","") or (c.get("utm",{}) or {}).get("term",""),
            "landing_page": (c.get("utm",{}) or {}).get("source",""),
            "received_iso": c.get("called_at") or c.get("created_at"), "status":"Genuine"})
    return leads, spam, None

def main():
    have_keys = any(os.environ.get(k) for k in ("GF_CONSUMER_KEY","CTM_API_KEY"))
    if not have_keys:
        print("No Gravity/CTM API keys configured - skipping fetch (dashboard left unchanged).")
        return
    base_path = os.path.join(ROOT,"leads.json")
    base = json.load(open(base_path)) if os.path.exists(base_path) else {"meta":{},"spend":{"period_spend_usd":0,"reported_conversions":0,"note":""},"excluded":{"form_test_entries":0,"form_spam":0}}  # keep meta/spend defaults
    gf, gferr = fetch_gravity()
    ctm, ctm_spam, ctmerr = fetch_ctm()
    errors = [e for e in (gferr, ctmerr) if e]
    if gf or ctm:  # only overwrite when we actually pulled something
        base["leads"] = gf + ctm
        base["excluded"]["call_spam"] = ctm_spam
    base["meta"]["last_fetch_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    base["meta"]["fetch_notes"] = errors or ["ok"]
    json.dump(base, open(os.path.join(ROOT,"leads.json"),"w"), ensure_ascii=False, indent=2)
    print("fetched forms:", len(gf), "calls:", len(ctm), "call-spam:", ctm_spam, "errors:", errors)

if __name__ == "__main__":
    main()
