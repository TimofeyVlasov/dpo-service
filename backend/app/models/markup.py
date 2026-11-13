from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MarkupSuggestion(Base):
    """Предложение нейросети по разметке курса. Живёт отдельно от самого курса,
    пока методист не примет его."""

    __tablename__ = "markup_suggestion"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("course.id", ondelete="CASCADE"), index=True
    )  # для какого курса предложение
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / accepted / rejected
    ranges: Mapped[list] = mapped_column(JSON)  # предложенные диапазоны, уже проверенные кодом
    raw_answer: Mapped[str] = mapped_column(Text, default="")  # что нейросеть ответила дословно
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )