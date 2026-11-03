from sqlalchemy.orm import Session

from app.models import Recommendation, RecommendationItem
from app.schemas.profile import Preferences, Profile
from app.services.course_provider import load_candidates
from app.services.dictionary_stub import DICTIONARY
from app.services.matching import compute_gaps, pick_set

WEEKS_HORIZON = 12   # на сколько недель вперёд планируем обучение
MAX_COURSES = 3 # максимум курсов в подборе


def recommend(db: Session, profile: Profile, prefs: Preferences) -> Recommendation:
    """Собирает всё вместе: профиль + справочник + курсы из базы -> подбор -> сохранение."""
    levels: dict[str, int] = {}
    targets: dict[str, int] = {}
    importance: dict[str, int] = {}
    for s in profile.skills:
        info = DICTIONARY.get(s.skill)
        if info is None:
            continue  # навыка нет в справочнике, пропускаем
        levels[s.skill] = s.level
        # цель = большая из личной и из справочника (правило ещё нужно подтвердить)
        targets[s.skill] = max(s.target, info.target)
        importance[s.skill] = info.importance

    gaps = compute_gaps(levels, targets, importance) # расчет пробелов
    candidates = load_candidates(db, profile.direction, set(gaps), prefs) # вызов прокладки: достаем из базы курсы по навыкам с пробелом, с учетом бюджета и языка
    hours_limit = prefs.hours_per_week * WEEKS_HORIZON if prefs.hours_per_week else None

    picks = pick_set(
        candidates, levels, targets, importance,
        max_courses=MAX_COURSES, hours_limit=hours_limit,
    )

    recommendation = Recommendation(
        user_id=profile.user_id,
        mode="gaps",
        direction=profile.direction,
        profile_snapshot=profile.model_dump(),
        total_contribution=sum(p.contribution for p in picks),
        items=[
            RecommendationItem(
                course_id=int(p.course.id),
                rank=i,
                label="best" if i == 1 else "extra",
                contribution=p.contribution,
                score=p.score,
                rationale=f"Закрывает около {round(p.contribution * 100)}% ваших пробелов.",
            )
            for i, p in enumerate(picks, start=1)
        ],
    )
    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)
    return recommendation