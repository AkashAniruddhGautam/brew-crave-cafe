# Brew & Crave Cafe Billing

The cafe clock and bill timestamps use server-synchronized India Standard Time (IST). The displayed date/time refreshes continuously, and browser clocks are resynchronized with the backend every minute. Order timestamps are recorded by the backend and displayed in IST.

## WhatsApp bill sharing

After completing a bill, select **Send bill on WhatsApp**, enter the customer's number, and choose **Download PDF & open chat**. The app creates and downloads the bill PDF and opens a WhatsApp chat with the bill number in a prefilled message. Attach the downloaded PDF in WhatsApp and press **Send**.

The browser cannot attach or send a file through a WhatsApp chat link automatically; automatic delivery requires WhatsApp Business Cloud API credentials, customer opt-in, and the required business setup.

## Run locally

1. Install Python 3.9 or newer.
2. From this folder, install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Start the server:

   ```powershell
   python app.py
   ```

4. Open <http://127.0.0.1:8000>. On first launch, create the owner username and password. Visit <http://127.0.0.1:8000/admin> to add/edit/hide products and manage staff accounts.

## Deploy the backend to Render

1. Push this project to a GitHub repository.
2. In Netlify, import the repository first. `netlify.toml` builds and publishes only `index.html`, `app.css` and `app.js` from `dist/`; the Python backend and database are not published as static files. The API proxy will not work until the Render hostname is set in `netlify.toml`.
3. Copy the generated Netlify site origin, such as `https://brew-crave-cafe.netlify.app`.
4. In Render, choose **New → Blueprint** and connect the same repository. Render reads `render.yaml`, installs `requirements.txt`, and deploys the Flask app with Gunicorn on the free web-service plan. The Blueprint allows the Netlify origin `https://cafebillingsystem.netlify.app`.
5. Wait for the Render deployment to become live and copy its exact `onrender.com` hostname. Render automatically allows its own hostname. If Netlify reports a host error because its proxy sends a different `Host` header, add the hostname received in that error to a `CAFE_ALLOWED_HOSTS` environment variable in Render (hostname only, comma-separated; no `https://`), then redeploy.

**Free-plan data warning:** Render's free service has no persistent disk. SQLite orders, products, owner/staff accounts, and the session-signing key are stored on its temporary filesystem and can be lost when the service restarts or redeploys. The free service can also sleep when idle and take time to wake up. This is suitable for trying the app, not for keeping cafe billing records. Back up important data and do not treat this deployment as durable storage.

Render's official [Flask deployment guide](https://render.com/docs/deploy-flask) and [persistent disk guide](https://render.com/docs/disks) explain these settings. A disk is not included with the free web-service filesystem.

## Deploy the frontend to Netlify

1. Replace `YOUR-RENDER-SERVICE.onrender.com` in `netlify.toml` with the exact Render hostname. Keep the `https://` prefix in the rewrite target.
2. Commit/push the changed file to GitHub; Netlify will rebuild and publish the frontend.
3. Open the deployed HTTPS Netlify site. Sign in/create the owner account there; do not use the Render API URL as the cafe UI.
4. If the Netlify site hostname changes, update `CAFE_ALLOWED_ORIGINS` in Render to the new exact `https://...netlify.app` origin, then redeploy/restart the Render service.

Netlify's `/api/*` rewrite proxies requests to Render while keeping the browser on the Netlify origin. This lets the secure, HTTP-only session cookie work without cross-site cookie settings or a public CORS policy. The `/admin` rewrite serves the single-page app on direct visits. See Netlify's official [proxy/rewrite guide](https://docs.netlify.com/manage/routing/redirects/rewrites-proxies/) and [build settings guide](https://docs.netlify.com/build/configure-builds/overview/).

## Data, security and operations

- On the Render free plan, orders, immutable bill item/price snapshots, products, user accounts, and the randomly generated session key live on an ephemeral filesystem and may disappear after a restart or redeploy. Keep protected backups of important business records.
- The default menu prices and 5% GST are sample values. Update products in `/admin`; confirm your actual tax settings with your accountant before issuing tax invoices.
- The app is designed for one Render instance and SQLite, not multiple backend instances or shared Wi-Fi.
- Cash/UPI/card are recorded as payment methods; the app does not process a real payment.
- If you later need multiple simultaneous backend instances, migrate SQLite to managed PostgreSQL before scaling out.
