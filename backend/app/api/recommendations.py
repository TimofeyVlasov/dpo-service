# Здесь описана группа адресов по теме ПОДБОР КУРСОВ ДЛЯ ЧЕЛОВЕКА

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Recommendation
from app.schemas.recommendation import CourseOut, RecommendationOut, RecommendationRequest
from app.services.profile_stub import ProfileNotFound, get_profile
from app.services.recommender import recommend

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def to_out(rec: Recommendation) -> RecommendationOut:
    return RecommendationOut(
        recommendation_id=rec.id,
        user_id=rec.user_id,
        mode=rec.mode,
        created_at=rec.created_at,
        total_contribution=rec.total_contribution,
        courses=[
            CourseOut(
                rank=item.rank,
                label=item.label,
                course_id=item.course_id,
                title=item.course.title,
                url=item.course.url,
                provider=item.course.provider,
                price=item.course.price,
                duration_h=item.course.duration_h,
                contribution=item.contribution,
                score=item.score,
                rationale=item.rationale,
            )
            for item in rec.items
        ],
    )


@router.post("", response_model=RecommendationOut)
def create_recommendation(body: RecommendationRequest, db: Session = Depends(get_db)):
    """Подбирает курсы для человека и сохраняет рекомендацию."""
    try:
        profile = get_profile(body.user_id)
    except ProfileNotFound:
        raise HTTPException(status_code=404, detail="Профиль не найден")
    return to_out(recommend(db, profile, body.preferences))