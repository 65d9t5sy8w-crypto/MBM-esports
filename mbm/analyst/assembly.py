"""Assemble dashboard snapshot from canonical intake envelopes + decisions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from mbm.analyst.calibration import build_calibration
from mbm.analyst.decision import CanonicalDecision, DecideFn
from mbm.analyst.models import BoardRow, DashboardSnapshot, PickDetail
from mbm.analyst.settlement import load_settlement
from mbm.core_pin import core_ready, core_status_message
from mbm.intake.normalization import normalize_manual_panel
from mbm.intake.types import EvidenceEnvelope, Recommendation


def _player_name(envelope: EvidenceEnvelope, player_id: str) -> str:
    for player in envelope.players:
        if player.player_id == player_id:
            return player.name
    return player_id or "unknown"


def _grade(probability: float, recommendation: str) -> str:
    if recommendation == Recommendation.PASS.value:
        return "PASS"
    if probability >= 0.7:
        return "A"
    if probability >= 0.6:
        return "B"
    if probability >= 0.55:
        return "C"
    return "D"


def _eligibility(
    decision: CanonicalDecision,
    *,
    core_is_ready: bool,
) -> tuple[bool, str]:
    if not core_is_ready:
        return False, "Core BLOCKED — projection not eligible for publication"
    if not decision.actionable:
        return False, "Evidence incomplete/unresolved/stale — not eligible"
    if decision.action is Recommendation.PASS:
        return False, "PASS recommendation — not eligible as a published pick"
    if not decision.opportunity.passed or not decision.conversion.passed:
        return False, "Headshots gates failed — not eligible"
    return True, "Eligible under Core-ready + complete evidence + gates"


def load_envelope(fixture_dir: Path) -> EvidenceEnvelope:
    payload = json.loads((fixture_dir / "normalized.json").read_text(encoding="utf-8"))
    raw_path = fixture_dir / "raw" / "payload.json"
    raw_ref = str(raw_path.as_posix()) if raw_path.is_file() else None
    return normalize_manual_panel(payload, raw_ref=raw_ref)


def discover_fixture_dirs(fixtures_root: Path) -> list[Path]:
    if not fixtures_root.is_dir():
        return []
    return sorted(
        child
        for child in fixtures_root.iterdir()
        if child.is_dir() and (child / "normalized.json").is_file()
    )


def assemble_pick(
    envelope: EvidenceEnvelope,
    decision: CanonicalDecision,
    *,
    pick_id: str,
    data_label: str,
    core_is_ready: bool,
) -> tuple[BoardRow, PickDetail]:
    line = next((m for m in envelope.market_lines if m.stat == "headshots"), None)
    if line is None and envelope.market_lines:
        line = envelope.market_lines[0]
    stat = line.stat if line else "unknown"
    line_val = float(line.line) if line else float("nan")
    player_id = envelope.target_player_id or (line.player_id if line else "")
    rec = decision.action.value
    prob = float(decision.probabilities.get(rec, 0.0))
    eligible, elig_reason = _eligibility(decision, core_is_ready=core_is_ready)
    pass_reason = "; ".join(decision.reasons) if decision.action is Recommendation.PASS else None

    attempts: list[dict[str, str]] = []
    for item in decision.provenance:
        if item.get("name") == "source_attempts" and isinstance(item.get("value"), list):
            attempts = [
                {
                    "source": str(a.get("source", "")),
                    "outcome": str(a.get("outcome", "")),
                    "detail": str(a.get("detail", "")),
                }
                for a in item["value"]
                if isinstance(a, dict)
            ]
            break
    if not attempts:
        attempts = [
            {"source": a.source, "outcome": a.outcome, "detail": a.detail}
            for a in envelope.source_attempts
        ]

    raw_refs = list(decision.raw_refs)
    if envelope.raw_ref and envelope.raw_ref not in raw_refs:
        raw_refs.insert(0, envelope.raw_ref)

    identity_notes = list(decision.identity_notes)
    for item in envelope.provenance:
        if item.name == "identity_failure_reasons" and isinstance(item.value, list):
            identity_notes.extend(str(v) for v in item.value)

    board = BoardRow(
        pick_id=pick_id,
        event_id=envelope.fixture.event_id,
        team_a=envelope.fixture.team_a,
        team_b=envelope.fixture.team_b,
        start_time=envelope.fixture.start_time,
        market_scope=envelope.fixture.market_scope.value,
        player_id=player_id,
        player_name=_player_name(envelope, player_id),
        stat=stat,
        line=line_val,
        recommendation=rec,
        grade=_grade(prob, rec),
        probability=prob,
        eligible=eligible,
        eligibility_reason=elig_reason,
        evidence_status=decision.evidence_status,
        last_refresh=envelope.captured_at,
        data_label=data_label,
    )
    detail = PickDetail(
        pick_id=pick_id,
        board=board,
        identity_status=decision.identity_status,
        identity_notes=identity_notes,
        source_attempts=attempts,
        raw_refs=raw_refs,
        map_context=dict(decision.map_context or envelope.map_context),
        opportunity=decision.opportunity,
        conversion=decision.conversion,
        provenance=list(decision.provenance),
        pass_reason=pass_reason,
        probabilities=dict(decision.probabilities),
        core_blocked=not core_is_ready,
    )
    return board, detail


def build_dashboard_snapshot(
    fixtures_root: Path,
    decide: DecideFn,
    *,
    data_label: str = "fixture/demo",
    now: datetime | None = None,
) -> DashboardSnapshot:
    now = now or datetime.now(timezone.utc)
    core_is_ready = core_ready()
    board: list[BoardRow] = []
    picks: dict[str, PickDetail] = {}
    settlements = []

    for fixture_dir in discover_fixture_dirs(fixtures_root):
        envelope = load_envelope(fixture_dir)
        decision = decide(envelope)
        pick_id = f"{envelope.fixture.event_id}:{envelope.target_player_id or 'player'}:headshots"
        row, detail = assemble_pick(
            envelope,
            decision,
            pick_id=pick_id,
            data_label=data_label,
            core_is_ready=core_is_ready,
        )
        board.append(row)
        picks[pick_id] = detail
        settlements.append(
            load_settlement(
                fixture_dir / "settlement.json",
                pick_id=pick_id,
                event_id=envelope.fixture.event_id,
                data_label=data_label,
            )
        )

    return DashboardSnapshot(
        title="MBM Esports Analyst Dashboard",
        data_label=data_label,
        core_status=core_status_message(),
        core_ready=core_is_ready,
        generated_at=now.isoformat().replace("+00:00", "Z"),
        board=board,
        picks=picks,
        settlements=settlements,
        calibration=build_calibration(board, settlements),
        notices=(
            f"Data label: {data_label}",
            core_status_message(),
            "Dashboard reads canonical intake/evidence records only.",
            "No live API / paid provider dependency.",
        ),
    )

