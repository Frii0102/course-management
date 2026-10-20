\set ON_ERROR_STOP on
-- Необов'язковий крок. Виконується адміністратором PostgreSQL.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'course_app') THEN
        CREATE ROLE course_app NOLOGIN;
    END IF;
END;
$$;
GRANT USAGE ON SCHEMA lms TO course_app;
GRANT EXECUTE ON ALL PROCEDURES IN SCHEMA lms TO course_app;
-- Єдина функція, яку викликає view під правами поточного користувача.
GRANT EXECUTE ON FUNCTION lms.progress_percent(bigint) TO course_app;
ALTER FUNCTION lms.progress_percent(bigint) SECURITY DEFINER;
DO $$
DECLARE item record;
BEGIN
    FOR item IN SELECT viewname FROM pg_views WHERE schemaname = 'lms' LOOP
        EXECUTE format('GRANT SELECT ON lms.%I TO course_app', item.viewname);
    END LOOP;
END;
$$;
-- Наприклад: GRANT course_app TO your_backend_login;
-- На базові таблиці й послідовності ця роль прав не отримує.
