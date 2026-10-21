import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Course, CourseCompetency


def make_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def new_course():
    return Course(
        external_id="stepik-1",
        title="SQL с нуля",
        url="https://example.com/sql",
        provider="Stepik",
    )


def test_course_with_range_is_saved():
    with make_session() as session:
        course = new_course()
        course.competencies.append(
            CourseCompetency(skill_code="SQL", from_level=0, to_level=50)
        )
        session.add(course)
        session.commit()
        assert session.query(CourseCompetency).count() == 1
        assert course.status == "draft"


def test_wrong_range_is_rejected():
    with make_session() as session:
        course = new_course()
        course.competencies.append(
            CourseCompetency(skill_code="SQL", from_level=60, to_level=40)
        )
        session.add(course)
        with pytest.raises(IntegrityError):
            session.commit()