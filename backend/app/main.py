# Сборка приложения и подключение групп адресов

from fastapi import FastAPI

from app.api import admin_courses

app = FastAPI(title="DPO service")
app.include_router(admin_courses.router)


@app.get("/health")
def health():
    return {"status": "ok"}