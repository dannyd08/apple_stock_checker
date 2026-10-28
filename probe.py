"""One request per region to see whether Apple's stock API answers from this machine."""

import json
import urllib.error
import urllib.request

from checker import USER_AGENT, fetch_stores

PROBES = [("California", {"path": "", "cppart": "UNLOCKED/US"}, "95014", "MK1F4LL/A"),
          ("India", {"path": "/in"}, "400051", "MK2D4HN/A"),
          ("Singapore", {"path": "/sg"}, "018972", "MK2D4X/A")]

try:
    req = urllib.request.Request("https://ipinfo.io/json", headers={"User-Agent": USER_AGENT})
    info = json.load(urllib.request.urlopen(req, timeout=10))
    print(f"egress: {info.get('ip')} {info.get('org')} {info.get('city')}, {info.get('country')}")
except Exception as e:
    print(f"egress lookup failed: {e}")

for name, region, location, part in PROBES:
    try:
        stores = fetch_stores(region, location, [part])
        print(f"{name}: OK, {len(stores)} stores returned")
    except urllib.error.HTTPError as e:
        print(f"{name}: HTTP {e.code}")
    except Exception as e:
        print(f"{name}: {type(e).__name__}: {e}")
