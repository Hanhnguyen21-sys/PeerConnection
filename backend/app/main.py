from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.users import router as users_router
from app.routes.events import router as events_router

app = FastAPI(title="Peer Connections API")
app.include_router(users_router)
app.include_router(events_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}