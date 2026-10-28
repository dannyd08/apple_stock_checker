// Paste into a new Cloudflare Worker and open its URL: shows whether Apple's
// stock API answers from Cloudflare's network.
const PROBES = [
  ["California", "", "95014", "MK1F4LL/A", "UNLOCKED/US"],
  ["India", "/in", "400051", "MK2D4HN/A"],
  ["Singapore", "/sg", "018972", "MK2D4X/A"],
];

export default {
  async fetch() {
    const lines = [];
    for (const [name, path, location, part, cppart] of PROBES) {
      const base = `https://www.apple.com${path}/shop`;
      const url = `${base}/fulfillment-messages?fae=true&pl=true&mts.0=regular` +
                  (cppart ? `&cppart=${cppart}` : "") + `&parts.0=${part}&location=${location}`;
      const res = await fetch(url, {headers: {Accept: "application/json", Referer: `${base}/buy-iphone/iphone-duo`}});
      lines.push(`${name}: HTTP ${res.status}`);
    }
    return new Response(lines.join("\n"));
  },
};
