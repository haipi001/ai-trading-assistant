from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import MonthlyDecisionReview
from app.schemas import MonthlyDecisionReviewRead
from app.schemas import MonthlyReviewGenerateRequest
from app.schemas import MonthlyReviewGenerateResponse
from app.services.monthly_reviews import MonthlyDecisionReviewService

router = APIRouter(prefix="/reviews/monthly", tags=["monthly-reviews"])


@router.post("/generate", response_model=MonthlyReviewGenerateResponse, status_code=201)
def generate_monthly_decision_review(
    payload: MonthlyReviewGenerateRequest,
    db: Session = Depends(get_db),
) -> MonthlyReviewGenerateResponse:
    result = MonthlyDecisionReviewService(db).generate(
        user_id=payload.user_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    return MonthlyReviewGenerateResponse(
        review=result.review,
        metrics=result.metrics,
        behavior_summary=result.behavior_summary,
        decision_quality_summary=result.decision_quality_summary,
        recommended_constitution_updates=result.recommended_constitution_updates,
        recommended_playbook_updates=result.recommended_playbook_updates,
        most_common_behavior_pattern=result.most_common_behavior_pattern,
        biggest_prevented_loss=result.biggest_prevented_loss,
        automatic_rule_updates_applied=result.automatic_rule_updates_applied,
    )


@router.get("", response_model=list[MonthlyDecisionReviewRead])
def list_generated_monthly_reviews(
    user_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[MonthlyDecisionReview]:
    query = select(MonthlyDecisionReview).order_by(MonthlyDecisionReview.period_start.desc()).limit(limit)
    if user_id:
        query = (
            select(MonthlyDecisionReview)
            .where(MonthlyDecisionReview.user_id == user_id)
            .order_by(MonthlyDecisionReview.period_start.desc())
            .limit(limit)
        )
    return list(db.scalars(query).all())


@router.get("/quarterly-trend")
def get_quarterly_review_trend(
    user_id: str = "default-user",
    months: int = 3,
    db: Session = Depends(get_db),
) -> dict:
    return MonthlyDecisionReviewService(db).quarterly_trend(user_id=user_id, months=months)


@router.get("/{review_id}", response_model=MonthlyDecisionReviewRead)
def get_generated_monthly_review(review_id: str, db: Session = Depends(get_db)) -> MonthlyDecisionReview:
    review = db.get(MonthlyDecisionReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Monthly decision review not found.")
    return review
