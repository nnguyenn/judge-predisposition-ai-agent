from fastapi import FastAPI
from app.db import Base, engine
from app.api.routes import router

app = FastAPI(title="Habeas 1225/1226 Judge Pattern Tracker", version="0.1.0")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


app.include_router(router, prefix="/api")