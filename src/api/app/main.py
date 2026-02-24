from fastapi import FastAPI
from .routes_jobs import router as jobs_router

app = FastAPI(
    title="Doc processing API",
    description="API de génération de documents",
    version="1.0.0")

app.include_router(jobs_router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "API fonctionne"}