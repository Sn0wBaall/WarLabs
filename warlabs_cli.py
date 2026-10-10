#!/usr/bin/env python3
"""
WarLabs CLI — Gestor de laboratorios (interfaz de línea de comandos)
Uso: python3 warlabs_cli.py [comando] [opciones]

La lógica de labs y Docker vive en warlabs_core.py, compartida con la GUI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

# Permite ejecutar el script desde cualquier directorio.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from warlabs_core import (  # noqa: E402
    FLAG_PATH,
    Lab,
    build_image,
    check_flag,
    container_status,
    deaccent,
    discover_labs,
    docker_problem,
    is_solved,
    load_progress,
    port_conflicts,
    progress_rows,
    remove_container,
    reset_progress,
    resolve_lab,
    snapshot,
    snapshot_error,
    start_container,
    stop_container,
    strip_md,
    submit_flag,
    solved_path,
)

# ── Dependencia opcional: rich ────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.live import Live
    from rich.markup import escape as rich_escape
    from rich import box as rich_box
    from rich.prompt import Confirm, Prompt
    from rich.syntax import Syntax

    RICH = True
except ImportError:
    RICH = False

# ── Constantes ────────────────────────────────────────────────────────────────
STATUS_POLL_INTERVAL = 2
EXIT_OK = 0
EXIT_ERR = 1
EXIT_USAGE = 2
HISTORY_FILE = Path.home() / ".warlabs_history"

# ── Colores ANSI (fallback sin rich) ─────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    GREEN   = "\033[38;2;63;185;80m"
    CYAN    = "\033[38;2;121;192;255m"
    PURPLE  = "\033[188;140;255m"
    YELLOW  = "\033[38;2;227;179;65m"
    RED     = "\033[38;2;248;81;73m"
    MUTED   = "\033[38;2;139;148;158m"
    SURFACE = "\033[48;2;22;27;34m"


def c(text, color):
    return f"{color}{text}{C.RESET}"


def cpad(text: str, width: int, color: str) -> str:
    """Colorea y ajusta al ancho, contando el texto visible y no los escapes.

    Ajustar el resultado de `c()` no sirve: los códigos ANSI ocupan caracteres y
    se comen el relleno, y las columnas salen descuadradas.
    """
    return c(text.ljust(width)[:width], color)


# ── Consola rich ──────────────────────────────────────────────────────────────
console = Console(highlight=False) if RICH else None
# Consola aparte para stderr: en modo `--json` el banner y los avisos no pueden
# ir a stdout o rompen el parseo. `Console` no tiene forma de redirigir en rich
# 15, así que se construye una instancia propia.
err_console = Console(highlight=False, stderr=True) if RICH else None


def print_info(msg):
    if RICH:
        console.print(f"  [bold][cyan]\\[*][/cyan][/bold] {msg}")
    else:
        print(f"  {c('[*]', C.CYAN)} {msg}")


def print_ok(msg):
    if RICH:
        console.print(f"  [bold][green]\\[+][/green][/bold] {msg}")
    else:
        print(f"  {c('[+]', C.GREEN)} {msg}")


def print_err(msg):
    if RICH:
        console.print(f"  [bold][red]\\[!][/red][/bold] {msg}")
    else:
        print(f"  {c('[!]', C.RED)} {msg}")


def print_warn(msg, to_stderr: bool = False):
    if RICH:
        out = err_console if to_stderr else console
        out.print(f"  [bold][yellow]\\[~][/yellow][/bold] {msg}")
    elif to_stderr:
        print(f"  {c('[~]', C.YELLOW)} {msg}", file=sys.stderr)
    else:
        print(f"  {c('[~]', C.YELLOW)} {msg}")


def print_raw(msg):
    """Línea literal (salida de docker), sin interpretación de markup."""
    if RICH:
        console.print(Text(rich_escape(msg)), style="dim", highlight=False)
    else:
        print(c(msg, C.MUTED))


def _p(rich_fmt, plain_fmt):
    """Imprime con rich o con ANSI básicos según disponibilidad."""
    if RICH:
        console.print(rich_fmt)
    else:
        print(plain_fmt)


def is_tty() -> bool:
    return sys.stdout.isatty()


def clear_screen() -> None:
    """Limpia la pantalla solo si tiene sentido (si no, rompe `warlabs list | grep`)."""
    if is_tty():
        os.system("cls" if os.name == "nt" else "clear")


# ── Banner ────────────────────────────────────────────────────────────────────
BANNER = r"""
 ██╗    ██╗ █████╗ ██████╗ ██╗      █████╗ ██████╗ ███████╗
 ██║    ██║██╔══██╗██╔══██╗██║     ██╔══██╗██╔══██╗██╔════╝
 ██║ █╗ ██║███████║██████╔╝██║     ███████║██████╔╝███████╗
 ██║███╗██║██╔══██║██╔══██╗██║     ██╔══██║██╔══██╗╚════██║
 ╚███╔███╔╝██║  ██║██║  ██║███████╗██║  ██║██████╔╝███████║
  ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═════╝ ╚══════╝
"""


def print_banner(to_stderr: bool = False):
    """Banner de arranque.

    `to_stderr` lo saca de stdout para no contaminar la salida `--json`:
    sin esto, `warlabs list --json | jq` se rompe con un error de parseo.
    """
    if RICH:
        out = err_console if to_stderr else console
        out.print(f"[green]{BANNER}[/green]")
        out.print(
            "  [bold cyan]Plataforma de laboratorios de hacking ético[/bold cyan]"
            "  [dim]|[/dim]  "
            "[dim]github.com/Sn0wBaall[/dim]\n"
        )
    elif to_stderr:
        print(c(BANNER, C.GREEN), file=sys.stderr)
        print(f"  {c('Plataforma de laboratorios de hacking ético', C.CYAN)}\n",
              file=sys.stderr)
    else:
        print(c(BANNER, C.GREEN))
        print(f"  {c('Plataforma de laboratorios de hacking ético', C.CYAN)}\n")


# ── Helpers compartidos ───────────────────────────────────────────────────────

LEVEL_COLOR = {"Fácil": "green", "Medio": "yellow", "Difícil": "red"}
LEVEL_ANSI = {"Fácil": C.GREEN, "Medio": C.YELLOW, "Difícil": C.RED}


def labs_or_exit(labs):
    if not labs:
        print_err("No se encontraron laboratorios. Verifica la estructura de niveles.")
        return False
    return True


def _lab_or_exit(labs, identifier) -> Lab | None:
    lab, error = resolve_lab(labs, identifier)
    if lab is None:
        print_err(error)
        if error and "No se encontró" in error:
            print_info("Usa 'list' para ver los labs disponibles.")
    return lab


def require_docker() -> bool:
    problem = docker_problem()
    if problem:
        print_err(problem)
        return False
    return True


def status_dot(status: str) -> tuple[str, str]:
    """(icono+texto, estilo rich)."""
    if status == "running":
        return "● running", "green"
    if status in ("exited", "created"):
        return f"○ {status}", "yellow"
    if status == "paused":
        return "◐ paused", "yellow"
    if status == "unknown":
        return "? sin datos", "yellow"
    return "○ stopped", "dim"


def solved_mark(lab: Lab, solved: dict) -> tuple[str, str, str]:
    """(símbolo, estilo rich, color ANSI) de la columna de progreso de un lab.

    Tres estados y no dos: un lab sin `content/flag.txt` no está pendiente de
    nada, está mal montado, y conviene que se note en la lista.
    """
    if lab.name in solved:
        return "✓", "green", C.GREEN
    if not lab.flag:
        return "?", "yellow", C.YELLOW
    return "·", "dim", C.MUTED


def warn_docker_unreachable(to_stderr: bool = False) -> None:
    """Avisa si los estados que se muestran no son fiables.

    Sin esto, con el socket de Docker inaccesible la lista enseña "4 detenidos"
    como si fuera un dato, y esconde lo único que importa. En modo `--json` el
    aviso va a stderr para no romper el JSON (allí ya va en `docker_error`).
    """
    problem = snapshot_error()
    if problem:
        print_warn(f"No se pudo consultar Docker: {problem}", to_stderr=to_stderr)
        if not to_stderr:
            print_info("Los estados que ves no son fiables "
                       "(suelen ser permisos del socket, no que esté parado).")


def show_endpoints(lab: Lab) -> None:
    for endpoint in lab.endpoints():
        text = endpoint.text
        if RICH:
            console.print(f"    [dim]→[/dim]  [bold green]{text}[/bold green]")
        else:
            print(f"    {c('→', C.MUTED)}  {c(text, C.GREEN)}")


def show_warnings(lab: Lab) -> None:
    for warning in lab.warnings():
        print_warn(warning)


def confirm(question: str, default: bool = False) -> bool:
    if RICH:
        return Confirm.ask(f"  [yellow]{question}[/yellow]", default=default)
    suffix = "[S/n]" if default else "[s/N]"
    answer = input(f"  {c(question + ' ' + suffix + ': ', C.YELLOW)}")
    yes = {"s", "si", "sí", "y", "yes"}
    return answer.strip().lower() in yes if not default else \
        answer.strip().lower() not in {"n", "no"}


def build_lab(lab: Lab, verbose: bool) -> bool:
    """Construye la imagen, mostrando el progreso si la salida es interactiva."""
    show = verbose or is_tty()
    if RICH:
        print_info(f"Construyendo imagen [cyan]{lab.image}[/cyan]...")
    else:
        print_info(f"Construyendo imagen {lab.image}...")

    def on_line(line: str) -> None:
        if show and line.strip():
            print_raw("    " + line)

    result = build_image(lab, on_line)
    if not result.ok:
        print_err("Error al construir la imagen:")
        for line in result.output.splitlines()[-15:]:
            print_raw("    " + line)
        if "invalid tag" in result.output or "must be lowercase" in result.output:
            print_info(f"El nombre de imagen del run.sh debe ir en minúsculas: "
                       f"usa '{lab.image.lower()}'.")
        return False
    print_ok("Imagen construida correctamente.")
    return True


def launch_lab(lab: Lab, verbose: bool) -> int:
    """Flujo común de `start` y `restart`."""
    show_warnings(lab)

    if not build_lab(lab, verbose):
        return EXIT_ERR

    conflicts = port_conflicts(lab.ports, ignore=lab.name)
    if conflicts:
        for port, owner in conflicts:
            print_err(f"Puerto {port} ocupado por el contenedor '{owner}'.")
        print_info("Detén el otro laboratorio con 'stop <lab>' o arranca este con otro puerto.")
        return EXIT_ERR

    ok, error = start_container(lab)
    if not ok:
        print_err(f"Error al iniciar el contenedor:\n{error}")
        if "is not allowed" in error or "sysctl" in error.lower():
            print_info("Docker ha rechazado un --sysctl del run.sh; revisa Lab.warnings().")
        return EXIT_ERR

    print_ok(f"Laboratorio {c(lab.name, C.CYAN)} en ejecución." if not RICH
             else f"Laboratorio [bold cyan]{lab.name}[/bold cyan] en ejecución.")

    if lab.ports:
        print()
        show_endpoints(lab)
    print()
    return EXIT_OK


# ── Comandos ──────────────────────────────────────────────────────────────────

def cmd_list(args) -> int:
    """Muestra todos los laboratorios disponibles."""
    labs = discover_labs()
    if not labs_or_exit(labs):
        return EXIT_ERR

    level = getattr(args, "level", None)
    if level:
        wanted = deaccent(level).lower()
        labs = [l for l in labs if l.level_key == wanted]
        if not labs:
            print_err(f"Ningún lab de nivel '{level}'.")
            return EXIT_ERR

    snap = snapshot()   # una sola llamada a docker para todos los labs
    solved = load_progress()   # una sola lectura del progreso

    if getattr(args, "json", False):
        payload = {
            "labs": [
                {
                    "name": lab.name,
                    "nivel": lab.level,
                    "estado": container_status(lab, snap),
                    "imagen": lab.image,
                    "puertos": [{"host": p.host, "container": p.container}
                                for p in lab.ports],
                    "flag": bool(lab.flag),
                    "superado": lab.name in solved,
                    "descripcion": lab.desc,
                }
                for lab in labs
            ],
            # Sin esto, un script leería "stopped" y concluiría que todo está
            # bien cuando en realidad no se pudo preguntar nada.
            "docker_error": snapshot_error(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK

    warn_docker_unreachable(to_stderr=getattr(args, "json", False))

    if RICH:
        table = Table(
            box=rich_box.ROUNDED,
            border_style="dim",
            header_style="bold cyan",
            show_lines=True,
            expand=True,
        )
        table.add_column("#",         style="dim",  width=4,  justify="right")
        table.add_column("Lab",       style="bold", min_width=12)
        table.add_column("Nivel",     justify="center", width=10)
        table.add_column("Estado",    justify="center", width=12)
        table.add_column("✓",         justify="center", width=6)
        table.add_column("Descripción", style="dim", ratio=1)

        for i, lab in enumerate(labs, 1):
            status = container_status(lab, snap)
            dot, dot_style = status_dot(status)
            level_style = LEVEL_COLOR.get(lab.level, "white")
            mark, mark_style, _ = solved_mark(lab, solved)
            desc = strip_md(lab.desc)
            table.add_row(
                str(i),
                f"[bold]{lab.name}[/bold]",
                f"[{level_style}]{lab.level}[/{level_style}]",
                f"[{dot_style}]{dot}[/{dot_style}]",
                f"[{mark_style}]{mark}[/{mark_style}]",
                desc[:80] + ("…" if len(desc) > 80 else ""),
            )

        console.print(table)
        console.print(f"  [dim]{len(labs)} laboratorio(s) encontrado(s), "
                      f"{len([l for l in labs if l.name in solved])} superado(s)[/dim]\n")
    else:
        sep = c("─" * 76, C.MUTED)
        print(sep)
        print(f"  {cpad('#', 4, C.MUTED)}  {cpad('Lab', 10, C.CYAN)}  "
              f"{cpad('Nivel', 9, C.CYAN)}  {cpad('Estado', 14, C.CYAN)}  "
              f"{cpad('✓', 5, C.CYAN)}")
        print(sep)
        for i, lab in enumerate(labs, 1):
            status = container_status(lab, snap)
            dot, _ = status_dot(status)
            dot_color = {"running": C.GREEN, "paused": C.YELLOW}.get(status, C.MUTED)
            level_color = LEVEL_ANSI.get(lab.level, C.MUTED)
            mark, _, mark_color = solved_mark(lab, solved)
            print(f"  {cpad(str(i), 4, C.MUTED)}  {cpad(lab.name, 10, C.CYAN)}  "
                  f"{cpad(lab.level, 9, level_color)}  {cpad(dot, 14, dot_color)}  "
                  f"{c(mark, mark_color)}")
            print(f"  {c('      ' + strip_md(lab.desc)[:64], C.MUTED)}")
        print(sep)
        print(f"\n  {c(str(len(labs)) + ' laboratorio(s) encontrado(s)', C.MUTED)}\n")
    return EXIT_OK


def cmd_info(args) -> int:
    """Muestra la información detallada de un lab, incluyendo el README."""
    labs = discover_labs()
    lab = _lab_or_exit(labs, args.lab)
    if lab is None:
        return EXIT_ERR

    status = container_status(lab)
    dot, _ = status_dot(status)
    show_warnings(lab)

    if getattr(args, "json", False):
        print(json.dumps({
            "name": lab.name,
            "nivel": lab.level,
            "estado": status,
            "imagen": lab.image,
            "path": str(lab.path),
            "puertos": [{"host": p.host, "container": p.container, "tipo": p.kind}
                        for p in lab.ports],
            "endpoints": [e.text for e in lab.endpoints()],
            "flags_extra": lab.extra_args,
            "descripcion": lab.desc,
            "objetivo": lab.objective,
            "flag": lab.flag,
            "readme": str(lab.readme) if lab.readme else None,
        }, ensure_ascii=False, indent=2))
        return EXIT_OK

    if RICH:
        header = Text()
        header.append(f"  {lab.name}", style="bold cyan")
        header.append(f"  [{lab.level}]", style=LEVEL_COLOR.get(lab.level, "white"))
        header.append(f"  {dot}", style="green" if status == "running" else "dim")
        console.print(Panel(header, border_style="dim", expand=False, padding=(0, 1)))
        console.print(f"\n  [dim]{lab.desc}[/dim]\n")
    else:
        level_color = LEVEL_ANSI.get(lab.level, C.MUTED)
        dot_color = C.GREEN if status == "running" else C.MUTED
        print(f"\n  {c(lab.name, C.CYAN)}  {c(lab.level, level_color)}  {c(dot, dot_color)}")
        print(f"  {c(lab.desc, C.MUTED)}\n")

    if lab.objective:
        _p(f"  [bold]Objetivo:[/bold] {lab.objective}\n", f"  {c('Objetivo:', C.BOLD)} {lab.objective}\n")

    if lab.ports:
        print_info("Endpoints:")
        show_endpoints(lab)
        print()

    if lab.readme and lab.readme.exists():
        content = lab.readme.read_text(encoding="utf-8", errors="replace")
        _render_readme_rich(content) if RICH else _render_readme_plain(content)
    else:
        print_warn("Sin README disponible para este laboratorio.")
    return EXIT_OK


def cmd_start(args) -> int:
    """Construye y lanza un laboratorio."""
    if not require_docker():
        return EXIT_ERR

    labs = discover_labs()
    lab = _lab_or_exit(labs, args.lab)
    if lab is None:
        return EXIT_ERR

    if container_status(lab) == "running" and not getattr(args, "force", False):
        print_warn(f"El laboratorio '{lab.name}' ya está en ejecución. Usa 'restart' para recrearlo.")
        return EXIT_OK
    return launch_lab(lab, args.verbose)


def cmd_stop(args) -> int:
    """Detiene y elimina laboratorios."""
    labs = discover_labs()
    if not labs_or_exit(labs):
        return EXIT_ERR

    if getattr(args, "all", False):
        snap = snapshot(force=True)
        targets = [l for l in labs if container_status(l, snap) == "running"]
        if not targets:
            print_warn("No hay laboratorios en ejecución.")
            return EXIT_OK
        if not args.force and not confirm(
            f"¿Detener y eliminar los {len(targets)} laboratorios activos?"
        ):
            print_info("Operación cancelada.")
            return EXIT_OK
        for lab in targets:
            print_info(f"Deteniendo {lab.name}...")
            ok, error = stop_container(lab)
            (print_ok if ok else print_err)(f"'{lab.name}' detenido." if ok else error)
        return EXIT_OK

    if not args.lab:
        print_err("Especifica un laboratorio o usa --all para detener todos.")
        return EXIT_USAGE

    lab = _lab_or_exit(labs, args.lab)
    if lab is None:
        return EXIT_ERR

    if container_status(lab) != "running":
        print_warn(f"El laboratorio '{lab.name}' no está en ejecución.")
        return EXIT_OK

    if not args.force and not confirm(f"¿Detener y eliminar '{lab.name}'?"):
        print_info("Operación cancelada.")
        return EXIT_OK

    print_info(f"Deteniendo {lab.name}...")
    ok, error = stop_container(lab)
    if ok:
        print_ok(f"Laboratorio '{lab.name}' detenido y eliminado.")
        return EXIT_OK
    print_err(error)
    return EXIT_ERR


def cmd_restart(args) -> int:
    """Recrea un laboratorio (stop + build + run)."""
    if not require_docker():
        return EXIT_ERR

    labs = discover_labs()
    lab = _lab_or_exit(labs, args.lab)
    if lab is None:
        return EXIT_ERR

    print_info(f"Reiniciando {lab.name}...")
    if container_status(lab) == "running":
        remove_container(lab.name)
        print_ok("Contenedor detenido.")
    return launch_lab(lab, args.verbose)


def cmd_status(args) -> int:
    """Muestra el estado actual de todos los contenedores de labs."""
    labs = discover_labs()
    if not labs_or_exit(labs):
        return EXIT_ERR

    snap = snapshot(force=True)
    states = {l.name: container_status(l, snap) for l in labs}
    running = [l for l in labs if states[l.name] == "running"]
    unknown = [l for l in labs if states[l.name] == "unknown"]
    stopped = [l for l in labs if l not in running and l not in unknown]

    if getattr(args, "json", False):
        print(json.dumps({
            "running": [l.name for l in running],
            "stopped": [l.name for l in stopped],
            "unknown": [l.name for l in unknown],
            "docker_error": snapshot_error(),
        }, ensure_ascii=False, indent=2))
        return EXIT_OK

    warn_docker_unreachable()

    if RICH:
        console.print(f"\n  [bold green]● Running[/bold green]  ({len(running)})")
        for lab in running:
            console.print(f"    [cyan]{lab.name}[/cyan]  [dim]{lab.level}[/dim]")
        console.print(f"\n  [dim]○ Stopped[/dim]  ({len(stopped)})")
        for lab in stopped:
            console.print(f"    [dim]{lab.name}  {lab.level}[/dim]")
        if unknown:
            console.print(f"\n  [yellow]? Sin datos[/yellow]  ({len(unknown)})")
            for lab in unknown:
                console.print(f"    [yellow]{lab.name}  {lab.level}[/yellow]")
        console.print()
    else:
        print(f"\n  {c('● Running', C.GREEN)}  ({len(running)})")
        for lab in running:
            print(f"    {c(lab.name, C.CYAN)}  {c(lab.level, C.MUTED)}")
        print(f"\n  {c('○ Stopped', C.MUTED)}  ({len(stopped)})")
        for lab in stopped:
            print(f"    {c(lab.name + '  ' + lab.level, C.MUTED)}")
        if unknown:
            print(f"\n  {c('? Sin datos', C.YELLOW)}  ({len(unknown)})")
            for lab in unknown:
                print(f"    {c(lab.name + '  ' + lab.level, C.YELLOW)}")
        print()
    return EXIT_OK


def cmd_logs(args) -> int:
    """Muestra los logs de un laboratorio."""
    labs = discover_labs()
    lab = _lab_or_exit(labs, args.lab)
    if lab is None:
        return EXIT_ERR

    follow = ["-f"] if args.follow else []
    tail = ["--tail", str(args.tail)] if args.tail else []
    try:
        return subprocess.run(["docker", "logs"] + follow + tail + [lab.name]).returncode
    except KeyboardInterrupt:
        return EXIT_OK


def cmd_shell(args) -> int:
    """Abre una shell interactiva dentro del contenedor de un lab."""
    labs = discover_labs()
    lab = _lab_or_exit(labs, args.lab)
    if lab is None:
        return EXIT_ERR

    if container_status(lab) != "running":
        print_err(f"El laboratorio '{lab.name}' no está en ejecución. Usa 'start' primero.")
        return EXIT_ERR

    shell = getattr(args, "shell", None) or "/bin/bash"
    print_info(f"Abriendo shell en {lab.name} ({shell})...")
    try:
        return subprocess.run(["docker", "exec", "-it", lab.name, shell]).returncode
    except KeyboardInterrupt:
        return EXIT_OK


def cmd_readme(args) -> int:
    """Muestra el README de un laboratorio."""
    labs = discover_labs()
    lab = _lab_or_exit(labs, args.lab)
    if lab is None:
        return EXIT_ERR

    if not lab.readme or not lab.readme.exists():
        print_warn("Este laboratorio no tiene README.")
        return EXIT_ERR

    content = lab.readme.read_text(encoding="utf-8", errors="replace")
    _render_readme_rich(content) if RICH else _render_readme_plain(content)
    return EXIT_OK


def cmd_flag(args) -> int:
    """Muestra la flag del lab (clave de solución)."""
    labs = discover_labs()
    lab = _lab_or_exit(labs, args.lab)
    if lab is None:
        return EXIT_ERR

    if not lab.flag:
        print_warn(f"{lab.name} no tiene flag definida (falta content/flag.txt).")
        return EXIT_ERR

    if RICH:
        console.print(Panel(f"[bold yellow]{lab.flag}[/bold yellow]",
                            title=f"[dim]Flag de {lab.name}[/dim]",
                            border_style="yellow", padding=(0, 2)))
    else:
        print(f"\n  {c(lab.flag, C.YELLOW)}\n")
    return EXIT_OK


def cmd_check(args) -> int:
    """Comprueba si la flag del lab se puede leer dentro del contenedor."""
    labs = discover_labs()
    lab = _lab_or_exit(labs, args.lab)
    if lab is None:
        return EXIT_ERR

    result = check_flag(lab)
    if result.solved:
        detail = c(result.detail, C.CYAN) if not RICH else f"[cyan]{result.detail}[/cyan]"
        print_ok(f"¡Lab superado! Flag en /root/flag.txt: {detail}")
        return EXIT_OK

    messages = {
        "absent": print_warn,
        "stopped": print_warn,
        "missing": print_err,
        "mismatch": print_err,
    }
    messages.get(result.state, print_err)(result.detail)
    if result.state == "absent":
        print_info("Crea content/flag.txt y añade el COPY al Dockerfile del lab.")
    return EXIT_ERR


def _ask_flag(lab: Lab, allow_stdin: bool = True) -> str:
    """Pide la flag por teclado, o la lee de stdin si viene por tubería.

    `allow_stdin=False` en el REPL: allí stdin es el bucle de comandos, así que
    leerlo entero se comería las líneas siguientes.
    """
    if allow_stdin and not sys.stdin.isatty():
        # `cat /root/flag.txt | warlabs solve lab-01` o un script que la pase.
        try:
            return sys.stdin.read()
        except OSError:
            return ""
    if RICH:
        return Prompt.ask(f"  [yellow]Flag de {lab.name}[/yellow]")
    return input(f"  {c('Flag de ' + lab.name + ': ', C.YELLOW)}")


def _progress_bar(done: int, total: int, width: int = 24) -> str:
    filled = round(width * done / total) if total else 0
    return "█" * filled + "░" * (width - filled)


def _celebrate(lab: Lab, result, labs: list[Lab], progress: dict) -> None:
    """Panel de lab superado + el siguiente pendiente que queda."""
    if RICH:
        note = "\n[dim]ya constaba como superado[/dim]" if result.already else ""
        console.print(Panel(
            f"[bold green]✓ {lab.name} superado[/bold green]{note}\n"
            f"[dim]flag entregada:[/dim] [bold yellow]{result.detail}[/bold yellow]",
            border_style="green", padding=(0, 2),
        ))
    else:
        print(f"\n  {c('✓ ' + lab.name + ' superado', C.GREEN)}"
              + (f" {c('(ya constaba)', C.MUTED)}" if result.already else ""))
        print(f"  {c('flag entregada: ' + result.detail, C.YELLOW)}\n")

    if not result.saved:
        print_warn(f"La flag es correcta, pero no se pudo guardar el progreso "
                   f"en {solved_path()}.")
        return

    pendientes = [l.name for l in labs if l.name not in progress]
    if pendientes:
        siguiente = pendientes[0]
        print_info(f"Siguiente pendiente: {siguiente}  →  warlabs start {siguiente}")
    else:
        print_ok("Has superado todos los labs. Enhorabuena.")


def cmd_submit(args) -> int:
    """Entrega la flag de un lab: comprueba si es la correcta y anota el progreso.

    A diferencia de `check`, que solo mira si el lab está bien montado, esto mide
    si la flag se ha resolvió de verdad: la que entregues se compara con
    content/flag.txt. No necesita Docker.
    """
    labs = discover_labs()
    lab = _lab_or_exit(labs, args.lab)
    if lab is None:
        return EXIT_ERR

    progress = load_progress()
    answer = getattr(args, "flag", None)
    if answer is None:
        try:
            answer = _ask_flag(lab, allow_stdin=getattr(args, "stdin", True))
        except (EOFError, KeyboardInterrupt):
            # Ctrl+D / Ctrl+C al preguntar: no es un fallo de la flag.
            print_info("Entrega cancelada.")
            return EXIT_USAGE

    result = submit_flag(lab, answer)

    if result.accepted:
        _celebrate(lab, result, labs, {**progress, lab.name: {}})
        return EXIT_OK

    if result.state == "absent":
        print_warn(result.detail)
        return EXIT_ERR

    if result.state == "empty":
        print_warn("No has entregado ninguna flag.")
        print_info(f"Pega la que encontraste en {FLAG_PATH} dentro del contenedor, "
                   "o usa 'warlabs submit <lab> -f FLAG{...}'.")
        return EXIT_USAGE

    print_err("Flag incorrecta. Vuelve a intentarlo.")
    return EXIT_ERR


def cmd_progress(args) -> int:
    """Muestra qué labs se han superado y cuánto queda."""
    labs = discover_labs()
    if not labs_or_exit(labs):
        return EXIT_ERR

    rows = progress_rows(labs)
    total = len(rows)
    hechos = [row for row in rows if row[1]]

    if getattr(args, "json", False):
        print(json.dumps({
            "superados": [lab.name for lab, _, _ in hechos],
            "pendientes": [lab.name for lab, ok, _ in rows if not ok],
            "resueltos": len(hechos),
            "total": total,
            "labs": [{"name": lab.name, "nivel": lab.level,
                      "superado": ok, "fecha": when}
                     for lab, ok, when in rows],
        }, ensure_ascii=False, indent=2))
        return EXIT_OK

    if RICH:
        table = Table(box=rich_box.ROUNDED, border_style="dim", header_style="bold cyan",
                      show_lines=True, expand=True)
        table.add_column("#",     style="dim",  width=4,  justify="right")
        table.add_column("Lab",   style="bold", min_width=12)
        table.add_column("Nivel", justify="center", width=10)
        table.add_column("Estado", justify="center", width=12)
        table.add_column("Superado", style="dim", width=22)

        for i, (lab, ok, when) in enumerate(rows, 1):
            estado = "[green]✓ superado[/green]" if ok else "[dim]· pendiente[/dim]"
            fecha = when[:10] if ok and when else "—"
            table.add_row(str(i), f"[bold]{lab.name}[/bold]",
                          f"[{LEVEL_COLOR.get(lab.level, 'white')}]{lab.level}[/]",
                          estado, fecha)

        console.print()
        console.print(table)
        console.print(f"  [bold green]{_progress_bar(len(hechos), total)}[/bold green] "
                      f"[bold]{len(hechos)}/{total}[/bold] labs superados")
        console.print(f"  [dim]Progreso en {solved_path()}[/dim]\n")
    else:
        for lab, ok, when in rows:
            mark = c("✓ superado", C.GREEN) if ok else c("· pendiente", C.MUTED)
            fecha = (when[:10] + " ") if when else " " * 10
            print(f"  {cpad(lab.name, 10, C.CYAN)}  {cpad(lab.level, 9, LEVEL_ANSI.get(lab.level, C.MUTED))}"
                  f"  {mark}  {c(fecha, C.MUTED)}")
        print(f"\n  {c(_progress_bar(len(hechos), total), C.GREEN)} "
              f"{c(f'{len(hechos)}/{total} labs superados', C.BOLD)}")
        print(f"  {c('Progreso en ' + str(solved_path()), C.MUTED)}\n")
    return EXIT_OK


def cmd_reset(args) -> int:
    """Olvida los labs superados: uno concreto, o todos con --all."""
    labs = discover_labs()
    lab = _lab_or_exit(labs, args.lab) if args.lab else None
    if args.lab and lab is None:
        return EXIT_ERR

    if getattr(args, "all", False):
        if not args.force and not confirm("¿Olvidar todos los labs superados?"):
            print_info("Operación cancelada.")
            return EXIT_OK
        cleared = reset_progress()
        if not cleared:
            print_warn("No había ningún lab superado que olvidar.")
        else:
            print_ok(f"Progreso olvidado: {', '.join(sorted(cleared))}.")
        return EXIT_OK

    if lab is None:
        print_err("Especifica un laboratorio o usa --all para olvidarlos todos.")
        return EXIT_USAGE

    if lab.name not in load_progress():
        print_warn(f"'{lab.name}' no constaba como superado.")
        return EXIT_OK

    if not args.force and not confirm(f"¿Olvidar el progreso de '{lab.name}'?"):
        print_info("Operación cancelada.")
        return EXIT_OK

    reset_progress([lab.name])
    print_ok(f"Progreso de '{lab.name}' olvidado.")
    return EXIT_OK


def cmd_watch(args) -> int:
    """Monitorea el estado de los labs en tiempo real."""
    labs = discover_labs()
    if not labs_or_exit(labs):
        return EXIT_ERR

    if not RICH:
        print_info("El modo watch requiere 'rich'. Instálalo con: pip install rich")
        return EXIT_ERR

    solved = load_progress()   # el progreso no cambia solo mientras miramos

    try:
        with Live(console=console, refresh_per_second=1) as live:
            while True:
                snap = snapshot(force=True)
                table = Table(
                    box=rich_box.SIMPLE,
                    border_style="dim",
                    header_style="bold cyan",
                    expand=True,
                    title="[dim]WarLabs — Watch  (Ctrl+C para salir)[/dim]",
                )
                table.add_column("Lab",     style="bold", min_width=14)
                table.add_column("Nivel",   justify="center", width=10)
                table.add_column("Estado",  justify="center", width=14)
                table.add_column("✓",       justify="center", width=6)

                for lab in labs:
                    status = container_status(lab, snap)
                    dot, dot_style = status_dot(status)
                    level_style = LEVEL_COLOR.get(lab.level, "white")
                    mark, mark_style, _ = solved_mark(lab, solved)
                    table.add_row(
                        lab.name,
                        f"[{level_style}]{lab.level}[/{level_style}]",
                        f"[{dot_style}]{dot}[/{dot_style}]",
                        f"[{mark_style}]{mark}[/{mark_style}]",
                    )
                live.update(table)
                time.sleep(STATUS_POLL_INTERVAL)
    except KeyboardInterrupt:
        print_info("Watch detenido.")
    return EXIT_OK


# ── Renderizado de README ─────────────────────────────────────────────────────

def _render_readme_rich(content: str):
    in_code = False
    code_buf: list[str] = []

    for line in content.splitlines():
        if line.strip().startswith("```"):
            if not in_code:
                in_code = True
                lang = line.strip().replace("```", "").strip() or "bash"
                code_buf = []
            else:
                in_code = False
                console.print(Panel(
                    Syntax("\n".join(code_buf), lang, theme="github-dark",
                           background_color="#161b22", word_wrap=True),
                    border_style="dim", padding=(0, 1),
                ))
            continue
        if in_code:
            code_buf.append(line)
            continue

        if line.startswith("# "):
            console.print(f"\n  [bold cyan]{line[2:]}[/bold cyan]")
            console.print(f"  [dim]{'─' * 50}[/dim]")
        elif line.startswith("## "):
            console.print(f"\n  [bold magenta]{line[3:]}[/bold magenta]")
        elif line.startswith("### "):
            console.print(f"\n  [bold yellow]{line[4:]}[/bold yellow]")
        elif re.match(r"^[-*+] ", line):
            console.print(f"    [green]•[/green] {_inline_rich(line[2:])}")
        elif line.strip() == "":
            console.print()
        else:
            console.print(f"  {_inline_rich(line)}")


def _inline_rich(text: str) -> str:
    text = re.sub(r"\*\*([^*]+)\*\*", r"[bold]\1[/bold]", text)
    text = re.sub(r"`([^`]+)`", r"[bold green on #1c2128]\1[/bold green on #1c2128]", text)
    return text


def _render_readme_plain(content: str):
    in_code = False
    for line in content.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            print(c("  " + ("┌" if in_code else "└") + "─" * 40, C.MUTED))
            continue
        if in_code:
            print(c("  │ " + line, C.GREEN))
            continue
        if line.startswith("# "):
            print(f"\n{c(line[2:].upper(), C.CYAN)}")
            print(c("─" * 50, C.MUTED))
        elif line.startswith("## "):
            print(f"\n{c(line[3:], C.PURPLE)}")
        elif line.startswith("### "):
            print(f"\n{c(line[4:], C.YELLOW)}")
        elif re.match(r"^[-*+] ", line):
            text = re.sub(r"\*\*([^*]+)\*\*", lambda m: c(m.group(1), C.BOLD), line[2:])
            print(f"  {c('•', C.GREEN)} {text}")
        elif line.strip() == "":
            print()
        else:
            text = re.sub(r"\*\*([^*]+)\*\*", lambda m: c(m.group(1), C.BOLD), line)
            print(f"  {text}")


# ── Modo interactivo ──────────────────────────────────────────────────────────

def _setup_readline(labs: list[Lab]) -> None:
    """Historial y completado con tabulador (si readline está disponible)."""
    try:
        import readline
    except ImportError:
        return

    readline.set_history_length(500)
    readline.parse_and_bind("tab: complete")
    try:
        readline.read_history_file(str(HISTORY_FILE))
    except (FileNotFoundError, OSError):
        pass
    readline.set_completer(_completer(labs))
    readline.set_completer_delims(" \t\n")


def _completer(labs: list[Lab]):
    import readline

    # Ojo: el `.split()` debe aplicarse a la cadena completa. El punto ata más
    # fuerte que la coma, así que `("a", "b").split()` intentaría hacer split de
    # la tupla y reventaría con AttributeError al montar el REPL.
    commands = " ".join((
        "list ls", "info i", "start up run", "stop down", "restart re",
        "status st", "logs", "shell sh exec", "readme r", "flag",
        "check", "solve s submit", "progress pr", "reset rs",
        "watch w", "clear cls", "help h ?", "exit quit q",
    )).split()
    names = [lab.name for lab in labs]
    prev = readline.get_line_buffer().split()

    def complete(text: str, state: int):
        options = names if len(prev) == 1 else commands
        matches = [o for o in options if o.startswith(text)]
        return matches[state] if state < len(matches) else None

    return complete


def _save_history() -> None:
    try:
        import readline
        readline.write_history_file(str(HISTORY_FILE))
    except (ImportError, OSError):
        pass


def interactive_mode() -> int:
    """Modo REPL interactivo cuando no se pasa ningún comando."""
    labs = discover_labs()
    if not labs_or_exit(labs):
        return EXIT_ERR

    _setup_readline(labs)
    print_info(f"Se encontraron {len(labs)} laboratorios en {Path(__file__).resolve().parent}\n")

    prompt = f"{c('warlabs', C.GREEN)}{c('>', C.MUTED)} "

    while True:
        try:
            # El prompt va como argumento de input(), nunca impreso aparte. Con
            # rich se imprimía el prompt y el input() solo existía en la rama
            # contraria: el bucle pedía entrada sin leerla y pintaba el prompt
            # infinitamente. Además, prompt en input() es lo que mantiene el
            # historial y el autocompletado de readline.
            parts = input(prompt).strip().split()
        except (KeyboardInterrupt, EOFError):       # Ctrl+C / Ctrl+D
            print(f"\n{c('Saliendo...', C.MUTED)}")
            break

        if not parts:
            continue

        cmd, *rest = parts
        arg = rest[0] if rest else None
        flags = set(rest[1:])

        if cmd in ("exit", "quit", "q", "salir"):
            print(c("Saliendo...", C.MUTED))
            break
        elif cmd in ("list", "ls", "l"):
            cmd_list(SimpleNamespace(level=arg, json=False))
        elif cmd in ("info", "i") and arg:
            cmd_info(SimpleNamespace(lab=arg, json=False))
        elif cmd in ("start", "up", "run") and arg:
            cmd_start(SimpleNamespace(lab=arg, verbose="-v" in flags, force="-f" in flags))
        elif cmd in ("stop", "down") and (arg == "--all" or "-a" in flags):
            cmd_stop(SimpleNamespace(lab=None, all=True, force="-f" in flags))
        elif cmd in ("stop", "down") and arg:
            cmd_stop(SimpleNamespace(lab=arg, all=False, force="-f" in flags))
        elif cmd in ("restart", "re") and arg:
            cmd_restart(SimpleNamespace(lab=arg, verbose="-v" in flags))
        elif cmd in ("clear", "cls"):
            clear_screen()
            print_banner()
        elif cmd in ("status", "st"):
            cmd_status(SimpleNamespace(json=False))
        elif cmd in ("readme", "r") and arg:
            cmd_readme(SimpleNamespace(lab=arg))
        elif cmd in ("flag", "f") and arg:
            cmd_flag(SimpleNamespace(lab=arg))
        elif cmd in ("check", "verify") and arg:
            cmd_check(SimpleNamespace(lab=arg))
        elif cmd in ("solve", "submit", "s") and arg:
            # `solve lab-01` pregunta la flag; `solve lab-01 FLAG{...}` la da.
            # stdin=False: dentro del REPL stdin es el bucle de comandos.
            extra = [p for p in rest[1:] if not p.startswith("-")]
            cmd_submit(SimpleNamespace(lab=arg, flag=extra[0] if extra else None,
                                       stdin=False))
        elif cmd in ("progress", "pr"):
            cmd_progress(SimpleNamespace(json=False))
        elif cmd in ("reset", "rs") and (arg == "--all" or "-a" in flags):
            cmd_reset(SimpleNamespace(lab=None, all=True, force="-f" in flags))
        elif cmd in ("reset", "rs") and arg:
            cmd_reset(SimpleNamespace(lab=arg, all=False, force="-f" in flags))
        elif cmd in ("logs") and arg:
            cmd_logs(SimpleNamespace(lab=arg, follow="-f" in flags, tail=50))
        elif cmd in ("shell", "sh", "exec") and arg:
            cmd_shell(SimpleNamespace(lab=arg, shell="/bin/bash"))
        elif cmd in ("watch", "w"):
            cmd_watch(SimpleNamespace())
        elif cmd in ("help", "h", "?"):
            _print_help()
        else:
            print_warn(f"Comando desconocido: '{cmd}'. Escribe 'help' para ver los comandos.")

    _save_history()
    return EXIT_OK


def _print_help():
    commands = [
        ("list [level]",      "Lista todos los labs (filtra por Fácil/Medio/Difícil)"),
        ("info <lab>",        "Muestra info y README de un lab"),
        ("start <lab>",       "Construye y lanza un lab"),
        ("stop <lab>",        "Detiene y elimina un lab"),
        ("stop --all",        "Detiene todos los labs activos"),
        ("restart <lab>",     "Reconstruye y reinicia un lab"),
        ("status",            "Estado actual de todos los contenedores"),
        ("logs <lab> [-f]",   "Muestra los logs del contenedor"),
        ("shell <lab>",       "Abre una shell dentro del contenedor"),
        ("readme <lab>",      "Muestra el README de un lab"),
        ("flag <lab>",        "Muestra la flag del lab (solución)"),
        ("check <lab>",       "Verifica la flag dentro del contenedor"),
        ("solve <lab> [flag]", "Entrega la flag: te dice si has superado el lab"),
        ("progress",          "Muestra los labs superados"),
        ("reset <lab>|--all", "Olvida un lab superado (o todos)"),
        ("clear",             "Limpia la consola"),
        ("watch",             "Monitoreo en tiempo real del estado"),
        ("exit / quit / salir", "Sale del modo interactivo"),
    ]

    if RICH:
        table = Table(box=rich_box.SIMPLE, border_style="dim", show_header=False, expand=False)
        table.add_column("Comando", style="bold cyan", min_width=22)
        table.add_column("Descripción", style="dim")
        for name, desc in commands:
            table.add_row(name, desc)
        console.print(Panel(table, title="[bold cyan]Comandos disponibles[/bold cyan]",
                            border_style="dim", padding=(0, 1)))
    else:
        print(f"\n  {c('Comandos disponibles:', C.CYAN)}\n")
        for name, desc in commands:
            print(f"  {cpad(name, 22, C.CYAN)}  {c(desc, C.MUTED)}")
        print()


# ── Punto de entrada ──────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="warlabs",
        description="WarLabs CLI — Gestor de laboratorios de hacking ético",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  warlabs                        Modo interactivo
  warlabs list                   Lista todos los labs
  warlabs list --json            Salida JSON para scripts
  warlabs list Fácil             Filtra por dificultad
  warlabs info lab-01            Info y README
  warlabs start lab-01           Lanza el lab-01
  warlabs stop lab-01            Detiene lab-01
  warlabs stop --all             Detiene todos los labs activos
  warlabs restart lab-01         Reconstruye y reinicia lab-01
  warlabs logs lab-01 -f         Sigue los logs en tiempo real
  warlabs shell lab-02           Abre bash dentro del contenedor
  warlabs flag lab-01            Muestra la flag del lab
  warlabs check lab-01           Verifica la flag en el contenedor
  warlabs solve lab-01           Entrega la flag (te la pide)
  warlabs solve lab-01 -f FLAG{...}   Entrega la flag directamente
  warlabs progress               Qué labs has superado
  warlabs reset lab-01           Olvida el progreso de un lab
  warlabs watch                  Monitoreo en tiempo real
        """,
    )

    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", aliases=["ls"], help="Lista todos los labs")
    p_list.add_argument("level", nargs="?", help="Filtrar por dificultad (Fácil/Medio/Difícil)")
    p_list.add_argument("--json", action="store_true", help="Salida en JSON")

    p_info = sub.add_parser("info", help="Muestra info y README de un lab")
    p_info.add_argument("lab", help="Nombre o número del lab")
    p_info.add_argument("--json", action="store_true", help="Solo metadatos, en JSON")

    p_start = sub.add_parser("start", aliases=["up"], help="Lanza un lab")
    p_start.add_argument("lab", help="Nombre o número del lab")
    p_start.add_argument("-v", "--verbose", action="store_true", help="Muestra la salida completa de Docker")
    p_start.add_argument("-f", "--force", action="store_true", help="Recrea aunque ya esté en ejecución")

    p_stop = sub.add_parser("stop", aliases=["down"], help="Detiene y elimina un lab")
    p_stop.add_argument("lab", nargs="?", default=None, help="Nombre o número del lab")
    p_stop.add_argument("-a", "--all", action="store_true", help="Detiene todos los labs activos")
    p_stop.add_argument("-f", "--force", action="store_true", help="Detiene sin pedir confirmación")

    sub.add_parser("status", aliases=["st"], help="Estado de todos los contenedores").add_argument(
        "--json", action="store_true", help="Salida en JSON")

    p_logs = sub.add_parser("logs", help="Muestra los logs de un lab")
    p_logs.add_argument("lab", help="Nombre o número del lab")
    p_logs.add_argument("-f", "--follow", action="store_true", help="Sigue los logs en tiempo real")
    p_logs.add_argument("--tail", type=int, default=50, help="Número de líneas a mostrar (default: 50)")

    p_shell = sub.add_parser("shell", aliases=["sh", "exec"], help="Abre una shell en el contenedor")
    p_shell.add_argument("lab", help="Nombre o número del lab")
    p_shell.add_argument("--shell", default="/bin/bash", help="Shell a ejecutar (default: /bin/bash)")

    p_readme = sub.add_parser("readme", aliases=["r"], help="Muestra el README de un lab")
    p_readme.add_argument("lab", help="Nombre o número del lab")

    p_restart = sub.add_parser("restart", aliases=["re"], help="Reconstruye y reinicia un lab")
    p_restart.add_argument("lab", help="Nombre o número del lab")
    p_restart.add_argument("-v", "--verbose", action="store_true", help="Muestra la salida completa de Docker")

    p_flag = sub.add_parser("flag", aliases=["f"], help="Muestra la flag del lab")
    p_flag.add_argument("lab", help="Nombre o número del lab")

    p_check = sub.add_parser("check", aliases=["verify"], help="Verifica la flag en el contenedor")
    p_check.add_argument("lab", help="Nombre o número del lab")

    p_solve = sub.add_parser("solve", aliases=["submit"], help="Entrega la flag de un lab")
    p_solve.add_argument("lab", help="Nombre o número del lab")
    p_solve.add_argument("-f", "--flag", default=None,
                         help="Flag a entregar (si no, se pide por teclado)")

    p_progress = sub.add_parser("progress", aliases=["pr"], help="Labs ya superados")
    p_progress.add_argument("--json", action="store_true", help="Salida en JSON")

    p_reset = sub.add_parser("reset", aliases=["rs"], help="Olvida labs superados")
    p_reset.add_argument("lab", nargs="?", default=None, help="Nombre o número del lab")
    p_reset.add_argument("-a", "--all", action="store_true", help="Olvida todos")
    p_reset.add_argument("-f", "--force", action="store_true", help="Sin pedir confirmación")

    sub.add_parser("watch", aliases=["w"], help="Monitoreo en tiempo real del estado")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        clear_screen()
        print_banner()
        return interactive_mode()

    dispatch = {
        "list": cmd_list, "ls": cmd_list,
        "info": cmd_info,
        "start": cmd_start, "up": cmd_start,
        "stop": cmd_stop, "down": cmd_stop,
        "status": cmd_status, "st": cmd_status,
        "logs": cmd_logs,
        "shell": cmd_shell, "sh": cmd_shell, "exec": cmd_shell,
        "readme": cmd_readme, "r": cmd_readme,
        "restart": cmd_restart, "re": cmd_restart,
        "flag": cmd_flag, "f": cmd_flag,
        "check": cmd_check, "verify": cmd_check,
        "solve": cmd_submit, "submit": cmd_submit,
        "progress": cmd_progress, "pr": cmd_progress,
        "reset": cmd_reset, "rs": cmd_reset,
        "watch": cmd_watch, "w": cmd_watch,
    }

    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return EXIT_USAGE

    # El banner va a stderr (y no se limpia la pantalla) cuando se pide --json:
    # si no, `warlabs list --json | jq` falla porque la salida no es JSON puro.
    wants_json = getattr(args, "json", False)
    if wants_json:
        print_banner(to_stderr=True)
    else:
        clear_screen()
        print_banner()

    try:
        return fn(args)
    except KeyboardInterrupt:
        print_warn("Interrumpido.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
