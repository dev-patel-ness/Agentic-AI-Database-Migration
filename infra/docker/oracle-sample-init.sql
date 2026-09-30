-- Oracle sample database - sample data for source/target testing
-- Runs as sys/oracle_dev_password@//localhost:1521/XE as sysdba (see
-- runUserScripts.sh, which executes every /opt/oracle/scripts/startup/*.sql on
-- EVERY container start, not just first init). All statements below are
-- written to be safe to re-run: user/table/sequence creation swallows
-- "already exists" errors via PL/SQL exception blocks.
--
-- Sample objects live under a dedicated SAMPLE_USER schema (not SYS) so that
-- discovery queries can filter by owner='SAMPLE_USER' instead of having to
-- pick our 4 tables out of thousands of Oracle-internal SYS-owned tables.
--
-- IMPORTANT: the initial sysdba connection lands in the CDB root, where plain
-- (non-common, non "C##"-prefixed) user creation is rejected with ORA-65096.
-- Switch into the XEPDB1 pluggable database first; the sample_user then lives
-- there, reachable via service_name=XEPDB1 (not XE) on port 1521.
ALTER SESSION SET CONTAINER = XEPDB1;

BEGIN
    EXECUTE IMMEDIATE 'CREATE USER sample_user IDENTIFIED BY oracle_dev_password';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -1920 THEN RAISE; END IF; -- -1920: user already exists
END;
/

GRANT CONNECT, RESOURCE, CREATE VIEW, UNLIMITED TABLESPACE TO sample_user;

CONNECT sample_user/oracle_dev_password@//localhost:1521/XEPDB1

-- Departments table
BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE departments (
        department_id NUMBER PRIMARY KEY,
        department_name VARCHAR2(100) NOT NULL UNIQUE,
        manager_id NUMBER,
        location VARCHAR2(100),
        created_at DATE DEFAULT SYSDATE
    )';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF; -- -955: name already used by an object
END;
/

-- Employees table
BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE employees (
        employee_id NUMBER PRIMARY KEY,
        first_name VARCHAR2(100) NOT NULL,
        last_name VARCHAR2(100) NOT NULL,
        email VARCHAR2(100) UNIQUE,
        department_id NUMBER REFERENCES departments(department_id),
        salary NUMBER(10, 2),
        hire_date DATE,
        is_active CHAR(1) DEFAULT ''Y'',
        created_at DATE DEFAULT SYSDATE
    )';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

-- Add self-referencing foreign key to departments
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE departments ADD CONSTRAINT fk_departments_manager
        FOREIGN KEY (manager_id) REFERENCES employees(employee_id)';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -2275 THEN RAISE; END IF; -- -2275: constraint already exists
END;
/

-- Projects table
BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE projects (
        project_id NUMBER PRIMARY KEY,
        project_name VARCHAR2(150) NOT NULL,
        description CLOB,
        start_date DATE NOT NULL,
        end_date DATE,
        budget NUMBER(15, 2),
        department_id NUMBER NOT NULL REFERENCES departments(department_id),
        status VARCHAR2(50) DEFAULT ''ACTIVE''
    )';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

-- Project assignments (many-to-many)
BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE project_assignments (
        assignment_id NUMBER PRIMARY KEY,
        project_id NUMBER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
        employee_id NUMBER NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
        role VARCHAR2(100),
        allocation_percentage NUMBER(5, 2),
        assigned_date DATE DEFAULT TRUNC(SYSDATE),
        UNIQUE (project_id, employee_id)
    )';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

-- Sequences for auto-increment
BEGIN
    EXECUTE IMMEDIATE 'CREATE SEQUENCE departments_seq START WITH 1 INCREMENT BY 1';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/
BEGIN
    EXECUTE IMMEDIATE 'CREATE SEQUENCE employees_seq START WITH 1 INCREMENT BY 1';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/
BEGIN
    EXECUTE IMMEDIATE 'CREATE SEQUENCE projects_seq START WITH 1 INCREMENT BY 1';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/
BEGIN
    EXECUTE IMMEDIATE 'CREATE SEQUENCE assignments_seq START WITH 1 INCREMENT BY 1';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

-- Indexes
BEGIN
    EXECUTE IMMEDIATE 'CREATE INDEX idx_employees_department ON employees(department_id)';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/
BEGIN
    EXECUTE IMMEDIATE 'CREATE INDEX idx_projects_department ON projects(department_id)';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/
BEGIN
    EXECUTE IMMEDIATE 'CREATE INDEX idx_assignments_project ON project_assignments(project_id)';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/
BEGIN
    EXECUTE IMMEDIATE 'CREATE INDEX idx_assignments_employee ON project_assignments(employee_id)';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

-- Sample data (NOTE: re-runs on every container start append duplicate rows;
-- acceptable for disposable local/dev sample data, see docs/repo memory).
INSERT INTO departments (department_id, department_name, location)
VALUES (departments_seq.NEXTVAL, 'Engineering', 'Building A');
INSERT INTO departments (department_id, department_name, location)
VALUES (departments_seq.NEXTVAL, 'Sales', 'Building B');
INSERT INTO departments (department_id, department_name, location)
VALUES (departments_seq.NEXTVAL, 'Operations', 'Building C');

INSERT INTO employees (employee_id, first_name, last_name, email, department_id, salary, hire_date)
VALUES (employees_seq.NEXTVAL, 'John', 'Smith', 'john.smith@example.com', 1, 85000.00, TO_DATE('2020-01-15', 'YYYY-MM-DD'));
INSERT INTO employees (employee_id, first_name, last_name, email, department_id, salary, hire_date)
VALUES (employees_seq.NEXTVAL, 'Jane', 'Doe', 'jane.doe@example.com', 1, 90000.00, TO_DATE('2019-03-20', 'YYYY-MM-DD'));
INSERT INTO employees (employee_id, first_name, last_name, email, department_id, salary, hire_date)
VALUES (employees_seq.NEXTVAL, 'Bob', 'Johnson', 'bob.johnson@example.com', 2, 75000.00, TO_DATE('2021-06-10', 'YYYY-MM-DD'));
INSERT INTO employees (employee_id, first_name, last_name, email, department_id, salary, hire_date)
VALUES (employees_seq.NEXTVAL, 'Alice', 'Williams', 'alice.williams@example.com', 3, 80000.00, TO_DATE('2020-09-05', 'YYYY-MM-DD'));

INSERT INTO projects (project_id, project_name, description, start_date, end_date, budget, department_id, status)
VALUES (projects_seq.NEXTVAL, 'Migration Platform', 'Database migration system', TO_DATE('2024-01-01', 'YYYY-MM-DD'), TO_DATE('2024-12-31', 'YYYY-MM-DD'), 500000.00, 1, 'ACTIVE');
INSERT INTO projects (project_id, project_name, description, start_date, end_date, budget, department_id, status)
VALUES (projects_seq.NEXTVAL, 'Cloud Initiative', 'Move to cloud infrastructure', TO_DATE('2024-02-01', 'YYYY-MM-DD'), TO_DATE('2024-11-30', 'YYYY-MM-DD'), 750000.00, 3, 'ACTIVE');
INSERT INTO projects (project_id, project_name, description, start_date, end_date, budget, department_id, status)
VALUES (projects_seq.NEXTVAL, 'Analytics Dashboard', 'Business intelligence system', TO_DATE('2024-03-01', 'YYYY-MM-DD'), TO_DATE('2024-10-31', 'YYYY-MM-DD'), 200000.00, 1, 'PLANNING');

INSERT INTO project_assignments (assignment_id, project_id, employee_id, role, allocation_percentage)
VALUES (assignments_seq.NEXTVAL, 1, 1, 'Tech Lead', 80.00);
INSERT INTO project_assignments (assignment_id, project_id, employee_id, role, allocation_percentage)
VALUES (assignments_seq.NEXTVAL, 1, 2, 'Developer', 100.00);
INSERT INTO project_assignments (assignment_id, project_id, employee_id, role, allocation_percentage)
VALUES (assignments_seq.NEXTVAL, 2, 3, 'Project Manager', 50.00);
INSERT INTO project_assignments (assignment_id, project_id, employee_id, role, allocation_percentage)
VALUES (assignments_seq.NEXTVAL, 2, 4, 'Operations', 75.00);
INSERT INTO project_assignments (assignment_id, project_id, employee_id, role, allocation_percentage)
VALUES (assignments_seq.NEXTVAL, 3, 2, 'Analyst', 60.00);

COMMIT;

-- Non-table objects (Phase 4 Schema Agent: exercise view/function/trigger
-- DDL translation, not just tables) -- see oracle-sample-extra-objects.sql
-- for the standalone copy applied live to already-provisioned containers.
-- CREATE OR REPLACE is naturally idempotent, safe to re-run every start.
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
