from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import PlaybookUpdateProposal
from app.schemas import PlaybookProposalApplyRequest
from app.schemas import PlaybookProposalApplyResponse
from app.schemas import PlaybookProposalDecisionRequest
from app.schemas import PlaybookProposalPublishRequest
from app.schemas import PlaybookProposalPublishResponse
from app.schemas import PlaybookUpdateProposalRead
from app.services.playbook_updates import PlaybookUpdateError
from app.services.playbook_updates import PlaybookUpdateProposalService

router = APIRouter(tags=["playbook-updates"])


@router.get("/playbook-update-proposals", response_model=list[PlaybookUpdateProposalRead])
def list_playbook_update_proposals(
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[PlaybookUpdateProposal]:
    query = select(PlaybookUpdateProposal)
    if status:
        query = query.where(PlaybookUpdateProposal.status == status)
    return list(
        db.scalars(query.order_by(PlaybookUpdateProposal.created_at.desc(), PlaybookUpdateProposal.id.desc()).limit(limit)).all()
    )


@router.post(
    "/playbook-update-proposals/from-post-trade-review/{review_id}",
    response_model=PlaybookUpdateProposalRead,
    status_code=201,
)
def create_playbook_update_proposal_from_review(
    review_id: str,
    db: Session = Depends(get_db),
) -> PlaybookUpdateProposal:
    service = PlaybookUpdateProposalService(db)
    try:
        return service.propose_from_post_trade_review(review_id)
    except PlaybookUpdateError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc


@router.post("/playbook-update-proposals/{proposal_id}/approve", response_model=PlaybookUpdateProposalRead)
def approve_playbook_update_proposal(
    proposal_id: str,
    payload: PlaybookProposalDecisionRequest,
    db: Session = Depends(get_db),
) -> PlaybookUpdateProposal:
    service = PlaybookUpdateProposalService(db)
    try:
        return service.approve(proposal_id, reviewer_id=payload.reviewer_id, decision_reason=payload.decision_reason)
    except PlaybookUpdateError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc


@router.post("/playbook-update-proposals/{proposal_id}/reject", response_model=PlaybookUpdateProposalRead)
def reject_playbook_update_proposal(
    proposal_id: str,
    payload: PlaybookProposalDecisionRequest,
    db: Session = Depends(get_db),
) -> PlaybookUpdateProposal:
    service = PlaybookUpdateProposalService(db)
    try:
        return service.reject(proposal_id, reviewer_id=payload.reviewer_id, decision_reason=payload.decision_reason)
    except PlaybookUpdateError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc


@router.post("/playbook-update-proposals/{proposal_id}/preview-manual-apply", response_model=PlaybookProposalApplyResponse)
def preview_manual_apply_playbook_update_proposal(
    proposal_id: str,
    payload: PlaybookProposalApplyRequest,
    db: Session = Depends(get_db),
) -> PlaybookProposalApplyResponse:
    service = PlaybookUpdateProposalService(db)
    try:
        proposal, playbook, patch_json = service.preview_manual_apply(
            proposal_id,
            target_strategy_playbook_id=payload.target_strategy_playbook_id,
            edited_rule_json=payload.edited_rule_json,
        )
    except PlaybookUpdateError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc
    return PlaybookProposalApplyResponse(proposal=proposal, playbook=playbook, patch_json=patch_json, auto_applied=False)


@router.post("/playbook-update-proposals/{proposal_id}/apply-manually", response_model=PlaybookProposalApplyResponse)
def apply_manually_playbook_update_proposal(
    proposal_id: str,
    payload: PlaybookProposalApplyRequest,
    db: Session = Depends(get_db),
) -> PlaybookProposalApplyResponse:
    service = PlaybookUpdateProposalService(db)
    try:
        proposal, playbook, patch_json = service.apply_manually(
            proposal_id,
            reviewer_id=payload.reviewer_id,
            decision_reason=payload.decision_reason,
            target_strategy_playbook_id=payload.target_strategy_playbook_id,
            edited_rule_json=payload.edited_rule_json,
        )
    except PlaybookUpdateError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc
    return PlaybookProposalApplyResponse(proposal=proposal, playbook=playbook, patch_json=patch_json, auto_applied=False)


@router.post("/playbook-update-proposals/{proposal_id}/publish-version", response_model=PlaybookProposalPublishResponse)
def publish_playbook_update_proposal_as_new_version(
    proposal_id: str,
    payload: PlaybookProposalPublishRequest,
    db: Session = Depends(get_db),
) -> PlaybookProposalPublishResponse:
    service = PlaybookUpdateProposalService(db)
    try:
        proposal, previous_playbook, published_playbook, publish_metadata = service.publish_as_new_version(
            proposal_id,
            reviewer_id=payload.reviewer_id,
            decision_reason=payload.decision_reason,
            publish_note=payload.publish_note,
        )
    except PlaybookUpdateError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc
    return PlaybookProposalPublishResponse(
        proposal=proposal,
        previous_playbook=previous_playbook,
        published_playbook=published_playbook,
        publish_metadata=publish_metadata,
    )
