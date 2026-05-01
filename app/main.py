import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("LLM Evaluation Agent starting up")
    yield


app = FastAPI(
    title="LLM Evaluation and Experimentation Agent",
    description=(
        "A production-credible MVP backend that evaluates LLM-generated outputs "
        "across multiple quality dimensions and recommends experiments to improve reliability."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)
