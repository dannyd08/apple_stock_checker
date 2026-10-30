"""Check Apple Store pickup availability for iPhone Duo and send alerts.

Runs once per invocation (GitHub Actions calls it on a schedule). Uses only the
standard library. State is kept in a JSON file so you are alerted when a model
*becomes* available at a store, not on every run while it stays in stock.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

STATE_FILE = os.environ.get("STATE_FILE", "state.json")
CONFIG_FILE = os.environ.get("CONFIG_FILE", "config.json")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_MENTION = os.environ.get("GITHUB_MENTION", "").strip()
# Optional: Pushover (pushover.net). Stock alerts go out at emergency priority, which
# repeats until acknowledged and, with Critical Alerts enabled in the iOS app, sounds
# through the mute switch.
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY", "").strip()
PUSHOVER_APP_TOKEN = os.environ.get("PUSHOVER_APP_TOKEN", "").strip()
PUSHOVER_RETRY = 30      # seconds between repeats of an unacknowledged stock alert
PUSHOVER_EXPIRE = 1800   # stop repeating after this many seconds
ALERT_ISSUE_TITLE = "iPhone Duo stock alerts"
# Send a "checker is blocked" alert after this many consecutive fully failed runs.
FAILURE_ALERT_THRESHOLD = 6
# Apple limits requests per address (a burst of ~30 earns a 541 for 10-15 minutes),
# so keep at least this many seconds between requests to it.
REQUEST_GAP = 2.0
_last_apple_request = 0.0
# After two checks in a row answered 541, wait this long (blocks last 10-15 min).
BLOCK_COOLDOWN = 600

# The newer fulfillment-messages endpoint sits behind Apple's browser bot check and
# answers HTTP 541 to scripts; retail/pickup-message is the older, plainer one.
DEFAULT_ENDPOINT = "retail/pickup-message"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


def http(url, data=None, headers=None, method=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


# Alerts matter more than any one request: retry a notification send a few times.
NOTIFY_RETRY_DELAYS = (3, 10, 30)


def http_retry(url, data=None, headers=None, method=None):
    for attempt, delay in enumerate((0,) + NOTIFY_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            return http(url, data, headers, method)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == len(NOTIFY_RETRY_DELAYS):
                raise  # a 4xx won't improve with a retry
            last = e
        except Exception as e:  # network blips: "Network is unreachable", timeouts
            if attempt == len(NOTIFY_RETRY_DELAYS):
                raise
            last = e
        print(f"  retrying {url.split('/')[2]} after {type(last).__name__}: {last}", file=sys.stderr)


def fetch_stores(region, location, parts, endpoint=None):
    """Return the pickup 'stores' list for one region/location query."""
    global _last_apple_request
    endpoint = endpoint or region.get("endpoint", DEFAULT_ENDPOINT)
    params = {"pl": "true", "mts.0": "regular"}
    if endpoint == "fulfillment-messages":
        params["fae"] = "true"
    if region.get("cppart"):
        params["cppart"] = region["cppart"]  # carrier, e.g. UNLOCKED/US
    for i, part in enumerate(parts):
        params[f"parts.{i}"] = part
    params["location"] = location
    base = f"https://www.apple.com{region['path']}/shop"
    url = f"{base}/{endpoint}?{urllib.parse.urlencode(params, safe='/')}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Referer": f"{base}/buy-iphone/iphone-duo",
    }
    wait = _last_apple_request + REQUEST_GAP - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    try:
        status, body = http(url, headers=headers)
    finally:
        _last_apple_request = time.monotonic()
    data = json.loads(body)
    # retail/pickup-message answers with body.stores; fulfillment-messages nests it deeper.
    if "stores" in data.get("body", {}):
        return data["body"]["stores"] or []
    return data["body"]["content"]["pickupMessage"].get("stores", [])


def check_region(region):
    """Return ({key: info} for available store/part pairs, successful query count,
    and whether Apple answered 541 so the run should stop)."""
    parts = list(region["models"])
    available, ok, blocked = {}, 0, False
    for location in region["locations"]:
        try:
            stores = fetch_stores(region, location, parts)
        except urllib.error.HTTPError as e:
            print(f"  [{region['name']}] {location}: HTTP {e.code}", file=sys.stderr)
            if e.code == 541:
                blocked = True  # per-address limit: don't make it worse this run
                break
            continue
        except Exception as e:  # network error, bad JSON, changed schema
            print(f"  [{region['name']}] {location}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        ok += 1
        for store in stores:
            for part, pa in (store.get("partsAvailability") or {}).items():
                if pa.get("pickupDisplay") != "available":
                    continue
                key = f"{region['name']}|{store.get('storeNumber')}|{part}"
                available[key] = {
                    "region": region["name"],
                    "model": region["models"].get(part, part),
                    "part": part,
                    "store": store.get("storeName", "?"),
                    "city": store.get("city", ""),
                    "quote": pa.get("pickupSearchQuote", ""),
                    "url": f"https://www.apple.com{region['path']}/shop/buy-iphone/iphone-duo",
                }
    print(f"  [{region['name']}] {ok}/{len(region['locations'])} queries ok, "
          f"{len(available)} store/model pairs available")
    return available, ok, blocked


def notify_ntfy(title, message, click=None, priority="high"):
    if not NTFY_TOPIC:
        return
    headers = {"Title": title.encode("utf-8"), "Priority": priority, "Tags": "iphone"}
    if click:
        headers["Click"] = click
    try:
        http_retry(f"{NTFY_SERVER}/{NTFY_TOPIC}", data=message.encode("utf-8"), headers=headers, method="POST")
    except Exception as e:
        print(f"ntfy failed: {e}", file=sys.stderr)


def notify_pushover(title, message, click=None, priority="high"):
    if not (PUSHOVER_USER_KEY and PUSHOVER_APP_TOKEN):
        return
    fields = {"token": PUSHOVER_APP_TOKEN, "user": PUSHOVER_USER_KEY,
              "title": title, "message": message}
    if click:
        fields["url"] = click
    if priority == "urgent":  # stock found: repeat until acknowledged
        fields.update({"priority": 2, "retry": PUSHOVER_RETRY, "expire": PUSHOVER_EXPIRE,
                       "sound": "persistent"})
    elif priority == "high":
        fields["priority"] = 1
    else:
        fields["priority"] = -1  # quiet, no sound
    try:
        http_retry("https://api.pushover.net/1/messages.json",
                   data=urllib.parse.urlencode(fields).encode(),
                   headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    except Exception as e:
        print(f"Pushover failed: {e}", file=sys.stderr)


def github_api(path, payload=None, method="GET"):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "duo-stock-checker",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    _, body = http_retry(f"https://api.github.com/repos/{GITHUB_REPOSITORY}{path}", data, headers, method)
    return json.loads(body) if body else None


def notify_github(title, message):
    """Comment on a single alerts issue; the @mention triggers a GitHub Mobile push."""
    if not (GITHUB_TOKEN and GITHUB_REPOSITORY):
        return
    try:
        issues = github_api("/issues?state=open&per_page=100")
        issue = next((i for i in issues if i["title"] == ALERT_ISSUE_TITLE and "pull_request" not in i), None)
        if issue is None:
            issue = github_api("/issues", {"title": ALERT_ISSUE_TITLE,
                                           "body": "Stock alerts from the checker are posted here."}, "POST")
        mention = f"@{GITHUB_MENTION} " if GITHUB_MENTION else ""
        github_api(f"/issues/{issue['number']}/comments",
                   {"body": f"{mention}**{title}**\n\n{message}"}, "POST")
    except Exception as e:
        print(f"GitHub issue alert failed: {e}", file=sys.stderr)


def notify(title, message, click=None, priority="high"):
    print(f"ALERT: {title}\n{message}")
    notify_ntfy(title, message, click, priority)
    notify_pushover(title, message, click, priority)
    notify_github(title, message)


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main():
    config = load_json(CONFIG_FILE, None)
    if config is None:
        sys.exit(f"missing or invalid {CONFIG_FILE}")
    state = load_json(STATE_FILE, {"available": {}, "consecutive_failures": 0})
    test_mode = "--test-notify" in sys.argv

    if test_mode:
        notify("Test alert: iPhone Duo checker",
               "Notifications work. You'll get alerts like this when stock appears.",
               priority="default")

    previous = state.get("available", {})
    now_available, total_ok, blocked = {}, 0, False
    for region in config["regions"]:
        avail, ok = {}, 0
        if not blocked:
            avail, ok, blocked = check_region(region)
            if blocked:
                print("  Apple answered 541 (rate limit); skipping the rest of this run")
        if ok < len(region["locations"]):
            # Some queries failed: keep that region's old entries so they don't re-alert later.
            for k, v in previous.items():
                if v["region"] == region["name"]:
                    avail.setdefault(k, v)
        now_available.update(avail)
        total_ok += ok

    if total_ok == 0:
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        print(f"All queries failed ({state['consecutive_failures']} runs in a row)")
        if state["consecutive_failures"] == FAILURE_ALERT_THRESHOLD:
            notify("iPhone Duo checker is blocked",
                   f"Every Apple request has failed for {FAILURE_ALERT_THRESHOLD} runs in a row. "
                   "Apple may be blocking GitHub's servers; check the Actions logs.",
                   priority="default")
        # Keep previous availability so a temporary outage doesn't re-trigger alerts.
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=1)
        return blocked

    if state.get("consecutive_failures", 0) >= FAILURE_ALERT_THRESHOLD:
        notify("iPhone Duo checker is working again", "Apple requests are succeeding again.",
               priority="low")
    state["consecutive_failures"] = 0

    new = {k: v for k, v in now_available.items() if k not in previous}
    if new:
        lines = [f"• {v['model']} — {v['store']}, {v['city']} ({v['region']})"
                 + (f": {v['quote']}" if v["quote"] else "")
                 for v in sorted(new.values(), key=lambda v: (v["region"], v["model"], v["store"]))]
        regions = sorted({v["region"] for v in new.values()})
        notify(f"iPhone Duo in stock: {', '.join(regions)}",
               "\n".join(lines[:25]) + (f"\n…and {len(lines) - 25} more" if len(lines) > 25 else ""),
               click=next(iter(new.values()))["url"], priority="urgent")
    else:
        print("No new availability.")

    state["available"] = now_available
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=1)
    return blocked


def run_loop(every, run_for=None):
    """Check every `every` seconds, for `run_for` seconds (forever if None).

    With `run_for` set (a chained GitHub Actions run), a 541 ends the run at once: the
    queued successor starts within seconds, almost certainly from a different address,
    which is the fastest way past a per-address block. Without it (a standalone loop),
    one 541 doubles the wait and two in a row trigger BLOCK_COOLDOWN.
    """
    stop_at = time.monotonic() + run_for if run_for else None
    blocked_streak = 0
    while True:
        print(time.strftime("%Y-%m-%d %H:%M:%S"), "checking", flush=True)
        blocked = main()
        sys.argv = [a for a in sys.argv if a != "--test-notify"]
        if blocked and stop_at:
            print("Ending this run early so the next one starts from a fresh address", flush=True)
            return
        blocked_streak = blocked_streak + 1 if blocked else 0
        delay = max(every, BLOCK_COOLDOWN) if blocked_streak >= 2 else every * (2 if blocked else 1)
        if stop_at and time.monotonic() + delay > stop_at:
            return
        time.sleep(delay)


def arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


if __name__ == "__main__":
    # "--every SECONDS" keeps checking in a loop; "--for SECONDS" ends the loop after
    # that long. GitHub Actions uses both to check more often than its scheduler can.
    if arg("--every"):
        run_loop(int(arg("--every")), int(arg("--for") or 0) or None)
    else:
        main()
