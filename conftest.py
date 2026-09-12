# Root conftest.py: having this file here (next to pyproject.toml, with no
# __init__.py anywhere) makes pytest add the project root to sys.path, so
# every test file can `from engine import ...` etc. regardless of which
# subdirectory it lives in.
