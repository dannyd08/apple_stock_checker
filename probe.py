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

for endpoint in ("retail/pickup-message", "fulfillment-messages"):
    for name, region, location, part in PROBES:
        try:
            stores = fetch_stores(region, location, [part], endpoint)
            summary = ", ".join(f"{s.get('storeName')}={s['partsAvailability'][part]['pickupDisplay']}"
                                for s in stores[:3] if part in s.get("partsAvailability", {}))
            print(f"{endpoint} {name}: OK, {len(stores)} stores ({summary})")
        except urllib.error.HTTPError as e:
            print(f"{endpoint} {name}: HTTP {e.code}")
        except Exception as e:
            print(f"{endpoint} {name}: {type(e).__name__}: {e}")
