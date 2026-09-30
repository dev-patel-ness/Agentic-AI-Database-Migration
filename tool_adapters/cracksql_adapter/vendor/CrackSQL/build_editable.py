#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Builds an editable-installable "cracksql" package from backend/ into
_package_build/, reusing the project's own modify_imports.py (import
rewriting) and package_adapter_unified.py (Flask route neutering) scripts,
but skipping the heavier sdist/wheel build step and heavy ML dependencies
(torch/transformers/sentence-transformers) that this project's Bedrock-only
usage never needs. Re-run any time backend/ changes; _package_build/ is a
derived/regenerable artifact (gitignored).
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT, "backend")
BUILD_DIR = os.path.join(ROOT, "_package_build")
PKG_DIR = os.path.join(BUILD_DIR, "cracksql")

EXCLUDE = {"__pycache__", ".pyc", ".DS_Store", "instance", "logs", "local_models", "sources", ".git"}


def _ignore(dir_, names):
    return [n for n in names if n in EXCLUDE or n.endswith(".pyc")]


def main():
    if os.path.isdir(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(PKG_DIR)

    print(f"Copying {BACKEND_DIR} -> {PKG_DIR}")
    for item in os.listdir(BACKEND_DIR):
        src = os.path.join(BACKEND_DIR, item)
        dst = os.path.join(PKG_DIR, item)
        if item in EXCLUDE:
            continue
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=_ignore)
        else:
            shutil.copy2(src, dst)

    with open(os.path.join(PKG_DIR, "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""CrackSQL - SQL dialect translation toolkit (editable local build)."""\n\n__version__ = "0.1.0"\n')

    print("Neutering Flask route registration (package_adapter_unified.py)...")
    subprocess.run([sys.executable, os.path.join(ROOT, "package_adapter_unified.py"), BUILD_DIR], check=True)

    print("Rewriting intra-package imports (modify_imports.py)...")
    subprocess.run([sys.executable, os.path.join(ROOT, "modify_imports.py"), PKG_DIR], check=True)

    setup_py = '''from setuptools import setup, find_packages

setup(
    name="cracksql",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "flask==2.2.5",
        "flask-sqlalchemy==3.0.2",
        "flask-migrate==3.1.0",
        "flask-cors==3.0.10",
        "Flask-APScheduler==1.12.3",
        "flask_caching==1.10.1",
        "func_timeout==4.3.5",
        "paramiko>=3.5.1",
        "PyJWT==2.3.0",
        "PyYAML>=6.0",
        "pymysql==1.0.2",
        "psycopg2-binary>=2.9",
        "pgvector>=0.2.5",
        "tiktoken>=0.3.3",
        "langchain-community>=0.3.13",
        "langchain>=0.1.0",
        "langchain-openai>=0.2.14",
        "openai>=1.3.0",
        "tenacity>=8.2.0",
        "numpy>=1.24.0",
        "sqlglot>=26.0.0",
        "antlr4-python3-runtime==4.13.2",
        "boto3>=1.34",
    ],
    python_requires=">=3.10",
)
'''
    with open(os.path.join(BUILD_DIR, "setup.py"), "w", encoding="utf-8") as f:
        f.write(setup_py)

    pyproject = '''[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"
'''
    with open(os.path.join(BUILD_DIR, "pyproject.toml"), "w", encoding="utf-8") as f:
        f.write(pyproject)

    print(f"Done. Editable package ready at: {BUILD_DIR}")


if __name__ == "__main__":
    main()
