from fastapi import FastAPI

app = FastAPI(title="DPO service")


@app.get("/health")
def health():
    return {"status": "ok"}