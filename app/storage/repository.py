import json
import logging
import sqlite3
from typing import Optional

from app.core.config import settings
from app.schemas.orchestration import EvaluationRunOutput

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS evaluation_runs (
    run_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    execution_time_ms INTEGER NOT NULL,
    baseline_reference TEXT NOT NULL,
    final_summary TEXT NOT NULL,
    full_result_json TEXT NOT NULL
);
"""


class EvaluationRunRepository:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or settings.DATABASE_PATH
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.commit()

    def save(self, result: EvaluationRunOutput) -> None:
        full_result_json = json.dumps(result.model_dump(mode="json"))
        baseline = result.baseline_reference or ""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO evaluation_runs
                    (run_id, timestamp, execution_time_ms, baseline_reference, final_summary, full_result_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.run_id,
                        result.timestamp,
                        result.execution_time_ms,
                        baseline,
                        result.final_summary,
                        full_result_json,
                    ),
                )
                conn.commit()
            logger.info("Repository: saved run_id=%s", result.run_id)
        except Exception as exc:
            logger.error("Repository: failed to save run_id=%s — %s", result.run_id, exc)
            raise

    def get(self, run_id: str) -> Optional[EvaluationRunOutput]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT full_result_json FROM evaluation_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
            if row is None:
                return None
            data = json.loads(row["full_result_json"])
            return EvaluationRunOutput.model_validate(data)
        except Exception as exc:
            logger.error("Repository: failed to get run_id=%s — %s", run_id, exc)
            raise
