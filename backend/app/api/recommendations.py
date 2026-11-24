# Здесь описана группа адресов по теме ПОДБОР КУРСОВ ДЛЯ ЧЕЛОВЕКА

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Recommendation
from app.schemas.recommendation import CourseOut, RecommendationOut, RecommendationRequest
from app.services import dictionary_client, profile_client
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
    """Получает профиль, подбирает курсы и сохраняет рекомендацию."""
    try:
        profile = profile_client.get_profile(body.user_id)
    except profile_client.ProfileNotFound:
        raise HTTPException(status_code=404, detail="Профиль не найден")
    except profile_client.ProfileUnavailable:
        raise HTTPException(status_code=503, detail="Сервис аккредитации недоступен")
    except profile_client.InvalidProfileResponse:
        raise HTTPException(
            status_code=502,
            detail="Сервис аккредитации вернул некорректный профиль",
        )

    try:
        recommendation = recommend(db, profile, body.preferences)
    except dictionary_client.DictionaryUnavailable:
        raise HTTPException(status_code=503, detail="Справочник компетенций недоступен")
    except dictionary_client.InvalidDictionaryResponse:
        raise HTTPException(
            status_code=502,
            detail="Сервис аккредитации вернул некорректный справочник",
        )

    return to_out(recommendation)