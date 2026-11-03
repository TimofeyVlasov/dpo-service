from datetime import datetime

from pydantic import BaseModel

from app.schemas.profile import Preferences

class RecommendationRequest(BaseModel): # Запрос на подбор
    user_id: str # что за человек
    preferences: Preferences = Preferences() # какие у него пожелания

class CourseOut(BaseModel): # Один курс в ответе. То, что нужно показать в карточке
    rank: int # место курса в подборе
    label: str # метка best для первого, extra для остальных
    course_id: int # номер курса в каталоге
    title: str # название
    url: str # ссылка на курс
    provider: str # платформа
    price: float # цена 
    duration_h: float | None # длительность в часах
    contribution: float # какую долю пробелов закрывает курс
    score: float # балл релевантности
    rationale: str # объяснение, почему этот курс

class RecommendationOut(BaseModel): # Весь ответ, общие данные подбора
    recommendation_id: int # номер подбора в базе
    user_id: str # для кого сделан подбор
    mode: str # режим подбора (закрыть пробелы или расти дальше)
    created_at: datetime # когда подбор создан
    total_contribution: float # общий вклад набора в закрытие пробелов, сумма вкладов курсов
    courses: list[CourseOut] # список курсов подбора