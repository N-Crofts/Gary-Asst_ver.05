# Gary Assistant

Gary is a Python-based project designed to support business development executives by streamlining workflows and automating tasks.  
The project enforces consistent coding standards through linting, formatting, type checking, and automated tests — all wired into **pre-commit hooks**.

---

## Prerequisites

- **Python** 3.11.9 (managed via [pyenv](https://github.com/pyenv/pyenv))
- **pip** (comes with Python / venv)
- **pre-commit** (installed via requirements.txt)

> **Optional (only if we add a frontend later):**
> - **Node.js** (via [nvm](https://github.com/nvm-sh/nvm) or [asdf](https://asdf-vm.com/))
>   - Recommended: Node 20.x LTS
>   - Install frontend dependencies with `npm install` or `yarn install` once a `package.json` is present

---

## Setup Instructions

1. **Install Python 3.11.9 via pyenv:**
   ```bash
   pyenv install 3.11.9
   pyenv local 3.11.9
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install pre-commit hooks:**
   ```bash
   pre-commit install
   ```

5. **Run hooks manually on all files (first run may take a few minutes):**
   ```bash
   pre-commit run --all-files
   ```

---

## Development Workflow

- Code formatting is enforced by **black**.
- Linting is handled by **ruff**.
- Type checking is handled by **mypy**.
- Tests are run with **pytest**.

### Useful Commands

- Run tests:
  ```bash
  pytest
  ```

- Run type checking:
  ```bash
  mypy .
  ```

- Run linting:
  ```bash
  ruff check .
  ```

- Auto-format code:
  ```bash
  black .
  ```

---

## Notes

- Commit hooks will automatically run before every commit to ensure code quality.
- If a hook fails, fix the issue and re-commit.
- You can skip hooks (not recommended) with:
  ```bash
  git commit --no-verify
  ```
