from fastapi import FastAPI

from app.api import admin_courses, recommendations

app = FastAPI(title="DPO service")
app.include_router(admin_courses.router)
app.include_router(recommendations.router)


@app.get("/health")
def health():
    return {"status": "ok"}