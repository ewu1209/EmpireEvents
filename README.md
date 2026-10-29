# EmpireEvents

A lobby-TV slideshow of upcoming events at Empire Scottsdale, pulled live from OfficeRnD.

```
TV browser ──► GitHub Pages (docs/)            static page: layout, slideshow, clock
     │
     └──────► Cloud Run function (function/)   calls the OfficeRnD API, returns events as JSON
                     │
                     └──► OfficeRnD public API   (client ID and secret come from Secret Manager)
```

- **`docs/`** is served by GitHub Pages. `index.html` fetches the function URL set in `config.js` every 5 minutes. It keeps the last good list in `localStorage`, so the screen survives outages and power cuts. Flyers load straight from OfficeRnD's CDN. Add `#3` to the URL to open on the third slide.
- **`function/`** is a Python Cloud Run function (`main.py`, entry point `events`).
  - Each call asks OfficeRnD for events starting from *now*, using `start[$gte]` and following the pages with `$cursorNext`.
  - It drops past and cancelled events, writes a short blurb from each description, and makes the RSVP QR codes.
  - Responses are cached for 5 minutes, and if OfficeRnD is down it serves the last good response.

No event data and no credentials are stored in this repo.

## Blurbs

The blurb is the opening of the event's OfficeRnD description, trimmed to about 190 characters. Lines that mention a promo code are always included, first and word for word. Disclaimers, waivers, date lines, emails, phone numbers and URLs are skipped. To change what a slide says, edit the event description in OfficeRnD.

## Deploying the function

**Live setup:** Google Cloud project `empire-events-2610`, region `us-west1`, function `empire-events`, running as the service account `empire-events-fn@empire-events-2610.iam.gserviceaccount.com`. That account can do only one thing: read the two OfficeRnD secrets. The OfficeRnD API app is **EmpireEvents TV** (Settings → Data & Extensibility → Developer Tools), which has the single scope `flex.collaboration.events.read`. Tokens come from `https://identity.officernd.com/oauth/token`.

From scratch:

```bash
P=empire-events-2610
gcloud services enable cloudfunctions.googleapis.com run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com --project=$P

# Runtime identity that can only read the two secrets
gcloud iam service-accounts create empire-events-fn --project=$P
scripts/set-secrets.sh $P        # prompts for client ID and secret (hidden), stores them, grants access

gcloud functions deploy empire-events --project=$P --gen2 --runtime=python312 --region=us-west1 \
  --source=function --entry-point=events --trigger-http --allow-unauthenticated \
  --memory=256Mi --max-instances=3 \
  --service-account=empire-events-fn@$P.iam.gserviceaccount.com \
  --set-env-vars=OFFICERND_ORG=empire,ALLOWED_ORIGIN=https://ewu1209.github.io \
  --set-secrets=OFFICERND_CLIENT_ID=officernd-client-id:latest,OFFICERND_CLIENT_SECRET=officernd-client-secret:latest
```

Put the function URL that the deploy prints into `docs/config.js`, then commit and push.

**Rotating credentials:** add new secret versions (`gcloud secrets versions add officernd-client-secret --data-file=-`), then redeploy. You can leave out `--allow-unauthenticated`, because the public access setting persists. A secret is read only when an instance starts.

**Troubleshooting:** the function logs OfficeRnD's OAuth error text, which never includes the secret. If you see `invalid_client`, the stored ID and secret don't match the OfficeRnD app.

The function is public by design: the TV can't sign in. It returns only what the screen shows, which is title, times, place, blurb, RSVP link, flyer URL and QR code.

## Environment variables (function)

| Name | Source | Purpose |
|---|---|---|
| `OFFICERND_CLIENT_ID` | Secret Manager | API client ID |
| `OFFICERND_CLIENT_SECRET` | Secret Manager | API client secret |
| `OFFICERND_ORG` | plain | organization slug (default `empire`) |
| `ALLOWED_ORIGIN` | plain | CORS origin of the Pages site (default `*`) |
| `CACHE_SECONDS` | plain | response cache lifetime (default `300`) |

## Running locally

```bash
cd function && pip install -r requirements.txt
export OFFICERND_CLIENT_ID=… OFFICERND_CLIENT_SECRET=…   # don't commit these anywhere
functions-framework --target=events --port=8080
```

Then serve `docs/` (for example with `python3 -m http.server`) and point `config.js` at `http://127.0.0.1:8080/` while testing.
