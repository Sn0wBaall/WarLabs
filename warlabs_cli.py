#!/usr/bin/env python3
"""
WarLabs CLI — Gestor de laboratorios (interfaz de línea de comandos)
Uso: python3 warlabs_cli.py [comando] [opciones]
"""

import subprocess
import argparse
import re
import os
import sys
import time
import socket
from pathlib import Path
from dataclasses import dataclass
from types import SimpleNamespace

# ── Dependencia opcional: rich ────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.live import Live
    from rich.columns import Columns
    from rich import box as rich_box
    from rich.prompt import Confirm
    from rich.syntax import Syntax
    RICH = True
except ImportError:
    RICH = False

# ── Constantes ────────────────────────────────────────────────────────────────
STATUS_POLL_INTERVAL = 8

# ── Colores ANSI (fallback sin rich) ─────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    GREEN   = "\033[38;2;63;185;80m"
    CYAN    = "\033[38;2;121;192;255m"
    PURPLE  = "\033[38;2;188;140;255m"
    YELLOW  = "\033[38;2;227;179;65m"
    RED     = "\033[38;2;248;81;73m"
    MUTED   = "\033[38;2;139;148;158m"
    BG      = "\033[48;2;13;17;23m"
    SURFACE = "\033[48;2;22;27;34m"

def c(text, color):
    return f"{color}{text}{C.RESET}"

# ── Consola rich ──────────────────────────────────────────────────────────────
console = Console(highlight=False) if RICH else None

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

def print_warn(msg):
    if RICH:
        console.print(f"  [bold][yellow]\\[~][/yellow][/bold] {msg}")
    else:
        print(f"  {c('[~]', C.YELLOW)} {msg}")

def _p(rich_fmt, plain_fmt):
    """Helper para imprimir con rich o plain según disponibilidad."""
    if RICH:
        console.print(rich_fmt)
    else:
        print(plain_fmt)

# ── Dataclass Lab ─────────────────────────────────────────────────────────────
@dataclass
class Lab:
    name:   str
    level:  str
    path:   Path
    desc:   str
    readme: Path | None

# ── Descubrimiento de labs ────────────────────────────────────────────────────
LEVEL_MAP = {
    "Facil":   "Fácil",
    "Medio":   "Medio",
    "Dificil": "Difícil",
}

LEVEL_COLOR = {
    "Fácil":   "green",
    "Medio":   "yellow",
    "Difícil": "red",
}

def _find_base_dir() -> Path:
    candidate = Path(__file__).resolve().parent
    for _ in range(5):
        if (candidate / "Facil").exists() or (candidate / "Medio").exists():
            return candidate
        candidate = candidate.parent
    return Path(__file__).resolve().parent

BASE_DIR = _find_base_dir()

def discover_labs() -> list[Lab]:
    labs = []
    for level_dir in ["Facil", "Medio", "Dificil"]:
        level_path = BASE_DIR / level_dir
        if not level_path.exists():
            continue
        for lab_dir in sorted(level_path.iterdir()):
            if not lab_dir.is_dir():
                continue
            if not (lab_dir / "Dockerfile").exists():
                continue
            readme = lab_dir / "README.md"
            desc = ""
            level_label = LEVEL_MAP.get(level_dir, level_dir)
            if readme.exists():
                lines = readme.read_text(encoding="utf-8").splitlines()
                for i, line in enumerate(lines):
                    if line.strip().startswith("### Descripción"):
                        for j in range(i + 1, min(i + 5, len(lines))):
                            if lines[j].strip():
                                desc = re.sub(r"\*\*([^*]+)\*\*", r"\1", lines[j].strip())
                                desc = re.sub(r"`([^`]+)`", r"\1", desc)
                                break
                        break
            labs.append(Lab(
                name=lab_dir.name,
                level=level_label,
                path=lab_dir,
                desc=desc or "Sin descripción disponible.",
                readme=readme if readme.exists() else None,
            ))
    return labs

def get_image_name(lab: Lab) -> str:
    run_sh = lab.path / "run.sh"
    if run_sh.exists():
        for line in run_sh.read_text().splitlines():
            if "image_name=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return f"warlabs/{lab.name.lower()}"

def container_status(lab: Lab) -> str:
    """
    Detecta el estado del contenedor de un lab.
    Intenta por nombre exacto primero, luego busca entre todos
    los contenedores por si fue lanzado con nombre distinto.
    """
    try:
        # Intento 1: nombre exacto del directorio (lab-01, lab-02...)
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", lab.name],
            capture_output=True, text=True, timeout=3
        )
        s = result.stdout.strip()
        if s and result.returncode == 0:
            return s

        # Intento 2: recorrer todos los contenedores (running + stopped)
        # por si el nombre difiere del nombre del directorio
        result2 = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=3
        )
        for line in result2.stdout.strip().splitlines():
            parts = line.split("\t", 1)
            if len(parts) < 2:
                continue
            cname, status_str = parts
            if cname == lab.name or lab.name in cname or cname in lab.name:
                return "running" if status_str.lower().startswith("up") else "stopped"

        return "stopped"
    except Exception:
        return "stopped"

def get_local_ip() -> str:
    for iface in ("wlan0", "eth0", "ens33", "enp0s3"):
        try:
            result = subprocess.run(
                ["ip", "-o", "-4", "addr", "show", iface],
                capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
                if m:
                    return m.group(1)
        except Exception:
            pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"

def parse_ports(lab: Lab) -> list[tuple[str, str]]:
    run_sh = lab.path / "run.sh"
    ports = []
    if not run_sh.exists():
        return ports
    content = run_sh.read_text()
    ssh = re.search(r'ssh_port="(\d+)"', content)
    web = re.search(r'web_port="(\d+)"', content)
    if ssh:
        ports.append((ssh.group(1), "22"))
    if web:
        p = web.group(1)
        ports.append((p, p))
    return ports

# ── Banner ────────────────────────────────────────────────────────────────────
BANNER = r"""
 ██╗    ██╗ █████╗ ██████╗ ██╗      █████╗ ██████╗ ███████╗
 ██║    ██║██╔══██╗██╔══██╗██║     ██╔══██╗██╔══██╗██╔════╝
 ██║ █╗ ██║███████║██████╔╝██║     ███████║██████╔╝███████╗
 ██║███╗██║██╔══██║██╔══██╗██║     ██╔══██║██╔══██╗╚════██║
 ╚███╔███╔╝██║  ██║██║  ██║███████╗██║  ██║██████╔╝███████║
  ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═════╝ ╚══════╝
"""

def print_banner():
    if RICH:
        console.print(f"[green]{BANNER}[/green]")
        console.print(
            "  [bold cyan]Plataforma de laboratorios de hacking ético[/bold cyan]"
            "  [dim]|[/dim]  "
            "[dim]github.com/Sn0wBaall[/dim]\n"
        )
    else:
        print(c(BANNER, C.GREEN))
        print(f"  {c('Plataforma de laboratorios de hacking ético', C.CYAN)}\n")

# ── Comandos ──────────────────────────────────────────────────────────────────

def cmd_list(args):
    """Muestra todos los laboratorios disponibles."""
    labs = discover_labs()

    if not labs:
        print_err("No se encontraron laboratorios. Verifica que estés en el directorio correcto.")
        return

    level_filter = args.level if hasattr(args, "level") and args.level else None
    if level_filter:
        def _norm(s):
            return s.lower().translate(str.maketrans("áéíóú", "aeiou"))
        level_filter_norm = _norm(level_filter)
        labs = [l for l in labs if _norm(l.level) == level_filter_norm or l.level == level_filter]

    if RICH:
        table = Table(
            box=rich_box.ROUNDED,
            border_style="dim",
            header_style="bold cyan",
            show_lines=True,
            expand=True,
        )
        table.add_column("#",        style="dim",    width=4,  justify="right")
        table.add_column("Lab",      style="bold",   min_width=12)
        table.add_column("Nivel",    justify="center", width=10)
        table.add_column("Estado",   justify="center", width=10)
        table.add_column("Descripción", style="dim", ratio=1)

        for i, lab in enumerate(labs, 1):
            status = container_status(lab)
            dot = "● running" if status == "running" else "○ stopped"
            dot_style = "green" if status == "running" else "dim"
            level_style = LEVEL_COLOR.get(lab.level, "white")
            table.add_row(
                str(i),
                f"[bold]{lab.name}[/bold]",
                f"[{level_style}]{lab.level}[/{level_style}]",
                f"[{dot_style}]{dot}[/{dot_style}]",
                lab.desc[:80] + ("…" if len(lab.desc) > 80 else ""),
            )

        console.print(table)
        console.print(f"  [dim]{len(labs)} laboratorio(s) encontrado(s)[/dim]\n")
    else:
        sep = c("─" * 70, C.MUTED)
        print(sep)
        print(f"  {c('#', C.MUTED):<6} {c('Lab', C.CYAN):<20} {c('level', C.CYAN):<10} {c('Estado', C.CYAN)}")
        print(sep)
        for i, lab in enumerate(labs, 1):
            status = container_status(lab)
            dot = c("●", C.GREEN) if status == "running" else c("○", C.MUTED)
            level_color = {
                "Fácil": C.GREEN, "Medio": C.YELLOW, "Difícil": C.RED
            }.get(lab.level, C.MUTED)
            print(f"  {c(str(i), C.MUTED):<6} {c(lab.name, C.CYAN):<20} {c(lab.level, level_color):<10} {dot}")
            print(f"  {c(' ' * 6 + lab.desc[:60], C.MUTED)}")
        print(sep)
        print(f"\n  {c(str(len(labs)) + ' laboratorio(s) encontrado(s)', C.MUTED)}\n")


def cmd_info(args):
    """Muestra la información detallada de un lab, incluyendo el README."""
    labs = discover_labs()
    lab = _resolve_lab(labs, args.lab)
    if not lab:
        return

    status = container_status(lab)
    dot = "● running" if status == "running" else "○ stopped"

    if RICH:
        level_style = LEVEL_COLOR.get(lab.level, "white")
        header = Text()
        header.append(f"  {lab.name}", style="bold cyan")
        header.append(f"  [{lab.level}]", style=level_style)
        header.append(f"  {dot}", style="green" if status == "running" else "dim")

        console.print(Panel(
            header,
            border_style="dim",
            expand=False,
            padding=(0, 1),
        ))
        console.print(f"\n  [dim]{lab.desc}[/dim]\n")
    else:
        level_color = {
            "Fácil": C.GREEN, "Medio": C.YELLOW, "Difícil": C.RED
        }.get(lab.level, C.MUTED)
        dot_str = c("●", C.GREEN) if status == "running" else c("○", C.MUTED)
        print(f"\n  {c(lab.name, C.CYAN)}  {c(lab.level, level_color)}  {dot_str}")
        print(f"  {c(lab.desc, C.MUTED)}\n")

    if lab.readme and lab.readme.exists():
        content = lab.readme.read_text(encoding="utf-8")
        if RICH:
            _render_readme_rich(content)
        else:
            _render_readme_plain(content)
    else:
        print_warn("Sin README disponible para este laboratorio.")


def cmd_start(args):
    """Construye y lanza un laboratorio."""
    labs = discover_labs()
    lab = _resolve_lab(labs, args.lab)
    if not lab:
        return

    status = container_status(lab)
    if status == "running":
        print_warn(f"El laboratorio '{lab.name}' ya está en ejecución.")
        return

    existing = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=5
    )
    if lab.name in existing.stdout.splitlines():
        print_info(f"Eliminando contenedor existente '{lab.name}'...")
        subprocess.run(["docker", "rm", "-f", lab.name], capture_output=True)

    image = get_image_name(lab)
    print_info(f"Construyendo imagen [bold]{image}[/bold]..." if RICH else f"Construyendo imagen {image}...")

    build = subprocess.run(
        ["docker", "build", "-t", image, "."],
        cwd=str(lab.path),
        capture_output=not args.verbose,
        text=True
    )

    if build.returncode != 0:
        print_err("Error al construir la imagen:")
        if not args.verbose and build.stderr:
            print(build.stderr[-1000:])
        return

    print_ok("Imagen construida correctamente.")

    ports = parse_ports(lab)
    port_args = []
    for host, cont in ports:
        port_args += ["-p", f"0.0.0.0:{host}:{cont}"]

    run_cmd = ["docker", "run", "-d", "--name", lab.name] + port_args + [image]
    run = subprocess.run(run_cmd, capture_output=True, text=True)

    if run.returncode != 0:
        err = run.stderr.strip()
        print_err(f"Error al iniciar el contenedor:\n{err}")
        return

    ip = get_local_ip()
    print_ok(f"Laboratorio [bold cyan]{lab.name}[/bold cyan] en ejecución." if RICH
             else f"Laboratorio {lab.name} en ejecución.")

    if ports:
        print()
        for host, cont in ports:
            if cont == "22":
                endpoint = f"ssh {ip} -p {host}"
            else:
                endpoint = f"http://{ip}:{host}"
            if RICH:
                console.print(f"    [dim]→[/dim]  [bold green]{endpoint}[/bold green]")
            else:
                print(f"    {c('→', C.MUTED)}  {c(endpoint, C.GREEN)}")
    print()


def cmd_stop(args):
    """Detiene y elimina laboratorios."""
    labs = discover_labs()

    if getattr(args, "all", False):
        targets = [l for l in labs if container_status(l) == "running"]
        if not targets:
            print_warn("No hay laboratorios en ejecución.")
            return
        if not args.force:
            if RICH:
                confirmed = Confirm.ask(
                    f"  [yellow]¿Detener y eliminar todos los [/yellow]"
                    f"[bold cyan]{len(targets)}[/bold cyan][yellow] laboratorios activos?[/yellow]",
                    default=False
                )
            else:
                ans = input(f"  {c('¿Detener todos los laboratorios activos? [s/N]: ', C.YELLOW)}")
                confirmed = ans.strip().lower() in ("s", "si", "sí", "y", "yes")
            if not confirmed:
                print_info("Operación cancelada.")
                return
        for lab in targets:
            print_info(f"Deteniendo {lab.name}...")
            subprocess.run(["docker", "rm", "-f", lab.name], capture_output=True)
            print_ok(f"'{lab.name}' detenido.")
        return

    if not args.lab:
        print_err("Especifica un laboratorio o usa --all para detener todos.")
        return

    lab = _resolve_lab(labs, args.lab)
    if not lab:
        return

    status = container_status(lab)
    if status != "running":
        print_warn(f"El laboratorio '{lab.name}' no está en ejecución.")
        return

    if not args.force:
        if RICH:
            confirmed = Confirm.ask(
                f"  [yellow]¿Seguro que quieres detener y eliminar[/yellow] "
                f"[bold cyan]{lab.name}[/bold cyan][yellow]?[/yellow]",
                default=False
            )
        else:
            ans = input(f"  {c('¿Detener y eliminar', C.YELLOW)} {c(lab.name, C.CYAN)}{c('? [s/N]: ', C.YELLOW)}")
            confirmed = ans.strip().lower() in ("s", "si", "sí", "y", "yes")

        if not confirmed:
            print_info("Operación cancelada.")
            return

    print_info(f"Deteniendo {lab.name}...")
    stop = subprocess.run(
        ["docker", "rm", "-f", lab.name],
        capture_output=True, text=True
    )

    if stop.returncode == 0:
        print_ok(f"Laboratorio '{lab.name}' detenido y eliminado.")
    else:
        print_err(stop.stderr.strip())


def cmd_restart(args):
    """Reinicia un laboratorio (stop + start)."""
    labs = discover_labs()
    lab = _resolve_lab(labs, args.lab)
    if not lab:
        return

    print_info(f"Reiniciando {lab.name}...")
    status = container_status(lab)
    if status == "running":
        subprocess.run(["docker", "rm", "-f", lab.name], capture_output=True)
        print_ok("Contenedor detenido.")

    image = get_image_name(lab)
    build = subprocess.run(
        ["docker", "build", "-t", image, "."],
        cwd=str(lab.path), capture_output=not args.verbose, text=True
    )
    if build.returncode != 0:
        print_err("Error al construir la imagen:")
        if not args.verbose and build.stderr:
            print(build.stderr[-1000:])
        return

    ports = parse_ports(lab)
    port_args = []
    for h, c in ports:
        port_args += ["-p", f"0.0.0.0:{h}:{c}"]

    run = subprocess.run(
        ["docker", "run", "-d", "--name", lab.name] + port_args + [image],
        capture_output=True, text=True
    )
    if run.returncode != 0:
        print_err(f"Error al iniciar:\n{run.stderr.strip()}")
        return

    ip = get_local_ip()
    print_ok(f"Laboratorio '{lab.name}' reiniciado.")
    if ports:
        for h, c in ports:
            endpoint = f"ssh {ip} -p {h}" if c == "22" else f"http://{ip}:{h}"
            _p(f"    [dim]→[/dim]  [bold green]{endpoint}[/bold green]",
              f"    {c('→', C.MUTED)}  {c(endpoint, C.GREEN)}")


def cmd_status(args):
    """Muestra el estado actual de todos los contenedores de labs."""
    labs = discover_labs()

    running = []
    stopped = []
    for lab in labs:
        status = container_status(lab)
        if status == "running":
            running.append(lab)
        else:
            stopped.append(lab)

    if RICH:
        console.print(f"\n  [bold green]● Running[/bold green]  ({len(running)})")
        for lab in running:
            console.print(f"    [cyan]{lab.name}[/cyan]  [dim]{lab.level}[/dim]")

        console.print(f"\n  [dim]○ Stopped[/dim]  ({len(stopped)})")
        for lab in stopped:
            console.print(f"    [dim]{lab.name}  {lab.level}[/dim]")
        console.print()
    else:
        print(f"\n  {c('● Running', C.GREEN)}  ({len(running)})")
        for lab in running:
            print(f"    {c(lab.name, C.CYAN)}  {c(lab.level, C.MUTED)}")
        print(f"\n  {c('○ Stopped', C.MUTED)}  ({len(stopped)})")
        for lab in stopped:
            print(f"    {c(lab.name + '  ' + lab.level, C.MUTED)}")
        print()


def cmd_logs(args):
    """Muestra los logs de un laboratorio en ejecución."""
    labs = discover_labs()
    lab = _resolve_lab(labs, args.lab)
    if not lab:
        return

    try:
        follow = ["-f"] if args.follow else []
        tail = ["--tail", str(args.tail)] if hasattr(args, "tail") and args.tail else []
        subprocess.run(["docker", "logs"] + follow + tail + [lab.name])
    except KeyboardInterrupt:
        pass


def cmd_shell(args):
    """Abre una shell interactiva dentro del contenedor de un lab."""
    labs = discover_labs()
    lab = _resolve_lab(labs, args.lab)
    if not lab:
        return

    status = container_status(lab)
    if status != "running":
        print_err(f"El laboratorio '{lab.name}' no está en ejecución. Usa 'start' primero.")
        return

    shell = args.shell if hasattr(args, "shell") and args.shell else "/bin/bash"
    print_info(f"Abriendo shell en [bold]{lab.name}[/bold] ({shell})..." if RICH
               else f"Abriendo shell en {lab.name} ({shell})...")
    subprocess.run(["docker", "exec", "-it", lab.name, shell])


def cmd_readme(args):
    """Muestra el README de un laboratorio."""
    labs = discover_labs()
    lab = _resolve_lab(labs, args.lab)
    if not lab:
        return

    if not lab.readme or not lab.readme.exists():
        print_warn("Este laboratorio no tiene README.")
        return

    content = lab.readme.read_text(encoding="utf-8")
    if RICH:
        _render_readme_rich(content)
    else:
        _render_readme_plain(content)


def cmd_watch(args):
    """Monitorea el estado de los labs en tiempo real."""
    labs = discover_labs()

    if not RICH:
        print_info("El modo watch requiere 'rich'. Instálalo con: pip install rich")
        return

    try:
        with Live(console=console, refresh_per_second=0.5) as live:
            while True:
                table = Table(
                    box=rich_box.SIMPLE,
                    border_style="dim",
                    header_style="bold cyan",
                    expand=True,
                    title=f"[dim]WarLabs — Watch  (Ctrl+C para salir)[/dim]",
                )
                table.add_column("Lab",    style="bold", min_width=14)
                table.add_column("level",  justify="center", width=10)
                table.add_column("Estado", justify="center", width=14)

                for lab in labs:
                    status = container_status(lab)
                    dot = "● running" if status == "running" else "○ stopped"
                    dot_style = "green" if status == "running" else "dim"
                    level_style = LEVEL_COLOR.get(lab.level, "white")
                    table.add_row(
                        lab.name,
                        f"[{level_style}]{lab.level}[/{level_style}]",
                        f"[{dot_style}]{dot}[/{dot_style}]",
                    )

                live.update(table)
                time.sleep(STATUS_POLL_INTERVAL)

    except KeyboardInterrupt:
        print_info("Watch detenido.")


# ── Helpers de renderizado README ─────────────────────────────────────────────

def _render_readme_rich(content: str):
    in_code = False
    code_buf = []

    for line in content.splitlines():
        if line.strip().startswith("```"):
            if not in_code:
                in_code = True
                lang = line.strip().replace("```", "").strip() or "bash"
                code_buf = []
            else:
                in_code = False
                syntax = Syntax(
                    "\n".join(code_buf),
                    lang,
                    theme="github-dark",
                    background_color="#161b22",
                    word_wrap=True,
                )
                console.print(Panel(syntax, border_style="dim", padding=(0, 1)))
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
        elif re.match(r'^[-*+] ', line):
            text = _inline_rich(line[2:])
            console.print(f"    [green]•[/green] {text}")
        elif line.strip() == "":
            console.print()
        else:
            console.print(f"  {_inline_rich(line)}")


def _inline_rich(text: str) -> str:
    text = re.sub(r'\*\*([^*]+)\*\*', r'[bold]\1[/bold]', text)
    text = re.sub(r'`([^`]+)`', r'[bold green on #1c2128]\1[/bold green on #1c2128]', text)
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
        elif re.match(r'^[-*+] ', line):
            text = re.sub(r'\*\*([^*]+)\*\*', lambda m: c(m.group(1), C.BOLD), line[2:])
            print(f"  {c('•', C.GREEN)} {text}")
        elif line.strip() == "":
            print()
        else:
            text = re.sub(r'\*\*([^*]+)\*\*', lambda m: c(m.group(1), C.BOLD), line)
            print(f"  {text}")


# ── Resolver lab por nombre o índice ──────────────────────────────────────────

def _resolve_lab(labs: list[Lab], identifier: str) -> Lab | None:
    if not identifier:
        return None
    identifier = identifier.strip()
    if not identifier:
        return None

    if identifier.isdigit():
        idx = int(identifier) - 1
        if 0 <= idx < len(labs):
            return labs[idx]
        print_err(f"Índice '{identifier}' fuera de rango. Hay {len(labs)} labs.")
        return None

    target = identifier.lower()

    exact = [l for l in labs if l.name.lower() == target]
    if len(exact) == 1:
        return exact[0]

    prefix = [l for l in labs if l.name.lower().startswith(target)]
    if len(prefix) == 1:
        return prefix[0]

    substr = [l for l in labs if target in l.name.lower()]
    if len(substr) == 1:
        return substr[0]

    if len(exact) > 1 or len(prefix) > 1 or len(substr) > 1:
        candidates = set(l.name for l in exact + prefix + substr)
        print_warn(f"Coincidencia ambigua. Labs: {', '.join(sorted(candidates))}")
        return None

    print_err(f"No se encontró ningún lab con nombre o índice '{identifier}'.")
    print_info("Usa 'list' para ver los labs disponibles.")
    return None


# ── Modo interactivo ──────────────────────────────────────────────────────────

def interactive_mode():
    """Modo REPL interactivo cuando no se pasa ningún comando."""
    labs = discover_labs()
    if not labs:
        print_err("No se encontraron laboratorios.")
        return

    print_info(f"Se encontraron {c(str(len(labs)), C.CYAN) if not RICH else len(labs)} laboratorios en {BASE_DIR}\n")

    while True:
        try:
            if RICH:
                console.print("[bold green]warlabs[/bold green][dim]>[/dim] ", end="")
                raw = input()
            else:
                raw = input(f"{c('warlabs', C.GREEN)}{c('>', C.MUTED)} ")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{c('Saliendo...', C.MUTED)}")
            break

        parts = raw.strip().split()
        if not parts:
            continue

        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None

        if cmd in ("exit", "quit", "q"):
            print(c("Saliendo...", C.MUTED))
            break
        elif cmd in ("list", "ls", "l"):
            cmd_list(SimpleNamespace(level=arg))
        elif cmd in ("info", "i") and arg:
            cmd_info(SimpleNamespace(lab=arg))
        elif cmd in ("start", "up", "run") and arg:
            cmd_start(SimpleNamespace(lab=arg, verbose=False))
        elif cmd in ("stop", "down") and arg == "--all":
            cmd_stop(SimpleNamespace(lab=None, all=True, force=False))
        elif cmd in ("stop", "down") and arg:
            cmd_stop(SimpleNamespace(lab=arg, all=False, force=False))
        elif cmd in ("restart", "re") and arg:
            cmd_restart(SimpleNamespace(lab=arg, verbose=False))
        elif cmd in ("clear", "cls"):
            os.system("clear")
            print_banner()
        elif cmd in ("status", "st"):
            cmd_status(SimpleNamespace())
        elif cmd in ("readme", "r") and arg:
            cmd_readme(SimpleNamespace(lab=arg))
        elif cmd in ("logs") and arg:
            cmd_logs(SimpleNamespace(lab=arg, follow="-f" in parts, tail=50))
        elif cmd in ("shell", "sh", "exec") and arg:
            cmd_shell(SimpleNamespace(lab=arg, shell="/bin/bash"))
        elif cmd in ("watch", "w"):
            cmd_watch(SimpleNamespace())
        elif cmd in ("help", "h", "?"):
            _print_help()
        else:
            print_warn(f"Comando desconocido: '{cmd}'. Escribe 'help' para ver los comandos.")


def _print_help():
    if RICH:
        table = Table(box=rich_box.SIMPLE, border_style="dim", show_header=False, expand=False)
        table.add_column("Comando", style="bold cyan", min_width=22)
        table.add_column("Descripción", style="dim")

        cmds = [
            ("list [level]",           "Lista todos los labs (filtra por Fácil/Medio/Difícil)"),
            ("info <lab>",             "Muestra info y README de un lab"),
            ("start <lab>",            "Construye y lanza un lab"),
            ("stop <lab>",             "Detiene y elimina un lab"),
            ("stop --all",             "Detiene todos los labs activos"),
            ("restart <lab>",          "Reconstruye y reinicia un lab"),
            ("status",                 "Estado actual de todos los contenedores"),
            ("logs <lab> [-f]",        "Muestra los logs del contenedor"),
            ("shell <lab>",            "Abre una shell dentro del contenedor"),
            ("readme <lab>",           "Muestra el README de un lab"),
            ("clear",                  "Limpia la consola"),
            ("watch",                  "Monitoreo en tiempo real del estado"),
            ("exit / quit",            "Sale del modo interactivo"),
        ]
        for c_name, c_desc in cmds:
            table.add_row(c_name, c_desc)

        console.print(Panel(table, title="[bold cyan]Comandos disponibles[/bold cyan]",
                           border_style="dim", padding=(0, 1)))
    else:
        print(f"\n  {c('Comandos disponibles:', C.CYAN)}\n")
        cmds = [
            ("list [level]",    "Lista todos los labs"),
            ("info <lab>",      "Info y README de un lab"),
            ("start <lab>",     "Lanza un lab"),
            ("stop <lab>",      "Detiene un lab"),
            ("stop --all",      "Detiene todos los labs activos"),
            ("restart <lab>",   "Reconstruye y reinicia un lab"),
            ("status",          "Estado de los contenedores"),
            ("logs <lab>",      "Logs del contenedor"),
            ("shell <lab>",     "Shell dentro del contenedor"),
            ("readme <lab>",    "Muestra el README"),
            ("clear",           "Limpia la consola"),
            ("watch",           "Monitoreo en tiempo real"),
            ("exit",            "Salir"),
        ]
        for name, desc in cmds:
            print(f"  {c(name, C.CYAN):<22}  {c(desc, C.MUTED)}")
        print()


# ── Punto de entrada ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="warlabs",
        description="WarLabs CLI — Gestor de laboratorios de hacking ético",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  warlabs                        Modo interactivo
  warlabs list                   Lista todos los labs
  warlabs list Fácil             Filtra por dificultad
  warlabs start lab-01           Lanza el lab-01
  warlabs stop lab-01            Detiene lab-01
  warlabs stop --all             Detiene todos los labs activos
  warlabs restart lab-01         Reconstruye y reinicia lab-01
  warlabs logs lab-01 -f         Sigue los logs en tiempo real
  warlabs shell lab-02           Abre bash dentro del contenedor
  warlabs watch                  Monitoreo en tiempo real
        """,
    )

    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", aliases=["ls"], help="Lista todos los labs")
    p_list.add_argument("level", nargs="?", help="Filtrar por dificultad (Fácil/Medio/Difícil)")

    # info
    p_info = sub.add_parser("info", help="Muestra info y README de un lab")
    p_info.add_argument("lab", help="Nombre o número del lab")

    # start
    p_start = sub.add_parser("start", aliases=["up"], help="Lanza un lab")
    p_start.add_argument("lab", help="Nombre o número del lab")
    p_start.add_argument("-v", "--verbose", action="store_true", help="Muestra la salida completa de Docker")

    # stop
    p_stop = sub.add_parser("stop", aliases=["down"], help="Detiene y elimina un lab")
    p_stop.add_argument("lab", nargs="?", default=None, help="Nombre o número del lab")
    p_stop.add_argument("-a", "--all", action="store_true", help="Detiene todos los labs activos")
    p_stop.add_argument("-f", "--force", action="store_true", help="Detiene sin pedir confirmación")

    # status
    sub.add_parser("status", aliases=["st"], help="Estado de todos los contenedores")

    # logs
    p_logs = sub.add_parser("logs", help="Muestra los logs de un lab")
    p_logs.add_argument("lab", help="Nombre o número del lab")
    p_logs.add_argument("-f", "--follow", action="store_true", help="Sigue los logs en tiempo real")
    p_logs.add_argument("--tail", type=int, default=50, help="Número de líneas a mostrar (default: 50)")

    # shell
    p_shell = sub.add_parser("shell", aliases=["sh", "exec"], help="Abre una shell en el contenedor")
    p_shell.add_argument("lab", help="Nombre o número del lab")
    p_shell.add_argument("--shell", default="/bin/bash", help="Shell a ejecutar (default: /bin/bash)")

    # readme
    p_readme = sub.add_parser("readme", aliases=["r"], help="Muestra el README de un lab")
    p_readme.add_argument("lab", help="Nombre o número del lab")

    # restart
    p_restart = sub.add_parser("restart", aliases=["re"], help="Reconstruye y reinicia un lab")
    p_restart.add_argument("lab", help="Nombre o número del lab")
    p_restart.add_argument("-v", "--verbose", action="store_true", help="Muestra la salida completa de Docker")

    # watch
    sub.add_parser("watch", aliases=["w"], help="Monitoreo en tiempo real del estado")

    args = parser.parse_args()

    if args.command is None:
        print_banner()
        interactive_mode()
        return

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
        "watch": cmd_watch, "w": cmd_watch,
    }

    fn = dispatch.get(args.command)
    if fn:
        print_banner()
        fn(args)


if __name__ == "__main__":
    os.system("clear")
    main()
