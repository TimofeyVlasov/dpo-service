from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Course(Base):
    __tablename__ = "course"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(500))
    provider: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[float] = mapped_column(default=0)
    duration_h: Mapped[float | None]
    language: Mapped[str] = mapped_column(String(10), default="ru")
    rating: Mapped[float | None]
    level_label: Mapped[str | None] = mapped_column(String(30))
    direction: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="draft")

    competencies: Mapped[list["CourseCompetency"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class CourseCompetency(Base):
    __tablename__ = "course_competency"

    course_id: Mapped[int] = mapped_column(
        ForeignKey("course.id", ondelete="CASCADE"), primary_key=True
    )
    skill_code: Mapped[str] = mapped_column(String(50), primary_key=True)
    from_level: Mapped[int]
    to_level: Mapped[int]

    course: Mapped["Course"] = relationship(back_populates="competencies")

    __table_args__ = (
        CheckConstraint(
            "from_level >= 0 AND to_level <= 100 AND from_level < to_level",
            name="check_range",
        ),
    )