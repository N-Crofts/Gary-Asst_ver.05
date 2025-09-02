# Contributing to Gary-Asst

Thanks for contributing! Here are a few conventions to follow so our history stays clean and easy to understand.

---

## ✅ Commit message format

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(optional scope): <short summary>
```

### Types
- **feat**: new feature
- **fix**: bug fix
- **docs**: documentation only (e.g., README)
- **test**: adding or updating tests
- **chore**: config, dependencies, environment, cleanup
- **refactor**: code changes that aren’t new features/bug fixes

### Examples
```
feat(digest): add sample endpoint for /digest/send
chore(repo): cleanup dependencies and add .env.example
docs(readme): add Quickstart and sanity test instructions
test(endpoints): add pytest checks for health and digest routes
```

---

## 🧹 Pre-commit hooks

Run once per machine:
```bash
pre-commit install
```

These will auto-fix style issues (whitespace, formatting) and run linters before commits.

### Handling pre-commit "failures"

When you commit, some hooks (like `end-of-file-fixer`, `trailing-whitespace`, `black`) may show **Failed**.
This doesn’t mean your commit is broken — it means the hook auto-fixed files and stopped the commit so you can stage the changes.

#### To fix and continue:
```bash
git add -A && git commit --amend --no-edit
```

#### Clean workflow:
```bash
# 1. Run hooks manually
pre-commit run --all-files

# 2. Stage changes
git add -A

# 3. Commit (example)
git commit -m "chore(repo): cleanup deps/env, update README, add tests & contributing"

# 4. Push
git push origin main
```

#### VS Code tip
Add these settings in `.vscode/settings.json` to avoid trailing whitespace/newline issues before they happen:
```json
{
  "files.trimTrailingWhitespace": true,
  "files.insertFinalNewline": true
}
```

---

## 🚀 Quickstart (recap)

```bash
git clone <repo-url>
cd gary-asst
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-all.txt
cp .env.example .env   # fill in keys
uvicorn app.main:app --reload
pytest -q
```
