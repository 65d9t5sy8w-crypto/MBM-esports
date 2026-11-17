"""NBA no-lookahead + purged chronological walk-forward acceptance tests.

Certification remains PENDING until this module passes in CI.
Deliberately injects future information and asserts MBM rejects it.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from mbm.behavioral.adapters.nba.analysis import PlayerGameStat, summarize_window
from mbm.behavioral.adapters.nba.audit import (
    MODEL_VERSION,
    SportsbookPriceAudit,
    build_audit_record,
    require_complete_audit,
)
from mbm.behavioral.adapters.nba.leakage import (
    PointInTimeCutoff,
    assert_no_lookahead,
    filter_as_of,
)
from mbm.behavioral.adapters.nba.metrics import ScoredPrediction, build_metrics_report
from mbm.behavioral.adapters.nba.projection import compare_to_market, select_pre_tip_snapshots
from mbm.behavioral.adapters.nba.props import prop_probabilities
from mbm.behavioral.adapters.nba.types import (
    AnalysisWindow,
    MarketSnapshot,
    NbaRecommendation,
    TimedObservation,
    WindowSummary,
)
from mbm.behavioral.adapters.nba.walkforward import (
    WalkForwardEvent,
    assert_training_precedes_evaluation,
    chronological_walk_forward,
    purge_overlapping_training,
    select_hyperparameters_earlier_only,
)


class TestNoLookahead(unittest.TestCase):
    def test_filter_as_of_drops_future_rows(self) -> None:
        rows = [
            TimedObservation("ok", "2025-11-14T12:00:00Z", 1),
            TimedObservation("leak", "2025-11-15T03:00:00Z", 99),
        ]
        kept = filter_as_of(rows, as_of="2025-11-15T02:00:00Z")
        self.assertEqual([r.key for r in kept], ["ok"])

    def test_assert_no_lookahead_raises_on_injected_future(self) -> None:
        rows = [TimedObservation("post_tip_line", "2025-11-15T03:00:00Z", -110)]
        with self.assertRaises(ValueError) as ctx:
            assert_no_lookahead(rows, as_of="2025-11-15T02:00:00Z")
        self.assertIn("lookahead rejected", str(ctx.exception))

    def test_settlement_labels_excluded_from_features(self) -> None:
        rows = [
            TimedObservation("feat", "2025-11-14T12:00:00Z", 1, is_label=False),
            TimedObservation(
                "label",
                "2025-11-15T05:00:00Z",
                30,
                is_label=True,
                valid_from="2025-11-15T02:00:00Z",
                valid_to="2025-11-15T05:00:00Z",
            ),
        ]
        kept = filter_as_of(rows, as_of="2025-11-15T02:00:00Z", allow_labels=False)
        self.assertEqual([r.key for r in kept], ["feat"])

    def test_research_window_ignores_post_cutoff_stats(self) -> None:
        history = [
            PlayerGameStat(
                "1", "237", "2025-11-10T02:00:00Z", "2", 2025, "points", 30,
                "2025-11-10T05:00:00Z",
            ),
            PlayerGameStat(
                "leak", "237", "2025-11-16T02:00:00Z", "2", 2025, "points", 50,
                "2025-11-16T05:00:00Z",
            ),
        ]
        summary = summarize_window(
            history,
            window=AnalysisWindow.LAST_10,
            as_of="2025-11-15T02:00:00Z",
            player_id="237",
            stat_name="points",
        )
        self.assertEqual(summary.sample_size, 1)
        self.assertEqual(summary.values, (30.0,))

    def test_post_tip_market_snapshots_rejected(self) -> None:
        snaps = [
            MarketSnapshot(
                "dk", "points", 27.5, -115, -105, "2025-11-14T21:00:00Z",
                "balldontlie", "prop:1", "910001", "237",
            ),
            MarketSnapshot(
                "fd", "points", 27.5, -200, 150, "2025-11-15T03:00:00Z",
                "balldontlie", "prop:leak", "910001", "237",
            ),
        ]
        usable = select_pre_tip_snapshots(snaps, game_start="2025-11-15T02:00:00Z")
        self.assertEqual(len(usable), 1)
        self.assertEqual(usable[0].vendor, "dk")
        prop = prop_probabilities(
            {
                "last_10": WindowSummary(
                    AnalysisWindow.LAST_10, 10, 29.0, tuple([29.0] * 10),
                    "2025-11-15T02:00:00Z",
                )
            },
            line=27.5,
        )
        cmp = compare_to_market(prop, snaps, game_start="2025-11-15T02:00:00Z")
        self.assertFalse(cmp.deferred_to_market)
        self.assertNotIn("fanduel", " ".join(cmp.notes))


class TestPurgedWalkForward(unittest.TestCase):
    def test_training_always_precedes_evaluation(self) -> None:
        events = [
            WalkForwardEvent("g1", "2025-11-01T02:00:00Z", (
                TimedObservation("f1", "2025-10-31T12:00:00Z", 1,
                                 valid_from="2025-10-20T00:00:00Z",
                                 valid_to="2025-10-31T12:00:00Z"),
            ), TimedObservation("l1", "2025-11-01T05:00:00Z", 1, is_label=True,
                                valid_from="2025-11-01T02:00:00Z",
                                valid_to="2025-11-01T05:00:00Z")),
            WalkForwardEvent("g2", "2025-11-05T02:00:00Z", (
                TimedObservation("f2", "2025-11-04T12:00:00Z", 1,
                                 valid_from="2025-10-25T00:00:00Z",
                                 valid_to="2025-11-04T12:00:00Z"),
            ), TimedObservation("l2", "2025-11-05T05:00:00Z", 1, is_label=True,
                                valid_from="2025-11-05T02:00:00Z",
                                valid_to="2025-11-05T05:00:00Z")),
            WalkForwardEvent("g3", "2025-11-10T02:00:00Z", (
                TimedObservation("f3", "2025-11-09T12:00:00Z", 1,
                                 valid_from="2025-11-01T00:00:00Z",
                                 valid_to="2025-11-09T12:00:00Z"),
            ), None),
        ]
        folds = chronological_walk_forward(events, min_train=1)
        self.assertGreaterEqual(len(folds), 2)
        for fold in folds:
            assert_training_precedes_evaluation(fold, events)
            self.assertEqual(fold.cutoff.as_of, fold.eval_start)
            # Hyperparameter tuning may only reference earlier folds.
            self.assertTrue(all(i < fold.fold_index for i in fold.tuning_fold_indices))

    def test_purge_excludes_earlier_game_with_overlapping_label_window(self) -> None:
        """Game date earlier than eval, but label window still touches eval → purge."""
        eval_start = "2025-11-10T02:00:00Z"
        # Tip-off was Nov 8, but settlement/label window extends through Nov 10 tip.
        overlapping_label = TimedObservation(
            key="slow_settle_label",
            observed_at="2025-11-10T04:00:00Z",
            value=28,
            is_label=True,
            valid_from="2025-11-08T02:00:00Z",
            valid_to="2025-11-10T04:00:00Z",
        )
        # Feature window that spans into eval period despite earlier game date.
        overlapping_feature = TimedObservation(
            key="rolling_feature_into_eval",
            observed_at="2025-11-09T12:00:00Z",
            value=1,
            valid_from="2025-11-01T00:00:00Z",
            valid_to="2025-11-10T12:00:00Z",  # overlaps eval
        )
        safe = TimedObservation(
            key="safe_feature",
            observed_at="2025-11-07T12:00:00Z",
            value=1,
            valid_from="2025-11-01T00:00:00Z",
            valid_to="2025-11-07T12:00:00Z",
        )
        kept, purged = purge_overlapping_training(
            [overlapping_label, overlapping_feature, safe],
            eval_start=eval_start,
            eval_end="2025-11-10T05:00:00Z",
        )
        self.assertIn("slow_settle_label", purged)
        self.assertIn("rolling_feature_into_eval", purged)
        self.assertEqual([r.key for r in kept], ["safe_feature"])

    def test_never_shuffles_across_time(self) -> None:
        events = [
            WalkForwardEvent("late", "2025-11-20T02:00:00Z", ()),
            WalkForwardEvent("early", "2025-11-01T02:00:00Z", ()),
            WalkForwardEvent("mid", "2025-11-10T02:00:00Z", ()),
        ]
        folds = chronological_walk_forward(events, min_train=1)
        eval_ids = [f.eval_game_id for f in folds]
        self.assertEqual(eval_ids, ["mid", "late"])

    def test_same_tip_off_excluded_from_training(self) -> None:
        events = [
            WalkForwardEvent("a", "2025-11-10T02:00:00Z", ()),
            WalkForwardEvent("b", "2025-11-10T02:00:00Z", ()),
            WalkForwardEvent("c", "2025-11-15T02:00:00Z", ()),
        ]
        folds = chronological_walk_forward(events, min_train=1)
        # a and b share tip-off — neither may train the other; only c can eval with prior.
        for fold in folds:
            if fold.eval_game_id in {"a", "b"}:
                self.fail("same tip-off games must not form folds against each other")
            self.assertEqual(fold.eval_game_id, "c")
            self.assertEqual(set(fold.train_game_ids), {"a", "b"})

    def test_run_walk_forward_passes_label_free_as_of_features(self) -> None:
        from mbm.behavioral.adapters.nba.walkforward import run_walk_forward

        events = [
            WalkForwardEvent(
                "g1",
                "2025-11-01T02:00:00Z",
                (TimedObservation("f1", "2025-10-31T12:00:00Z", 1),),
                TimedObservation(
                    "l1",
                    "2025-11-01T05:00:00Z",
                    1,
                    is_label=True,
                    valid_from="2025-11-01T02:00:00Z",
                    valid_to="2025-11-01T05:00:00Z",
                ),
            ),
            WalkForwardEvent(
                "g2",
                "2025-11-05T02:00:00Z",
                (
                    TimedObservation("pre", "2025-11-04T12:00:00Z", 1),
                    TimedObservation("post", "2025-11-05T03:00:00Z", 99),
                ),
                TimedObservation(
                    "l2",
                    "2025-11-05T05:00:00Z",
                    1,
                    is_label=True,
                    valid_from="2025-11-05T02:00:00Z",
                    valid_to="2025-11-05T05:00:00Z",
                ),
            ),
        ]
        seen: list[WalkForwardEvent] = []

        def predict(_fold, ev):
            seen.append(ev)
            return "ok"

        results = run_walk_forward(events, predict, min_train=1)
        self.assertEqual(len(results), 1)
        fold, pred, label = results[0]
        self.assertEqual(pred, "ok")
        self.assertIsNotNone(label)
        self.assertTrue(label.is_label)
        self.assertEqual(seen[0].label, None)
        self.assertEqual([f.key for f in seen[0].features], ["pre"])
        self.assertEqual(fold.eval_game_id, "g2")

    def test_hyperparameter_tuning_rejects_current_or_future_folds(self) -> None:
        events = [
            WalkForwardEvent(f"g{i}", f"2025-11-{i:02d}T02:00:00Z", ())
            for i in (1, 5, 10, 15)
        ]
        folds = chronological_walk_forward(events, min_train=1)
        fold = folds[-1]
        with self.assertRaises(ValueError):
            select_hyperparameters_earlier_only(
                fold,
                candidate_scores_by_fold={
                    fold.fold_index: {"a": 0.1},  # illegal: current fold
                },
            )
        # Legal: only earlier folds
        choice = select_hyperparameters_earlier_only(
            fold,
            candidate_scores_by_fold={
                idx: {"alpha": 0.2, "beta": 0.1} for idx in fold.tuning_fold_indices
            },
            lower_is_better=True,
        )
        self.assertEqual(choice, "beta")

    def test_every_prediction_has_recorded_cutoff(self) -> None:
        events = [
            WalkForwardEvent("g1", "2025-11-01T02:00:00Z", ()),
            WalkForwardEvent("g2", "2025-11-05T02:00:00Z", ()),
        ]
        folds = chronological_walk_forward(events, min_train=1)
        for fold in folds:
            self.assertIsInstance(fold.cutoff, PointInTimeCutoff)
            self.assertEqual(fold.cutoff.game_id, fold.eval_game_id)
            self.assertEqual(fold.cutoff.as_of, fold.eval_start)

    def test_purge_gap_extends_exclusion(self) -> None:
        row = TimedObservation(
            "near",
            "2025-11-09T20:00:00Z",
            1,
            valid_from="2025-11-09T18:00:00Z",
            valid_to="2025-11-09T20:00:00Z",
        )
        kept, purged = purge_overlapping_training(
            [row],
            eval_start="2025-11-10T02:00:00Z",
            purge_gap=timedelta(hours=12),
        )
        self.assertIn("near", purged)
        self.assertEqual(kept, [])


class TestAuditAndMetrics(unittest.TestCase):
    def test_audit_requires_reproducibility_fields(self) -> None:
        with self.assertRaises(ValueError):
            build_audit_record(
                prediction_timestamp="2025-11-15T01:00:00Z",
                game_id="910001",
                cutoff_as_of="2025-11-15T02:00:00Z",
                source_snapshot_identifiers=(),
                sportsbook_price=None,
                settlement_outcome=None,
                settlement_value=None,
                action="MORE",
                p_more=0.6,
                fold_index=0,
                train_game_ids=["g1"],
                purged_train_keys=[],
            )

    def test_complete_audit_roundtrip(self) -> None:
        price = SportsbookPriceAudit(
            vendor="draftkings",
            line=27.5,
            more_odds=-115,
            less_odds=-105,
            captured_at="2025-11-14T21:30:00Z",
            raw_evidence_ref="player_prop:501",
        )
        record = build_audit_record(
            prediction_timestamp="2025-11-15T01:00:00Z",
            game_id="910001",
            cutoff_as_of="2025-11-15T02:00:00Z",
            source_snapshot_identifiers=("synthetic:stats", "synthetic:player_props"),
            sportsbook_price=price,
            settlement_outcome="more",
            settlement_value=30.0,
            action="MORE",
            p_more=0.62,
            fold_index=3,
            train_game_ids=["900001", "900002"],
            purged_train_keys=["rolling_feature_into_eval"],
        )
        require_complete_audit(record)
        payload = record.to_dict()
        self.assertEqual(payload["model_version"], MODEL_VERSION)
        self.assertEqual(payload["sportsbook_price"]["vendor"], "draftkings")
        self.assertEqual(payload["settlement_outcome"], "more")
        self.assertEqual(payload["prediction_timestamp"], "2025-11-15T01:00:00Z")

    def test_metrics_reported_separately_with_sample_sizes(self) -> None:
        rows = [
            ScoredPrediction("g1", 0.7, True, True, 0.9, 0.7),
            ScoredPrediction("g2", 0.4, False, False, 0.8, 0.6),
            ScoredPrediction("g3", 0.55, True, False, -1.0, 0.55),
            ScoredPrediction("g4", 0.5, True, None, None, 0.5),  # unsettled PASS-ish
        ]
        report = build_metrics_report(rows)
        self.assertEqual(report.sample_size, 4)
        self.assertIsNotNone(report.hit_rate)
        self.assertEqual(report.hit_rate_n, 3)
        self.assertIsNotNone(report.brier_score)
        self.assertEqual(report.brier_n, 3)
        self.assertIsNone(report.calibration_error)  # insufficient sample
        self.assertEqual(report.calibration_n, 3)
        self.assertIsNotNone(report.realized_roi)
        self.assertEqual(report.roi_n, 3)
        self.assertIn("separately", " ".join(report.notes))


class TestMacroscopeLeakageRegressions(unittest.TestCase):
    """Regressions for as_of line selection, scoping, NaN stats, ISO sort."""

    def test_as_of_rejects_line_between_cutoff_and_tip(self) -> None:
        from mbm.behavioral.adapters.nba.gates import evaluate_nba_prop
        from mbm.intake.types import (
            EvidenceEnvelope,
            EvidenceStatus,
            FixtureIdentity,
            IdentityStatus,
            MarketScope,
        )

        tip = "2025-11-15T20:00:00Z"
        as_of = "2025-11-15T18:00:00Z"
        env = EvidenceEnvelope(
            source="synthetic_test_fixture",
            captured_at="2025-11-15T17:00:00Z",
            fixture=FixtureIdentity(
                event_id="synthetic-910001",
                team_a="A",
                team_b="B",
                start_time=tip,
                format="nba_game",
                market_scope=MarketScope.FULL_GAME,
            ),
            players=[],
            match_logs=[],
            map_context={
                "not_for_projection": False,
                "game": {"id": 910001, "season": 2025},
                "player_props": [
                    {
                        "id": 1,
                        "game_id": 910001,
                        "player_id": 237,
                        "prop_type": "points",
                        "line_value": "27.5",
                        "updated_at": "2025-11-15T19:00:00Z",  # after as_of, before tip
                        "vendor": "dk",
                        "market": {"type": "over_under", "over_odds": -110, "under_odds": -110},
                    }
                ],
                "sportsbook_prices": [],
                "stats": [],
            },
            market_lines=[],
            evidence_status=EvidenceStatus.VERIFIED,
            identity_status=IdentityStatus.RESOLVED,
            target_player_id="237",
        )
        decision = evaluate_nba_prop(
            env,
            cutoff=PointInTimeCutoff(
                game_id="910001",
                game_start=tip,
                as_of=as_of,
                recorded_at="2025-11-15T17:00:00Z",
            ),
            history=[],
            min_sample=1,
        )
        self.assertIsNone(decision.evaluated_line)
        self.assertIn("missing_pre_tip_market_line", decision.reasons)

    def test_prop_selection_scoped_to_game_and_player(self) -> None:
        from mbm.behavioral.adapters.nba.gates import evaluate_nba_prop
        from mbm.intake.types import (
            EvidenceEnvelope,
            EvidenceStatus,
            FixtureIdentity,
            IdentityStatus,
            MarketScope,
        )

        tip = "2025-11-15T02:00:00Z"
        env = EvidenceEnvelope(
            source="synthetic_test_fixture",
            captured_at="2025-11-15T01:00:00Z",
            fixture=FixtureIdentity(
                event_id="synthetic-910001",
                team_a="A",
                team_b="B",
                start_time=tip,
                format="nba_game",
                market_scope=MarketScope.FULL_GAME,
            ),
            players=[],
            match_logs=[],
            map_context={
                "not_for_projection": False,
                "game": {"id": 910001, "season": 2025},
                "player_props": [
                    {
                        "id": 99,
                        "game_id": 999999,
                        "player_id": 237,
                        "prop_type": "points",
                        "line_value": "99.5",
                        "updated_at": "2025-11-15T01:50:00Z",
                        "vendor": "other-game",
                        "market": {"type": "over_under", "over_odds": -110, "under_odds": -110},
                    },
                    {
                        "id": 98,
                        "game_id": 910001,
                        "player_id": 1,
                        "prop_type": "points",
                        "line_value": "11.5",
                        "updated_at": "2025-11-15T01:55:00Z",
                        "vendor": "other-player",
                        "market": {"type": "over_under", "over_odds": -110, "under_odds": -110},
                    },
                    {
                        "id": 1,
                        "game_id": 910001,
                        "player_id": 237,
                        "prop_type": "points",
                        "line_value": "27.5",
                        "updated_at": "2025-11-15T01:00:00Z",
                        "vendor": "dk",
                        "market": {"type": "over_under", "over_odds": -110, "under_odds": -110},
                    },
                ],
                "sportsbook_prices": [],
                "stats": [],
            },
            market_lines=[],
            evidence_status=EvidenceStatus.VERIFIED,
            identity_status=IdentityStatus.RESOLVED,
            target_player_id="237",
        )
        hist = [
            PlayerGameStat(
                game_id=f"g{i}",
                player_id="237",
                game_start=f"2025-11-{i:02d}T02:00:00Z",
                opponent_team_id="2",
                season=2025,
                stat_name="points",
                stat_value=30.0,
                observed_at=f"2025-11-{i:02d}T05:00:00Z",
            )
            for i in range(1, 10)
        ]
        decision = evaluate_nba_prop(
            env,
            cutoff=PointInTimeCutoff(
                game_id="910001",
                game_start=tip,
                as_of=tip,
                recorded_at="2025-11-15T01:00:00Z",
            ),
            history=hist,
            min_sample=5,
        )
        self.assertEqual(decision.evaluated_player_id, "237")
        self.assertEqual(decision.evaluated_line, 27.5)
        self.assertNotEqual(decision.evaluated_line, 99.5)
        self.assertNotEqual(decision.evaluated_line, 11.5)

    def test_unparseable_snapshot_does_not_abort_evaluation(self) -> None:
        from mbm.behavioral.adapters.nba.gates import evaluate_nba_prop
        from mbm.intake.types import (
            EvidenceEnvelope,
            EvidenceStatus,
            FixtureIdentity,
            IdentityStatus,
            MarketScope,
        )

        tip = "2025-11-15T02:00:00Z"
        env = EvidenceEnvelope(
            source="synthetic_test_fixture",
            captured_at="2025-11-15T01:00:00Z",
            fixture=FixtureIdentity(
                event_id="synthetic-910001",
                team_a="A",
                team_b="B",
                start_time=tip,
                format="nba_game",
                market_scope=MarketScope.FULL_GAME,
            ),
            players=[],
            match_logs=[],
            map_context={
                "not_for_projection": True,
                "game": {"id": 910001, "season": 2025},
                "player_props": [
                    {
                        "id": 1,
                        "game_id": 910001,
                        "player_id": 237,
                        "prop_type": "points",
                        "line_value": "27.5",
                        "updated_at": "2025-11-14T21:00:00Z",
                        "vendor": "dk",
                        "market": {"type": "over_under", "over_odds": -110, "under_odds": -110},
                    },
                    {
                        "id": 2,
                        "game_id": 910001,
                        "player_id": 999,
                        "prop_type": "points",
                        "line_value": "10.5",
                        "updated_at": "not-a-timestamp",
                        "vendor": "bad",
                        "market": {"type": "over_under", "over_odds": -110, "under_odds": -110},
                    },
                ],
                "sportsbook_prices": [],
                "stats": [],
            },
            market_lines=[],
            evidence_status=EvidenceStatus.INCOMPLETE,
            identity_status=IdentityStatus.RESOLVED,
            target_player_id="237",
        )
        decision = evaluate_nba_prop(
            env,
            cutoff=PointInTimeCutoff(
                game_id="910001",
                game_start=tip,
                as_of=tip,
                recorded_at="2025-11-15T01:00:00Z",
            ),
            history=[],
            min_sample=1,
        )
        self.assertEqual(decision.evaluated_line, 27.5)

    def test_compare_to_market_sorts_by_parsed_instant(self) -> None:
        # 22:00-05:00 == 03:00Z, which is after 01:00Z but still before a 05:00Z tip.
        # Lexicographic string sort would wrongly prefer the Z timestamp.
        snaps = [
            MarketSnapshot(
                "older_utc", "points", 27.5, -115, -105, "2025-11-15T01:00:00Z",
                "balldontlie", "prop:1", "910001", "237",
            ),
            MarketSnapshot(
                "newer_offset", "points", 27.5, -200, 150, "2025-11-14T22:00:00-05:00",
                "balldontlie", "prop:2", "910001", "237",
            ),
        ]
        prop = prop_probabilities(
            {
                "last_10": WindowSummary(
                    AnalysisWindow.LAST_10, 10, 29.0, tuple([29.0] * 10),
                    "2025-11-15T05:00:00Z",
                )
            },
            line=27.5,
        )
        cmp = compare_to_market(
            prop,
            snaps,
            game_start="2025-11-15T05:00:00Z",
            game_id="910001",
            player_id="237",
            prop_type="points",
        )
        self.assertIn("newer_offset", " ".join(cmp.notes))

    def test_non_finite_stats_rejected(self) -> None:
        from mbm.behavioral.adapters.nba.analysis import stats_from_envelope_context

        rows = stats_from_envelope_context(
            {
                "stats": [
                    {
                        "id": 1,
                        "player": {"id": 237},
                        "team": {"id": 14},
                        "game": {
                            "id": 1,
                            "datetime": "2025-11-10T02:00:00Z",
                            "home_team_id": 14,
                            "visitor_team_id": 13,
                        },
                        "pts": "NaN",
                        "reb": "Infinity",
                        "ast": 5,
                        "min": "30:00",
                        "observed_at": "2025-11-10T05:00:00Z",
                    }
                ]
            }
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].stat_name, "assists")
        self.assertEqual(rows[0].stat_value, 5.0)

    def test_non_finite_market_line_cannot_grade_a(self) -> None:
        from mbm.behavioral.adapters.nba.gates import evaluate_nba_prop
        from mbm.intake.types import (
            EvidenceEnvelope,
            EvidenceStatus,
            FixtureIdentity,
            IdentityStatus,
            MarketLine,
            MarketScope,
        )

        tip = "2025-11-15T02:00:00Z"
        hist = [
            PlayerGameStat(
                game_id=f"g{i}",
                player_id="237",
                game_start=f"2025-11-{i:02d}T02:00:00Z",
                opponent_team_id="2",
                season=2025,
                stat_name="points",
                stat_value=30.0,
                observed_at=f"2025-11-{i:02d}T05:00:00Z",
            )
            for i in range(1, 10)
        ]
        env = EvidenceEnvelope(
            source="synthetic_test_fixture",
            captured_at="2025-11-15T01:00:00Z",
            fixture=FixtureIdentity(
                event_id="synthetic-910001",
                team_a="A",
                team_b="B",
                start_time=tip,
                format="nba_game",
                market_scope=MarketScope.FULL_GAME,
            ),
            players=[],
            match_logs=[],
            map_context={
                "not_for_projection": False,
                "game": {"id": 910001, "season": 2025},
                "player_props": [
                    {
                        "id": 1,
                        "game_id": 910001,
                        "player_id": 237,
                        "prop_type": "points",
                        "line_value": "Infinity",
                        "updated_at": "2025-11-14T21:00:00Z",
                        "vendor": "dk",
                        "market": {"type": "over_under", "over_odds": -110, "under_odds": -110},
                    }
                ],
                "sportsbook_prices": [],
                "stats": [],
            },
            market_lines=[
                MarketLine("237", "points", float("inf"), MarketScope.FULL_GAME),
            ],
            evidence_status=EvidenceStatus.VERIFIED,
            identity_status=IdentityStatus.RESOLVED,
            target_player_id="237",
        )
        decision = evaluate_nba_prop(
            env,
            cutoff=PointInTimeCutoff(
                game_id="910001",
                game_start=tip,
                as_of=tip,
                recorded_at="2025-11-15T01:00:00Z",
            ),
            history=hist,
            min_sample=5,
        )
        self.assertIsNone(decision.evaluated_line)
        self.assertNotEqual(decision.grade, "A")
        self.assertEqual(decision.action, NbaRecommendation.PASS)

    def test_malformed_stat_timestamps_skipped(self) -> None:
        from mbm.behavioral.adapters.nba.analysis import stats_from_envelope_context

        rows = stats_from_envelope_context(
            {
                "stats": [
                    {
                        "player": {"id": 237},
                        "team": {"id": 14},
                        "game": {"id": 1, "datetime": "not-a-date", "season": 2025},
                        "pts": 20,
                        "observed_at": "2025-11-10T05:00:00Z",
                    },
                    {
                        "player": {"id": 237},
                        "team": {"id": 14},
                        "game": {
                            "id": 2,
                            "datetime": "2025-11-10T02:00:00Z",
                            "season": "twenty-five",
                        },
                        "pts": 22,
                        "observed_at": "2025-11-10T05:00:00Z",
                    },
                    {
                        "player": {"id": 237},
                        "team": {"id": 14},
                        "game": {
                            "id": 3,
                            "datetime": "2025-11-10T02:00:00Z",
                            "season": 2025,
                        },
                        "pts": 24,
                        "observed_at": "bad-observed",
                    },
                    {
                        "player": {"id": 237},
                        "team": {"id": 14},
                        "game": {
                            "id": 4,
                            "datetime": "2025-11-10T02:00:00Z",
                            "season": 2025,
                        },
                        "pts": 26,
                        "observed_at": "2025-11-10T05:00:00Z",
                    },
                ]
            }
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].stat_value, 26.0)

    def test_parse_iso_accepts_space_separated_timestamp(self) -> None:
        from mbm.behavioral.adapters.nba.leakage import parse_iso, market_snapshot_usable

        dt = parse_iso("2025-11-14 21:30:00+00:00")
        self.assertEqual(dt.year, 2025)
        self.assertEqual(dt.hour, 21)
        self.assertTrue(
            market_snapshot_usable(
                captured_at="2025-11-14 21:30:00+00:00",
                game_start="2025-11-15T02:00:00Z",
            )
        )


if __name__ == "__main__":
    unittest.main()
