# SPEC-1-CSV-Wrangler-CLI

## Background

We need a small, reproducible Python 3.13 project that ships a command‑line tool to wrangle CSV data into clean CSV/Parquet outputs. The project must be managed with **uv** (fast resolver/venv), packaged with **hatch**, and include a standard DevEx/tooling stack (**black**, **ruff**, **pyrefly**, **pytest**, **coverage**, **bandit**) plus runtime validation via **pydantic**. The goal is to offer reliable, scriptable transformations (select/rename/filter/drop-nulls, string trimming, NA normalization) with optional row validation against a simple schema, and to be CI‑ready from day one.

Assumptions:
- Default DataFrame engine is **Polars** for speed and strong Python 3.13 support; Pandas can be swapped if required.
- Users operate it via `wrangle-csv` CLI and simple YAML/JSON config files for column maps and schema definitions.
- MVP targets single-file CSV inputs of up to ~5–10M rows on a developer laptop; larger-scale jobs can be iterated later (streaming/chunking).



## Requirements

### Must Have (M)
- Python **3.13** runtime with `uv` for env & dependency management.
- Packaged with **hatch**; single console entrypoint `wrangle-csv`.
- Input: local CSV (UTF‑8) with header.
- Core transforms: select columns, rename columns, trim strings, normalize empty strings→NULL, filter rows, drop rows with NULLs in specified columns.
- Optional row validation via **Pydantic** using simple YAML/JSON schema (`int|float|str|bool|datetime|date`).
- Output formats: CSV and Parquet.
- Deterministic behavior and clear exit codes; errors printed to stderr.
- Tooling: **black**, **ruff**, **pyrefly**, **pytest**, **coverage** (≥85%), **bandit**; all runnable via `uv run`.
- Tests for CLI and a sample data round‑trip.

### Should Have (S)
- Config files for rename map and schema (YAML/JSON) loaded via flags.
- Sensible defaults (e.g., `--format csv`).
- Performance: handle ~10M rows on a developer laptop (assumes Polars, sufficient RAM, columnar ops, no per‑row Python loops in hot path).
- Helpful `--help` text with examples.
- Pre-commit style hooks (black, ruff) optional but documented.

### Could Have (C)
- Additional transforms: date parsing with specific formats, currency normalization, case normalization, deduplication rules, computed columns via expressions, simple join/merge by key with a second CSV.
- Streaming/chunked CSV reading when memory is constrained.
- Progress bar for long runs.

### Won’t Have (W)
- Distributed processing (Spark/Dask) in MVP.
- Remote data sources (S3/DB) in MVP.
- GUI.



## Method

### Overview
A single-file CLI (`wrangle-csv`) backed by Polars for fast columnar transforms and optional Pydantic row validation. Tooling is standardized in `pyproject.toml` and run through `uv`. CI uses GitHub Actions to run linting, tests, coverage, and Bandit.

### Tech choices (validated for Python 3.13)
- Runtime libs: **polars** (≥1.30), **pydantic** (≥2.11).
- Dev/tooling: **black** (25.1.0), **ruff** (0.13.2), **pytest** (8.4.2), **coverage** (7.10.7), **bandit** (≥1.8.6), **pyrefly** (latest), **hatch** (1.14.2), **hatchling** (1.27.0), **uv** (latest).

### Project layout
```
csv-wrangler/
├─ pyproject.toml
├─ README.md
├─ src/
│  └─ wrangler/
│     ├─ __init__.py
│     ├─ cli.py
│     └─ schema.py
├─ config/
│  ├─ rename.yaml        # optional
│  └─ schema.yaml        # optional
└─ tests/
   └─ test_cli.py
```

### CLI (flags)
- Positional: `input_csv`
- Required: `-o/--output <file>`
- Optional:
  - `--select <cols...>`
  - `--rename <path.yaml|json>`
  - `--drop-nulls-in <cols...>`
  - `--filter <expr>` (repeatable; Polars SQL expressions)
  - `--schema <path.yaml|json>`
  - `--format [csv|parquet]` (default: csv)
  - **NEW**: `--date-parse <col:fmt>` (repeatable) — e.g., `--date-parse order_date:%Y-%m-%d` or `--date-parse ts:%Y-%m-%dT%H:%M:%S%z`

### Config formats
- **Rename map (YAML/JSON):** `{ old_name: new_name, ... }`
- **Schema (YAML/JSON):**
  ```yaml
  schema:
    id: int
    amount: float
    when: datetime
    code: str
  ```

### Data wrangling algorithm (MVP)
1. Read CSV → Polars DataFrame (`pl.read_csv`).
2. Trim all string columns and convert empty strings to NULL.
3. Apply renames, then column selection.
4. Drop rows with NULLs in specified columns.
5. Apply zero or more filter expressions (Polars `sql_expr`).
6. **Date parsing:** for each `col:fmt` pair, cast `pl.col(col).str.strptime(pl.Datetime, format=fmt, strict=True, exact=True)`; on failure, exit with an error summarizing offending rows.
7. Optional Pydantic validation (if schema provided) across intersecting columns; fail-fast on first error.
8. Write to CSV or Parquet.

### PlantUML — component & flow
```plantuml
@startuml
skinparam shadowing false
skinparam packageStyle rectangle
actor User
rectangle CLI {
  [Argument Parser]
parse args --> [Wrangler]
}
rectangle Core {
  [Polars Engine]
  [Schema Validator]
(Pydantic)
}
User --> [Argument Parser]
[Argument Parser] --> [Polars Engine] : read_csv, transforms
[Polars Engine] --> [Schema Validator] : optional row dicts
[Schema Validator] --> [Polars Engine] : pass/fail
[Polars Engine] --> User : write CSV/Parquet
@enduml
```

### Key modules (concise)
- `cli.py`: argparse + orchestration. Implements `--date-parse` and calls core `wrangle(...)`.
- `schema.py`: builds dynamic Pydantic model from `{column: type}` and returns a validator.

### `pyproject.toml` (authoritative)
```toml
[build-system]
requires = ["hatchling>=1.27.0"]
build-backend = "hatchling.build"

[project]
name = "csv-wrangler"
version = "0.1.0"
description = "Tiny CSV wrangling CLI using Polars + Pydantic."
readme = "README.md"
requires-python = ">=3.13"
authors = [{ name = "Your Name" }]
license = { text = "MIT" }
keywords = ["csv", "wrangling", "polars", "pydantic"]

dependencies = [
  "polars>=1.30,<2.0",
  "pydantic>=2.11,<3.0",
  "pyyaml>=6.0"
]

[project.scripts]
wrangle-csv = "wrangler.cli:main"

[tool.uv]
managed = true

[tool.uv.dependency-groups]
dev = [
  "black==25.1.0",
  "ruff==0.13.2",
  "pytest==8.4.2",
  "coverage==7.10.7",
  "bandit>=1.8.6",
  "pyrefly>=0.3.0",
]

[tool.black]
line-length = 100
target-version = ["py313"]

[tool.ruff]
target-version = "py313"
line-length = 100
extend-select = ["I"]
src = ["src"]
exclude = [".venv", ".uv"]

[tool.pytest.ini_options]
addopts = "-q"
testpaths = ["tests"]

[tool.coverage.run]
branch = true
source = ["wrangler"]

[tool.coverage.report]
show_missing = true
skip_covered = true
fail_under = 85

[tool.bandit]
skips = ["B101"]
targets = ["src"]
exclude_dirs = ["tests"]

[tool.pyrefly]
python_version = "3.13"
project_includes = ["src/**/*.py", "tests/**/*.py"]
```

### Pseudocode for date parsing
```python
for spec in date_parse_specs:  # e.g., ["order_date:%Y-%m-%d", "ts:%Y-%m-%dT%H:%M:%S%z"]
    col, fmt = spec.split(":", 1)
    df = df.with_columns(
        pl.col(col).str.strptime(pl.Datetime, format=fmt, strict=True, exact=True)
    )
```

### Testing strategy (MVP)
- Unit tests for: trimming/NULL normalization, select/rename, filters, `--date-parse` happy-path and failure-path, schema validation failure, parquet output.
- Coverage gate at 85%.

## Implementation

1) **Bootstrap**
- Create repo, add files per layout above.
- `uv sync --all-groups` to create envs and install toolchain.

2) **CLI & core**
- Implement `wrangle(...)` with transforms + `--date-parse`.
- Implement `schema.py` dynamic model builder.

3) **Quality gates**
- Add tests in `tests/` for CLI scenarios.
- Run `uv run pytest`; add coverage report target.
- Lint & format: `uv run ruff check . && uv run black .`.
- Security: `uv run bandit -r src`.

4) **Packaging**
- Ensure `hatchling` build via `uv build`; entry point works: `uv run wrangle-csv -h`.

5) **CI (GitHub Actions)** — `.github/workflows/ci.yml`
```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Sync deps
        run: uv sync --all-groups
      - name: Lint
        run: |
          uv run ruff check .
          uv run black --check .
      - name: Type check (pyrefly)
        run: uv run pyrefly check
      - name: Test
        run: uv run coverage run -m pytest
      - name: Coverage report
        run: uv run coverage report --fail-under=85
      - name: Security scan
        run: uv run bandit -r src
```

6) **Docs**
- `README.md` quick-start and examples; note date parsing flag usage.

## Milestones
- M1 (Day 1–2): Repo scaffolded; `pyproject.toml`; hello‑world CLI; CI green on empty tests.
- M2 (Day 3–4): Implement transforms + date parsing; add tests; reach coverage ≥85%.
- M3 (Day 5): Pydantic validation; error handling; docs/examples complete.
- M4 (Day 6): Packaging (`uv build`); publish pre-release (optional).

## Gathering Results
- Functional: Golden file tests pass for representative datasets; schema validation catches bad rows.
- Performance: On a ~5–10M row CSV, end‑to‑end runtime on a dev laptop is acceptable (< a few minutes) and memory stable; capture timings in README.
- Quality: CI runs clean (ruff, black, pyrefly, pytest, coverage ≥85, bandit).
- UX: `--help` output is concise; errors print actionable messages (missing columns, bad date format, validation failure).

## Need Professional Help in Developing Your Architecture?
Please contact me at [sammuti.com](https://sammuti.com) :)

