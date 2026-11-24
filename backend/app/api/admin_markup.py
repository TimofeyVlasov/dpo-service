# Группа адресов: разметка курсов нейросетью

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.markup import AcceptIn, SuggestionOut
from app.services import catalog, dictionary_client, markup
from app.services.llm import LLMUnavailable

router = APIRouter(prefix="/admin", tags=["admin: markup"])


@router.post(
    "/courses/{course_id}/suggest-markup", response_model=SuggestionOut, status_code=201
)
def suggest_markup(course_id: int, db: Session = Depends(get_db)):
    """Нейросеть предлагает разметку курса. В курс она не попадает до решения методиста."""
    return _run(lambda: markup.to_out(markup.suggest(db, course_id)))


@router.get("/courses/{course_id}/suggestions", response_model=list[SuggestionOut])
def list_suggestions(course_id: int, db: Session = Depends(get_db)):
    """Все предложения по курсу, новые сверху."""
    return _run(lambda: [markup.to_out(s) for s in markup.list_suggestions(db, course_id)])


@router.post("/suggestions/{suggestion_id}/accept", response_model=SuggestionOut)
def accept_suggestion(
    suggestion_id: int, body: AcceptIn | None = None, db: Session = Depends(get_db)
):
    """Принять: разметка записывается в курс. В теле можно прислать свои ranges."""
    ranges = body.ranges if body else None
    return _run(lambda: markup.to_out(markup.accept(db, suggestion_id, ranges)))


@router.post("/suggestions/{suggestion_id}/reject", response_model=SuggestionOut)
def reject_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    """Отклонить предложение. Курс не меняется."""
    return _run(lambda: markup.to_out(markup.reject(db, suggestion_id)))


def _run(action):
    """Переводит ошибки сервиса в понятные ответы API."""
    try:
        return action()
    except catalog.CourseNotFound:
        raise HTTPException(status_code=404, detail="курс не найден")
    except catalog.CatalogRuleError as error:
        raise HTTPException(status_code=409, detail=str(error))
    except dictionary_client.DictionaryUnavailable:
        raise HTTPException(status_code=503, detail="Справочник компетенций недоступен")
    except dictionary_client.InvalidDictionaryResponse:
        raise HTTPException(
            status_code=502,
            detail="Сервис аккредитации вернул некорректный справочник",
        )
    except markup.SuggestionNotFound:
        raise HTTPException(status_code=404, detail="предложение не найдено")
    except markup.SuggestionStateError as error:
        raise HTTPException(status_code=409, detail=str(error))
    except markup.BadAnswer as error:
        raise HTTPException(
            status_code=502, detail=f"нейросеть дала непригодный ответ: {error}"
        )
    except LLMUnavailable:
        raise HTTPException(
            status_code=503, detail="нейросеть сейчас недоступна, попробуйте позже"
        )