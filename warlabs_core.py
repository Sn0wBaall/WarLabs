#!/usr/bin/env python3
"""
WarLabs — Núcleo compartido por la CLI y la GUI.

Contiene toda la lógica de labs y Docker: descubrimiento, parsing de run.sh,
estado de contenedores, conflictos de puertos y operaciones sobre Docker.

Sin dependencias externas (ni rich ni customtkinter) para poder testearlo
de forma aislada. Tanto warlabs_cli.py como WarLabs.py deben importar de aquí:
si una función aparece duplicada en las interfaces, es un bug esperando a
ocurrir (ya pasó con un lab cuyo run.sh pasaba flags extra que los launchers
ignoraban, así que el contenedor arrancaba con otra configuración).
"""

from __future__ import annotations

import functools
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

# ── Constantes ────────────────────────────────────────────────────────────────
LEVEL_DIRS = ("Facil", "Medio", "Dificil")
LEVEL_MAP = {"Facil": "Fácil", "Medio": "Medio", "Dificil": "Difícil"}

DOCKER_TIMEOUT = 5      # segundos para comandos docker de consulta
SNAPSHOT_TTL = 0.5     # ventana de caché de `docker ps -a`
BUILD_TAIL_LINES = 40  # líneas de build conservadas para el diagnóstico

# sysctls que Docker permite sin --privileged (ver docs de `docker run --sysctl`).
# El resto cambia también el host, así que Docker los rechaza.
_NAMESPACED_SYSCTL_PREFIXES = ("net.", "fs.mqueue.")
_NAMESPACED_SYSCTL_KEYS = (
    "kernel.msgmax", "kernel.msgmnb", "kernel.msgmni", "kernel.sem",
    "kernel.shmall", "kernel.shmmax", "kernel.shmmni", "kernel.shm_rmid_forced",
)

FLAG_PATH = "/root/flag.txt"   # ubicación de la flag dentro del contenedor
SOLVED_FILE = Path.home() / ".warlabs_solved.json"   # progreso: labs superados


class DockerError(RuntimeError):
    """Fallo al hablar con el demonio de Docker."""


# ── Modelo de datos ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Port:
    """Puerto publicado por un lab (host → contenedor)."""
    host: str
    container: str

    @property
    def kind(self) -> str:
        return "ssh" if self.container == "22" else "http"

    @property
    def arg(self) -> str:
        return f"0.0.0.0:{self.host}:{self.container}"


@dataclass(frozen=True)
class Endpoint:
    """Endpoint accesible una vez lanzado el lab."""
    kind: str
    host: str
    port: str

    @property
    def text(self) -> str:
        if self.kind == "ssh":
            return f"ssh {self.host} -p {self.port}"
        return f"http://{self.host}:{self.port}"

    @property
    def url(self) -> str | None:
        """URL abrible en el navegador (None para SSH)."""
        return f"http://{self.host}:{self.port}" if self.kind == "http" else None


@dataclass
class Lab:
    name: str
    level: str
    path: Path
    desc: str
    readme: Path | None
    image: str
    ports: list[Port] = field(default_factory=list)
    extra_args: list[str] = field(default_factory=list)  # flags extra del run.sh
    flag: str | None = None
    objective: str = ""

    @property
    def level_key(self) -> str:
        """Clave sin acentos para comparar/completar en la CLI."""
        return deaccent(self.level).lower()

    def endpoints(self, ip: str | None = None) -> list[Endpoint]:
        ip = ip or local_ip()
        return [Endpoint(p.kind, ip, p.host) for p in self.ports]

    def warnings(self) -> list[str]:
        """Avisos sobre la configuración del lab (sysctls no permitidos, etc.)."""
        out = []
        for key in iter_sysctls(self.extra_args):
            if not sysctl_is_namespaced(key):
                out.append(
                    f"El run.sh usa --sysctl {key}, que no es namespaced: "
                    f"Docker lo rechazará salvo --privileged (y desactivaría "
                    f"el ajuste en todo el host)."
                )
        if self.image != self.image.lower():
            out.append(
                f"El nombre de imagen '{self.image}' tiene mayúsculas: Docker "
                f"exige repositorios y etiquetas en minúsculas y el build "
                f"fallaría. Usa '{self.image.lower()}' en el run.sh."
            )
        return out


# ── Utilidades de texto ───────────────────────────────────────────────────────

def deaccent(text: str) -> str:
    return text.translate(str.maketrans("áéíóúÁÉÍÓÚüñ", "aeiouAEIOUun"))


def strip_md(text: str) -> str:
    """Quita **negrita** y `código` de un fragmento markdown."""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


# ── Descubrimiento ────────────────────────────────────────────────────────────

def find_base_dir() -> Path:
    """Sube desde la ubicación del script hasta encontrar la raíz de WarLabs."""
    candidate = Path(__file__).resolve().parent
    for _ in range(5):
        if (candidate / "Facil").exists() or (candidate / "Medio").exists():
            return candidate
        candidate = candidate.parent
    return Path(__file__).resolve().parent


BASE_DIR = find_base_dir()


def _read_section(lines: list[str], heading: str, max_lines: int = 4) -> str:
    """Devuelve el primer párrafo con texto tras un heading markdown '### X'."""
    for i, line in enumerate(lines):
        if line.strip().lower().startswith(heading.lower()):
            buf = []
            for j in range(i + 1, min(i + 1 + max_lines, len(lines))):
                candidate = lines[j].strip()
                if not candidate:
                    if buf:
                        break
                    continue
                buf.append(strip_md(candidate))
            return " ".join(buf)
    return ""


def flag_path(lab_path: Path) -> Path | None:
    """Ruta del fichero de flag del lab en el repo (si existe)."""
    for candidate in (lab_path / "content" / "flag.txt", lab_path / "flag.txt"):
        if candidate.is_file():
            return candidate
    return None


def _load_run_sh(lab_path: Path) -> tuple[str, dict[str, str]]:
    run_sh = lab_path / "run.sh"
    if not run_sh.is_file():
        return "", {}
    content = run_sh.read_text(encoding="utf-8", errors="replace")
    return content, parse_sh_vars(content)


def parse_sh_vars(content: str) -> dict[str, str]:
    """Extrae `nombre="valor"` / `nombre=valor` de un script de shell."""
    vars_: dict[str, str] = {}
    for name, value in re.findall(r"^\s*(?:export\s+)?([A-Za-z_]\w*)=(.+)$", content, re.M):
        value = value.strip()
        # quita comentarios finales fuera de comillas
        value = re.sub(r"\s+#.*$", "", value).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        vars_[name] = value
    return vars_


def expand(value: str, vars_: dict[str, str]) -> str:
    """Resuelve ${var} y $var contra el diccionario de variables del script."""

    def _sub(match: re.Match) -> str:
        return vars_.get(match.group(1) or match.group(2), match.group(0))

    for _ in range(3):  # por si hay referências anidadas
        new = re.sub(r"\$\{(\w+)\}|\$(\w+)", _sub, value)
        if new == value:
            break
        value = new
    return value


def parse_docker_run(content: str, vars_: dict[str, str]) -> list[str]:
    """Tokeniza el `docker run` de un run.sh resolviendo sus variables.

    Devuelve los tokens posteriores a `docker run`, sin redirecciones.
    """
    match = re.search(r"^\s*docker\s+run\b(.*?)(?:\n\S|\Z)", content, re.M | re.S)
    if not match:
        return []
    body = match.group(1)
    body = re.sub(r"\\[ \t]*\n", " ", body)        # continuaciones de línea
    body = re.sub(r">/?\S+", " ", body)              # > /dev/null, 2>&1, >&2
    try:
        tokens = shlex.split(body, comments=True)
    except ValueError:
        return []
    return [expand(tok, vars_) for tok in tokens]


# Flags de `docker run` que consumen el token siguiente como valor.
# Sin esta lista, `--sysctl kernel.randomize_va_space=0` perdería su valor
# (el segundo token no empieza por `-` y se tomaría por el nombre de imagen).
_VALUE_FLAGS = frozenset({
    "--add-host", "--annotation", "--blkio-weight", "--cap-add", "--cap-drop",
    "--cgroup-parent", "--cgroupns", "--cidfile", "--cpu-period", "--cpu-quota",
    "--cpus", "--cpuset-cpus", "--cpu-shares", "-d", "--device",
    "--device-cgroup-rule", "--device-read-bps", "--device-write-bps", "-e",
    "--entrypoint", "--env", "--env-file", "--expose", "-g", "--gpus",
    "--group-add", "-h", "--hostname", "--ip", "--ip6", "--ipc", "--isolation",
    "--kernel-memory", "-l", "--label", "--link", "--link-local-ip",
    "--log-driver", "--log-opt", "-m", "--memory", "--memory-reservation",
    "--memory-swap", "--mount", "--name", "--network", "--net",
    "--oom-kill-disable", "--oom-scoreadj", "-p", "--pid", "--pids-limit",
    "--platform", "--publish", "--read-timeout", "--restart", "--runtime",
    "--security-opt", "--shm-size", "--stop-signal", "--stop-timeout",
    "--sysctl", "--tmpfs", "-u", "--ulimit", "--user", "--userns", "--uts",
    "-v", "--volume", "-w", "--workdir",
})


def split_run_tokens(tokens: list[str]) -> tuple[list[Port], list[str]]:
    """Separa los tokens en puertos publicados y flags adicionales.

    Se ignoran `-d`, `--name <x>` y el nombre de imagen (los gestiona el core).
    """
    ports: list[Port] = []
    extra: list[str] = []

    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1

        if token in ("-p", "--publish"):
            if index < len(tokens):
                _add_port(ports, tokens[index])
                index += 1
            continue
        if token.startswith("--publish="):
            _add_port(ports, token.split("=", 1)[1])
            continue
        if token == "--name":
            index += 1  # el nombre lo pone el core (nombre del directorio)
            continue
        if token.startswith("--name="):
            continue
        if token in ("-d", "--detach", "--rm"):
            continue
        if token.startswith("-"):
            extra.append(token)
            if token in _VALUE_FLAGS and index < len(tokens):
                extra.append(tokens[index])
                index += 1
            continue
        break  # el primer token no-flag es la imagen: el resto es el CMD

    return ports, extra


def _add_port(ports: list[Port], spec: str) -> None:
    parts = spec.split(":")
    if len(parts) == 2:
        host, container = parts
    elif len(parts) >= 3:
        host, container = parts[-2], parts[-1]
    else:
        return
    container = container.split("/")[0]
    if host.isdigit() and container.isdigit():
        ports.append(Port(host, container))


def iter_sysctls(args: list[str]) -> list[str]:
    """Extrae las claves de todos los --sysctl presentes en una lista de args."""
    keys = []
    for i, arg in enumerate(args):
        if arg == "--sysctl" and i + 1 < len(args):
            keys.append(args[i + 1].split("=", 1)[0])
        elif arg.startswith("--sysctl="):
            keys.append(arg.split("=", 1)[0].removeprefix("--sysctl="))
    return keys


def sysctl_is_namespaced(key: str) -> bool:
    """¿Docker permite este sysctl en un contenedor sin --privileged?"""
    if key in _NAMESPACED_SYSCTL_KEYS:
        return True
    return key.startswith(_NAMESPACED_SYSCTL_PREFIXES)


def discover_labs(base_dir: Path | None = None) -> list[Lab]:
    """Escanea Facil/Medio/Dificil y devuelve los labs con Dockerfile."""
    base_dir = base_dir or BASE_DIR
    labs: list[Lab] = []

    for level_dir in LEVEL_DIRS:
        level_path = base_dir / level_dir
        if not level_path.is_dir():
            continue

        for lab_dir in sorted(level_path.iterdir()):
            if not lab_dir.is_dir() or not (lab_dir / "Dockerfile").is_file():
                continue

            readme = lab_dir / "README.md"
            desc = objective = ""
            if readme.is_file():
                lines = readme.read_text(encoding="utf-8", errors="replace").splitlines()
                desc = _read_section(lines, "### Descripción", max_lines=3)
                objective = _read_section(lines, "### Objetivo", max_lines=3)

            content, vars_ = _load_run_sh(lab_dir)
            ports, extra = split_run_tokens(parse_docker_run(content, vars_))
            if not ports:  # run.sh ausente o sin `docker run`: variables *_port
                ports = _ports_from_vars(vars_)

            fpath = flag_path(lab_dir)
            flag = fpath.read_text(encoding="utf-8", errors="replace").strip() if fpath else None

            labs.append(Lab(
                name=lab_dir.name,
                level=LEVEL_MAP.get(level_dir, level_dir),
                path=lab_dir,
                desc=desc or "Sin descripción disponible.",
                readme=readme if readme.is_file() else None,
                image=vars_.get("image_name") or f"warlabs/{lab_dir.name.lower()}",
                ports=ports,
                extra_args=extra,
                flag=flag or None,
                objective=objective,
            ))

    return labs


def _ports_from_vars(vars_: dict[str, str]) -> list[Port]:
    """Fallback: deduce puertos de ssh_port= / web_port=."""
    ports: list[Port] = []
    for name, value in vars_.items():
        if not name.endswith("_port") or not str(value).isdigit():
            continue
        container = "22" if "ssh" in name else "80"
        ports.append(Port(str(value), container))
    return ports


# ── Resolución de nombres ─────────────────────────────────────────────────────

def resolve_lab(labs: list[Lab], identifier: str | None) -> tuple[Lab | None, str | None]:
    """Resuelve un lab por nombre, prefijo, subcadena o índice de la tabla.

    Devuelve (lab, None) o (None, mensaje_de_error).
    """
    if not identifier or not identifier.strip():
        return None, "Especifica un laboratorio (nombre o número)."

    identifier = identifier.strip()
    if identifier.isdigit():
        index = int(identifier) - 1
        if 0 <= index < len(labs):
            return labs[index], None
        return None, f"Índice '{identifier}' fuera de rango. Hay {len(labs)} labs."

    target = identifier.lower()
    exact = [l for l in labs if l.name.lower() == target]
    if len(exact) == 1:
        return exact[0], None

    prefix = [l for l in labs if l.name.lower().startswith(target)]
    if len(prefix) == 1:
        return prefix[0], None

    substr = [l for l in labs if target in l.name.lower()]
    if len(substr) == 1:
        return substr[0], None

    if exact or prefix or substr:
        candidates = sorted({l.name for l in exact + prefix + substr})
        return None, f"Coincidencia ambigua. Labs: {', '.join(candidates)}"

    return None, f"No se encontró ningún lab con nombre o índice '{identifier}'."


# ── Docker ────────────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def docker_problem() -> str | None:
    """Devuelve None si Docker responde, o un mensaje con el problema."""
    if shutil.which("docker") is None:
        return "No se encontró el comando 'docker' en el PATH. Instálalo y reinicia la sesión."

    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"No se pudo ejecutar docker: {exc}"

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        hint = detail[-1] if detail else "sin detalle"
        return f"El demonio de Docker no responde: {hint}"
    return None


@dataclass(frozen=True)
class ContainerInfo:
    name: str
    state: str
    published: tuple[str, ...] = ()   # puertos publicados en el host

    @property
    def running(self) -> bool:
        return self.state == "running"


_snapshot_cache: dict[str, ContainerInfo] = {}
_snapshot_time = 0.0
_snapshot_error: str | None = None
_snapshot_lock = threading.Lock()

_PUBLISHED_RE = re.compile(r"(?:[\d.]+|\[::\]):(\d+)->")


def _parse_published(spec: str) -> tuple[str, ...]:
    return tuple(_PUBLISHED_RE.findall(spec or ""))


def snapshot_error() -> str | None:
    """Motivo por el que el último `snapshot` no refleja la realidad, o `None`.

    Sin esto, no se puede distinguir "no hay contenedores" de "no he podido
    preguntar", y la interfaz acaba enseñando un `stopped` inventado.
    """
    return _snapshot_error


def snapshot(force: bool = False) -> dict[str, ContainerInfo]:
    """Estado de TODOS los contenedores en una sola llamada a `docker ps -a`.

    Cacheado unos 500 ms para que un refresco que consulta varios labs no
    lance un subproceso por lab (esto era lo que bloqueaba la GUI al teclear).
    """
    global _snapshot_time, _snapshot_error

    now = time.monotonic()
    if not force and _snapshot_cache and now - _snapshot_time < SNAPSHOT_TTL:
        return _snapshot_cache

    info: dict[str, ContainerInfo] = {}
    error: str | None = None
    try:
        proc = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.State}}\t{{.Ports}}"],
            capture_output=True, text=True, timeout=DOCKER_TIMEOUT,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                name, state = parts[0], parts[1]
                published = _parse_published(parts[2]) if len(parts) > 2 else ()
                info[name] = ContainerInfo(name, state, published)
        else:
            detail = (proc.stderr or proc.stdout).strip().splitlines()
            error = detail[-1] if detail else f"docker ps devolvió {proc.returncode}"
    except subprocess.TimeoutExpired:
        error = f"docker ps tardó más de {DOCKER_TIMEOUT}s"
    except OSError as exc:
        error = f"no se pudo ejecutar docker: {exc}"

    with _snapshot_lock:
        _snapshot_cache.clear()
        _snapshot_cache.update(info)
        _snapshot_time = time.monotonic()
        _snapshot_error = error
        return dict(_snapshot_cache)


def container_status(lab: Lab, snap: dict[str, ContainerInfo] | None = None) -> str:
    """Estado del contenedor de un lab, usando un snapshot compartido.

    Devuelve `"unknown"` si el snapshot no se pudo obtener: adivinar `stopped`
    sería mentir, y fue exactamente lo que pasaba con Docker inaccesible.
    """
    snap = snapshot() if snap is None else snap
    if lab.name in snap:
        return snap[lab.name].state
    for name, info in snap.items():
        if lab.name in name or name in lab.name:
            return info.state
    return "unknown" if _snapshot_error else "stopped"


def port_conflicts(ports: list[Port], ignore: str | None = None) -> list[tuple[str, str]]:
    """Puertos del lab ya ocupados por otro contenedor. -> [(puerto, dueño)]"""
    snap = snapshot()
    taken: dict[str, str] = {}
    for name, info in snap.items():
        if not info.running or name == ignore:
            continue
        for port in info.published:
            taken.setdefault(port, name)

    conflicts = []
    for port in ports:
        if port.host in taken:
            conflicts.append((port.host, taken[port.host]))
    return conflicts


@functools.lru_cache(maxsize=1)
def local_ip() -> str:
    """IP local de la máquina (wlan0 → eth0 → ... → socket → localhost)."""
    for iface in ("wlan0", "eth0", "enp0s3", "ens33", "enp0s31f6", "enp0s32f6"):
        try:
            proc = subprocess.run(
                ["ip", "-o", "-4", "addr", "show", iface],
                capture_output=True, text=True, timeout=3,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", proc.stdout)
                if match:
                    return match.group(1)
        except (subprocess.TimeoutExpired, OSError):
            pass

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "localhost"
    finally:
        sock.close()


# ── Operaciones sobre contenedores ───────────────────────────────────────────

@dataclass
class BuildResult:
    ok: bool
    output: str          # últimas líneas (diagnóstico)
    image: str


def _legacy_build_requested() -> bool:
    """WARLABS_LEGACY_BUILD=1 fuerza siempre el builder clásico."""
    return os.environ.get("WARLABS_LEGACY_BUILD", "").strip().lower() in {
        "1", "true", "yes", "si", "sí",
    }


def _is_buildkit_crash(lines: list[str]) -> bool:
    """¿El fallo es el crash de BuildKit (exit 139 en un RUN)?

    En Raspberry Pi (ARM) el ejecutor de BuildKit de Docker 29 muere con
    SIGSEGV en 0.3s nada más lanzar el paso, sin dejar ni una línea en dmesg:
    por eso parece un fallo de `apt` cuando en realidad es del builder.
    `docker run` con la misma imagen funciona, así que no reintentamos a ciegas
    ante cualquier error, solo ante esta firma concreta.
    """
    return any("exit code: 139" in line for line in lines)


def _stream_build(lab: Lab, on_line, legacy: bool) -> tuple[int, list[str]]:
    """Lanza `docker build` línea a línea. -> (código de salida, últimas líneas)"""
    env = os.environ.copy()
    if legacy:
        env["DOCKER_BUILDKIT"] = "0"

    tail: list[str] = []
    proc = subprocess.Popen(
        ["docker", "build", "-t", lab.image, "."],
        cwd=str(lab.path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            tail.append(line)
            if len(tail) > BUILD_TAIL_LINES:
                del tail[0]
            if on_line is not None:
                on_line(line)
    finally:
        proc.stdout.close() if proc.stdout else None
        proc.wait()

    return proc.returncode, tail


def build_image(lab: Lab, on_line=None) -> BuildResult:
    """Construye la imagen del lab. Si on_line es callable, recibe cada línea.

    Hacer streaming importa: en un Raspberry Pi un `docker build` puede tardar
    minutos y, capturando la salida, la GUI parecía congelada.

    Si BuildKit revienta con su crash de exit 139 se reintenta una vez con el
    builder clásico, que hace la misma operación correctamente en la Pi.
    """
    if _legacy_build_requested():
        rc, tail = _stream_build(lab, on_line, legacy=True)
        return BuildResult(ok=rc == 0, output="\n".join(tail), image=lab.image)

    rc, tail = _stream_build(lab, on_line, legacy=False)
    if rc != 0 and _is_buildkit_crash(tail):
        if on_line is not None:
            on_line("BuildKit ha fallado; se reintenta con el builder clásico.")
        rc, tail = _stream_build(lab, on_line, legacy=True)

    return BuildResult(ok=rc == 0, output="\n".join(tail), image=lab.image)


def remove_container(name: str) -> None:
    subprocess.run(
        ["docker", "rm", "-f", name],
        capture_output=True, text=True, timeout=60,
    )


def run_command(lab: Lab) -> list[str]:
    """Construye el `docker run` respetando los flags extra del run.sh del lab.

    Antes se montaba a mano aquí y en la GUI, y por eso los flags extra de un
    lab se perdían por el camino. Ahora la fuente de verdad es el run.sh.
    """
    cmd = ["docker", "run", "-d", "--name", lab.name]
    cmd += lab.extra_args
    for port in lab.ports:
        cmd += ["-p", port.arg]
    cmd.append(lab.image)
    return cmd


def start_container(lab: Lab, force: bool = True) -> tuple[bool, str]:
    """(Re)crea el contenedor del lab. -> (ok, mensaje_de_error)"""
    snap = snapshot()
    if lab.name in snap or force:
        remove_container(lab.name)

    proc = subprocess.run(
        run_command(lab), capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "docker run falló").strip()
    return True, proc.stdout.strip()


def stop_container(lab: Lab) -> tuple[bool, str]:
    proc = subprocess.run(
        ["docker", "rm", "-f", lab.name],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "docker rm falló").strip()
    return True, ""


@dataclass
class FlagCheck:
    state: str        # "ok" | "mismatch" | "missing" | "absent" | "stopped" | "error"
    detail: str

    @property
    def solved(self) -> bool:
        return self.state == "ok"


def check_flag(lab: Lab) -> FlagCheck:
    """Comprueba si la flag del repo está presente dentro del contenedor."""
    if not lab.flag:
        return FlagCheck("absent", f"{lab.name} no tiene flag definida (content/flag.txt).")

    status = container_status(lab)
    if status == "unknown":
        # No es que esté parado: es que no hemos podido preguntarlo.
        return FlagCheck("error", f"No se pudo consultar Docker: {snapshot_error()}")
    if status != "running":
        return FlagCheck("stopped", f"{lab.name} no está en ejecución (estado: {status}).")

    try:
        proc = subprocess.run(
            ["docker", "exec", lab.name, "cat", FLAG_PATH],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return FlagCheck("error", str(exc))

    if proc.returncode != 0:
        return FlagCheck("missing", f"No existe {FLAG_PATH} dentro del contenedor.")

    found = proc.stdout.strip()
    if found == lab.flag:
        return FlagCheck("ok", found)
    return FlagCheck("mismatch", f"{FLAG_PATH} contiene algo distinto a la flag del repo.")


# ── Entrega de flags y progreso ───────────────────────────────────────────────
#
# `check_flag` dice si el lab está bien montado (que `/root/flag.txt` existe en el
# contenedor), no si quien lo usa lo ha resuelto. Eso lo cubre `submit_flag`,
# que compara la flag que se entrega con la del repo y anota el lab como superado.
#
# El progreso vive en `~/.warlabs_solved.json` y no en el repo a propósito: los
# labs se comparten y el estado de cada quien es suyo. `WARLABS_SOLVED` lo
# sobrescribe (lo usan los tests).


@dataclass
class SubmitResult:
    state: str        # "ok" | "wrong" | "absent" | "empty"
    detail: str
    saved: bool = True     # False si la flag vale pero no se pudo anotar el progreso
    already: bool = False  # el lab ya constaba como superado de antes

    @property
    def accepted(self) -> bool:
        return self.state == "ok"


def normalize_flag(text: str) -> str:
    """Normaliza lo que se pega desde una terminal: espacios, comillas y \n.

    Copiar con Ctrl+Shift+V mete comillas triples y espacios que no son parte de
    la flag; sin esto el fallo siempre parecería culpa de quien la entrega.
    """
    text = (text or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'`":
        text = text[1:-1].strip()
    return text


def submit_flag(lab: Lab, answer: str) -> SubmitResult:
    """Comprueba la flag entregada para `lab` y anota el progreso si acierta.

    No necesita Docker: comparar contra `content/flag.txt` es lo que hace
    falta, y así se puede entregar la flag con el contenedor ya parado.
    """
    if not lab.flag:
        return SubmitResult("absent", f"{lab.name} no tiene flag definida (content/flag.txt).")

    guess = normalize_flag(answer)
    if not guess:
        return SubmitResult("empty", "No has entregado ninguna flag.")

    if guess != lab.flag:
        # El detalle no dice en qué falla: sería regalarle la respuesta a medias.
        return SubmitResult("wrong", "La flag entregada no coincide con la del lab.")

    already = is_solved(lab.name)
    saved = mark_solved(lab, guess)
    return SubmitResult("ok", lab.flag, saved, already)


# ── Progreso persistido ───────────────────────────────────────────────────────

def solved_path() -> Path:
    """Ruta del fichero de progreso (WARLABS_SOLVED la sobrescribe)."""
    override = os.environ.get("WARLABS_SOLVED")
    return Path(override) if override else SOLVED_FILE


def load_progress() -> dict[str, dict]:
    """Progreso guardado: {"lab-01": {"flag": ..., "when": ...}}.

    Un fichero corrupto o ilegible devuelve `{}` en vez de reventar: perder el
    historial de labs superados no puede impedir usar la herramienta.
    """
    try:
        raw = solved_path().read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {name: entry for name, entry in data.items() if isinstance(entry, dict)}


def save_progress(data: dict[str, dict]) -> bool:
    """Escribe el progreso. -> ¿se pudo guardar?"""
    try:
        path = solved_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        return True
    except OSError:
        return False


def is_solved(name: str, progress: dict | None = None) -> bool:
    return name in (load_progress() if progress is None else progress)


def mark_solved(lab: Lab, answer: str) -> bool:
    """Anota `lab` como superado. -> ¿se pudo guardar?"""
    progress = load_progress()
    progress[lab.name] = {
        "flag": normalize_flag(answer),
        "nivel": lab.level,
        "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return save_progress(progress)


def forget(name: str) -> bool:
    """Quita un lab del progreso. -> ¿quedó algo que guardar / se pudo guardar?"""
    progress = load_progress()
    if name in progress:
        del progress[name]
    return save_progress(progress)


def reset_progress(names: list[str] | None = None) -> list[str]:
    """Borra el progreso. Sin `names`, lo borra todo. -> labs borrados."""
    progress = load_progress()
    targets = list(progress) if names is None else [n for n in names if n in progress]
    for name in targets:
        del progress[name]
    save_progress(progress)
    return targets


def progress_rows(labs: list[Lab]) -> list[tuple[Lab, bool, str]]:
    """(lab, superado, fecha) para cada lab, para pintar tablas de progreso."""
    progress = load_progress()
    return [(lab, lab.name in progress, str(progress.get(lab.name, {}).get("when", "")))
            for lab in labs]
