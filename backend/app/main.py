from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .routers import (auth, master, investor, rollover, settlement, mam, copy, saga,
                       allocation, latency, outbox_router, adapters, public)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="PAMM Platform M4", version="0.4.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

@app.get("/health")
def health(): return {"status": "ok", "env": settings.environment, "version": "0.4.0"}

@app.get("/ready")
def ready(): return {"status": "ready"}

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(master.router, prefix="/api", tags=["master"])
app.include_router(investor.router, prefix="/api", tags=["investor"])
app.include_router(rollover.router, prefix="/api", tags=["rollover"])
app.include_router(settlement.router, prefix="/api", tags=["settlement"])
app.include_router(mam.router, prefix="/api", tags=["mam"])
app.include_router(copy.router, prefix="/api", tags=["copy"])
app.include_router(saga.router, prefix="/api", tags=["saga"])
app.include_router(allocation.router, prefix="/api", tags=["allocation"])
app.include_router(latency.router, prefix="/api", tags=["latency"])
app.include_router(outbox_router.router, prefix="/api", tags=["outbox"])
app.include_router(adapters.router, prefix="/api", tags=["adapters"])
app.include_router(public.router, prefix="/api/public", tags=["public"])

