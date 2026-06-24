from app.core.logging import configure_logging
from app.core.telemetry import configure_telemetry
from app.db.session import verify_database_connection
from app.services.worker_service import WorkerService


def main() -> None:
    configure_logging()
    configure_telemetry()
    verify_database_connection()
    worker = WorkerService()
    worker.recover()
    try:
        while worker.thread and worker.thread.is_alive():
            worker.thread.join(timeout=1)
    except KeyboardInterrupt:
        worker.shutdown()


if __name__ == "__main__":
    main()
