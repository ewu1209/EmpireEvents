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

You need an OfficeRnD API app (**Settings → Developer Tools**) with the scope `flex.collaboration.events.read`, plus a Google Cloud project with billing enabled.

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable cloudfunctions.googleapis.com run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com

# Store the credentials in Secret Manager. They are typed at a hidden prompt, so they stay out of shell history.
printf 'OfficeRnD client ID: '; read -rs ID; echo
printf '%s' "$ID" | gcloud secrets create officernd-client-id --data-file=- && unset ID
printf 'OfficeRnD client secret: '; read -rs SECRET; echo
printf '%s' "$SECRET" | gcloud secrets create officernd-client-secret --data-file=- && unset SECRET

# Let the function's runtime service account read them
SA="$(gcloud projects describe "$(gcloud config get project)" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
for s in officernd-client-id officernd-client-secret; do
  gcloud secrets add-iam-policy-binding $s --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
done

gcloud functions deploy empire-events --gen2 --runtime=python312 --region=us-west1 \
  --source=function --entry-point=events --trigger-http --allow-unauthenticated \
  --memory=256Mi --max-instances=3 \
  --set-env-vars=OFFICERND_ORG=empire,ALLOWED_ORIGIN=https://YOUR_GITHUB_USER.github.io \
  --set-secrets=OFFICERND_CLIENT_ID=officernd-client-id:latest,OFFICERND_CLIENT_SECRET=officernd-client-secret:latest
```

Put the function URL that the deploy prints into `docs/config.js`, then commit and push. To rotate the credentials, run `gcloud secrets versions add …` and redeploy.

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
