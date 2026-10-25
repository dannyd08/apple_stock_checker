# iPhone Duo stock checker

Checks Apple Store pickup availability for every iPhone Duo model in **California**,
**India** and **Singapore**, and alerts you when a model becomes available at a store.
It alerts once when stock appears, not on every check while it stays in stock.

## Where it can run

Apple answers requests from cloud servers (GitHub Actions, cloud VMs) with HTTP 541,
so the checker has to run on a **home internet connection**: a Mac or PC that stays on,
a Raspberry Pi, or an old Android phone with [Termux](https://termux.dev). It needs only
Python 3, with no packages to install.

```sh
git clone https://github.com/dannyd08/apple_stock_checker
cd apple_stock_checker
NTFY_TOPIC=your-topic-name python3 checker.py --every 300 --test-notify
```

`--every 300` checks every 5 minutes until you stop it. `--test-notify` sends one test
alert at start-up. On a Mac, prefix the command with `caffeinate -i` so the Mac doesn't
sleep. To keep it running after you close the terminal, use
`nohup ... > checker.log 2>&1 &`.

The GitHub Actions workflow is kept for manual test runs (Actions → Run workflow). Its
5-minute schedule is commented out; uncomment it if Apple stops blocking GitHub.

## Alerts

- **ntfy:** install the [ntfy](https://ntfy.sh) app, subscribe to a random topic name,
  and pass that name as `NTFY_TOPIC` (for GitHub runs, add it as the repository secret
  `NTFY_TOPIC`).
- **GitHub app:** with `GITHUB_TOKEN` and `GITHUB_REPOSITORY` set (automatic in
  Actions), each alert is also a comment on the "iPhone Duo stock alerts" issue that
  @-mentions `GITHUB_MENTION`, which triggers a GitHub Mobile push.

If every request fails for 6 checks in a row, you get one "checker is blocked" alert.

## Changing what it watches

Edit `config.json`: remove models you don't want, or add postcodes under `locations`.
Each location query returns the Apple Stores nearest to it.
