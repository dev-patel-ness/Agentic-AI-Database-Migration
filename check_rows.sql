SELECT 'DEPARTMENTS_UC' as table_name, count(*) FROM sample."DEPARTMENTS"
UNION ALL SELECT 'departments_lc', count(*) FROM sample.departments
UNION ALL SELECT 'EMPLOYEES_UC', count(*) FROM sample."EMPLOYEES"
UNION ALL SELECT 'employees_lc', count(*) FROM sample.employees
UNION ALL SELECT 'PROJECTS_UC', count(*) FROM sample."PROJECTS"
UNION ALL SELECT 'projects_lc', count(*) FROM sample.projects
UNION ALL SELECT 'PA_UC', count(*) FROM sample."PROJECT_ASSIGNMENTS"
UNION ALL SELECT 'pa_lc', count(*) FROM sample.project_assignments;
