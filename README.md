# gary-asst
# Gary Assistant

Early MVP of the Gary Assistant project.

---

## 🚀 Getting Started

### 1. Clone the repo
```bash
git clone <your-repo-url>
cd gary-asst/dev

2. Set Python version (via pyenv)

pyenv local 3.11.9

3. Create a virtual environment

python -m venv .venv
source .venv/bin/activate

4. Install dependencies

pip install --upgrade pip
pip install -r requirements.txt

5. Install pre-commit hooks

pre-commit install
pre-commit run --all-files

    Hooks will run automatically on every git commit.

🧪 Running Tests

pytest -q

📝 Project Structure

gary-asst/
└── dev/
    ├── src/              # App source code
    │   └── app.py
    ├── tests/            # Unit tests
    │   └── test_smoke.py
    ├── requirements.txt  # Python dependencies
    └── .pre-commit-config.yaml

✅ Development Workflow

    Make changes in src/ or tests/.

    Run pytest to check tests.

    Stage & commit your changes with Git — formatting, linting, and type checks will run automatically.


👉 This way, anyone (Nick, you, or future collaborators) can go from zero → running in <5 minutes.  

Do you want me to also add a **section about contribution rules** (e.g., commit message style, branching) so the workflow is standardized from day one?
