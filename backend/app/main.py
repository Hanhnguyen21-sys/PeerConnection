from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.errors import ApiError, api_error_handler
from app.routes.users import router as users_router
from app.routes.events import router as events_router
from app.routes.shifts import router as shifts_router
from app.routes.locations import router as locations_router
from app.routes.reports import router as reports_router

app = FastAPI(title="Peer Connections API")
app.include_router(users_router)
app.include_router(events_router)
app.include_router(shifts_router)
app.include_router(locations_router)
app.include_router(reports_router)
app.add_exception_handler(ApiError, api_error_handler)

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