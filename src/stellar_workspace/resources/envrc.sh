# Parent settings are inherited, but every workspace selects its own venv.
source_up_if_exists
export SW_WORKSPACE="$PWD"
export SW_CACHE_DIR="$PWD/cache"
export TMPDIR="$PWD/.tmp"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
mkdir -p "$TMPDIR" "$SW_CACHE_DIR" "$PWD/programs/bin" "$PWD/scratch"
if [ ! -f "$PWD/.venv/bin/activate" ]; then
  sw_bootstrap_python="${SW_PYTHON:-python3}"
  sw_base_python="$("$sw_bootstrap_python" -c 'import sys; print(sys._base_executable)')" || return 1
  "$sw_base_python" -m venv "$PWD/.venv" || return 1
fi
source "$PWD/.venv/bin/activate"
PATH_add "$PWD/programs/bin"
PATH_add "$PWD/tools"
watch_file workspace.toml
