from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.course import Course

class Recommendation(Base):
    """Один подбор курсов для одного человека"""

    __tablename__ = "recommendation"

    id: Mapped[int] = mapped_column(primary_key=True) # номер подбора
    user_id: Mapped[str] = mapped_column(String(64), index=True) # чей это подбор
    mode: Mapped[str] = mapped_column(String(20)) #режим подбора (закрыть пробелы или расти дальше)
    direction: Mapped[str] = mapped_column(String(50)) # направление
    profile_snapshot: Mapped[dict] = mapped_column(JSON) # снимок профиля на момент подбора
    total_contribution: Mapped[float] = mapped_column(default=0) # общий вклад набора курсов (например 0.773, то есть 77.3% пробелов закрыто)
    created_at: Mapped[datetime] = mapped_column( 
        DateTime(timezone=True), server_default=func.now() # когда создан подбор
    )

    items: Mapped[list["RecommendationItem"]] = relationship(
        back_populates="recommendation",
        cascade="all,delete-orphan",
        order_by="RecommendationItem.rank",
    )

class RecommendationItem(Base):
    """Один курс внутри подбора"""

    __tablename__ = "recommendation_item"

    id: Mapped[int] = mapped_column(primary_key=True) # собственный номер строки
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendation.id", ondelete="CASCADE") # к какому подбору относится строка
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id")) # какой курс из каталога
    rank: Mapped[int] # место в подборе (1, 2 или 3)
    label: Mapped[str] = mapped_column(String(20)) # метка best для первого и extra для остальных
    contribution: Mapped[float] # какую долю пробелов закрывает курс (вклад курса)
    score: Mapped[float] # балл релевантности
    rationale: Mapped[str] = mapped_column(Text, default="") # здесь лежит пояснение от ИИ, почему этот курс
    
    recommendation: Mapped["Recommendation"] = relationship(back_populates="items")
    course: Mapped["Course"] = relationship()