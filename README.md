# iPhone Duo stock checker

Checks Apple Store pickup availability for every iPhone Duo model in **California**,
**India** and **Singapore** every 5 minutes, using GitHub Actions. It alerts you when a
model becomes available at a store.

## Alerts

- **GitHub app:** each alert is a comment on the "iPhone Duo stock alerts" issue that
  @-mentions the repo owner, so GitHub Mobile sends a push notification. This works with
  no setup.
- **ntfy (optional, faster):** install the [ntfy](https://ntfy.sh) app, subscribe to a
  random topic name, and add that name as the repository secret `NTFY_TOPIC`
  (Settings → Secrets and variables → Actions).

Run the workflow by hand with **Send a test notification** ticked to check both.

## Changing what it watches

Edit `config.json`: remove models you don't want, or add postcodes under `locations`.
Each location query returns the Apple Stores nearest to it.
