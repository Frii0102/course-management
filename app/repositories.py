from dataclasses import fields

from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from .models import Course, Enrollment, Submission


def to_model(model, row):
    if row is None:
        return None
    return model(**{field.name: row[field.name] for field in fields(model)})


class BaseRepository:
    def __init__(self, connection):
        self.connection = connection

    def _read(self, view, **filters):
        query = sql.SQL("SELECT * FROM lms.{}").format(sql.Identifier(view))
        if filters:
            conditions = [sql.SQL("{} = %s").format(sql.Identifier(key)) for key in filters]
            query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions)
        query += sql.SQL(" ORDER BY 1")
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, list(filters.values()))
            return [dict(row) for row in cursor.fetchall()]

    def _call(self, procedure, args=(), returns_id=False):
        values = list(args)
        if returns_id:
            values.append(None)
        query = sql.SQL("CALL lms.{}({})").format(
            sql.Identifier(procedure),
            sql.SQL(", ").join(sql.Placeholder() for _ in values),
        )
        with self.connection.cursor() as cursor:
            cursor.execute(query, values)
            if returns_id:
                return cursor.fetchone()[0]


class UserRepository(BaseRepository):
    def list(self):
        return self._read("v_users")

    def create(self, email, name, role, detail=""):
        return self._call("sp_create_user", (email, name, role, detail), returns_id=True)

    def delete(self, user_id):
        self._call("sp_set_deleted", ("users", user_id, True))

    def restore(self, user_id):
        self._call("sp_set_deleted", ("users", user_id, False))


class CategoryRepository(BaseRepository):
    def list(self):
        return self._read("v_categories")

    def create(self, name):
        return self._call("sp_create_category", (name,), returns_id=True)

    def delete(self, category_id):
        self._call("sp_set_deleted", ("categories", category_id, True))

    def restore(self, category_id):
        self._call("sp_set_deleted", ("categories", category_id, False))


class CourseRepository(BaseRepository):
    def list(self):
        return [to_model(Course, row) for row in self._read("v_courses")]

    def get(self, course_id):
        rows = self._read("v_courses", id=course_id)
        return to_model(Course, rows[0]) if rows else None

    def create(self, code, title, category_id, description=""):
        return self._call("sp_create_course", (code, title, category_id, description), returns_id=True)

    def update(self, course_id, title, description):
        self._call("sp_update_course", (course_id, title, description))

    def assign_instructor(self, course_id, instructor_id):
        self._call("sp_assign_instructor", (course_id, instructor_id))

    def add_prerequisite(self, course_id, prerequisite_id):
        self._call("sp_add_prerequisite", (course_id, prerequisite_id))

    def add_module(self, course_id, title, position):
        return self._call("sp_add_module", (course_id, title, position), returns_id=True)

    def add_lesson(self, module_id, title, content, minutes, position):
        return self._call("sp_add_lesson", (module_id, title, content, minutes, position), returns_id=True)

    def add_material(self, lesson_id, title, url, kind):
        self._call("sp_add_material", (lesson_id, title, url, kind))

    def structure(self, course_id):
        return self._read("v_course_structure", course_id=course_id)

    def publish(self, course_id):
        self._call("sp_publish_course", (course_id,))

    def delete(self, course_id):
        self._call("sp_set_deleted", ("courses", course_id, True))

    def restore(self, course_id):
        self._call("sp_set_deleted", ("courses", course_id, False))

    def search(self, text):
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM lms.v_courses "
                "WHERE to_tsvector('simple', title || ' ' || description) "
                "@@ plainto_tsquery('simple', %s) ORDER BY id", (text,),
            )
            return [to_model(Course, row) for row in cursor.fetchall()]


class CohortRepository(BaseRepository):
    def create(self, course_id, name, starts_on, ends_on, capacity):
        return self._call("sp_create_cohort", (course_id, name, starts_on, ends_on, capacity), returns_id=True)

    def list(self, course_id):
        return self._read("v_cohorts", course_id=course_id)


class EnrollmentRepository(BaseRepository):
    def create(self, cohort_id, student_id):
        return self._call("sp_enroll", (cohort_id, student_id), returns_id=True)

    def get(self, enrollment_id):
        rows = self._read("v_enrollments", id=enrollment_id)
        return to_model(Enrollment, rows[0]) if rows else None

    def cancel(self, enrollment_id):
        self._call("sp_cancel_enrollment", (enrollment_id,))

    def complete_lesson(self, enrollment_id, lesson_id):
        self._call("sp_complete_lesson", (enrollment_id, lesson_id))

    def finish(self, enrollment_id):
        self._call("sp_finish_enrollment", (enrollment_id,))

    def review(self, enrollment_id, rating, comment):
        self._call("sp_review", (enrollment_id, rating, comment))

    def certificates(self, enrollment_id):
        return self._read("v_certificates", enrollment_id=enrollment_id)


class AssignmentRepository(BaseRepository):
    def create(self, lesson_id, title, description, max_score):
        return self._call("sp_add_assignment", (lesson_id, title, description, max_score), returns_id=True)

    def list(self, course_id):
        return self._read("v_assignments", course_id=course_id)

    def delete(self, assignment_id):
        self._call("sp_set_deleted", ("assignments", assignment_id, True))

    def restore(self, assignment_id):
        self._call("sp_set_deleted", ("assignments", assignment_id, False))

    def submit(self, enrollment_id, assignment_id, answer):
        return self._call("sp_submit", (enrollment_id, assignment_id, answer), returns_id=True)

    def grade(self, submission_id, score, feedback):
        self._call("sp_grade", (submission_id, score, feedback))

    def submissions(self, enrollment_id):
        return [to_model(Submission, row) for row in self._read("v_submissions", enrollment_id=enrollment_id)]


class AuditRepository(BaseRepository):
    def history(self, entity, record_id):
        return self._read("v_change_history", table_name=entity, record_id=record_id)

    def recycle_bin(self):
        return self._read("v_recycle_bin")
