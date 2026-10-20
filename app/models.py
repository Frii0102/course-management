from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class Course:
    id: int
    code: str
    title: str
    category_id: int
    description: str
    status: str


@dataclass
class Enrollment:
    id: int
    student_id: int
    cohort_id: int
    course_id: int
    status: str
    progress_percent: Decimal


@dataclass
class Submission:
    id: int
    enrollment_id: int
    assignment_id: int
    answer: str
    score: Optional[Decimal]
    feedback: Optional[str]
