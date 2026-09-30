-- PostgreSQL sample database - sample data for source/target testing

-- Create sample schema
CREATE SCHEMA IF NOT EXISTS sample;

-- Employees table
CREATE TABLE sample.employees (
    employee_id SERIAL PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE,
    department_id INTEGER,
    salary NUMERIC(10, 2),
    hire_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Departments table
CREATE TABLE sample.departments (
    department_id SERIAL PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL UNIQUE,
    manager_id INTEGER REFERENCES sample.employees(employee_id),
    location VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Projects table
CREATE TABLE sample.projects (
    project_id SERIAL PRIMARY KEY,
    project_name VARCHAR(150) NOT NULL,
    description TEXT,
    start_date DATE NOT NULL,
    end_date DATE,
    budget NUMERIC(15, 2),
    department_id INTEGER REFERENCES sample.departments(department_id),
    status VARCHAR(50) DEFAULT 'ACTIVE'
);

-- Project assignments (many-to-many)
CREATE TABLE sample.project_assignments (
    assignment_id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES sample.projects(project_id) ON DELETE CASCADE,
    employee_id INTEGER NOT NULL REFERENCES sample.employees(employee_id) ON DELETE CASCADE,
    role VARCHAR(100),
    allocation_percentage NUMERIC(5, 2),
    assigned_date DATE DEFAULT CURRENT_DATE,
    UNIQUE(project_id, employee_id)
);

-- Create indexes
CREATE INDEX idx_employees_department ON sample.employees(department_id);
CREATE INDEX idx_employees_email ON sample.employees(email);
CREATE INDEX idx_projects_department ON sample.projects(department_id);
CREATE INDEX idx_assignments_project ON sample.project_assignments(project_id);
CREATE INDEX idx_assignments_employee ON sample.project_assignments(employee_id);

-- Sample data
INSERT INTO sample.departments (department_name, location) VALUES
    ('Engineering', 'Building A'),
    ('Sales', 'Building B'),
    ('Operations', 'Building C');

INSERT INTO sample.employees (first_name, last_name, email, department_id, salary, hire_date) VALUES
    ('John', 'Smith', 'john.smith@example.com', 1, 85000.00, '2020-01-15'),
    ('Jane', 'Doe', 'jane.doe@example.com', 1, 90000.00, '2019-03-20'),
    ('Bob', 'Johnson', 'bob.johnson@example.com', 2, 75000.00, '2021-06-10'),
    ('Alice', 'Williams', 'alice.williams@example.com', 3, 80000.00, '2020-09-05');

INSERT INTO sample.projects (project_name, description, start_date, end_date, budget, department_id, status) VALUES
    ('Migration Platform', 'Database migration system', '2024-01-01', '2024-12-31', 500000.00, 1, 'ACTIVE'),
    ('Cloud Initiative', 'Move to cloud infrastructure', '2024-02-01', '2024-11-30', 750000.00, 3, 'ACTIVE'),
    ('Analytics Dashboard', 'Business intelligence system', '2024-03-01', '2024-10-31', 200000.00, 1, 'PLANNING');

INSERT INTO sample.project_assignments (project_id, employee_id, role, allocation_percentage) VALUES
    (1, 1, 'Tech Lead', 80.00),
    (1, 2, 'Developer', 100.00),
    (2, 3, 'Project Manager', 50.00),
    (2, 4, 'Operations', 75.00),
    (3, 2, 'Analyst', 60.00);

-- Non-table objects (Phase 4 Schema Agent: exercise view/function/trigger
-- DDL translation, not just tables) -- see postgres-sample-extra-objects.sql
-- for the standalone copy applied live to already-provisioned containers.
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

CREATE TRIGGER trg_normalize_employee_email
BEFORE INSERT OR UPDATE ON sample.employees
FOR EACH ROW EXECUTE FUNCTION sample.normalize_employee_email();

