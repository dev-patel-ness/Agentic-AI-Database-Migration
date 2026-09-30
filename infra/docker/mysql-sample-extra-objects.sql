-- Additional sample objects for Phase 4 (Schema Agent) testing: exercise
-- view/function/trigger DDL translation, not just tables.
USE sample_source;

CREATE OR REPLACE VIEW active_employees AS
SELECT employee_id, first_name, last_name, department_id
FROM employees
WHERE is_active = TRUE;

DROP FUNCTION IF EXISTS get_employee_count;
DELIMITER //
CREATE FUNCTION get_employee_count(dept_id INT) RETURNS INT
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE emp_count INT;
    SELECT COUNT(*) INTO emp_count FROM employees WHERE department_id = dept_id;
    RETURN emp_count;
END//
DELIMITER ;

DROP TRIGGER IF EXISTS trg_normalize_employee_email;
DELIMITER //
CREATE TRIGGER trg_normalize_employee_email
BEFORE INSERT ON employees
FOR EACH ROW
BEGIN
    SET NEW.email = LOWER(NEW.email);
END//
DELIMITER ;
