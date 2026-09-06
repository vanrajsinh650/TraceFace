#!/usr/bin/env bash
# TraceFace bootstrap script (Linux / macOS)
# Creates a Python virtual environment, installs dependencies, runs diagnostics.

set -e

# Navigate to repository root (parent of scripts/ directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "TraceFace Setup — $(uname -s)"
echo "Repository root: $REPO_ROOT"

# Detect Python (prefer python3, fall back to python)
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" &>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "ERROR: Python is not installed or not in PATH."
  echo "Install Python 3.10–3.12 from https://www.python.org/downloads/"
  exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1)
echo "Found: $PY_VERSION"

# Create virtual environment if missing
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  $PYTHON -m venv .venv
fi

# Activate the environment
source .venv/bin/activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Run diagnostics (allow non-zero exit — just report)
echo ""
echo "Running environment diagnostics..."
set +e
python main.py doctor
DOCTOR_EXIT=$?
set -e

echo ""
if [ $DOCTOR_EXIT -eq 0 ]; then
  echo "Setup complete! All checks passed."
else
  echo "Setup complete with warnings. Review the doctor output above."
fi

echo ""
echo "Next steps:"
echo "  source .venv/bin/activate                                            # activate venv"
echo "  python main.py proof-verify fixtures/demo_evidence.json              # verify published proof"
echo "  python main.py --image fixtures/sample_face.jpg --no-blockchain      # live mode with included sample"
