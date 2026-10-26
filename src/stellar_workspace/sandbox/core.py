"""Pure sandbox planning and owned host-service lifecycle."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile

from ..workspace import WorkspaceError, SANDBOX_DEFAULTS
from .proxy import Proxy, GH_ADAPTER
from .credentials import credential_env, credential_paths, secret_values

SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
# Installation trees stay read-only, including when sharing host Codex state.
LOCAL_TOOL_DIRECTORIES = (".local/bin", ".local/lib/node_modules",
                          ".codex/packages")


@dataclass
class Plan:
    root: Path
    cwd: Path
    mounts: list[tuple[str, str, str]] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    hidden_files: list[Path] = field(default_factory=list)
    state_directories: list[Path] = field(default_factory=list)
    auth_seeds: list[tuple[Path, Path]] = field(default_factory=list)
    capabilities: dict = field(default_factory=dict)

    def as_dict(self):
        return {"workspace": str(self.root), "cwd": str(self.cwd), "mounts": self.mounts,
                "environment": self.env, "hidden_credential_files": list(map(str, self.hidden_files)),
                "local_agent_state": list(map(str, self.state_directories)),
                "provider_auth_seeds": [(str(a), str(b)) for a,b in self.auth_seeds],
                "capabilities": self.capabilities}


def build_plan(root: Path, config: dict, overrides: dict | None = None, *, agent_name: str | None = None) -> Plan:
    options = {**SANDBOX_DEFAULTS, **config.get("sandbox", {}), **(overrides or {})}
    root = root.resolve()
    if not (root / ".venv/bin/python").exists():
        raise WorkspaceError("Workspace .venv is missing; activate its direnv environment and install stellar-workspace")
    for rel in (".tmp", "cache", ".venv"):
        if (root / rel).is_symlink() or not (root / rel).is_dir():
            raise WorkspaceError(f"Expected workspace-local {rel}/ directory")
    if not options["network"] and options["gh_proxy"]:
        raise WorkspaceError("--no-network is incompatible with the host GitHub bridge")
    home = Path.home().resolve()
    cwd = Path.cwd().resolve()
    plan = Plan(root, cwd if cwd.is_relative_to(root) else root)
    plan.capabilities = {k: options[k] for k in ("network", "gpu", "gh_proxy", "agent_profiles")}
    for path in ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc"):
        if Path(path).exists():
            plan.mounts.append(("--ro-bind", path, path))
    resolve = "/run/systemd/resolve"
    if Path(resolve).is_dir():
        plan.mounts.append(("--ro-bind", resolve, resolve))
    plan.mounts.extend([("--proc", "/proc", ""), ("--dev", "/dev", ""),
                        ("--dev-bind", "/dev/pts", "/dev/pts"),
                        ("--tmpfs", str(home), ""), ("--bind", str(root / ".tmp"), "/tmp"),
                        ("--bind", str(root), str(root))])
    # Read venv metadata instead of executing Python during a dry-run plan.
    try:
        cfg = dict(line.split(" = ", 1) for line in (root / ".venv/pyvenv.cfg").read_text().splitlines() if " = " in line)
        home_bin = Path(cfg["home"]).resolve(strict=True)
        executable = Path(cfg.get("executable", str((root / ".venv/bin/python").resolve()))).resolve(strict=True)
        base = home_bin.parent if home_bin.name in {"bin", "Scripts"} else home_bin
        if not base.is_absolute() or not executable.is_absolute():
            raise ValueError("interpreter paths must be absolute")
    except (OSError, ValueError, KeyError) as exc:
        raise WorkspaceError(f"Cannot inspect workspace Python metadata: {exc}") from exc
    for external in {base.resolve(), executable.resolve().parent}:
        if not external.is_relative_to(root) and not external.is_relative_to(Path("/usr")):
            if external == Path("/") or external == home:
                raise WorkspaceError("Python base would expose an overly broad path")
            plan.mounts.append(("--ro-bind", str(external), str(external)))
    if agent_name:
        from ..agents.config import valid_name
        valid_name(agent_name)
    # Match the original workspace launcher: ordinary interactive use shares
    # host auth, config and writable session/runtime state. Explicit profiles
    # below instead use isolated workspace state (including for named agents).
    codex_home = home / ".codex"
    if "codex" not in options["agent_profiles"] and codex_home.is_dir():
        plan.mounts.append(("--bind", str(codex_home), str(codex_home)))
    for profile in options["agent_profiles"]:
        if profile != "codex":
            raise WorkspaceError(f"Unknown agent profile: {profile}")
        # Keep sessions/config local: host configs and shell snapshots may embed
        # GitHub tokens. Share only the selected provider's authentication file.
        state = (root / "agents" / agent_name / "state" / profile) if agent_name else (root / "cache/agent-state" / profile)
        if any(p.is_symlink() for p in (state, *state.parents) if p.is_relative_to(root)):
            raise WorkspaceError(f"Agent state must be workspace-local: {state}")
        plan.state_directories.append(state)
        target = home / f".{profile}"
        plan.mounts.append(("--bind", str(state), str(target)))
        auth_name = "auth.json"
        auth = target / auth_name
        if auth.is_file() and not auth.is_symlink():
            if any(secret in auth.read_text() for secret in secret_values()):
                raise WorkspaceError(f"Selected agent auth contains a host credential: {auth}")
            plan.auth_seeds.append((auth, state / auth_name))
    # Mount after agent state so ~/.codex/packages remains visible with a
    # Codex profile. Preserve lexical destinations for ~/.local/bin symlinks.
    for relative in LOCAL_TOOL_DIRECTORIES:
        path = home / relative
        if path.is_dir() and not path.is_symlink():
            plan.mounts.append(("--ro-bind", str(path), str(path)))
    protected_credentials = credential_paths(root)
    used = set()
    for key, flag in (("ro", "--ro-bind"), ("rw", "--bind")):
        for raw in options[key]:
            path = Path(raw).expanduser()
            path = (root / path).resolve() if not path.is_absolute() else path.resolve()
            if not path.exists():
                raise WorkspaceError(f"Mount does not exist: {path}")
            protected = [*protected_credentials, root, root / ".tmp", root / ".venv", home, Path("/usr"), Path("/etc"), Path("/proc"), Path("/dev"), Path("/sys"), Path("/run")]
            if path == Path("/tmp") or any(path == p or path in p.parents or p in path.parents for p in used) or any(path == p or path in p.parents or p in path.parents for p in protected if p != home) or path == home or path in home.parents:
                raise WorkspaceError(f"Conflicting or protected extra mount: {path}")
            if path.is_relative_to(home) and path.parts[len(home.parts)] in {".ssh", ".aws", ".gnupg"}:
                raise WorkspaceError(f"Credential mounts are not supported: {path}")
            used.add(path)
            plan.mounts.append((flag, str(path), str(path)))
    # Mask known host credentials after all broad system/optional mounts.
    # Home credentials are already hidden; masking also handles GH_CONFIG_DIR
    # outside home (for example a custom configuration under /opt).
    for path in dict.fromkeys(protected_credentials):
        if path.is_relative_to(root) and path != root / ".venv/pip.conf":
            raise WorkspaceError(f"Host credential path is inside the writable workspace: {path}")
        if path.is_dir():
            plan.mounts.append(("--tmpfs", str(path), ""))
        elif path.is_file():
            plan.hidden_files.append(path)
    if options["gpu"]:
        for device in ("/dev/kfd", "/dev/dri"):
            if not Path(device).exists():
                raise WorkspaceError(f"Requested AMD GPU device missing: {device}")
            plan.mounts.append(("--dev-bind", device, device))
        # AMD NPUs use accelerator nodes, which may be absent on GPU-only hosts.
        if Path("/dev/accel").exists():
            plan.mounts.append(("--dev-bind", "/dev/accel", "/dev/accel"))
        plan.mounts.append(("--ro-bind", "/sys", "/sys"))
    plan.env = {"HOME": str(home), "USER": os.environ.get("USER", str(os.getuid())),
                "TERM": os.environ.get("TERM", "xterm-256color"), "LANG": os.environ.get("LANG", "C.UTF-8"),
                "SHELL": "/bin/bash", "SW_WORKSPACE": str(root), "SW_CACHE_DIR": str(root / "cache"),
                "SW_SANDBOX": "1", "VIRTUAL_ENV": str(root / ".venv"), "TMPDIR": "/tmp", "TMP": "/tmp", "TEMP": "/tmp",
                "XDG_CACHE_HOME": str(root / "cache"),
                "PIP_CONFIG_FILE": os.devnull, "PIP_KEYRING_PROVIDER": "disabled",
                "UV_KEYRING_PROVIDER": "disabled", "UV_NO_CONFIG": "1",
                "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
                "PATH": f"{root}/.venv/bin:{root}/tools:{root}/programs/bin:{home}/.local/bin:{SYSTEM_PATH}"}
    reserved = set(plan.env) | {"GH_CONFIG_DIR", "GIT_CONFIG_GLOBAL","BASH_ENV", "ENV", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME", "SW_GH_SOCKET"}
    for key, value in options["env"].items():
        if not key.isidentifier() or key in reserved or credential_env(key) or "\x00" in value or any(secret in value for secret in secret_values()):
            raise WorkspaceError(f"Unsupported environment override: {key}")
        plan.env[key] = value
    if any(secret in value for secret in secret_values() for value in plan.env.values()):
        raise WorkspaceError("A host environment setting contains a host credential; refusing launch")
    return plan


def argv_for(plan: Plan, handles: list) -> list[str]:
    args = ["--die-with-parent", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts"]
    if not plan.capabilities["network"]:
        args.append("--unshare-net")
    for flag, src, dst in plan.mounts:
        args += [flag, src] + ([dst] if dst else [])
    for path in plan.hidden_files:
        handle = tempfile.TemporaryFile()
        handles.append(handle)
        args += ["--ro-bind-data", str(handle.fileno()), str(path)]
    args += ["--chdir", str(plan.cwd), "--clearenv"]
    for key, value in plan.env.items():
        args += ["--setenv", key, value]
    return args


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def execute(plan: Plan, command: list[str]) -> int:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise WorkspaceError("Bubblewrap (bwrap) is required; install it using your Linux package manager")
    proxy, child = None, None
    handles, old_handlers = [], {}
    # Runtime lives under the writable workspace, so /tmp remapping cannot hide it.
    with tempfile.TemporaryDirectory(prefix="sw-sandbox-", dir=plan.root / ".tmp") as runtime, tempfile.TemporaryDirectory(prefix="sw-", dir="/tmp") as sockets:
        directory = Path(runtime)
        socket_dir = Path(sockets)
        adapters = directory / "bin"
        adapters.mkdir()
        try:
            for state in plan.state_directories:
                state.mkdir(parents=True, exist_ok=True)
            for auth, destination in plan.auth_seeds:
                if not destination.exists():
                    shutil.copy2(auth, destination)
                    destination.chmod(0o600)
            if plan.capabilities["gh_proxy"]:
                plan.mounts.append(("--bind", str(socket_dir), "/run/sw"))
                binary = shutil.which("gh", path=SYSTEM_PATH)
                if not binary:
                    raise WorkspaceError("GitHub proxy requested but host gh is unavailable")
                proxy = Proxy(socket_dir / "gh.sock", binary, plan.root)
                (adapters / "gh").write_text(GH_ADAPTER)
                (adapters / "gh").chmod(0o700)
                plan.env["SW_GH_SOCKET"] = "/run/sw/gh.sock"
            plan.env["PATH"] = f"{adapters}:{plan.env['PATH']}"
            if not command:
                from importlib.resources import files
                rc = directory / "bashrc"
                rc.write_text(files("stellar_workspace").joinpath("resources", "sandbox-bashrc.sh").read_text())
                command = ["/bin/bash", "--rcfile", str(rc)]
            args = argv_for(plan, handles)
            child = subprocess.Popen([bwrap, *args, "--", *command], pass_fds=[h.fileno() for h in handles], start_new_session=True,
                                     env={"PATH": SYSTEM_PATH, "LANG": plan.env["LANG"], "HOME": plan.env["HOME"]})
            def forward(signum, frame):
                if child.poll() is None:
                    try:
                        os.killpg(child.pid, signum)
                    except ProcessLookupError:
                        pass
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                old_handlers[sig] = signal.signal(sig, forward)
            code = child.wait()
            return 128 - code if code < 0 else code
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
            stop(child)
            for handle in handles:
                handle.close()
            if proxy:
                proxy.close()
