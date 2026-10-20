import os
import json
from pathlib import Path

import psycopg2

from .repositories import (
    AssignmentRepository, AuditRepository, CategoryRepository, CohortRepository,
    CourseRepository, EnrollmentRepository, UserRepository,
)


class UnitOfWork:
    """One connection and one transaction for all repositories."""

    def __init__(self, user_id, dsn=None):
        self.user_id = user_id
        self.dsn = dsn or os.getenv("LMS_DSN")
        local_config = Path(__file__).resolve().parents[1] / ".local_postgres" / "connection.json"
        if not self.dsn and local_config.exists():
            self.dsn = psycopg2.extensions.make_dsn(**json.loads(local_config.read_text()))
        if not self.dsn:
            self.dsn = "dbname=course_management host=localhost"
        self.connection = None

    def __enter__(self):
        self.connection = psycopg2.connect(self.dsn)
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("CALL lms.sp_set_actor(%s)", (self.user_id,))
            self.users = UserRepository(self.connection)
            self.categories = CategoryRepository(self.connection)
            self.courses = CourseRepository(self.connection)
            self.cohorts = CohortRepository(self.connection)
            self.enrollments = EnrollmentRepository(self.connection)
            self.assignments = AssignmentRepository(self.connection)
            self.audit = AuditRepository(self.connection)
        except Exception:
            self.connection.close()
            raise
        return self

    def commit(self):
        # Після commit цей Unit of Work завершений; для нових операцій потрібен новий with.
        self.connection.commit()
        self.connection.close()

    def __exit__(self, exc_type, exc, traceback):
        if self.connection is not None and not self.connection.closed:
            try:
                self.connection.rollback()
            finally:
                self.connection.close()
