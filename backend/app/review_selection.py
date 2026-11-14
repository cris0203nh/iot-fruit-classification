"""AG-056 I01: deterministic, read-only routing of human-review cases.

The detector validates capture, not E0/E1/E2. AG-055 proposals are experimental,
so no score, confidence, or agreement is permission to accept a visual grade.
This pure module has no database, filesystem, model or API side effects. I02 will
adapt persisted facts into these immutable inputs and expose the review queue.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Literal, Mapping, Any

RULE_VERSION = "ag056-review-selection-v1"
_AG037_FLAG = re.compile(r"^AG037\|image=(I-\d{1,9})\|sha256=([a-fA-F0-9]{64})\|cause=([^|]+)")
Priority = Literal["high", "normal"]
VALID_STATUSES = frozenset({"processing", "pending_review", "completed", "error", "cancelled"})
QUALITY_STATUSES = frozenset({
    "experimental_proposal", "needs_review", "experimental_e0e1e2_pilot",
    "experimental_e0e1e2_v2",
})


@dataclass(frozen=True)
class ImageEvidence:
    image_id: str
    sha256: str | None = None


@dataclass(frozen=True)
class DetectionEvidence:
    assessment_id: int
    image_id: str
    image_sha256: str
    outcome: str
    reason: str
    created_at: datetime


@dataclass(frozen=True)
class QualityView:
    image_id: str
    grade: str | None
    evaluable: bool | None
    partial_coverage: bool = False


@dataclass(frozen=True)
class QualityEvidence:
    prediction_id: int
    status: str
    reason: str
    created_at: datetime
    sources: tuple[ImageEvidence, ...]
    views: tuple[QualityView, ...] = ()


@dataclass(frozen=True)
class UncertaintyFlag:
    event_id: int
    image_id: str | None
    image_sha256: str | None
    reason: str
    performed_at: datetime


@dataclass(frozen=True)
class HumanDecision:
    review_id: int
    image_id: str
    image_sha256: str
    performed_at: datetime


@dataclass(frozen=True)
class EvaluationFacts:
    evaluation_id: str
    status: str
    images: tuple[ImageEvidence, ...] = ()
    detections: tuple[DetectionEvidence, ...] = ()
    quality_predictions: tuple[QualityEvidence, ...] = ()
    uncertainty_flags: tuple[UncertaintyFlag, ...] = ()
    human_decisions: tuple[HumanDecision, ...] = ()
    # AG-037 /vision/resolve wrote a review event without AG-038 image evidence.
    # Such a legacy resolution may close only earlier AG-037 flags/detections,
    # never AG-055 proposals or a new flag added after that resolution.
    legacy_ag037_resolutions: tuple[datetime, ...] = ()


@dataclass(frozen=True)
class RoutingReason:
    code: str
    priority: Priority
    image_id: str | None
    source: str


@dataclass(frozen=True)
class SelectionResult:
    evaluation_id: str
    requires_review: bool
    priority: Priority | None
    reasons: tuple[RoutingReason, ...]
    image_ids: tuple[str, ...]
    rule_version: str = RULE_VERSION



def parse_ag037_uncertainty(event_id: int, reason: str, performed_at: datetime) -> UncertaintyFlag:
    """Decode the real AG-037 marker; unknown formats remain visible as high-risk flags."""
    match = _AG037_FLAG.match(reason)
    return UncertaintyFlag(event_id, match.group(1) if match else None,
                           match.group(2).lower() if match else None,
                           match.group(3) if match else "uncertainty_unparsed", performed_at)


def parse_ag055_quality(prediction_id: int, status: str, reason: str,
                        created_at: datetime, details: Mapping[str, Any]) -> QualityEvidence:
    """Normalize stored AG-055 JSON for V1/V2 and two-view proposals without inference."""
    sources: list[ImageEvidence] = []
    source_rows = details.get("sources")
    if isinstance(source_rows, list):
        for item in source_rows:
            if isinstance(item, dict) and isinstance(item.get("imageId"), str):
                sha = item.get("sha256")
                sha = sha.lower() if isinstance(sha, str) and re.fullmatch(r"[0-9a-fA-F]{64}", sha) else None
                sources.append(ImageEvidence(item["imageId"], sha))

    views: list[QualityView] = []
    raw_views = details.get("perView")
    if isinstance(raw_views, list):
        for item in raw_views:
            if not isinstance(item, dict) or not isinstance(item.get("imageId"), str):
                continue
            grade = item.get("label") if status.startswith("experimental_e0e1e2_") else item.get("suggestion")
            if grade not in ("E0", "E1", "E2"):
                grade = None
            evaluable = item.get("evaluable")
            if not isinstance(evaluable, bool):
                evaluable = grade is not None if status == "experimental_proposal" else None
            segment = item.get("segmentation")
            partial = bool(segment.get("partialCoverage") is True) if isinstance(segment, dict) else False
            views.append(QualityView(item["imageId"], grade, evaluable, partial))
    return QualityEvidence(prediction_id, status, reason, created_at,
                           tuple(sources), tuple(views))


def _utc(value: datetime) -> datetime:
    """SQLite can return naive UTC timestamps; compare them safely to aware UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def select_for_human_review(facts: EvaluationFacts) -> SelectionResult:
    """Return unresolved, actionable causes; never change a classification.

    A canonical AG-038 decision closes only evidence for the SAME image/hash
    recorded at/after the signal. It cannot close another view or a later model
    snapshot. A completed evaluation can thus re-enter the queue when a new
    review signal appears. Historic diagnostic-only AG-055 outputs are ignored.
    """
    if facts.status not in VALID_STATUSES:
        raise ValueError(f"Unsupported evaluation status: {facts.status}")

    def empty() -> SelectionResult:
        return SelectionResult(facts.evaluation_id, False, None, (), ())

    if facts.status in {"error", "cancelled"}:
        return empty()  # Technical failures and cancellations have a separate workflow.

    current = {item.image_id: item.sha256 for item in facts.images}
    if len(current) != len(facts.images):
        raise ValueError("Image identifiers must be unique within the evaluation")

    decisions = tuple(facts.human_decisions)
    legacy = tuple(_utc(t) for t in facts.legacy_ag037_resolutions)
    found: dict[tuple[str, str | None], RoutingReason] = {}

    def add(code: str, priority: Priority, image_id: str | None, source: str) -> None:
        key = (code, image_id)
        value = RoutingReason(code, priority, image_id, source)
        previous = found.get(key)
        if previous is None or (priority == "high" and previous.priority != "high"):
            found[key] = value

    def addressed(image_id: str, sha256: str, at: datetime, *, ag037: bool = False) -> bool:
        moment = _utc(at)
        if any(d.image_id == image_id and d.image_sha256 == sha256
               and _utc(d.performed_at) >= moment for d in decisions):
            return True
        return ag037 and facts.status == "completed" and any(t >= moment for t in legacy)

    def source_problem(image_id: str, sha256: str, origin: str) -> bool:
        if image_id not in current:
            add("source_not_in_evaluation", "high", image_id, origin)
            return True
        if not sha256 or current[image_id] is None:
            add("source_hash_unverified", "high", image_id, origin)
            return True
        if current[image_id] != sha256:
            add("source_hash_mismatch", "high", image_id, origin)
            return True
        return False

    # A pending capture with a missing/modified physical source cannot be
    # treated as ordinary review work even if no model has run yet.
    if facts.status == "pending_review":
        for photo in facts.images:
            if photo.sha256 is None:
                add("evidence_unavailable", "high", photo.image_id, "source-integrity")

    for signal in facts.uncertainty_flags:
        origin = f"ag037-event:{signal.event_id}"
        if not signal.image_id or not signal.image_sha256:
            # A malformed/legacy flag cannot be silently treated as resolved.
            add("uncertainty_without_image_identity", "high", None, origin)
            continue
        if source_problem(signal.image_id, signal.image_sha256, origin):
            continue
        if not addressed(signal.image_id, signal.image_sha256,
                         signal.performed_at, ag037=True):
            add("manual_or_uncertain_detection", "high", signal.image_id, origin)

    for signal in facts.detections:
        if signal.outcome == "ready_to_capture":
            continue
        origin = f"ag037-assessment:{signal.assessment_id}"
        if source_problem(signal.image_id, signal.image_sha256, origin):
            continue
        if not addressed(signal.image_id, signal.image_sha256,
                         signal.created_at, ag037=True):
            add("uncertain_detection" if signal.outcome == "pending_review"
                else "unknown_detection_outcome", "high", signal.image_id, origin)

    # Do not route diagnostic-only datasets or original-label classifiers.
    for prediction in facts.quality_predictions:
        if prediction.status not in QUALITY_STATUSES:
            continue
        origin = f"ag055-prediction:{prediction.prediction_id}"
        if not prediction.sources:
            add("quality_source_missing", "high", None, origin)
            continue
        labels = {v.grade for v in prediction.views if v.grade in {"E0", "E1", "E2"}}
        disagreement = len(labels) > 1 or prediction.reason == "vistas_discrepantes"
        views = {v.image_id: v for v in prediction.views}
        if len(views) != len(prediction.views) or any(v not in {s.image_id for s in prediction.sources} for v in views):
            add("quality_views_inconsistent", "high", None, origin)

        for source in prediction.sources:
            if source_problem(source.image_id, source.sha256 or "", origin):
                continue
            if addressed(source.image_id, source.sha256 or "", prediction.created_at):
                continue
            view = views.get(source.image_id)
            if view is None:
                add("quality_view_missing", "high", source.image_id, origin)
            if prediction.status == "needs_review":
                add("quality_analysis_requires_review", "high", source.image_id, origin)
            if view is not None and view.evaluable is False:
                add("quality_not_evaluable", "high", source.image_id, origin)
            if view is not None and view.partial_coverage:
                add("quality_partial_coverage", "high", source.image_id, origin)
            if view is not None and view.grade == "E2":
                add("quality_possible_e2", "high", source.image_id, origin)
            if disagreement:
                add("quality_disagreement", "high", source.image_id, origin)
            # AG-055 scores are uncalibrated, including a two-view agreement.
            add("quality_proposal_unconfirmed", "normal", source.image_id, origin)

    # A started acquisition is not ready for review without an explicit flag.
    if facts.status == "processing" and not any(r.code in {
        "manual_or_uncertain_detection", "uncertain_detection", "unknown_detection_outcome",
        "uncertainty_without_image_identity", "source_hash_mismatch",
        "source_hash_unverified", "source_not_in_evaluation",
    } for r in found.values()):
        return empty()

    if facts.status == "pending_review" and not found:
        add("acquisition_pending_review" if current else "acquisition_evidence_missing",
            "normal" if current else "high", None, "evaluation-status")

    ordered = tuple(sorted(found.values(), key=lambda r: (
        0 if r.priority == "high" else 1, r.code, r.image_id or "", r.source)))
    image_ids = tuple(sorted({r.image_id for r in ordered if r.image_id is not None}))
    return SelectionResult(facts.evaluation_id, bool(ordered),
                           "high" if any(r.priority == "high" for r in ordered)
                           else "normal" if ordered else None, ordered, image_ids)
