// ==UserScript==
// @name         MBM PrizePicks Browser Bridge
// @namespace    mbm-esports
// @version      0.1.0
// @description  Posts PrizePicks projections response JSON only to MBM capture-board. Never sends cookies, request headers, or storage.
// @match        https://app.prizepicks.com/*
// @match        https://prizepicks.com/*
// @match        https://*.prizepicks.com/*
// @grant        none
// ==/UserScript==

(function () {
  "use strict";

  // Live capture MUST use HTTPS. Do not point the live bridge at 127.0.0.1.
  // Set on the PrizePicks origin, e.g.:
  //   localStorage.setItem("mbm_prizepicks_capture_url",
  //     "https://your-https-domain/api/live/prizepicks/capture-board");
  const configuredUrl =
    typeof localStorage !== "undefined"
      ? localStorage.getItem("mbm_prizepicks_capture_url")
      : null;
  const MBM_CAPTURE_URL = (configuredUrl || "").trim();
  const MBM_BRIDGE_TOKEN =
    (typeof localStorage !== "undefined" &&
      localStorage.getItem("mbm_bridge_token")) ||
    "";

  function assertLiveCaptureUrl(url) {
    if (!url) {
      throw new Error(
        "Set localStorage mbm_prizepicks_capture_url to your HTTPS capture-board URL " +
          "(https://your-https-domain/api/live/prizepicks/capture-board). " +
          "Do not use 127.0.0.1 for live capture."
      );
    }
    let parsed;
    try {
      parsed = new URL(url);
    } catch (_e) {
      throw new Error("mbm_prizepicks_capture_url is not a valid URL");
    }
    if (parsed.protocol !== "https:") {
      throw new Error(
        "Live PrizePicks bridge requires HTTPS capture URL; got " + parsed.protocol
      );
    }
    const host = parsed.hostname.toLowerCase();
    if (host === "127.0.0.1" || host === "localhost") {
      throw new Error(
        "Do not point the live PrizePicks bridge at 127.0.0.1/localhost; use your HTTPS domain"
      );
    }
    if (!parsed.pathname.replace(/\/$/, "").endsWith("/api/live/prizepicks/capture-board")) {
      throw new Error(
        "Capture URL path must end with /api/live/prizepicks/capture-board"
      );
    }
  }

  const SENSITIVE_FRAGMENTS = [
    "authorization",
    "cookie",
    "set-cookie",
    "token",
    "api_key",
    "apikey",
    "device_id",
    "device-id",
    "deviceid",
    "session",
    "password",
    "secret",
  ];

  function isoNow() {
    return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  }

  function walkSensitive(value, path, hits) {
    if (value && typeof value === "object") {
      if (Array.isArray(value)) {
        value.forEach((item, i) => walkSensitive(item, path + "[" + i + "]", hits));
        return;
      }
      Object.keys(value).forEach((key) => {
        const child = path ? path + "." + key : key;
        const low = String(key).toLowerCase();
        if (SENSITIVE_FRAGMENTS.some((frag) => low.includes(frag))) {
          hits.push(child);
        }
        walkSensitive(value[key], child, hits);
      });
    }
  }

  function rejectSensitive(obj) {
    const hits = [];
    walkSensitive(obj, "", hits);
    if (hits.length) {
      throw new Error(
        "Bridge refused send: sensitive keys present: " + hits.slice(0, 12).join(", ")
      );
    }
  }

  function isProjectionsUrl(url) {
    try {
      const u = typeof url === "string" ? new URL(url, location.href) : new URL(url.url || url);
      return (
        u.hostname === "api.prizepicks.com" &&
        u.pathname.replace(/\/$/, "").endsWith("/projections")
      );
    } catch (_e) {
      return false;
    }
  }

  /** Validate body; return payload or null if MBM must not be called. */
  function validateResponseBody(body) {
    if (!body || typeof body !== "object" || Array.isArray(body)) return null;
    if (!Array.isArray(body.data)) return null;
    if (body.data.length === 0) return null; // empty → do not call MBM
    return body;
  }

  function buildBridgeRequest(payload) {
    // Response JSON only — never cookies, request headers, or browser storage values.
    const body = {
      source: "prizepicks_browser_bridge",
      captured_at: isoNow(),
      authoritative_capture: false,
      payload: payload,
    };
    rejectSensitive(body);
    return body;
  }

  function showStatus(msg) {
    let el = document.getElementById("mbm-pp-bridge-status");
    if (!el) {
      el = document.createElement("div");
      el.id = "mbm-pp-bridge-status";
      el.setAttribute(
        "style",
        [
          "position:fixed",
          "z-index:2147483647",
          "right:12px",
          "bottom:12px",
          "max-width:360px",
          "padding:10px 12px",
          "font:12px/1.4 ui-monospace,Consolas,monospace",
          "color:#111",
          "background:#f5f2e9",
          "border:1px solid #333",
          "box-shadow:0 2px 8px rgba(0,0,0,.2)",
          "white-space:pre-wrap",
        ].join(";")
      );
      document.documentElement.appendChild(el);
    }
    el.textContent = msg;
  }

  function postToMbm(bridgeBody) {
    assertLiveCaptureUrl(MBM_CAPTURE_URL);
    const headers = {
      "Content-Type": "application/json",
    };
    if (MBM_BRIDGE_TOKEN) {
      headers["X-MBM-Bridge-Token"] = MBM_BRIDGE_TOKEN;
    }
    // Only these headers — never Cookie / Authorization from PrizePicks.
    // Ordinary fetch only (no GM_xmlhttpRequest / no @connect).
    const raw = JSON.stringify(bridgeBody);

    return fetch(MBM_CAPTURE_URL, {
      method: "POST",
      headers: headers,
      body: raw,
      credentials: "omit", // never attach browser cookies to MBM
    }).then(async (res) => {
      const text = await res.text();
      let parsed;
      try {
        parsed = JSON.parse(text || "{}");
      } catch (_e) {
        parsed = { raw: text };
      }
      if (!res.ok) throw new Error("MBM HTTP " + res.status + ": " + text);
      return parsed;
    });
  }

  function formatResult(result) {
    const captured = result.status || "?";
    const cleared = result.cleared_status || "?";
    return [
      "MBM PrizePicks bridge",
      "captured_at: " + (result.captured_at || ""),
      "record_count: " + String(result.record_count ?? ""),
      "status: " + captured + "  (CAPTURED ≠ CLEARED)",
      "cleared_status: " + cleared,
      "authoritative_capture: " + String(result.authoritative_capture),
      "scoring_touched: " + String(result.scoring_touched),
    ].join("\n");
  }

  async function capturePayload(payload) {
    const valid = validateResponseBody(payload);
    if (!valid) {
      showStatus("MBM bridge: invalid/empty projections — not calling MBM");
      return null;
    }
    const bridgeBody = buildBridgeRequest(valid);
    const result = await postToMbm(bridgeBody);
    showStatus(formatResult(result));
    return result;
  }

  // Intercept browser-visible projections responses (response body only).
  const origFetch = window.fetch;
  window.fetch = async function mbmBridgedFetch(input, init) {
    const response = await origFetch.apply(this, arguments);
    try {
      if (isProjectionsUrl(input)) {
        const clone = response.clone();
        clone
          .json()
          .then((body) => capturePayload(body))
          .catch(() => {
            showStatus("MBM bridge: projections response was not JSON — not calling MBM");
          });
      }
    } catch (_e) {
      /* never break PrizePicks */
    }
    return response;
  };

  async function manualCapture() {
    try {
      // Same-tab fetch uses the browser session for PrizePicks only.
      // Response JSON is copied into the MBM body; cookies are not forwarded.
      const res = await origFetch("https://api.prizepicks.com/projections", {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        showStatus("MBM bridge: PrizePicks HTTP " + res.status + " — not calling MBM");
        return;
      }
      const body = await res.json();
      await capturePayload(body);
    } catch (err) {
      showStatus("MBM bridge error: " + (err && err.message ? err.message : String(err)));
    }
  }

  // Manual capture: Alt+Shift+M (no GM APIs / no @connect).
  document.addEventListener(
    "keydown",
    (ev) => {
      if (ev.altKey && ev.shiftKey && (ev.key === "M" || ev.key === "m")) {
        ev.preventDefault();
        manualCapture();
      }
    },
    true
  );

  try {
    assertLiveCaptureUrl(MBM_CAPTURE_URL);
    showStatus(
      "MBM PrizePicks bridge armed\n" +
        "target: " +
        MBM_CAPTURE_URL +
        "\nJSON body only → HTTPS MBM (no cookies/headers)\n" +
        "manual: Alt+Shift+M"
    );
  } catch (err) {
    showStatus(
      "MBM PrizePicks bridge idle\n" +
        (err && err.message ? err.message : String(err)) +
        "\nDashboard may stay local; live capture needs HTTPS."
    );
  }
})();
