#!/usr/bin/env bash
# deploy.sh — copy the Repo2Skill agent skill into a target Agent skills directory.
#
# Layout produced at <target_dir>/<skill_name>/:
#   SKILL.md
#   skill.yaml
#   scripts/        (CLI wrappers: structure.py, extract.py, assemble.py, audit_g1.py, audit_g2.py)
#   references/     (extractor-guide.md, enrichment-guide.md, g2-review.md, suite-mode.md, trust-levels.md)
#   repo2skill/     (vendored Python package from src/repo2skill/)
#
# Usage:
#   bash repo2skill-skill/deploy.sh <target_dir> [--skill-name NAME] [--force] [--install-deps]
#
# Examples:
#   bash repo2skill-skill/deploy.sh ~/.claude/skills
#   bash repo2skill-skill/deploy.sh ~/.claude/skills --force --install-deps

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: deploy.sh <target_dir> [options]

Arguments:
  <target_dir>          Agent skills directory (e.g. ~/.claude/skills).

Options:
  --skill-name NAME     Subdirectory name under target_dir (default: repo2skill).
  --force               Overwrite an existing destination directory.
  --install-deps        Run `python3 -m pip install -r scripts/requirements.txt`
                        after copying. Use the active Python environment.
  -h, --help            Show this help and exit.
EOF
}

TARGET_DIR=""
SKILL_NAME="repo2skill"
FORCE=0
INSTALL_DEPS=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --skill-name)
            [[ $# -ge 2 ]] || { echo "Error: --skill-name requires an argument" >&2; exit 2; }
            SKILL_NAME="$2"
            shift 2
            ;;
        --force)
            FORCE=1
            shift
            ;;
        --install-deps)
            INSTALL_DEPS=1
            shift
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "Error: unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            if [[ -z "$TARGET_DIR" ]]; then
                TARGET_DIR="$1"
                shift
            else
                echo "Error: unexpected positional argument: $1" >&2
                usage >&2
                exit 2
            fi
            ;;
    esac
done

if [[ -z "$TARGET_DIR" ]]; then
    echo "Error: <target_dir> is required" >&2
    usage >&2
    exit 2
fi

# Validate --skill-name early: it becomes a subdirectory name *and* the target
# of `rm -rf` when --force is set. Reject anything that could traverse outside
# of <target_dir>.
if [[ -z "$SKILL_NAME" || "$SKILL_NAME" == "." || "$SKILL_NAME" == ".." || "$SKILL_NAME" == */* ]]; then
    echo "Error: --skill-name must be a simple directory name (no '/', '.', '..')" >&2
    exit 2
fi
if ! [[ "$SKILL_NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "Error: --skill-name may only contain letters, digits, '.', '_' and '-'" >&2
    exit 2
fi

# Resolve repo root from this script's location: <repo_root>/repo2skill-skill/deploy.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SRC_PKG="$REPO_ROOT/src/repo2skill"
SKILL_SRC="$REPO_ROOT/repo2skill-skill"

if [[ ! -d "$SRC_PKG" ]]; then
    echo "Error: missing Python package source: $SRC_PKG" >&2
    exit 1
fi
if [[ ! -f "$SKILL_SRC/SKILL.md" ]]; then
    echo "Error: missing skill entry: $SKILL_SRC/SKILL.md" >&2
    exit 1
fi

# Expand ~ in TARGET_DIR
TARGET_DIR="${TARGET_DIR/#\~/$HOME}"
mkdir -p "$TARGET_DIR"
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"

DEST="$TARGET_DIR/$SKILL_NAME"

# Defensive guard: never let `rm -rf` operate on '/' or an empty path even if
# upstream validation is somehow bypassed.
if [[ -z "$DEST" || "$DEST" == "/" ]]; then
    echo "Refusing to operate on '$DEST'" >&2
    exit 1
fi

if [[ -e "$DEST" ]]; then
    if [[ "$FORCE" -eq 1 ]]; then
        echo "Removing existing $DEST"
        rm -rf "$DEST"
    else
        echo "Error: destination already exists: $DEST" >&2
        echo "       Re-run with --force to overwrite." >&2
        exit 1
    fi
fi

mkdir -p "$DEST"

echo "Deploying Repo2Skill -> $DEST"

# Use cp -a where possible for predictable behaviour.
cp "$SKILL_SRC/SKILL.md"   "$DEST/SKILL.md"
cp "$SKILL_SRC/skill.yaml" "$DEST/skill.yaml"

copy_dir() {
    # copy_dir <src> <dest>
    local src="$1"
    local dest="$2"
    mkdir -p "$dest"
    # Exclude __pycache__ and *.pyc artifacts.
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --exclude '__pycache__' --exclude '*.pyc' "$src/" "$dest/"
    else
        # Fallback: tar pipe with excludes.
        ( cd "$src" && tar --exclude '__pycache__' --exclude '*.pyc' -cf - . ) \
            | ( cd "$dest" && tar -xf - )
    fi
}

copy_dir "$SKILL_SRC/scripts"    "$DEST/scripts"
copy_dir "$SKILL_SRC/references" "$DEST/references"
copy_dir "$SRC_PKG"              "$DEST/repo2skill"

if [[ "$INSTALL_DEPS" -eq 1 ]]; then
    REQ_FILE="$DEST/scripts/requirements.txt"
    if [[ -f "$REQ_FILE" ]]; then
        # Show which interpreter will receive the deps. The Agent runtime calls
        # python3 from its own PATH, which may differ from this shell. Verify
        # this matches the Python the Agent will use before continuing.
        PY_BIN="$(command -v python3 || true)"
        if [[ -z "$PY_BIN" ]]; then
            echo "Error: python3 not found on PATH; cannot --install-deps" >&2
            exit 1
        fi
        PY_VER="$("$PY_BIN" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
        IN_VENV="$("$PY_BIN" -c 'import sys; print("yes" if sys.prefix != sys.base_prefix else "no")')"
        echo
        echo "Installing Python dependencies"
        echo "  interpreter : $PY_BIN  (Python $PY_VER)"
        echo "  in venv     : $IN_VENV"
        echo "  requirements: $REQ_FILE"
        if [[ "$IN_VENV" == "no" ]]; then
            # Detect PEP 668 marker (Debian/Ubuntu/Homebrew may ship it).
            STDLIB_DIR="$("$PY_BIN" -c 'import sysconfig; print(sysconfig.get_paths()["stdlib"])')"
            if [[ -f "$STDLIB_DIR/EXTERNALLY-MANAGED" ]]; then
                echo
                echo "Warning: this Python is marked EXTERNALLY-MANAGED (PEP 668)." >&2
                echo "         pip install will likely refuse. Recommended: create a venv," >&2
                echo "         activate it, and re-run with --install-deps. See docs/usage-guide.md." >&2
            fi
        fi
        "$PY_BIN" -m pip install -r "$REQ_FILE"
    else
        echo "Warning: $REQ_FILE not found; skipping --install-deps" >&2
    fi
fi

echo
echo "Done. Deployed layout:"
echo "  $DEST/"
echo "  |- SKILL.md"
echo "  |- skill.yaml"
echo "  |- scripts/"
echo "  |- references/"
echo "  \`- repo2skill/    (vendored Python package)"
echo
echo "Skill entry: $DEST/SKILL.md"
