"""NBA research + market-intelligence behavioral adapter."""

from mbm.behavioral.adapters.nba.audit import (
    MODEL_VERSION,
    BacktestAuditRecord,
    build_audit_record,
    require_complete_audit,
)
from mbm.behavioral.adapters.nba.gates import evaluate_nba_prop
from mbm.behavioral.adapters.nba.leakage import (
    PointInTimeCutoff,
    assert_no_lookahead,
    filter_as_of,
    reject_future_information,
)
from mbm.behavioral.adapters.nba.walkforward import (
    WalkForwardFold,
    chronological_walk_forward,
    purge_overlapping_training,
)

__all__ = [
    "MODEL_VERSION",
    "BacktestAuditRecord",
    "PointInTimeCutoff",
    "WalkForwardFold",
    "assert_no_lookahead",
    "build_audit_record",
    "chronological_walk_forward",
    "evaluate_nba_prop",
    "filter_as_of",
    "purge_overlapping_training",
    "reject_future_information",
    "require_complete_audit",
]
