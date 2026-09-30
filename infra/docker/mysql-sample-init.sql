-- MySQL sample database - sample data for source/target testing

USE sample_source;

-- Employees table
CREATE TABLE employees (
    employee_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE,
    department_id INT,
    salary DECIMAL(10, 2),
    hire_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Departments table
CREATE TABLE departments (
    department_id INT AUTO_INCREMENT PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL UNIQUE,
    manager_id INT,
    location VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (manager_id) REFERENCES employees(employee_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add foreign key for employees.department_id
ALTER TABLE employees ADD CONSTRAINT fk_employees_department 
    FOREIGN KEY (department_id) REFERENCES departments(department_id);

-- Projects table
CREATE TABLE projects (
    project_id INT AUTO_INCREMENT PRIMARY KEY,
    project_name VARCHAR(150) NOT NULL,
    description TEXT,
    start_date DATE NOT NULL,
    end_date DATE,
    budget DECIMAL(15, 2),
    department_id INT NOT NULL,
    status VARCHAR(50) DEFAULT 'ACTIVE',
    FOREIGN KEY (department_id) REFERENCES departments(department_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Project assignments (many-to-many)
CREATE TABLE project_assignments (
    assignment_id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    employee_id INT NOT NULL,
    role VARCHAR(100),
    allocation_percentage DECIMAL(5, 2),
    assigned_date DATE DEFAULT (CURDATE()),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    UNIQUE KEY unique_project_employee (project_id, employee_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create indexes
CREATE INDEX idx_employees_department ON employees(department_id);
CREATE INDEX idx_employees_email ON employees(email);
CREATE INDEX idx_projects_department ON projects(department_id);
CREATE INDEX idx_assignments_project ON project_assignments(project_id);
CREATE INDEX idx_assignments_employee ON project_assignments(employee_id);

-- Sample data
INSERT INTO departments (department_name, location) VALUES
    ('Engineering', 'Building A'),
    ('Sales', 'Building B'),
    ('Operations', 'Building C');

INSERT INTO employees (first_name, last_name, email, department_id, salary, hire_date) VALUES
    ('John', 'Smith', 'john.smith@example.com', 1, 85000.00, '2020-01-15'),
    ('Jane', 'Doe', 'jane.doe@example.com', 1, 90000.00, '2019-03-20'),
    ('Bob', 'Johnson', 'bob.johnson@example.com', 2, 75000.00, '2021-06-10'),
    ('Alice', 'Williams', 'alice.williams@example.com', 3, 80000.00, '2020-09-05');

INSERT INTO projects (project_name, description, start_date, end_date, budget, department_id, status) VALUES
    ('Migration Platform', 'Database migration system', '2024-01-01', '2024-12-31', 500000.00, 1, 'ACTIVE'),
    ('Cloud Initiative', 'Move to cloud infrastructure', '2024-02-01', '2024-11-30', 750000.00, 3, 'ACTIVE'),
    ('Analytics Dashboard', 'Business intelligence system', '2024-03-01', '2024-10-31', 200000.00, 1, 'PLANNING');

INSERT INTO project_assignments (project_id, employee_id, role, allocation_percentage) VALUES
    (1, 1, 'Tech Lead', 80.00),
    (1, 2, 'Developer', 100.00),
    (2, 3, 'Project Manager', 50.00),
    (2, 4, 'Operations', 75.00),
    (3, 2, 'Analyst', 60.00);

-- Non-table objects (Phase 4 Schema Agent: exercise view/function/trigger
-- DDL translation, not just tables) -- see mysql-sample-extra-objects.sql
-- for the standalone copy applied live to already-provisioned containers.
CREATE OR REPLACE VIEW active_employees AS
SELECT employee_id, first_name, last_name, department_id
FROM employees
WHERE is_active = TRUE;

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

DELIMITER //
CREATE TRIGGER trg_normalize_employee_email
BEFORE INSERT ON employees
FOR EACH ROW
BEGIN
    SET NEW.email = LOWER(NEW.email);
END//
DELIMITER ;

