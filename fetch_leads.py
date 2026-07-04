#!/usr/bin/env python3
"""Fetch leads from Gravity Forms REST API v2 + CallTrackingMetrics API, filter out
spam/test, and write leads.json for the dashboard generator.

Field IDs are auto-discovered from each form's definition by label, so the script keeps
working even if the form structure changes.

Env vars (GitHub Secrets):
  GF_BASE_URL, GF_CONSUMER_KEY, GF_CONSUMER_SECRET, GF_FORM_IDS (e.g. "6,7")
  CTM_ACCOUNT_ID, CTM_API_KEY, CTM_API_SECRET
  LOOKBACK_DAYS (optional, default 30)
"""
import os, json, base64, datetime, urllib.request, urllib.parse
from zoneinfo import ZoneInfo

MT = ZoneInfo("America/Denver")
UTC = datetime.timezone.utc
LOOKBACK = int(os.environ.get("LOOKBACK_DAYS", "30"))
ROOT = os.path.dirname(os.path.abspath(__file__))
TEST_MARKERS = ("test@test.com", "test test", "1234567", "asdf", "example.com", "qwerty")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
def _get(url, headers):
    headers = {**headers, "User-Agent": UA, "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code} @ {url.split('?')[0]} :: {body}")

def is_junk(name, email, phone):
    blob = f"{name} {email} {phone}".lower()
    return any(m in blob for m in TEST_MARKERS)

def utc_to_mt_iso(s):
    if not s:
        return None
    s = s.replace("T", " ").split("+")[0].strip()
    try:
        dt = datetime.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        return dt.astimezone(MT).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None

def discover_fields(form):
    """Map roles -> field id (string) using field labels/types."""
    roles = {}
    for f in form.get("fields", []):
        fid = str(f.get("id"))
        label = (f.get("label") or "").lower()
        ftype = f.get("type", "")
        if ftype == "name" and "name" not in roles: roles["name"] = fid
        elif ("name" in label and "user" not in label and "name" not in roles and ftype in ("text","name")): roles["name"] = fid
        if "email" in label and "email" not in roles: roles["email"] = fid
        if "phone" in label and "phone" not in roles: roles["phone"] = fid
        if "service" in label and "service" not in roles: roles["service"] = fid
        if "utm" in label and "utm" not in roles: roles["utm"] = fid
        if "gclid" in label and "gclid" not in roles: roles["gclid"] = fid
    return roles

def get_val(entry, fid):
    if not fid:
        return ""
    if fid in entry and entry[fid]:
        return entry[fid]
    # Name / composite fields store sub-inputs like "1.3", "1.6"
    parts = [entry.get(f"{fid}.{i}", "") for i in (2,3,4,6,8)]
    joined = " ".join(p for p in parts if p).strip()
    return joined

def fetch_gravity():
    base = os.environ.get("GF_BASE_URL"); ck = os.environ.get("GF_CONSUMER_KEY"); cs = os.environ.get("GF_CONSUMER_SECRET")
    if not (base and ck and cs):
        return [], "Gravity Forms API keys not set"
    base = base.rstrip("/")
    form_ids = [x.strip() for x in os.environ.get("GF_FORM_IDS", "6").split(",") if x.strip()]
    auth = base64.b64encode(f"{ck}:{cs}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    out = []; notes = []
    for fid in form_ids:
        try:
            form = _get(f"{base}/wp-json/gf/v2/forms/{fid}", headers)
            roles = discover_fields(form)
            data = _get(f"{base}/wp-json/gf/v2/forms/{fid}/entries?paging%5Bpage_size%5D=200", headers)
        except Exception as ex:
            notes.append(f"form {fid}: {ex}")
            continue
        ents = data.get("entries", []) if isinstance(data, dict) else []
        print(f"  form {fid}: roles={roles} total_count={data.get('total_count') if isinstance(data,dict) else '?'} entries={len(ents)}")
        for e in ents:
            name = get_val(e, roles.get("name")) or "(no name)"
            email = get_val(e, roles.get("email"))
            phone = get_val(e, roles.get("phone"))
            if is_junk(name, email, phone):
                continue
            out.append({
                "id": f"F-{e.get('id')}", "channel": "Form", "form": form.get("title", f"form {fid}"),
                "name": name, "email": email, "phone": phone,
                "service": get_val(e, roles.get("service")),
                "keyword": get_val(e, roles.get("utm")),
                "landing_page": e.get("source_url", ""),
                "received_iso": utc_to_mt_iso(e.get("date_created")),
                "status": "Genuine"})
    return out, ("; ".join(notes) if notes else None)

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
        dur = c.get("duration", 0) or 0
        tags = " ".join(c.get("tags", [])).lower() if isinstance(c.get("tags"), list) else str(c.get("tags", "")).lower()
        is_spam = ("spam" in tags) or ("robocall" in tags) or (dur < 20 and "lead" not in tags)
        if is_spam:
            spam += 1; continue
        leads.append({
            "id": f"C-{c.get('id')}", "channel": "Call", "form": "",
            "name": c.get("name") or c.get("caller_name") or c.get("caller_number", "Caller"),
            "email": "", "phone": c.get("caller_number", ""),
            "service": "", "keyword": c.get("keyword", "") or (c.get("utm", {}) or {}).get("term", ""),
            "landing_page": (c.get("utm", {}) or {}).get("source", ""),
            "received_iso": utc_to_mt_iso(c.get("called_at") or c.get("created_at")), "status": "Genuine"})
    return leads, spam, None

def main():
    have_keys = any(os.environ.get(k) for k in ("GF_CONSUMER_KEY", "CTM_API_KEY"))
    if not have_keys:
        print("No Gravity/CTM API keys configured - skipping fetch (dashboard left unchanged).")
        return
    base_path = os.path.join(ROOT, "leads.json")
    base = json.load(open(base_path)) if os.path.exists(base_path) else {
        "meta": {"account": "Grizzly Insulation Co.", "ads_account_id": "403-750-9921",
                 "source_timezone": "America/Denver", "source_timezone_label": "Mountain Time (GMT-06:00)",
                 "display_timezone_secondary": "Asia/Kolkata", "note": ""},
        "spend": {"period_spend_usd": 8590.45, "reported_conversions": 8, "note": "Google Ads Jun 3-Jul 2 2026 (static until Ads API added)."},
        "excluded": {"form_test_entries": 22, "form_spam": 0}, "leads": []}
    gf, gferr = fetch_gravity()
    ctm, ctm_spam, ctmerr = fetch_ctm()
    errors = [e for e in (gferr, ctmerr) if e]
    if gf or ctm:
        base["leads"] = gf + ctm
        base["excluded"]["call_spam"] = ctm_spam
    base["meta"]["last_fetch_utc"] = datetime.datetime.now(UTC).isoformat()
    base["meta"]["fetch_notes"] = errors or ["ok"]
    json.dump(base, open(base_path, "w"), ensure_ascii=False, indent=2)
    print("fetched forms:", len(gf), "calls:", len(ctm), "call-spam:", ctm_spam, "errors:", errors)

if __name__ == "__main__":
    main()
