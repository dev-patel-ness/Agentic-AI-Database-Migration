-- Additional sample objects for Phase 4 (Schema Agent) testing: exercise
-- view/function/trigger DDL translation, not just tables. Runs every
-- container start (see runUserScripts.sh) like oracle-sample-init.sql;
-- CREATE OR REPLACE is naturally idempotent for view/function/trigger.
ALTER SESSION SET CONTAINER = XEPDB1;
CONNECT sample_user/oracle_dev_password@//localhost:1521/XEPDB1

CREATE OR REPLACE VIEW active_employees AS
SELECT employee_id, first_name, last_name, department_id
FROM employees
WHERE is_active = 'Y';
/

CREATE OR REPLACE FUNCTION get_employee_count(dept_id IN NUMBER) RETURN NUMBER IS
    emp_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO emp_count FROM employees WHERE department_id = dept_id;
    RETURN emp_count;
END;
/

CREATE OR REPLACE TRIGGER trg_normalize_employee_email
BEFORE INSERT OR UPDATE ON employees
FOR EACH ROW
BEGIN
    :NEW.email := LOWER(:NEW.email);
END;
/
