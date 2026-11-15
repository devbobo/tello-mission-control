import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import control, flights, sequences, status, telemetry, video
from app.services.drone_manager import DroneManager
from app.services.flight_log_service import FlightLogService
from app.services.telemetry_service import TelemetryService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Tello Web Controller backend...")
    dm = DroneManager()
    ts = TelemetryService(dm)
    flight_log_service = FlightLogService(settings.flight_log_db_path)
    await flight_log_service.start()
    dm.add_command_log_callback(flight_log_service.handle_command_log)
    ts.subscribe(flight_log_service.record_telemetry)
    app.state.drone_manager = dm
    app.state.telemetry_service = ts
    app.state.flight_log_service = flight_log_service
    await ts.start()
    logger.info("Backend ready. Mock mode: %s", settings.use_mock_drone)

    yield

    # Shutdown
    logger.info("Shutting down...")
    await ts.stop()
    await dm.shutdown()
    await flight_log_service.stop()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Tello Web Controller API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(control.router)
app.include_router(flights.router)
app.include_router(telemetry.router)
app.include_router(video.router)
app.include_router(sequences.router)
app.include_router(status.router)
