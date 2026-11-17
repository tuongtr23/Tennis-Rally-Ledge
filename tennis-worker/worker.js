// Rally Ledger feed — Cloudflare Worker (cron + D1)
//
// Every minute the cron handler pulls the upstream feed, converts it to the
// Rally Ledger match format, stores the current snapshot, and writes each
// newly finished match to the database once.
//
// Routes (all GET, JSON):
//   /health              when the feed was last refreshed, and whether it is stale
//   /events              current tournaments
//   /events/:id/draw     matches of one tournament, grouped by round
//   /live                matches in progress right now
//   /matches/:id         one match, live or finished
//   /players             every recorded player
//   /players/:id         one player and their recorded matches
//   /raw                 untouched upstream JSON, for checking field names
//
// Upstream is ESPN's public scoreboard JSON. It is undocumented, so all of the
// provider-specific reading lives in espnToModel() below. A second provider
// only needs a second adapter that returns the same shape.

const UPSTREAM = "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard";
const SOURCE = "espn";
const EDGE_TTL = 20;      // seconds a response is reused for all visitors
const STALE_AFTER = 180;  // seconds without a good refresh before data is marked stale
const FINAL = ["finished", "retired", "walkover"];

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(refresh(env));
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const cors = {
      "Access-Control-Allow-Origin": env.ALLOW_ORIGIN || "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Vary": "Origin",
    };
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    if (request.method !== "GET") return json({ error: "GET only" }, 405, cors);

    const cache = caches.default;
    const key = new Request(url.origin + url.pathname);
    const hit = await cache.match(key);
    if (hit) return withCors(hit, cors);

    let out;
    try {
      out = await route(url.pathname, env);
    } catch (e) {
      return json({ error: e.message }, 500, cors);
    }
    if (!out) return json({ error: "Not found" }, 404, cors);
    const res = json(out, 200, { "Cache-Control": "public, max-age=" + EDGE_TTL });
    ctx.waitUntil(cache.put(key, res.clone()));
    return withCors(res, cors);
  },
};

/* ------------------------------ routes ------------------------------ */

async function route(path, env) {
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);

  if (parts[0] === "raw" && parts.length === 1) {
    const up = await fetch(UPSTREAM, { headers: { "User-Agent": "rally-ledger-worker" } });
    return await up.json();
  }

  const snap = await loadSnapshot(env);
  const head = {
    updated: snap.updated,
    stale: !snap.updated || (Date.now() - Date.parse(snap.updated)) / 1000 > STALE_AFTER,
    source: SOURCE,
  };

  if (parts.length === 0 || (parts[0] === "health" && parts.length === 1))
    return { ...head, lastError: snap.lastError || null, events: snap.events.length, matches: snap.matches.length };

  if (parts[0] === "events" && parts.length === 1) {
    const events = snap.events.map((e) => {
      const ms = snap.matches.filter((m) => m.eventId === e.id);
      return { ...e, matches: ms.length, live: ms.filter((m) => m.state === "live").length };
    });
    return { ...head, events };
  }

  if (parts[0] === "events" && parts[2] === "draw" && parts.length === 3) {
    const id = parts[1];
    // Finished matches from the database, overlaid with whatever is current.
    const saved = await env.DB.prepare("SELECT data FROM matches WHERE event_id = ?").bind(id).all();
    const byId = new Map();
    for (const r of saved.results || []) { const m = JSON.parse(r.data); byId.set(m.id, m); }
    for (const m of snap.matches) if (m.eventId === id) byId.set(m.id, m);
    if (!byId.size) return null;
    const event = snap.events.find((e) => e.id === id) ||
      (await env.DB.prepare("SELECT id, name, venue, start, end FROM events WHERE id = ?").bind(id).first());
    const draws = {};
    for (const m of byId.values()) {
      const d = (draws[m.draw || "Draw"] ||= {});
      (d[m.round || "Round"] ||= []).push(m);
    }
    for (const d of Object.values(draws))
      for (const r of Object.values(d)) r.sort((a, b) => String(a.start).localeCompare(String(b.start)));
    return { ...head, event, draws };
  }

  if (parts[0] === "live" && parts.length === 1)
    return { ...head, matches: snap.matches.filter((m) => m.state === "live") };

  if (parts[0] === "matches" && parts.length === 2) {
    let m = snap.matches.find((x) => x.id === parts[1]);
    if (!m) {
      const r = await env.DB.prepare("SELECT data FROM matches WHERE id = ?").bind(parts[1]).first();
      if (r) m = JSON.parse(r.data);
    }
    return m ? { ...head, match: m } : null;
  }

  if (parts[0] === "players" && parts.length === 1) {
    const r = await env.DB.prepare("SELECT id, name, country FROM players ORDER BY name").all();
    return { ...head, players: r.results || [] };
  }

  if (parts[0] === "players" && parts.length === 2) {
    const p = await env.DB.prepare("SELECT id, name, country, aliases FROM players WHERE id = ?").bind(parts[1]).first();
    if (!p) return null;
    p.aliases = JSON.parse(p.aliases || "[]");
    const r = await env.DB.prepare(
      "SELECT data FROM matches WHERE p1_id = ? OR p2_id = ? ORDER BY start DESC LIMIT 200"
    ).bind(p.id, p.id).all();
    const current = snap.matches.filter((m) => !FINAL.includes(m.state) && m.players.some((x) => x.id === p.id));
    return { ...head, player: p, current, matches: (r.results || []).map((x) => JSON.parse(x.data)) };
  }

  return null;
}

/* --------------------------- refresh (cron) -------------------------- */

async function loadSnapshot(env) {
  const row = await env.DB.prepare("SELECT data FROM snapshot WHERE id = 1").first();
  return row ? JSON.parse(row.data) : { updated: null, events: [], matches: [], saved: [] };
}

async function saveSnapshot(env, snap) {
  await env.DB.prepare(
    "INSERT INTO snapshot (id, data, updated) VALUES (1, ?1, ?2) " +
    "ON CONFLICT(id) DO UPDATE SET data = ?1, updated = ?2"
  ).bind(JSON.stringify(snap), new Date().toISOString()).run();
}

async function refresh(env) {
  const prev = await loadSnapshot(env);
  const now = new Date().toISOString();

  let model;
  try {
    const up = await fetch(UPSTREAM, { headers: { "User-Agent": "rally-ledger-worker" } });
    if (!up.ok) throw new Error("Upstream returned " + up.status);
    model = espnToModel(await up.json());
  } catch (e) {
    // Keep serving the last good data; /health shows the error and stale flag.
    prev.lastError = { at: now, message: e.message };
    await saveSnapshot(env, prev);
    return;
  }

  const prevById = new Map(prev.matches.map((m) => [m.id, m]));
  for (const m of model.matches) addTiming(m, prevById.get(m.id), now);

  // Write each finished match to the database once.
  const savedBefore = new Set(prev.saved || []);
  const stmts = [];
  const savedNow = [];
  for (const m of model.matches) {
    if (!FINAL.includes(m.state)) continue;
    savedNow.push(m.id);
    if (savedBefore.has(m.id)) continue;
    const ev = model.events.find((e) => e.id === m.eventId);
    if (ev) stmts.push(env.DB.prepare(
      "INSERT INTO events (id, name, venue, start, end, updated) VALUES (?1, ?2, ?3, ?4, ?5, ?6) " +
      "ON CONFLICT(id) DO UPDATE SET name = ?2, venue = ?3, start = ?4, end = ?5, updated = ?6"
    ).bind(ev.id, ev.name, ev.venue, ev.start, ev.end, now));
    for (const p of m.players) stmts.push(env.DB.prepare(
      "INSERT INTO players (id, name, country, updated) VALUES (?1, ?2, ?3, ?4) " +
      "ON CONFLICT(id) DO UPDATE SET country = ?3, updated = ?4"
    ).bind(p.id, p.name, p.country, now));
    const w = m.players.findIndex((p) => p.winner);
    stmts.push(env.DB.prepare(
      "INSERT INTO matches (id, event_id, draw, round, court, start, state, best_of, p1_id, p2_id, winner, score, seconds, data, updated) " +
      "VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15) " +
      "ON CONFLICT(id) DO UPDATE SET state = ?7, winner = ?11, score = ?12, seconds = ?13, data = ?14, updated = ?15"
    ).bind(m.id, m.eventId, m.draw, m.round, m.court, m.start, m.state, m.bestOf,
      m.players[0]?.id ?? null, m.players[1]?.id ?? null, w < 0 ? null : w,
      scoreText(m), m.seconds, JSON.stringify(m), now));
  }
  // D1 accepts batches; keep each one small.
  for (let i = 0; i < stmts.length; i += 40) await env.DB.batch(stmts.slice(i, i + 40));

  await saveSnapshot(env, { updated: now, events: model.events, matches: model.matches, saved: savedNow });
}

// Durations come from when this Worker first saw each set start and end, so
// they are accurate to about a minute. A match first seen already finished
// has no timings.
function addTiming(m, prev, now) {
  const live = m.state === "live";
  const done = FINAL.includes(m.state);
  m.startedAt = prev?.startedAt ?? (live ? now : null);
  m.endedAt = prev?.endedAt ?? (done && m.startedAt ? now : null);
  m.seconds = m.startedAt && m.endedAt ? secs(m.startedAt, m.endedAt) : null;
  m.sets.forEach((s, i) => {
    const ps = prev?.sets?.[i];
    const complete = i < m.sets.length - 1 || done;
    // A set already complete when first seen was not observed, so it gets no timing.
    s.startedAt = ps?.startedAt ?? (live && !complete ? now : null);
    s.endedAt = ps?.endedAt ?? (complete && s.startedAt ? now : null);
    s.seconds = s.startedAt && s.endedAt ? secs(s.startedAt, s.endedAt) : null;
  });
}

const secs = (a, b) => Math.max(0, Math.round((Date.parse(b) - Date.parse(a)) / 1000));

function scoreText(m) {
  return m.sets.map((s) => {
    const tb = s.tiebreak == null ? "" : "(" + s.tiebreak + ")";
    return s.games[0] + "-" + s.games[1] + tb;
  }).join(" ");
}

/* ------------------------- provider adapter -------------------------- */

// Returns { events: [...], matches: [...] } in the Rally Ledger format.
function espnToModel(data) {
  const events = [], matches = [];
  for (const ev of data.events || []) {
    const eventId = SOURCE + ":" + ev.id;
    events.push({
      id: eventId,
      name: ev.name || ev.shortName || "",
      venue: ev.venue?.displayName || ev.venue?.fullName || "",
      start: ev.date || null,
      end: ev.endDate || null,
    });
    // Tennis nests matches under groupings (Men's Singles, Men's Doubles, ...).
    const groups = ev.groupings || [{ grouping: {}, competitions: ev.competitions || [] }];
    for (const g of groups) {
      const draw = g.grouping?.displayName || g.grouping?.slug || "";
      for (const c of g.competitions || []) {
        const comps = (c.competitors || []).slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
        const players = comps.map((p) => {
          const name = p.athlete?.displayName || p.roster?.displayName || p.team?.displayName || "TBD";
          return {
            id: slug(name),
            name,
            country: p.athlete?.flag?.alt || p.athlete?.country || "",
            seed: toInt(p.seed ?? p.tournamentSeed),
            winner: !!p.winner,
          };
        });
        const n = Math.max(0, ...comps.map((p) => (p.linescores || []).length));
        const sets = [];
        for (let i = 0; i < n; i++) {
          const a = comps[0]?.linescores?.[i], b = comps[1]?.linescores?.[i];
          const ga = toInt(a?.value) ?? 0, gb = toInt(b?.value) ?? 0;
          // Tiebreak is recorded as the loser's points, e.g. 7-6(4).
          const tb = ga === gb ? null : toInt((ga < gb ? a : b)?.tiebreak);
          sets.push({ games: [ga, gb], tiebreak: tb });
        }
        const srv = comps.findIndex((p) => p.possession);
        matches.push({
          id: SOURCE + ":" + c.id,
          eventId,
          draw,
          round: c.round?.displayName || c.round?.name || "",
          court: c.venue?.court || c.venue?.fullName || "",
          start: c.date || c.startDate || null,
          state: mapState(c.status?.type),
          status: c.status?.type?.detail || c.status?.type?.description || "",
          bestOf: toInt(c.format?.regulation?.periods) || 3,
          server: srv < 0 ? null : srv,
          players,
          sets,
          game: null,   // current game points: needs a point-by-point feed
          stats: null,  // match statistics: needs a point-by-point feed
        });
      }
    }
  }
  return { events, matches };
}

function mapState(t = {}) {
  const s = ((t.name || "") + " " + (t.description || "")).toLowerCase();
  if (s.includes("walkover")) return "walkover";
  if (s.includes("retire")) return "retired";
  if (s.includes("suspend") || s.includes("delay") || s.includes("postpone")) return "suspended";
  if (s.includes("cancel")) return "cancelled";
  if (t.state === "post" || t.completed) return "finished";
  if (t.state === "in") return "live";
  return "scheduled";
}

const toInt = (v) => (v == null || v === "" || isNaN(Number(v)) ? null : Math.trunc(Number(v)));

const slug = (name) =>
  name.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "tbd";

/* ------------------------------ helpers ------------------------------ */

function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...headers },
  });
}

function withCors(res, cors) {
  const out = new Response(res.body, res);
  for (const [k, v] of Object.entries(cors)) out.headers.set(k, v);
  return out;
}

// Exported for local testing only.
export { espnToModel, addTiming, refresh, route };
