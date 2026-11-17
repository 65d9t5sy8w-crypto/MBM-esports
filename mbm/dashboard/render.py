"""HTML rendering for analyst dashboard views."""

from __future__ import annotations

import html
from typing import Any

from mbm.analyst.models import DashboardSnapshot, PickDetail


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _badge(rec: str) -> str:
    cls = {"OVER": "over", "UNDER": "under", "PASS": "pass"}.get(rec, "pass")
    return f'<span class="badge {cls}">{_e(rec)}</span>'


def _bool(v: bool) -> str:
    return "yes" if v else "no"


BASE_CSS = """
:root {
  --bg: #f3efe6;
  --ink: #1a1f16;
  --muted: #5c6456;
  --panel: #fffdf8;
  --line: #d5d0c4;
  --accent: #0b6e4f;
  --warn: #9a3412;
  --pass: #6b7280;
  --over: #0b6e4f;
  --under: #9a3412;
  --font: "IBM Plex Sans", "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", Consolas, monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: var(--font);
  color: var(--ink);
  background:
    radial-gradient(circle at 10% 0%, #e7f0e8 0%, transparent 40%),
    linear-gradient(180deg, #f7f3ea 0%, var(--bg) 100%);
  min-height: 100vh;
}
header {
  padding: 1.25rem 1.5rem 0.75rem;
  border-bottom: 1px solid var(--line);
  background: rgba(255,253,248,0.9);
  backdrop-filter: blur(6px);
  position: sticky; top: 0; z-index: 2;
}
h1 { margin: 0 0 0.35rem; font-size: 1.45rem; letter-spacing: -0.02em; }
.sub { color: var(--muted); font-size: 0.92rem; }
.banner {
  margin-top: 0.75rem;
  padding: 0.65rem 0.85rem;
  border-left: 4px solid var(--warn);
  background: #fff7ed;
  color: var(--warn);
  font-family: var(--mono);
  font-size: 0.85rem;
}
.banner.ok { border-color: var(--accent); background: #ecfdf5; color: var(--accent); }
nav { display: flex; gap: 0.75rem; margin-top: 0.9rem; flex-wrap: wrap; }
nav a {
  color: var(--ink);
  text-decoration: none;
  padding: 0.35rem 0.7rem;
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 999px;
  font-size: 0.88rem;
}
nav a.active { background: var(--ink); color: #fff; }
main { padding: 1.25rem 1.5rem 3rem; max-width: 1200px; }
.note {
  display: inline-block;
  margin-bottom: 1rem;
  padding: 0.25rem 0.55rem;
  border: 1px dashed var(--line);
  color: var(--muted);
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--panel);
  border: 1px solid var(--line);
}
th, td {
  text-align: left;
  padding: 0.55rem 0.65rem;
  border-bottom: 1px solid var(--line);
  font-size: 0.9rem;
  vertical-align: top;
}
th { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
tr:hover td { background: #faf6ee; }
.badge {
  display: inline-block;
  min-width: 3.5rem;
  text-align: center;
  padding: 0.15rem 0.45rem;
  border-radius: 0.25rem;
  font-family: var(--mono);
  font-size: 0.78rem;
  font-weight: 600;
}
.badge.over { background: #d1fae5; color: var(--over); }
.badge.under { background: #ffedd5; color: var(--under); }
.badge.pass { background: #e5e7eb; color: var(--pass); }
.card {
  background: var(--panel);
  border: 1px solid var(--line);
  padding: 1rem;
  margin-bottom: 1rem;
}
.card h2 { margin: 0 0 0.75rem; font-size: 1.1rem; }
.grid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
.kv { font-family: var(--mono); font-size: 0.82rem; white-space: pre-wrap; }
.muted { color: var(--muted); }
.fail { color: var(--warn); }
.ok { color: var(--accent); }
a.pick { color: var(--accent); font-weight: 600; }
.insufficient { color: var(--warn); font-weight: 600; }
"""


def render_shell(
    snapshot: DashboardSnapshot,
    body: str,
    active: str,
    *,
    route_prefix: str = "",
) -> str:
    banner_cls = "banner ok" if snapshot.core_ready else "banner"
    prefix = route_prefix.rstrip("/")
    board_href = f"{prefix}/" if prefix else "/"
    settlement_href = f"{prefix}/settlement" if prefix else "/settlement"
    calibration_href = f"{prefix}/calibration" if prefix else "/calibration"
    # NBA board lives at /nba (not /nba/).
    if prefix == "/nba":
        board_href = "/nba"
    links = [
        ("board", "Today’s Board", board_href),
        ("settlement", "Settlement", settlement_href),
        ("calibration", "Calibration", calibration_href),
    ]
    nav = []
    for key, label, href in links:
        cls = "active" if active == key else ""
        nav.append(f'<a class="{cls}" href="{href}">{_e(label)}</a>')
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_e(snapshot.title)}</title>
  <style>{BASE_CSS}</style>
</head>
<body>
  <header>
    <h1>{_e(snapshot.title)}</h1>
    <div class="sub">Generated {_e(snapshot.generated_at)} · {_e(snapshot.data_label)}</div>
    <div class="{banner_cls}">{_e(snapshot.core_status)}</div>
    <nav>{"".join(nav)}</nav>
  </header>
  <main>
    <div class="note">fixture / demo data</div>
    {body}
  </main>
</body>
</html>"""


def render_board(snapshot: DashboardSnapshot, *, route_prefix: str = "") -> str:
    prefix = route_prefix.rstrip("/")
    pick_base = f"{prefix}/pick" if prefix else "/pick"
    rows = []
    for row in snapshot.board:
        elig = f'<span class="ok">eligible</span>' if row.eligible else f'<span class="fail">not eligible</span>'
        rows.append(
            "<tr>"
            f"<td><a class='pick' href='{pick_base}/{_e(row.pick_id)}'>{_e(row.event_id)}</a><div class='muted'>{_e(row.team_a)} vs {_e(row.team_b)}</div><div class='muted'>{_e(row.start_time)}</div></td>"
            f"<td>{_e(row.market_scope)}</td>"
            f"<td>{_e(row.player_name)}<div class='muted'>{_e(row.stat)} {_e(row.line)}</div></td>"
            f"<td>{_badge(row.recommendation)}</td>"
            f"<td>{_e(row.grade)} · {_e(f'{row.probability:.2f}')}</td>"
            f"<td>{elig}<div class='muted'>{_e(row.eligibility_reason)}</div></td>"
            f"<td>{_e(row.evidence_status)}<div class='muted'>refresh {_e(row.last_refresh)}</div></td>"
            "</tr>"
        )
    body = f"""
    <div class="card">
      <h2>Today’s Board</h2>
      <table>
        <thead>
          <tr>
            <th>Fixture</th><th>Scope</th><th>Player / Line</th>
            <th>Rec</th><th>Grade / Prob</th><th>Eligibility</th><th>Evidence</th>
          </tr>
        </thead>
        <tbody>{"".join(rows) if rows else "<tr><td colspan='7'>No fixtures loaded</td></tr>"}</tbody>
      </table>
    </div>
    """
    return render_shell(snapshot, body, "board", route_prefix=route_prefix)


def render_pick(
    snapshot: DashboardSnapshot,
    pick: PickDetail,
    *,
    route_prefix: str = "",
) -> str:
    attempts = "".join(
        f"<li><strong>{_e(a['source'])}</strong> — {_e(a['outcome'])}: {_e(a['detail'])}</li>"
        for a in pick.source_attempts
    ) or "<li class='muted'>No source attempts recorded</li>"
    prov = "".join(
        f"<li><code>{_e(p.get('name'))}</code> ← {_e(p.get('source'))}: {_e(p.get('value'))}</li>"
        for p in pick.provenance
    ) or "<li class='muted'>No provenance</li>"
    raw = "".join(f"<li><code>{_e(r)}</code></li>" for r in pick.raw_refs) or "<li class='muted'>None</li>"
    pass_block = (
        f"<div class='card'><h2>PASS reason</h2><p class='fail kv'>{_e(pick.pass_reason)}</p></div>"
        if pick.pass_reason
        else ""
    )
    prefix = route_prefix.rstrip("/")
    back_href = "/nba" if prefix == "/nba" else (f"{prefix}/" if prefix else "/")
    body = f"""
    <p><a href="{back_href}">← Back to board</a></p>
    <div class="card">
      <h2>Pick Detail · {_e(pick.pick_id)}</h2>
      <div class="grid">
        <div>
          <div class="muted">Recommendation</div>
          <div>{_badge(pick.board.recommendation)} · eligible={_e(_bool(pick.board.eligible))}</div>
          <div class="muted">{_e(pick.board.eligibility_reason)}</div>
        </div>
        <div>
          <div class="muted">Identity</div>
          <div class="kv">{_e(pick.identity_status)}</div>
          <div class="muted">{_e('; '.join(pick.identity_notes) or 'resolved')}</div>
        </div>
        <div>
          <div class="muted">Core</div>
          <div class="kv">{'BLOCKED' if pick.core_blocked else 'READY'}</div>
        </div>
      </div>
    </div>
    {pass_block}
    <div class="grid">
      <div class="card">
        <h2>Headshots gates</h2>
        <p>Opportunity: <strong class="{'ok' if pick.opportunity.passed else 'fail'}">{_e(_bool(pick.opportunity.passed))}</strong></p>
        <p class="kv">{_e(pick.opportunity.detail)}</p>
        <p>Conversion: <strong class="{'ok' if pick.conversion.passed else 'fail'}">{_e(_bool(pick.conversion.passed))}</strong></p>
        <p class="kv">{_e(pick.conversion.detail)}</p>
      </div>
      <div class="card">
        <h2>Map / veto / MR12</h2>
        <pre class="kv">{_e(pick.map_context)}</pre>
      </div>
    </div>
    <div class="card">
      <h2>Source-attempt ledger</h2>
      <ul>{attempts}</ul>
    </div>
    <div class="card">
      <h2>Raw evidence references</h2>
      <ul>{raw}</ul>
    </div>
    <div class="card">
      <h2>Feature provenance</h2>
      <ul>{prov}</ul>
    </div>
    <div class="card">
      <h2>Probabilities</h2>
      <pre class="kv">{_e(pick.probabilities)}</pre>
    </div>
    """
    return render_shell(snapshot, body, "board", route_prefix=route_prefix)


def render_settlement(snapshot: DashboardSnapshot, *, route_prefix: str = "") -> str:
    rows = []
    for s in snapshot.settlements:
        rows.append(
            "<tr>"
            f"<td>{_e(s.event_id)}<div class='muted'>{_e(s.pick_id)}</div></td>"
            f"<td>{_e(s.status)}</td>"
            f"<td>{_e(s.recorded_result)}</td>"
            f"<td>{_e(s.outcome)}</td>"
            f"<td>{_e(s.source)}<div class='muted'>{_e(s.captured_at)}</div></td>"
            "</tr>"
        )
    body = f"""
    <div class="card">
      <h2>Settlement Monitor</h2>
      <table>
        <thead><tr><th>Pick</th><th>Status</th><th>Result</th><th>W/L/P</th><th>Source / Capture</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </div>
    """
    return render_shell(snapshot, body, "settlement", route_prefix=route_prefix)


def render_calibration(snapshot: DashboardSnapshot, *, route_prefix: str = "") -> str:
    cal = snapshot.calibration

    def buckets(items):
        out = []
        for b in items:
            sample = (
                f"<span class='insufficient'>insufficient_sample</span>"
                if b.sample_state == "insufficient_sample"
                else "<span class='ok'>ok</span>"
            )
            metric = (
                "n/a (insufficient sample)"
                if b.sample_state == "insufficient_sample"
                else f"W{b.wins}/L{b.losses}/P{b.pushes}"
            )
            out.append(
                "<tr>"
                f"<td>{_e(b.key)}</td><td>{b.projections}</td><td>{b.settlements}</td>"
                f"<td>{metric}</td><td>{sample}</td>"
                "</tr>"
            )
        return "".join(out)

    notes = "".join(f"<li>{_e(n)}</li>" for n in cal.notes)
    body = f"""
    <div class="card">
      <h2>Calibration View</h2>
      <p>Projections: <strong>{cal.projection_count}</strong> · Settled: <strong>{cal.settlement_count}</strong></p>
      <p class="muted">Performance rates are withheld unless settled sample ≥ threshold. No fabricated metrics.</p>
    </div>
    <div class="grid">
      <div class="card">
        <h2>By market</h2>
        <table>
          <thead><tr><th>Market</th><th>Proj</th><th>Settled</th><th>Record</th><th>Sample</th></tr></thead>
          <tbody>{buckets(cal.by_market)}</tbody>
        </table>
      </div>
      <div class="card">
        <h2>By recommendation</h2>
        <table>
          <thead><tr><th>Rec</th><th>Proj</th><th>Settled</th><th>Record</th><th>Sample</th></tr></thead>
          <tbody>{buckets(cal.by_recommendation)}</tbody>
        </table>
      </div>
    </div>
    <div class="card"><h2>Notes</h2><ul>{notes}</ul></div>
    """
    return render_shell(snapshot, body, "calibration", route_prefix=route_prefix)


def render_not_found(
    snapshot: DashboardSnapshot, message: str, *, route_prefix: str = ""
) -> str:
    return render_shell(
        snapshot,
        f"<div class='card'><h2>Not found</h2><p>{_e(message)}</p></div>",
        "board",
        route_prefix=route_prefix,
    )
