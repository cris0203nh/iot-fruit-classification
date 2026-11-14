"""AG-056 I01: unit tests for a read-only selection engine; no IoT/model needed."""
from datetime import datetime, timedelta, timezone
import unittest

from app.review_selection import (
    DetectionEvidence, EvaluationFacts, HumanDecision, ImageEvidence,
    QualityEvidence, QualityView, UncertaintyFlag, select_for_human_review,
    parse_ag037_uncertainty, parse_ag055_quality,
)

T0 = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
I1 = ImageEvidence("I-000001", "a" * 64)
I2 = ImageEvidence("I-000002", "b" * 64)


def case(status="completed", **changes):
    return EvaluationFacts("E-000001", status, images=(I1, I2), **changes)


def proposal(*, status="experimental_e0e1e2_v2", views=(), at=T0, sources=(I1, I2), reason="v2_no_external_evaluation"):
    return QualityEvidence(19, status, reason, at, sources, tuple(views))


def decision(image=I1, at=T0 + timedelta(seconds=1)):
    return HumanDecision(7, image.image_id, image.sha256, at)


class ReviewSelectionTests(unittest.TestCase):
    def codes(self, result):
        return {r.code for r in result.reasons}

    def test_unstarted_processing_excluded(self):
        self.assertFalse(select_for_human_review(case("processing")).requires_review)

    def test_processing_quality_proposal_is_not_ready(self):
        result = select_for_human_review(case("processing", quality_predictions=(proposal(),)))
        self.assertFalse(result.requires_review)

    def test_acquisition_pending_review_without_ai(self):
        result = select_for_human_review(case("pending_review"))
        self.assertEqual((result.requires_review, result.priority), (True, "normal"))
        self.assertEqual(self.codes(result), {"acquisition_pending_review"})

    def test_pending_without_evidence_is_priority_not_false_success(self):
        result = select_for_human_review(EvaluationFacts("E-000002", "pending_review"))
        self.assertEqual(self.codes(result), {"acquisition_evidence_missing"})
        self.assertEqual(result.priority, "high")

    def test_pending_capture_with_lost_image_requires_priority(self):
        result = select_for_human_review(EvaluationFacts(
            "E-000040", "pending_review", images=(ImageEvidence("I-000040", None),)))
        self.assertEqual(result.priority, "high")
        self.assertIn("evidence_unavailable", self.codes(result))

    def test_ready_detector_does_not_create_work(self):
        detection = DetectionEvidence(3, I1.image_id, I1.sha256,
                                      "ready_to_capture", "deteccion_apta_para_captura", T0)
        self.assertFalse(select_for_human_review(case(detections=(detection,))).requires_review)

    def test_uncertain_detector_prioritized_without_quality_grade(self):
        detection = DetectionEvidence(3, I1.image_id, I1.sha256,
                                      "pending_review", "confianza_insuficiente", T0)
        result = select_for_human_review(case("pending_review", detections=(detection,)))
        self.assertEqual(result.priority, "high")
        self.assertEqual(self.codes(result), {"uncertain_detection"})

    def test_force_review_flag_on_completed(self):
        flag = UncertaintyFlag(12, I1.image_id, I1.sha256, "solicitud_manual", T0)
        result = select_for_human_review(case(uncertainty_flags=(flag,)))
        self.assertTrue(result.requires_review)
        self.assertEqual(result.image_ids, (I1.image_id,))
        self.assertIn("manual_or_uncertain_detection", self.codes(result))

    def test_ag038_review_closes_same_image_and_sha(self):
        flag = UncertaintyFlag(12, I1.image_id, I1.sha256, "solicitud_manual", T0)
        result = select_for_human_review(case(uncertainty_flags=(flag,), human_decisions=(decision(),)))
        self.assertFalse(result.requires_review)

    def test_review_of_different_image_does_not_close_incident(self):
        flag = UncertaintyFlag(12, I1.image_id, I1.sha256, "solicitud_manual", T0)
        result = select_for_human_review(case(uncertainty_flags=(flag,), human_decisions=(decision(I2),)))
        self.assertTrue(result.requires_review)

    def test_old_review_does_not_close_new_manual_flag(self):
        flag = UncertaintyFlag(12, I1.image_id, I1.sha256, "solicitud_manual", T0)
        result = select_for_human_review(case(uncertainty_flags=(flag,),
            human_decisions=(decision(I1, T0 - timedelta(seconds=1)),)))
        self.assertTrue(result.requires_review)

    def test_legacy_ag037_only_resolves_older_ag037_incident(self):
        flag = UncertaintyFlag(12, I1.image_id, I1.sha256, "solicitud_manual", T0)
        detection = DetectionEvidence(3, I1.image_id, I1.sha256, "pending_review", "sin_deteccion", T0)
        result = select_for_human_review(case(uncertainty_flags=(flag,), detections=(detection,),
            legacy_ag037_resolutions=(T0 + timedelta(seconds=1),)))
        self.assertFalse(result.requires_review)

    def test_later_manual_flag_reopens_old_legacy_resolution(self):
        flag = UncertaintyFlag(12, I1.image_id, I1.sha256, "solicitud_manual", T0 + timedelta(seconds=2))
        result = select_for_human_review(case(uncertainty_flags=(flag,),
            legacy_ag037_resolutions=(T0 + timedelta(seconds=1),)))
        self.assertTrue(result.requires_review)

    def test_ag055_v2_agreement_remains_unconfirmed(self):
        result = select_for_human_review(case(quality_predictions=(proposal(views=(
            QualityView(I1.image_id, "E0", True), QualityView(I2.image_id, "E0", True))),)))
        self.assertEqual(result.priority, "normal")
        self.assertEqual(self.codes(result), {"quality_proposal_unconfirmed"})
        self.assertEqual(result.image_ids, (I1.image_id, I2.image_id))

    def test_e2_and_disagreement_are_priority_not_a_final_diagnosis(self):
        result = select_for_human_review(case(quality_predictions=(proposal(views=(
            QualityView(I1.image_id, "E1", True), QualityView(I2.image_id, "E2", True))),)))
        self.assertEqual(result.priority, "high")
        self.assertIn("quality_possible_e2", self.codes(result))
        self.assertIn("quality_disagreement", self.codes(result))

    def test_v2_segmentation_reject_and_partial_view(self):
        result = select_for_human_review(case(quality_predictions=(proposal(views=(
            QualityView(I1.image_id, None, False),
            QualityView(I2.image_id, "E0", True, partial_coverage=True))),)))
        self.assertIn("quality_not_evaluable", self.codes(result))
        self.assertIn("quality_partial_coverage", self.codes(result))
        self.assertEqual(result.priority, "high")

    def test_two_view_mismatch_needs_review(self):
        result = select_for_human_review(case(quality_predictions=(proposal(
            status="needs_review", reason="vistas_discrepantes"),)))
        self.assertEqual(result.priority, "high")
        self.assertIn("quality_analysis_requires_review", self.codes(result))

    def test_exploratory_original_label_is_diagnostic_only(self):
        result = select_for_human_review(case(quality_predictions=(proposal(
            status="exploratory_original_labels"),)))
        self.assertFalse(result.requires_review)

    def test_one_review_does_not_silence_second_photo(self):
        result = select_for_human_review(case(quality_predictions=(proposal(views=(
            QualityView(I1.image_id, "E0", True), QualityView(I2.image_id, "E0", True))),),
            human_decisions=(decision(I1),)))
        self.assertTrue(result.requires_review)
        self.assertEqual(result.image_ids, (I2.image_id,))

    def test_two_reviewed_views_resolve_quality_snapshot(self):
        result = select_for_human_review(case(quality_predictions=(proposal(views=(
            QualityView(I1.image_id, "E0", True), QualityView(I2.image_id, "E0", True))),),
            human_decisions=(decision(I1), decision(I2))))
        self.assertFalse(result.requires_review)

    def test_new_model_snapshot_reopens_case_after_prior_decision(self):
        old = proposal(at=T0, views=(QualityView(I1.image_id, "E0", True), QualityView(I2.image_id, "E0", True)))
        new = QualityEvidence(20, old.status, old.reason, T0 + timedelta(seconds=2),
                              (I1, I2), (QualityView(I1.image_id, "E0", True), QualityView(I2.image_id, "E0", True)))
        result = select_for_human_review(case(quality_predictions=(old, new),
            human_decisions=(decision(I1), decision(I2))))
        self.assertTrue(result.requires_review)
        self.assertEqual(result.image_ids, (I1.image_id, I2.image_id))

    def test_mismatch_hash_is_priority_and_cannot_be_resolved_by_old_decision(self):
        wrong = ImageEvidence(I1.image_id, "c" * 64)
        result = select_for_human_review(case(quality_predictions=(proposal(sources=(wrong,)),),
            human_decisions=(decision(I1),)))
        self.assertIn("source_hash_mismatch", self.codes(result))
        self.assertEqual(result.priority, "high")

    def test_missing_hash_not_accepted_silently(self):
        sample = ImageEvidence(I1.image_id, None)
        result = select_for_human_review(EvaluationFacts("E-000001", "completed",
            images=(sample,), quality_predictions=(proposal(sources=(I1,)),)))
        self.assertIn("source_hash_unverified", self.codes(result))

    def test_lost_foreign_image_never_returns_normal(self):
        foreign = ImageEvidence("I-000099", "d" * 64)
        result = select_for_human_review(case(quality_predictions=(proposal(sources=(foreign,)),)))
        self.assertIn("source_not_in_evaluation", self.codes(result))

    def test_snapshot_missing_view_is_high_priority(self):
        result = select_for_human_review(case(quality_predictions=(proposal(views=(
            QualityView(I1.image_id, "E0", True),)),)))
        self.assertIn("quality_view_missing", self.codes(result))
        self.assertEqual(result.priority, "high")

    def test_parse_real_ag037_flag(self):
        parsed = parse_ag037_uncertainty(10,
            f"AG037|image={I1.image_id}|sha256={I1.sha256}|cause=sin_deteccion|note=", T0)
        self.assertEqual((parsed.image_id, parsed.image_sha256, parsed.reason),
                         (I1.image_id, I1.sha256, "sin_deteccion"))
        malformed = parse_ag037_uncertainty(11, "AG037|corrupt-marker", T0)
        result = select_for_human_review(case(uncertainty_flags=(malformed,)))
        self.assertIn("uncertainty_without_image_identity", self.codes(result))

    def test_parse_real_ag055_v2_snapshot(self):
        sample = parse_ag055_quality(4, "experimental_e0e1e2_v2", "v2_no_external_evaluation", T0, {
            "sources": [{"imageId": I1.image_id, "sha256": I1.sha256},
                        {"imageId": I2.image_id, "sha256": I2.sha256}],
            "perView": [{"imageId": I1.image_id, "label": "E0", "evaluable": True,
                         "segmentation": {"partialCoverage": False}},
                        {"imageId": I2.image_id, "label": None, "evaluable": False,
                         "status": "no_evaluable"}]})
        result = select_for_human_review(case(quality_predictions=(sample,)))
        self.assertEqual(sample.views[0].grade, "E0")
        self.assertIn("quality_not_evaluable", self.codes(result))

    def test_parse_real_two_view_quality_proposal(self):
        sample = parse_ag055_quality(6, "experimental_proposal", "two_views_agree_experimental_only", T0, {
            "sources": [{"imageId": I1.image_id, "sha256": I1.sha256},
                        {"imageId": I2.image_id, "sha256": I2.sha256}],
            "perView": [{"imageId": I1.image_id, "suggestion": "E1"},
                        {"imageId": I2.image_id, "suggestion": "E1"}]})
        result = select_for_human_review(case(quality_predictions=(sample,)))
        self.assertEqual(result.priority, "normal")
        self.assertEqual(self.codes(result), {"quality_proposal_unconfirmed"})

    def test_malformed_snapshot_sources_do_not_fake_review_coverage(self):
        sample = parse_ag055_quality(8, "experimental_e0e1e2_v2", "invalid", T0, {
            "sources": [{"imageId": I1.image_id, "sha256": "INVALID"}], "perView": []})
        result = select_for_human_review(case(quality_predictions=(sample,)))
        self.assertIn("source_hash_unverified", self.codes(result))

    def test_malformed_model_views_are_prioritized(self):
        result = select_for_human_review(case(quality_predictions=(proposal(
            sources=(I1,), views=(QualityView(I2.image_id, "E0", True),)),)))
        self.assertIn("quality_views_inconsistent", self.codes(result))

    def test_empty_quality_sources_prioritized(self):
        result = select_for_human_review(case(quality_predictions=(proposal(sources=()),)))
        self.assertIn("quality_source_missing", self.codes(result))

    def test_cancelled_and_error_not_a_review_job(self):
        flag = UncertaintyFlag(12, I1.image_id, I1.sha256, "solicitud_manual", T0)
        for status in ("cancelled", "error"):
            with self.subTest(status=status):
                result = select_for_human_review(case(status, uncertainty_flags=(flag,)))
                self.assertFalse(result.requires_review)

    def test_unknown_status_fails_closed(self):
        with self.assertRaises(ValueError):
            select_for_human_review(case("mystery"))

    def test_deterministic_and_no_mutation(self):
        facts = case(quality_predictions=(proposal(views=(QualityView(I1.image_id, "E2", True),)),))
        self.assertEqual(select_for_human_review(facts), select_for_human_review(facts))
        self.assertEqual(facts.status, "completed")

    def test_sqlite_naive_datetime_accepted_as_utc(self):
        result = select_for_human_review(case(uncertainty_flags=(UncertaintyFlag(
            1, I1.image_id, I1.sha256, "sin_deteccion", T0.replace(tzinfo=None)),),
            human_decisions=(decision(),)))
        self.assertFalse(result.requires_review)

    def test_duplicate_image_identifiers_rejected(self):
        with self.assertRaises(ValueError):
            select_for_human_review(EvaluationFacts("E-1", "completed", images=(I1, I1)))


if __name__ == "__main__":
    unittest.main()
