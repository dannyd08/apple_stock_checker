// iPhone Duo stock checker for Google Apps Script (runs on Google's servers).
//
// 1. Run probe() and read the log. If every region says "HTTP 541", Apple blocks
//    Google's servers too, and there is no point continuing.
// 2. Otherwise run install() once. It checks every 5 minutes from then on and
//    emails you (and pings ntfy, if NTFY_TOPIC is set) when stock appears.

const NTFY_TOPIC = '';  // optional, e.g. 'duo-watch-c5b2777ba264'
const FAILURE_ALERT_THRESHOLD = 6;

const REGIONS = [
  {
    "name": "California",
    "path": "",
    "cppart": "UNLOCKED/US",
    "locations": [
      "94103",
      "95014",
      "95815",
      "90036",
      "92660",
      "92122"
    ],
    "models": {
      "MK1E4LL/A": "iPhone Duo 256GB Star White",
      "MK1F4LL/A": "iPhone Duo 256GB Night Sky",
      "MK1G4LL/A": "iPhone Duo 512GB Star White",
      "MK1H4LL/A": "iPhone Duo 512GB Night Sky",
      "MK1J4LL/A": "iPhone Duo 1TB Star White",
      "MK1L4LL/A": "iPhone Duo 1TB Night Sky",
      "MK1Q4LL/A": "iPhone Duo 2TB Star White",
      "MK1R4LL/A": "iPhone Duo 2TB Night Sky"
    }
  },
  {
    "name": "India",
    "path": "/in",
    "locations": [
      "400051",
      "110017",
      "560024",
      "411001"
    ],
    "models": {
      "MK2D4HN/A": "iPhone Duo 256GB Star White",
      "MK2E4HN/A": "iPhone Duo 256GB Night Sky",
      "MK2F4HN/A": "iPhone Duo 512GB Star White",
      "MK2G4HN/A": "iPhone Duo 512GB Night Sky",
      "MK2H4HN/A": "iPhone Duo 1TB Star White",
      "MK2J4HN/A": "iPhone Duo 1TB Night Sky",
      "MK2K4HN/A": "iPhone Duo 2TB Star White",
      "MK2L4HN/A": "iPhone Duo 2TB Night Sky"
    }
  },
  {
    "name": "Singapore",
    "path": "/sg",
    "locations": [
      "018972"
    ],
    "models": {
      "MK2D4X/A": "iPhone Duo 256GB Star White",
      "MK2E4X/A": "iPhone Duo 256GB Night Sky",
      "MK2F4X/A": "iPhone Duo 512GB Star White",
      "MK2G4X/A": "iPhone Duo 512GB Night Sky",
      "MK2H4X/A": "iPhone Duo 1TB Star White",
      "MK2J4X/A": "iPhone Duo 1TB Night Sky",
      "MK2K4X/A": "iPhone Duo 2TB Star White",
      "MK2L4X/A": "iPhone Duo 2TB Night Sky"
    }
  }
];

function fetchStores_(region, location, parts) {
  const params = ['fae=true', 'pl=true', 'mts.0=regular'];
  if (region.cppart) params.push('cppart=' + region.cppart);  // carrier, e.g. UNLOCKED/US
  parts.forEach((p, i) => params.push('parts.' + i + '=' + p));
  params.push('location=' + encodeURIComponent(location));
  const base = 'https://www.apple.com' + region.path + '/shop';
  const res = UrlFetchApp.fetch(base + '/fulfillment-messages?' + params.join('&'), {
    muteHttpExceptions: true,
    headers: {Accept: 'application/json', Referer: base + '/buy-iphone/iphone-duo'},
  });
  if (res.getResponseCode() !== 200) throw new Error('HTTP ' + res.getResponseCode());
  return JSON.parse(res.getContentText()).body.content.pickupMessage.stores || [];
}

function probe() {
  REGIONS.forEach(region => {
    const part = Object.keys(region.models)[0];
    try {
      const stores = fetchStores_(region, region.locations[0], [part]);
      Logger.log(region.name + ': OK, ' + stores.length + ' stores returned');
    } catch (e) {
      Logger.log(region.name + ': ' + e.message);
    }
  });
}

function notify_(title, message) {
  Logger.log(title + '\n' + message);
  MailApp.sendEmail(Session.getEffectiveUser().getEmail(), title, message);
  if (NTFY_TOPIC) {
    UrlFetchApp.fetch('https://ntfy.sh/' + NTFY_TOPIC, {
      method: 'post', payload: message, headers: {Title: title, Priority: 'high', Tags: 'iphone'},
      muteHttpExceptions: true,
    });
  }
}

function check() {
  const props = PropertiesService.getScriptProperties();
  const previous = JSON.parse(props.getProperty('available') || '{}');
  let failures = Number(props.getProperty('failures') || 0);
  const now = {};
  let totalOk = 0;

  REGIONS.forEach(region => {
    const parts = Object.keys(region.models);
    let ok = 0;
    region.locations.forEach(location => {
      let stores;
      try {
        stores = fetchStores_(region, location, parts);
      } catch (e) {
        Logger.log(region.name + ' ' + location + ': ' + e.message);
        return;
      }
      ok++;
      stores.forEach(store => {
        Object.entries(store.partsAvailability || {}).forEach(([part, pa]) => {
          if (pa.pickupDisplay !== 'available') return;
          now[region.name + '|' + store.storeNumber + '|' + part] = {
            region: region.name, model: region.models[part] || part,
            store: store.storeName, city: store.city || '', quote: pa.pickupSearchQuote || '',
          };
        });
      });
    });
    if (ok < region.locations.length) {
      // Some queries failed: keep that region's old entries so they don't re-alert later.
      Object.entries(previous).forEach(([k, v]) => {
        if (v.region === region.name && !(k in now)) now[k] = v;
      });
    }
    totalOk += ok;
  });

  if (totalOk === 0) {
    failures++;
    props.setProperty('failures', String(failures));
    if (failures === FAILURE_ALERT_THRESHOLD) {
      notify_('iPhone Duo checker is blocked',
              'Every Apple request has failed ' + failures + ' times in a row.');
    }
    return;
  }
  if (failures >= FAILURE_ALERT_THRESHOLD) {
    notify_('iPhone Duo checker is working again', 'Apple requests are succeeding again.');
  }
  props.setProperty('failures', '0');

  const fresh = Object.keys(now).filter(k => !(k in previous)).map(k => now[k]);
  if (fresh.length) {
    const lines = fresh.map(v => '• ' + v.model + ' — ' + v.store + ', ' + v.city +
                                 ' (' + v.region + ')' + (v.quote ? ': ' + v.quote : ''));
    const regions = [...new Set(fresh.map(v => v.region))].sort().join(', ');
    notify_('iPhone Duo in stock: ' + regions, lines.join('\n'));
  }
  props.setProperty('available', JSON.stringify(now));
}

function install() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('check').timeBased().everyMinutes(5).create();
  notify_('iPhone Duo checker installed', 'Checking every 5 minutes. Alerts arrive by email.');
  check();
}

function uninstall() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
}
