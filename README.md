# Lefko Digital — Private Leads Dashboard (Grizzly Insulation Co.)

Self-updating, encrypted leads dashboard. Aggregates **form leads (Gravity Forms)** and
**phone-call leads (CallTrackingMetrics)**, filters spam/test entries, and shows the real
lead picture against ad spend. Times in **Mountain Time (Grizzly's Google Ads timezone)**
with **IST in brackets**.

## Security model
- Lead data (names/emails/phones) is **AES-256-GCM encrypted client-side** (Web Crypto).
- The published `index.html` contains **only ciphertext** — no readable PII in page source.
- Password prompt decrypts in the browser; the password is a **GitHub Secret** (`DASH_PASSWORD`) and is never stored in the repo.
- `robots.txt` (disallow all, incl. GPTBot/ClaudeBot/CCBot/PerplexityBot) + `noindex,noai,noarchive` meta tags block search engines and AI crawlers.
- Recommended: keep the repo **private** and use an unguessable Pages URL.

## Auto-refresh (every 8 hours)
`.github/workflows/refresh.yml` runs on cron `0 */8 * * *` (00:00 / 08:00 / 16:00 UTC):
1. `scripts/fetch_leads.py` pulls Gravity Forms + CTM, filters spam/test → `data/leads.json`
2. `scripts/generate_dashboard.py` rebuilds the encrypted `index.html`
3. Commits & pushes the update.

## Required GitHub Secrets
| Secret | Purpose |
|---|---|
| `DASH_PASSWORD` | Dashboard unlock password |
| `GF_BASE_URL` | e.g. https://grizzlyinsulationco.com |
| `GF_CONSUMER_KEY` / `GF_CONSUMER_SECRET` | Gravity Forms REST API key (Forms → Settings → REST API) |
| `GF_FORM_IDS` | e.g. `6,7` |
| `CTM_ACCOUNT_ID` | CallTrackingMetrics account id |
| `CTM_API_KEY` / `CTM_API_SECRET` | CTM API credentials (Account → Integrations → API) |

Google Ads spend is layered in via the Google Ads API in a later phase (shown as a static
figure until then).

## Manual/local build
```bash
pip install cryptography
DASH_PASSWORD="yourpass" python3 scripts/generate_dashboard.py
```
