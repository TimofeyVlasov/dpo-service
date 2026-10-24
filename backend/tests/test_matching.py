from pytest import approx

from app.services.matching import (
    CourseData,
    Range,
    closable_share,
    compute_gaps,
    coverage,
    is_too_hard,
    pick_set,
    relevance,
)

# Тестовый пример человека с пробелами
LEVELS = {"PYTHON": 30, "SQL": 20, "ASYNC": 25, "DOCKER": 10, "GIT": 65}
TARGETS = {"PYTHON": 70, "SQL": 70, "ASYNC": 60, "DOCKER": 60, "GIT": 60}
IMPORTANCE = {"PYTHON": 3, "SQL": 3, "ASYNC": 2, "DOCKER": 2, "GIT": 1}


def make_courses() -> dict[str, CourseData]:
    return {
        "A": CourseData("A", [Range("PYTHON", 0, 60), Range("SQL", 0, 40)], 0, 4.7, 40),
        "B": CourseData("B", [Range("SQL", 0, 50)], 0, 4.8, 20),
        "C": CourseData("C", [Range("ASYNC", 20, 60)], 4500, 4.5, 30),
        "D": CourseData("D", [Range("DOCKER", 0, 60)], 0, 4.6, 25),
        "E": CourseData("E", [Range("PYTHON", 0, 70)], 0, 4.4, 35),
        "F": CourseData("F", [Range("SQL", 40, 80)], 3000, 4.9, 30),
    }


def test_gaps_and_urgency():
    gaps = compute_gaps(LEVELS, TARGETS, IMPORTANCE)
    assert "GIT" not in gaps                      # уровень выше цели, пробела нет
    assert gaps["SQL"].gap == 50
    assert gaps["PYTHON"].urgency == approx(0.2727, abs=1e-3)
    assert gaps["SQL"].urgency == approx(0.3409, abs=1e-3)
    assert gaps["ASYNC"].urgency == approx(0.1591, abs=1e-3)
    assert gaps["DOCKER"].urgency == approx(0.2273, abs=1e-3)
    assert sum(g.urgency for g in gaps.values()) == approx(1.0)


def test_closable_share():
    assert closable_share(25, 70, 0, 50) == approx(25 / 45)
    assert closable_share(20, 70, 0, 40) == approx(0.4)
    assert closable_share(80, 70, 0, 50) == 0     # пробела нет


def test_coverage_round_one():
    gaps = compute_gaps(LEVELS, TARGETS, IMPORTANCE)
    c = make_courses()
    assert coverage(c["A"], gaps) == approx(0.3409, abs=1e-3)
    assert coverage(c["E"], gaps) == approx(0.2727, abs=1e-3)
    assert coverage(c["D"], gaps) == approx(0.2273, abs=1e-3)
    assert coverage(c["B"], gaps) == approx(0.2045, abs=1e-3)
    assert coverage(c["C"], gaps) == approx(0.1591, abs=1e-3)


def test_too_hard_course_is_penalized():
    gaps = compute_gaps(LEVELS, TARGETS, IMPORTANCE)
    c = make_courses()
    assert is_too_hard(c["F"], gaps)              # SQL 20 < 40 - 10
    assert not is_too_hard(c["A"], gaps)
    assert relevance(c["F"], gaps) == approx(6.9, abs=0.1)


def test_relevance_round_one():
    gaps = compute_gaps(LEVELS, TARGETS, IMPORTANCE)
    c = make_courses()
    assert relevance(c["A"], gaps) == approx(56.6, abs=0.1)
    assert relevance(c["E"], gaps) == approx(51.5, abs=0.1)
    assert relevance(c["D"], gaps) == approx(49.0, abs=0.1)
    assert relevance(c["B"], gaps) == approx(47.9, abs=0.1)
    assert relevance(c["C"], gaps) == approx(34.3, abs=0.1)


def test_greedy_set_for_example():
    picks = pick_set(
        list(make_courses().values()), LEVELS, TARGETS, IMPORTANCE,
        max_courses=3, hours_limit=96,
    )
    assert [p.course.id for p in picks] == ["A", "D", "F"]
    assert picks[0].score == approx(56.6, abs=0.1)
    assert picks[1].score == approx(56.6, abs=0.1)
    assert picks[2].score == approx(55.6, abs=0.1)


def test_contributions_relative_to_original_gaps():
    picks = pick_set(
        list(make_courses().values()), LEVELS, TARGETS, IMPORTANCE,
        max_courses=3, hours_limit=96,
    )
    assert picks[0].contribution == approx(0.341, abs=1e-3)
    assert picks[1].contribution == approx(0.227, abs=1e-3)
    assert picks[2].contribution == approx(0.205, abs=1e-3)
    assert sum(p.contribution for p in picks) == approx(0.773, abs=1e-3)


def test_hours_limit_stops_selection():
    picks = pick_set(
        list(make_courses().values()), LEVELS, TARGETS, IMPORTANCE,
        max_courses=3, hours_limit=72,
    )
    assert [p.course.id for p in picks] == ["A", "D"]   # третий курс уже не помещается