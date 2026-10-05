// FieldGuard frontend: plain JS, hash routing, no build step.
"use strict";
const $app = document.getElementById("app"), $tabs = document.getElementById("tabs"), $who = document.getElementById("who");
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  del(k) { try { localStorage.removeItem(k); } catch {} },
};
let draft = null, gps = null, gpsError = null, cleanup = null, lastResult = null;
const deviceId = store.get("fg_device") || (() => { const d = "web-" + Math.random().toString(36).slice(2, 10); store.set("fg_device", d); return d; })();

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtTime = (iso) => { try { return new Date(iso).toLocaleString(); } catch { return iso; } };
const badge = (r, big) => `<span class="badge ${esc(r)} ${big ? "big" : ""}">${esc(r)}</span>`;

async function api(path, opts = {}, auth = true) {
  const headers = { ...(opts.headers || {}) };
  const t = store.get("fg_token");
  if (auth && t) headers.Authorization = "Bearer " + t;
  const r = await fetch("/api" + path, { ...opts, headers });
  if (r.status === 401 && auth) { logout(); throw new Error("Please log in again"); }
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(msg);
  }
  return r;
}
const getJSON = async (p, o, a) => (await api(p, o, a)).json();
const blobUrl = async (p) => URL.createObjectURL(await (await api(p)).blob());

function logout() { store.del("fg_token"); store.del("fg_name"); draft = null; location.hash = "#/login"; }
function setTab(name) { document.querySelectorAll("#tabs a").forEach((a) => a.classList.toggle("on", a.dataset.tab === name)); }

// ---------- router ----------
const routes = {
  login: viewLogin, new: viewNew, capture: viewCapture, result: viewResult,
  history: viewHistory, record: viewRecord, verify: viewVerify,
};
async function route() {
  if (cleanup) { cleanup(); cleanup = null; }
  const [name, arg] = (location.hash.replace(/^#\//, "") || "new").split("/");
  if (name === "logout") return logout();
  const isPublic = name === "login" || name === "verify";
  if (!store.get("fg_token") && !isPublic) { location.hash = "#/login"; return; }
  $tabs.hidden = isPublic || !store.get("fg_token");
  $who.textContent = store.get("fg_name") || "";
  setTab(name === "record" ? "history" : name === "capture" || name === "result" ? "new" : name);
  window.scrollTo(0, 0);
  try { await (routes[name] || viewNew)(arg); }
  catch (e) { $app.innerHTML = `<div class="warn">${esc(e.message)}</div>`; }
}
window.addEventListener("hashchange", route);
window.addEventListener("load", () => {
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) navigator.serviceWorker.register("sw.js").catch(() => {});
  route();
});

// ---------- login ----------
function viewLogin() {
  $app.innerHTML = `<h1>Officer login</h1><div class="card">
    <label>Username</label><input id="u" autocomplete="username" autocapitalize="none">
    <label>Password</label><input id="p" type="password" autocomplete="current-password">
    <div id="err"></div><button id="go">Log in</button></div>
    <p class="muted">Presumptive colour reading with a tamper-evident record. Not a substitute for laboratory confirmation.</p>`;
  const go = async () => {
    try {
      const r = await getJSON("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: $app.querySelector("#u").value, password: $app.querySelector("#p").value }) }, false);
      store.set("fg_token", r.token); store.set("fg_name", `${r.name} (${r.operator_id})`); location.hash = "#/new";
    } catch (e) { $app.querySelector("#err").innerHTML = `<div class="warn">${esc(e.message)}</div>`; }
  };
  $app.querySelector("#go").onclick = go;
  $app.querySelector("#p").onkeydown = (e) => { if (e.key === "Enter") go(); };
}

// ---------- new test ----------
async function viewNew() {
  const { kits } = await getJSON("/kits");
  const d = draft || (draft = { kit: kits[0].id, lot: "", expiry: "", control: false, elapsed: 0, timerDone: false });
  const kit = () => kits.find((k) => k.id === d.kit);
  $app.innerHTML = `<h1>New test</h1><div class="card">
    <label>Kit type</label><select id="kit">${kits.map((k) => `<option value="${esc(k.id)}" ${k.id === d.kit ? "selected" : ""}>${esc(k.label)}</option>`).join("")}</select>
    <label>Lot number</label><input id="lot" value="${esc(d.lot)}" autocapitalize="characters">
    <label>Expiry date</label><input id="exp" type="date" value="${esc(d.expiry)}">
    <div id="expmsg"></div></div>
    <div class="card"><h2 style="margin-top:0">Protocol</h2>
      <label class="check"><input type="checkbox" id="ctl" ${d.control ? "checked" : ""}> Control step completed</label>
      <div class="timer" id="clock">--:--</div>
      <div class="muted" id="winmsg" style="text-align:center"></div>
      <button class="ghost" id="start">Start reading timer</button></div>
    <button id="next" disabled>Continue to capture</button>`;
  const q = (s) => $app.querySelector(s);
  let iv = null;
  const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  const expired = () => d.expiry && d.expiry < new Date().toISOString().slice(0, 10);
  const refresh = () => {
    d.kit = q("#kit").value; d.lot = q("#lot").value.trim(); d.expiry = q("#exp").value; d.control = q("#ctl").checked;
    q("#expmsg").innerHTML = expired() ? `<div class="warn">This kit has expired. The test is blocked.</div>` : "";
    q("#winmsg").textContent = `Reading window for this kit: ${kit().reading_window_s} s`;
    if (!iv) q("#clock").textContent = d.timerDone ? "Done" : fmt(kit().reading_window_s);
    q("#start").disabled = !d.control || expired() || !d.lot || !d.expiry || !!iv;
    q("#next").disabled = !(d.control && d.timerDone && d.lot && d.expiry && !expired());
  };
  ["#kit", "#lot", "#exp", "#ctl"].forEach((s) => (q(s).oninput = () => { if (s === "#kit") { d.timerDone = false; d.elapsed = 0; } refresh(); }));
  q("#start").onclick = () => {
    const total = kit().reading_window_s, t0 = Date.now(); d.timerDone = false;
    q("#start").disabled = true;
    iv = setInterval(() => {
      const el = Math.floor((Date.now() - t0) / 1000);
      q("#clock").textContent = fmt(Math.max(total - el, 0));
      if (el >= total) { clearInterval(iv); iv = null; d.timerDone = true; d.elapsed = total; if (navigator.vibrate) navigator.vibrate(200); refresh(); }
    }, 250);
  };
  cleanup = () => iv && clearInterval(iv);
  q("#next").onclick = () => (location.hash = "#/capture");
  refresh();
}

// ---------- capture ----------
function locate() {
  if (!navigator.geolocation) { gpsError = "GPS not supported"; return; }
  navigator.geolocation.getCurrentPosition(
    (p) => { gps = { lat: p.coords.latitude, lng: p.coords.longitude, acc: p.coords.accuracy }; gpsError = null; paintGps(); },
    (e) => { gpsError = e.message; paintGps(); }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 5000 });
}
function paintGps() {
  const el = document.getElementById("gps");
  if (el) el.innerHTML = gps ? `<div class="ok">GPS ready (±${Math.round(gps.acc)} m)</div>` : `<div class="warn">GPS: ${esc(gpsError || "locating…")} (the record will be saved without location)</div>`;
}
async function viewCapture() {
  if (!draft || !draft.timerDone) { location.hash = "#/new"; return; }
  $app.innerHTML = `<h1>Capture</h1>
    <div class="cam" id="cam"><video id="vid" playsinline muted autoplay></video><div class="frame"><span>Place the whole card (all 4 corner markers) and the kit inside the frame</span></div></div>
    <div id="gps"></div><div id="cerr"></div>
    <button id="snap">Take photo</button><div id="after" hidden>
      <div class="row"><button class="ghost" id="retake">Retake</button><button id="use">Use photo</button></div></div>`;
  const q = (s) => $app.querySelector(s), vid = q("#vid");
  let stream = null, blob = null;
  cleanup = () => stream && stream.getTracks().forEach((t) => t.stop());
  locate(); paintGps();
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
    vid.srcObject = stream;
  } catch (e) {
    q("#cerr").innerHTML = `<div class="warn">Camera unavailable: ${esc(e.message)}. The app needs HTTPS (or localhost) and camera permission. Photos cannot be chosen from the gallery.</div>`;
    q("#snap").disabled = true; return;
  }
  q("#snap").onclick = () => {
    const c = document.createElement("canvas"); c.width = vid.videoWidth; c.height = vid.videoHeight;
    c.getContext("2d").drawImage(vid, 0, 0);
    c.toBlob((b) => {
      blob = b; vid.pause(); q("#snap").hidden = true; q("#after").hidden = false; locate();
    }, "image/jpeg", 0.95);
  };
  q("#retake").onclick = () => { blob = null; vid.play(); q("#snap").hidden = false; q("#after").hidden = true; };
  q("#use").onclick = async () => {
    q("#use").disabled = q("#retake").disabled = true;
    $app.insertAdjacentHTML("beforeend", `<div class="spin" id="busy">Analysing and signing…</div>`);
    const fd = new FormData();
    fd.append("photo", blob, "capture.jpg"); fd.append("kit_type", draft.kit); fd.append("kit_lot", draft.lot);
    fd.append("kit_expiry", draft.expiry); fd.append("control_done", draft.control ? "true" : "false");
    fd.append("timer_seconds", String(draft.elapsed)); fd.append("client_time", new Date().toISOString());
    fd.append("device_id", deviceId); if (gps) fd.append("gps", JSON.stringify(gps));
    try {
      lastResult = await getJSON("/tests", { method: "POST", body: fd });
      location.hash = "#/result";
    } catch (e) {
      q("#busy").remove(); q("#use").disabled = q("#retake").disabled = false;
      q("#cerr").innerHTML = `<div class="warn">${esc(e.message)}</div>`;
    }
  };
}

// ---------- result ----------
function viewResult() {
  const r = lastResult;
  if (!r) { location.hash = "#/new"; return; }
  if (r.status === "RETAKE") {
    $app.innerHTML = `<h1>Retake needed</h1><div class="card" style="text-align:center">${badge("RETAKE", true)}
      <p>${esc(r.reason)}</p><p class="muted">No record was saved for this photo.</p></div>
      <a class="btn" href="#/capture">Retake photo</a>`;
    return;
  }
  const rec = r.record; draft = null;
  $app.innerHTML = `<h1>Result</h1><div class="card" style="text-align:center">${badge(rec.result, true)}
    <p style="margin:12px 0 0">Match score <b>${rec.match_score.toFixed(2)}</b> <span class="muted">(colour match, not a probability)</span></p>
    <p class="muted">Presumptive result. Laboratory confirmation is required.</p></div>
    <div class="card"><div class="kv"><div>Record</div><div class="mono">${esc(rec.id)}</div>
    <div>Time (server)</div><div>${esc(fmtTime(rec.server_time_utc))}</div>
    <div>Record hash</div><div class="mono">${esc(rec.record_hash)}</div></div></div>
    <a class="btn" href="#/record/${esc(rec.id)}">Open record</a><a class="btn ghost" href="#/new">New test</a>`;
}

// ---------- history ----------
async function viewHistory() {
  $app.innerHTML = `<h1>Test log</h1><div class="card">
    <input id="q" placeholder="Search lot, operator, id, hash">
    <div class="row"><select id="res"><option value="">All results</option><option>POSITIVE</option><option>NEGATIVE</option><option>INCONCLUSIVE</option></select>
    <input id="from" type="date" title="From"><input id="to" type="date" title="To"></div></div>
    <div id="list" class="spin">Loading…</div><button class="ghost" id="chain">Verify entire log</button><div id="chainmsg"></div>`;
  const q = (s) => $app.querySelector(s);
  let timer = null;
  const load = async () => {
    const p = new URLSearchParams({ q: q("#q").value, result: q("#res").value, date_from: q("#from").value, date_to: q("#to").value });
    const rows = await getJSON("/tests?" + p);
    q("#list").className = "";
    q("#list").innerHTML = rows.length ? rows.map((r) => `<a class="card item" href="#/record/${esc(r.id)}">
      <div><b>${esc(r.kit_lot)}</b> · ${esc(r.kit_type)}<small>${esc(fmtTime(r.server_time_utc))} · ${esc(r.operator_id)}</small></div>${badge(r.result)}</a>`).join("")
      : `<p class="muted">No matching tests.</p>`;
  };
  ["#q", "#res", "#from", "#to"].forEach((s) => (q(s).oninput = () => { clearTimeout(timer); timer = setTimeout(load, 250); }));
  q("#chain").onclick = async () => {
    const r = await getJSON("/verify-chain", {}, false);
    q("#chainmsg").innerHTML = r.ok ? `<div class="ok">Log intact: ${r.checked} records checked.</div>`
      : `<div class="warn">Log broken at record ${esc(r.bad_id)}: ${esc(r.reason)} (${r.checked} of ${r.total} checked before the break).</div>`;
  };
  await load();
}

// ---------- record detail ----------
async function viewRecord(id) {
  const rec = await getJSON("/tests/" + id);
  const g = rec.gps ? `${rec.gps.lat.toFixed(5)}, ${rec.gps.lng.toFixed(5)} (±${Math.round(rec.gps.accuracy)} m)` : "not available";
  $app.innerHTML = `<h1>Record</h1><div class="card" style="text-align:center">${badge(rec.result, true)}
    <p class="muted" style="margin:8px 0 0">match score ${rec.match_score.toFixed(2)} · presumptive</p></div>
    <div class="card"><div class="kv">
      <div>Time (server)</div><div>${esc(fmtTime(rec.server_time_utc))}</div>
      <div>Device time</div><div>${esc(rec.client_time ? fmtTime(rec.client_time) : "-")} <span class="muted">(unverified)</span></div>
      <div>Operator</div><div>${esc(rec.operator_id)}</div><div>Device</div><div>${esc(rec.device_id)}</div>
      <div>GPS</div><div>${esc(g)}</div><div>Kit</div><div>${esc(rec.kit_type)}, lot ${esc(rec.kit_lot)}, exp ${esc(rec.kit_expiry)}</div>
      <div>Protocol</div><div>control ${rec.protocol_steps.control_done ? "done" : "not done"}, timer ${rec.protocol_steps.timer_seconds}s</div>
      <div>Colour distances</div><div>${Object.entries(rec.colour_scores).map(([k, v]) => `${esc(k)} ${v}`).join(", ")}</div>
      <div>Image SHA-256</div><div class="mono">${esc(rec.image_sha256)}</div>
      <div>Previous hash</div><div class="mono">${esc(rec.prev_hash)}</div>
      <div>Record hash</div><div class="mono">${esc(rec.record_hash)}</div></div></div>
    <div class="row"><img class="thumb" id="im1" alt="Original photo"><img class="thumb" id="im2" alt="Analysed card"></div>
    <button id="ver">Verify record</button><div id="vres"></div>
    <button class="ghost" id="pdf">Download PDF report</button>
    <a class="btn ghost" href="#/verify/${esc(rec.id)}">Open public verify page</a>`;
  const q = (s) => $app.querySelector(s);
  blobUrl(`/tests/${id}/image`).then((u) => (q("#im1").src = u)).catch(() => {});
  blobUrl(`/tests/${id}/annotated`).then((u) => (q("#im2").src = u)).catch(() => {});
  q("#ver").onclick = async () => { q("#vres").innerHTML = verifyHtml(await getJSON("/verify/" + id, {}, false)); };
  q("#pdf").onclick = async () => {
    const a = document.createElement("a"); a.href = await blobUrl(`/tests/${id}/report.pdf`); a.download = `fieldguard-${id.slice(0, 8)}.pdf`; a.click();
  };
}

// ---------- verify (public) ----------
const CHECK_LABELS = { hash_and_signature: "Record hash and signature", chain_link: "Link to previous record",
  index_matches_record: "Log entry matches record", image_matches_hash: "Photo matches its hash", record_readable: "Record readable" };
function verifyHtml(v) {
  const rows = Object.entries(v.checks).map(([k, ok]) => `<div class="item" style="padding:6px 0"><span>${esc(CHECK_LABELS[k] || k)}</span><b style="color:var(--${ok ? "neg" : "pos"})">${ok ? "OK" : "FAILED"}</b></div>`).join("");
  return `<div class="banner ${v.valid ? "valid" : "invalid"}" style="margin-top:12px">${v.valid ? "RECORD VALID" : "RECORD INVALID"}</div><div class="card" style="margin-top:12px">${rows}</div>`;
}
async function viewVerify(id) {
  $app.innerHTML = `<h1>Verify record</h1><div class="spin">Checking…</div>`;
  const v = await getJSON("/verify/" + id, {}, false);
  const s = v.summary || {};
  $app.innerHTML = `<h1>Verify record</h1>${verifyHtml(v)}${v.summary ? `<div class="card"><div class="kv">
    <div>Result</div><div>${badge(s.result)}</div><div>Time (server)</div><div>${esc(fmtTime(s.server_time_utc))}</div>
    <div>Operator</div><div>${esc(s.operator_id)}</div><div>Kit</div><div>${esc(s.kit_type)}, lot ${esc(s.kit_lot)}</div>
    <div>Record hash</div><div class="mono">${esc(s.record_hash)}</div><div>Signed with</div><div class="mono">Ed25519 key ${esc(v.public_key)}</div></div></div>` : ""}
    <p class="muted">Valid means the record has not been changed since it was signed. Presumptive result only: laboratory confirmation is required.</p>
    <a class="btn ghost" href="#/login">Officer login</a>`;
}
