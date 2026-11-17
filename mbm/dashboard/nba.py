"""NBA dashboard snapshot assembly + HTML render helpers.

Kept free of provider HTTP clients. Consumes analyst models / envelopes only.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mbm.analyst.calibration import build_calibration
from mbm.analyst.decision import CanonicalDecision
from mbm.analyst.models import (
    BoardRow,
    CalibrationView,
    DashboardSnapshot,
    PickDetail,
    SettlementRow,
)
from mbm.analyst.settlement import load_settlement
from mbm.core_pin import core_ready, core_status_message
from mbm.intake.types import EvidenceEnvelope, Recommendation


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def load_nba_envelope(path: Path) -> EvidenceEnvelope:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return EvidenceEnvelope.from_dict(payload)


def discover_nba_normalized(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    found: list[Path] = []
    for child in sorted(root.rglob("normalized.json")):
        found.append(child)
    return found


def assemble_nba_snapshot(
    envelopes: list[tuple[str, EvidenceEnvelope]],
    decide: Callable[[EvidenceEnvelope], CanonicalDecision],
    *,
    data_label: str = "nba-fixture/demo",
    now: datetime | None = None,
    settlements_root: Path | None = None,
) -> DashboardSnapshot:
    now = now or datetime.now(timezone.utc)
    ready = core_ready()
    board: list[BoardRow] = []
    picks: dict[str, PickDetail] = {}
    settlements: list[SettlementRow] = []

    for pick_id, envelope in envelopes:
        decision = decide(envelope)
        # Prefer the market identity actually evaluated by gates, not market_lines[0].
        evaluated = decision.map_context.get("evaluated_market")
        evaluated = evaluated if isinstance(evaluated, dict) else {}
        fallback = envelope.market_lines[0] if envelope.market_lines else None
        eval_player = evaluated.get("player_id")
        eval_stat = evaluated.get("stat")
        eval_line = evaluated.get("line")
        rec = decision.action.value
        prob = float(decision.probabilities.get(rec, 0.0))
        nba_action = decision.map_context.get("nba_action", rec)
        grade = str(decision.map_context.get("nba_grade") or ("PASS" if rec == "PASS" else "D"))
        eligible = bool(ready and decision.actionable and decision.action is not Recommendation.PASS)
        elig_reason = (
            "Eligible under Core-ready + NBA gates"
            if eligible
            else (
                "Core BLOCKED — projection not eligible for publication"
                if not ready
                else "; ".join(decision.reasons) or "not eligible"
            )
        )
        resolved_player_id = (
            str(eval_player)
            if eval_player
            else (envelope.target_player_id or (fallback.player_id if fallback else ""))
        )
        try:
            board_line = float(eval_line) if eval_line is not None else (
                float(fallback.line) if fallback else float("nan")
            )
        except (TypeError, ValueError):
            board_line = float("nan")
        board_stat = str(eval_stat) if eval_stat else (fallback.stat if fallback else "unknown")
        row = BoardRow(
            pick_id=pick_id,
            event_id=envelope.fixture.event_id,
            team_a=envelope.fixture.team_a,
            team_b=envelope.fixture.team_b,
            start_time=envelope.fixture.start_time,
            market_scope=envelope.fixture.market_scope.value,
            player_id=resolved_player_id,
            player_name=next(
                (p.name for p in envelope.players if p.player_id == resolved_player_id),
                resolved_player_id,
            ),
            stat=board_stat,
            line=board_line,
            recommendation=str(nba_action),
            grade=grade,
            probability=prob,
            eligible=eligible,
            eligibility_reason=elig_reason,
            evidence_status=envelope.evidence_status.value,
            last_refresh=envelope.captured_at,
            data_label=data_label,
        )
        detail = PickDetail(
            pick_id=pick_id,
            board=row,
            identity_status=decision.identity_status,
            identity_notes=list(decision.identity_notes),
            source_attempts=[
                {"source": a.source, "outcome": a.outcome, "detail": a.detail}
                for a in envelope.source_attempts
            ],
            raw_refs=list(decision.raw_refs),
            map_context=dict(decision.map_context),
            opportunity=decision.opportunity,
            conversion=decision.conversion,
            provenance=list(decision.provenance),
            pass_reason="; ".join(decision.reasons) if decision.action is Recommendation.PASS else None,
            probabilities=dict(decision.probabilities),
            core_blocked=not ready,
        )
        board.append(row)
        picks[pick_id] = detail
        if settlements_root is not None:
            settle_path = settlements_root / pick_id / "settlement.json"
            settlements.append(
                load_settlement(
                    settle_path,
                    pick_id=pick_id,
                    event_id=envelope.fixture.event_id,
                    data_label=data_label,
                )
            )

    calibration: CalibrationView = build_calibration(board, settlements)
    return DashboardSnapshot(
        title="MBM NBA Research Board",
        data_label=data_label,
        core_status=core_status_message(),
        core_ready=ready,
        generated_at=now.isoformat().replace("+00:00", "Z"),
        board=board,
        picks=picks,
        settlements=settlements,
        calibration=calibration,
        notices=(
            "NBA MORE/LESS shown; shared Core gates still apply.",
            "Paid BallDontLie endpoints disabled until access verified.",
            "Certification pending purged walk-forward leakage suite.",
            "Synthetic fixtures are not live provider evidence.",
        ),
    )


def render_nba_board(snapshot: DashboardSnapshot) -> str:
    rows = []
    for r in snapshot.board:
        rows.append(
            "<tr>"
            f"<td><a href='/nba/pick/{_e(r.pick_id)}'>{_e(r.pick_id)}</a></td>"
            f"<td>{_e(r.team_a)} vs {_e(r.team_b)}</td>"
            f"<td>{_e(r.player_name)}</td>"
            f"<td>{_e(r.stat)} {_e(r.line)}</td>"
            f"<td>{_e(r.recommendation)}</td>"
            f"<td>{_e(r.grade)}</td>"
            f"<td>{r.probability:.3f}</td>"
            f"<td>{'yes' if r.eligible else 'no'}</td>"
            f"<td>{_e(r.evidence_status)}</td>"
            "</tr>"
        )
    notices = "".join(f"<li>{_e(n)}</li>" for n in snapshot.notices)
    body = f"""
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{_e(snapshot.title)}</title>
<style>
body{{font-family:"IBM Plex Sans",sans-serif;background:linear-gradient(180deg,#eef3f8,#f7f5ef);color:#142033;margin:0}}
header{{padding:1.2rem 1.5rem;background:rgba(255,255,255,.9);border-bottom:1px solid #d5dde8}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #d5dde8}}
th,td{{padding:.55rem .65rem;border-bottom:1px solid #e6ebf2;font-size:.9rem;text-align:left}}
.banner{{margin:.75rem 0;padding:.65rem .85rem;border-left:4px solid #9a3412;background:#fff7ed}}
nav a{{margin-right:.6rem}}
main{{padding:1.25rem 1.5rem;max-width:1200px}}
</style></head><body>
<header>
  <h1>{_e(snapshot.title)}</h1>
  <div>Data: {_e(snapshot.data_label)} · Core: {_e(snapshot.core_status)}</div>
  <div class="banner">{_e(snapshot.core_status)}</div>
  <nav>
    <a href="/nba">NBA Board</a>
    <a href="/nba/settlement">Settlement</a>
    <a href="/nba/calibration">Calibration</a>
    <a href="/">CS2 Board</a>
  </nav>
</header>
<main>
  <p>Games, player research, market comparisons, settlement.</p>
  <ul>{notices}</ul>
  <table>
    <thead><tr>
      <th>Pick</th><th>Game</th><th>Player</th><th>Market</th>
      <th>Rec</th><th>Grade</th><th>P</th><th>Eligible</th><th>Evidence</th>
    </tr></thead>
    <tbody>
    {''.join(rows) or '<tr><td colspan="9">No NBA rows</td></tr>'}
    </tbody>
  </table>
</main></body></html>
"""
    return body
