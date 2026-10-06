from fastapi import FastAPI

from app.api import router as caсhe_router
from app.database import Base, engine

app = FastAPI()

app.include_router(caсhe_router, tags=["caсhe"])

Base.metadata.create_all(bind=engine)
