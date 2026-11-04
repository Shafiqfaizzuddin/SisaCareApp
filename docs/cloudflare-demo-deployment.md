# Cloudflare demo deployment for sisacare.online

This setup keeps the application, Florence-2, Ollama, SQLite and uploaded report
photos on the presentation laptop. Cloudflare Tunnel publishes only the FastAPI
web server at `https://sisacare.online`. The laptop must remain awake and online.

## Prepare the local application

1. Back up `backend/storage/sisacare.db` and `backend/storage/reports` before
   exposing the application. Keep the backup outside the published frontend.
2. Keep `backend/.env` private. It still holds the existing Supabase and SMTP
   configuration; `scripts/run-cloudflare-api.ps1` overrides only deployment
   settings in its process. Do not place secrets in `frontend/.env.production`.
3. Set `VITE_API_BASE_URL=/api/v1` in the ignored
   `frontend/.env.production`. Keep the existing public Supabase URL/key, Google
   web client ID and Maps browser key there. The new Google Web client is in the
   `SisaCare AI Demo` project (`sisacare-ai-demo`) under the Faiz Google account.
   Keep its client ID synchronized across `frontend/.env.local`,
   `frontend/.env.production`, `backend/.env`, and the Supabase Google provider.
   Supabase currently also permits the previous client ID for rollback. The
   application uses Google ID tokens; the Supabase OAuth client secret remains
   paired with the previous client for its separate redirect flow.
   The `SisaCare Incident Map` JavaScript Map ID and a browser API key now live in
   the same Google Cloud project. The key permits `https://sisacare.online/*`,
   `http://localhost:5173/*`, and `http://127.0.0.1:5173/*`, and is limited to
   Maps JavaScript, Places API (New), and Geocoding API. Build from `frontend` with
   `npm run build` after any frontend environment change.
4. Start Florence-2 once from the repository root:
   `./florence_service/.venv/Scripts/python.exe -m florence_service.run`.
   Confirm `http://127.0.0.1:8765/health` reports `model_ready: true`.
5. Start Ollama and confirm `ollama list` includes the configured vision
   (`qwen2.5vl:3b`) and report (`llama3.2`) models.
6. Run `./scripts/run-cloudflare-api.ps1` from PowerShell. It serves the built
   frontend and API together on `http://127.0.0.1:8000`; keep this process
   running during the demo. Check `/api/v1/health` and a nested frontend route.
   To start Florence, Ollama, the backend, and the Tunnel in hidden background
   processes for a presentation, run `./scripts/start-cloudflare-demo.ps1`
   instead. It avoids duplicate listeners and writes logs under the ignored
   `backend/.runtime` directory. These processes stop when Windows shuts down;
   run the script again after a reboot. Keep the laptop awake and online.

Do not expose Florence-2 port 8765, Ollama port 11434 or the SQLite files as
Tunnel routes. Do not start a second Florence worker on the same port.

## Cloudflare dashboard

1. Confirm `sisacare.online` is active in the Cloudflare dashboard and its
   nameservers are configured.
2. Under **Networking > Tunnels**, create a Cloudflare Tunnel named
   `sisacare-demo`, using the Windows connector on the presentation laptop.
   Keep the connector token private. The official Cloudflare Windows binary is
   saved at `backend/.runtime/cloudflared.exe`; the access-restricted token file
   is `backend/.runtime/cloudflare-token.txt`. From the repository root, run
   `./backend/.runtime/cloudflared.exe tunnel run --token-file ./backend/.runtime/cloudflare-token.txt`.
   Both files are ignored by Git. Never paste the token into source code.
3. Add one **Published application** route: root domain `sisacare.online`,
   service URL `http://127.0.0.1:8000`. If the dashboard requires a subdomain
   field, leave it blank for the root.
4. Confirm the Tunnel reports **Healthy** and open `https://sisacare.online`.
   Cloudflare serves HTTPS to visitors while the connector reaches FastAPI
   through local HTTP.

## Authentication, maps and mail

- In Google Cloud, the SisaCare Web OAuth client is published for External users and permits
  `https://sisacare.online`, `http://localhost:5173`, and
  `http://127.0.0.1:5173` as JavaScript origins. The Supabase callback is
  registered as a redirect URI. The frontend and backend must use the same
  client ID. The public privacy notice is at `/privacy`.
- In Supabase Auth URL Configuration, set Site URL to
  `https://sisacare.online`. Allow the exact redirect URLs used by the app:
  `/login`, `/account`, and `/password-reset`; retain localhost URLs for local
  development. Keep Confirm email enabled.
- Google Maps Platform shows a linked billing account and a **Pay as you go**
  plan for this project; this setup did not add a payment method. Usage can
  incur charges. The browser key is restricted to this site and local
  development, and only Maps JavaScript API, Places API (New), and Geocoding
  API are enabled. Review billing budgets and quotas in Google Cloud before
  inviting others to use the demo. The production Map ID and key passed a
  browser map-load check on `sisacare.online`. Photo analysis does not depend
  on Maps.
- The API startup script sets `EMAIL_PUBLIC_BASE_URL` to the HTTPS domain.
  Mailtrap Sandbox captures admin messages; actual user email delivery still
  requires a delivery-capable `USER_SMTP_*` account.

## Demo checks

Test from a phone on mobile data: website, email/password and Google sign-in,
photo analysis, incident map, report submission, admin review and email links.
The backend uses one worker so its email outbox and SQLite writes remain within
the existing prototype architecture. Keep the laptop powered and disable sleep
for the presentation. Supabase free projects may pause after inactivity, so
check the hosted project before demo day.
