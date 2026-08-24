# Cross-platform installation and verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand installation guidance for Windows and Linux and verify every requested project path from the Windows workstation.

**Architecture:** Keep runtime code unchanged. Reorganize `README.md` into platform-specific prerequisites and commands, then document optional model/index/GEPA paths and a reproducible verification checklist. Execute the checklist locally, recording exact pass/fail limitations in the handoff rather than claiming unsupported hardware paths.

**Tech Stack:** Python 3.11, pip/venv, Node.js 22/npm, pytest, flake8, Next.js, Docker Compose, Chroma/Qwen, GEPA, vLLM-compatible endpoint.

---

### Task 1: Rewrite platform installation documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add prerequisite matrix and platform sections**

Add Windows PowerShell instructions using `py -3.11`, `.venv\Scripts\Activate.ps1`, `python -m pip`, and PowerShell HTTP checks. Add Linux/macOS instructions using `python3.11`, `source .venv/bin/activate`, and `curl`. State that Python 3.11 is required by the pinned model artifacts and that Node.js 22/npm are required for the dashboard.

- [ ] **Step 2: Add Windows execution policy and dependency troubleshooting**

Document the scoped PowerShell activation-policy command, the direct `\.venv\Scripts\python.exe` fallback, and the Windows alternative to `curl` (`Invoke-WebRequest` or `Invoke-RestMethod`). Explain that Docker Desktop must be running before Compose commands.

- [ ] **Step 3: Separate basic, Docker, retrieval, LLM, and GEPA paths**

Make it explicit that API/dashboard is the baseline, Chroma/Qwen downloads a model on first indexing, GEPA is installed from its separate requirements file, and Gemma/vLLM is an optional external model service. Preserve the existing Apple Silicon vLLM-Metal instructions and add Windows/Linux alternatives only where supported by an OpenAI-compatible endpoint.

- [ ] **Step 4: Add a full verification checklist**

Include exact commands for backend tests/lint, dashboard test/lint/build, `docker compose config`, Compose smoke, retrieval indexing, and GEPA `--check`. Include cleanup commands that do not remove normal volumes by accident.

- [ ] **Step 5: Check README formatting and links**

Run `git diff --check` and inspect all changed command blocks for shell/platform consistency. Confirm existing links remain valid and no command silently assumes macOS on Windows/Linux.

### Task 2: Install and verify local Windows paths

**Files:**
- No source changes; use existing `.venv` and `src/dashboard` working directories.

- [ ] **Step 1: Verify Python 3.11 environment and dependencies**

Run `.venv\Scripts\python.exe --version`, `-m pip check`, and imports for FastAPI, spaCy, scikit-learn, joblib, Chroma, and sentence-transformers. Install from `requirements.txt` only if the environment is missing a pinned dependency.

- [ ] **Step 2: Run backend quality checks**

Run `.venv\Scripts\python.exe -m pytest tests/ -q --cov=src --cov-report=term` and flake8 with the README command. Capture failures with their actual cause.

- [ ] **Step 3: Run dashboard checks**

From `src/dashboard`, run `npm ci`, `npm test`, `npm run lint`, and `npm run build`.

- [ ] **Step 4: Run API and dashboard process smoke**

Start API and dashboard in separate PowerShell processes, poll `/api/v1/health` and `http://localhost:3000/`, then stop only the started processes. Verify an API endpoint used by the dashboard.

### Task 3: Verify optional retrieval, GEPA, and container paths

**Files:**
- No source changes unless verification reveals a documentation-only command correction.

- [ ] **Step 1: Run GEPA contract validation**

Install `requirements-prompt-optimization.txt` into the Python 3.11 environment if needed, then run `python -m src.prompt_optimization.optimize_gepa --check` without starting a live optimization experiment.

- [ ] **Step 2: Run deterministic Chroma smoke before network-heavy indexing**

Use the project’s supported smoke/environment flags where available. Run the real Qwen indexing command only if model download and available disk/RAM permit it; record model download or hardware failures separately from application failures.

- [ ] **Step 3: Validate Compose configuration and images**

Run `docker compose config --quiet` and `docker compose build api dashboard`. If successful, start the isolated smoke project with LLM disabled, embedding warmup disabled, and smoke indexing enabled; poll API/dashboard endpoints and the refresh job status.

- [ ] **Step 4: Inspect and clean isolated Compose resources**

Collect `docker compose ps` and logs on failure. Stop only the isolated smoke project with its volumes; do not remove the default project volumes.

### Task 4: Finalize evidence and handoff

**Files:**
- Modify: `README.md` only if verification exposed a command mismatch.

- [ ] **Step 1: Re-run documentation and changed-file checks**

Run `git diff --check`, inspect `git status --short`, and ensure pre-existing changes such as `src/dashboard/next.config.ts` and `.freebuff/` are untouched.

- [ ] **Step 2: Report outcomes by path**

Summarize pass/fail for local backend, dashboard, API/dashboard runtime, Compose, Chroma/Qwen, GEPA, and Gemma/vLLM. For unavailable platform hardware or external services, state the exact blocker and the command that was not run or could not complete.

