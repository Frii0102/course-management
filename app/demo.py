from datetime import date, timedelta
from uuid import uuid4

from psycopg2 import Error

from .unit_of_work import UnitOfWork

ADMIN = 1
INSTRUCTOR = 2
STUDENT = 3


def main():
    suffix = uuid4().hex[:10]
    print("1. Створення курсу, уроку, завдання та групи в одній транзакції")
    with UnitOfWork(ADMIN) as uow:
        course = uow.courses.create("PY-" + suffix, "Основи Python", 1, "Практичний навчальний курс")
        uow.courses.assign_instructor(course, INSTRUCTOR)
        module = uow.courses.add_module(course, "Початок роботи", 1)
        lesson = uow.courses.add_lesson(module, "Змінні", "Типи даних і змінні", 45, 1)
        uow.courses.add_material(lesson, "Документація Python", "https://docs.python.org/3/", "link")
        assignment = uow.assignments.create(lesson, "Перша програма", "Вивести своє ім'я", 100)
        uow.courses.publish(course)
        cohort = uow.cohorts.create(course, "ТК-31", date.today(), date.today() + timedelta(days=60), 20)
        print(uow.courses.get(course))
        uow.commit()

    print("\n2. Зарахування, виконання уроку та надсилання роботи")
    with UnitOfWork(STUDENT) as uow:
        enrollment = uow.enrollments.create(cohort, STUDENT)
        uow.enrollments.complete_lesson(enrollment, lesson)
        submission = uow.assignments.submit(enrollment, assignment, 'print("Ілона")')
        print(uow.enrollments.get(enrollment))
        uow.commit()

    print("\n3. Відкат зміни назви: видалення курсу з активним студентом заборонене")
    try:
        with UnitOfWork(ADMIN) as uow:
            uow.courses.update(course, "Ця назва не збережеться", "Тест rollback")
            uow.courses.delete(course)
            uow.commit()
    except Error as error:
        print("База відхилила операцію:", error.diag.message_primary)
    with UnitOfWork(ADMIN) as uow:
        print("Назва після rollback:", uow.courses.get(course).title)

    print("\n4. Оцінювання та завершення навчання")
    with UnitOfWork(INSTRUCTOR) as uow:
        uow.assignments.grade(submission, 95, "Завдання виконане правильно")
        uow.enrollments.finish(enrollment)
        print(uow.enrollments.certificates(enrollment))
        uow.commit()

    print("\n5. Відгук випускниці")
    with UnitOfWork(STUDENT) as uow:
        uow.enrollments.review(enrollment, 5, "Зрозумілі приклади")
        uow.commit()

    print("\n6. Soft delete, відновлення та журнал аудиту")
    with UnitOfWork(ADMIN) as uow:
        temporary = uow.courses.create("TMP-" + suffix, "Тимчасовий курс", 1)
        uow.courses.delete(temporary)
        print("Курс прихований:", uow.courses.get(temporary) is None)
        print("Кошик:", uow.audit.recycle_bin())
        uow.courses.restore(temporary)
        print("Курс відновлений:", uow.courses.get(temporary) is not None)
        for change in uow.audit.history("courses", temporary):
            print(change["operation"], change["changed_by_name"], change["changed_at"])
        uow.commit()


if __name__ == "__main__":
    main()
