-- Additional sample objects for Phase 4 (Schema Agent) testing: exercise
-- view/function/trigger DDL translation, not just tables.

CREATE OR REPLACE VIEW sample.active_employees AS
SELECT employee_id, first_name, last_name, department_id
FROM sample.employees
WHERE is_active = TRUE;

CREATE OR REPLACE FUNCTION sample.get_employee_count(dept_id INTEGER)
RETURNS INTEGER AS $$
DECLARE
    emp_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO emp_count FROM sample.employees WHERE department_id = dept_id;
    RETURN emp_count;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sample.normalize_employee_email()
RETURNS TRIGGER AS $$
BEGIN
    NEW.email := LOWER(NEW.email);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_normalize_employee_email ON sample.employees;
CREATE TRIGGER trg_normalize_employee_email
BEFORE INSERT OR UPDATE ON sample.employees
FOR EACH ROW EXECUTE FUNCTION sample.normalize_employee_email();
