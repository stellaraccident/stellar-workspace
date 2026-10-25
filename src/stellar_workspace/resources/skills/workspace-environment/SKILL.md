---
name: workspace-environment
description: Set up or repair this workspace's direnv venv and local program or scratch paths.
---

Each workspace owns `.venv`, `.tmp`, `programs/` and `scratch/`; a parent venv
must not substitute for the local venv. The generated `.envrc` loads parent
settings and then activates the local environment. The human runs `direnv allow`
from an external shell after reviewing `.envrc`; agents should not grant trust.

Before installation, bootstrap with `python3 /path/to/stellar-workspace/sw-init.py
/path/to/workspace`. After activation, use the selected `python -m pip install
/path/to/stellar-workspace`, or `--force-reinstall` to update it. If missing,
`sw-init --repair` restores managed files; `--upgrade --dry-run` previews current
templates. Never delete an existing venv or replace edited `.envrc` automatically.
Use `SW_PYTHON` to select a base Python 3.11+ on first activation.

Keep programs and their own data in `programs/NAME/`, or small binaries in
`programs/bin` (on PATH). Put outputs in `build/`, reusable data in `cache/`,
temporary files in `.tmp/`, and disposable experiments/downloads in `scratch/`.
Do not commit these local outputs or remove them without a task requiring it.
