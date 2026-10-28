# iPhone Duo stock checker

Checks Apple Store pickup availability for the iPhone Duo (512 GB and 1 TB, Night Sky)
in the **SF Bay Area**, **Mumbai** and **Singapore** every 3 minutes on GitHub Actions,
and alerts you when one becomes available at a store. It alerts once when stock appears, not on every
check while it stays in stock.

## Alerts

- **ntfy (phone push, recommended):** install the [ntfy](https://ntfy.sh) app, subscribe
  to a random topic name, and add that name as the repository secret `NTFY_TOPIC`
  (Settings → Secrets and variables → Actions → New repository secret). Stock alerts are
  sent at ntfy's "urgent" priority and tapping one opens Apple's buy page.
- **GitHub (no setup):** each alert is also a comment on the "iPhone Duo stock alerts"
  issue that @-mentions the repo owner, so the GitHub mobile app and email notify you.

To test: Actions → "Check iPhone Duo stock" → Run workflow, with
**Send a test notification** ticked.

If every request fails for 6 runs in a row, you get one "checker is blocked" alert, and
one "working again" alert when it recovers.

## How it talks to Apple

Apple's buy page uses `/shop/fulfillment-messages`, but that endpoint sits behind a
browser bot check (`/shop/shld/s3/verify.js` sets a `shld_bt_ck` cookie) and answers
HTTP 541 to any script from any network. The older `/shop/retail/pickup-message`
endpoint returns the same store data without it.

Apple does limit that endpoint per address: a burst of roughly 30 requests earns 541s
for 10–15 minutes. Each check is one request per location (3 in total), 2 seconds
apart, and a check stops at the first 541, keeping the previous state so nothing
re-alerts.

## How often it checks

GitHub's scheduler can't fire more often than every 5 minutes, and its fires are
best-effort: often 5–15 minutes late and occasionally dropped. So the workflow fires
every 15 minutes and each run loops, checking every 3 minutes for 28 minutes
(`CHECK_EVERY` and `RUN_FOR` in `.github/workflows/check.yml`). Runs share a
concurrency group, so the next fire waits as "pending" until the current run ends and
then takes over; one run is always active as long as at least one fire in every 28
minutes gets through. A fire that arrives while another is already pending replaces
it, which appears as a cancelled run in the Actions tab; that's normal. After any 541
the loop waits 10 minutes before trying again. Manual runs do a single check.

## Changing what it watches

Edit `config.json`: add or remove models (every colour and size is listed in the git
history of this file), or change the postcodes under `locations`. Each location query returns the 12 nearest Apple Stores (fewer in India
and Singapore); 94103 covers the Bay Area from Corte Madera to Palo Alto. More
locations mean more requests per check. `probe.py` makes one request per region to each endpoint and prints
what came back; the "Probe Apple endpoints" workflow runs it on GitHub.

## Running it yourself

Only Python 3 is needed:

```sh
NTFY_TOPIC=your-topic python3 checker.py --every 300 --test-notify
```
