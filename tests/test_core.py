"""
Tests de warlabs_core: parsing de run.sh, descubrimiento, resolución de labs y
estado de contenedores. No requieren Docker (se sustituye subprocess).

    python3 -m pytest tests/ -v
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import warlabs_core as core  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def no_snapshot_cache():
    """Cada test parte de la caché de snapshot vacía."""
    core._snapshot_cache.clear()
    core._snapshot_time = 0.0
    core._snapshot_error = None
    yield
    core._snapshot_cache.clear()
    core._snapshot_time = 0.0
    core._snapshot_error = None


@pytest.fixture
def labs():
    return core.discover_labs()


@pytest.fixture(autouse=True)
def progreso_aislado(monkeypatch, tmp_path):
    """El progreso va a un fichero temporal: los tests no tocan el del usuario."""
    path = tmp_path / "solved.json"
    monkeypatch.setenv("WARLABS_SOLVED", str(path))
    return path


class FakeResult:
    """Doble de subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def fake_run(returncode=0, stdout="", stderr=""):
    return FakeResult(returncode, stdout, stderr)


# ── Descubrimiento ────────────────────────────────────────────────────────────

def test_discover_labs_encuentra_los_tres(labs):
    """Averigua qué labs hay, en vez de fijar el número.

    El recuento se deriva del repo para que añadir un lab no rompa el test.
    Lo que sí se fija es lo que el descubrimiento garantiza: orden estable,
    un directorio por lab, nombre = nombre de la carpeta.
    """
    esperados = sorted(
        p.name for nivel in core.LEVEL_DIRS
        for p in (core.BASE_DIR / nivel).glob("lab-*")
        if p.is_dir() and (p / "Dockerfile").is_file()
    ) if any((core.BASE_DIR / n).is_dir() for n in core.LEVEL_DIRS) else []

    assert [lab.name for lab in labs] == esperados
    assert labs, "el repositorio debe tener al menos un lab"


def test_descubrimiento_usa_el_nombre_del_directorio_como_nivel(labs):
    """El nivel viene del directorio que contiene el lab, no de su nombre."""
    niveles = {lab.name: lab.level for lab in labs}
    assert niveles["lab-01"] == "Fácil"
    assert niveles["lab-03"] == "Fácil"


def test_cada_lab_descubierto_cumple_las_convenciones(labs):
    """Las reglas de CREAR-LABS.md, comprobadas por el propio repo.

    Si un lab nuevo se salta una convención, esto falla en vez de que se note
    en la GUI a medias.
    """
    for lab in labs:
        assert lab.readme, f"{lab.name}: falta README.md"
        assert lab.flag, f"{lab.name}: falta content/flag.txt"
        assert lab.flag.startswith("FLAG{") and lab.flag.endswith("}"), \
            f"{lab.name}: flag con formato raro -> {lab.flag}"
        # Estilo leet: el cuerpo lleva dígitos en lugar de letras (CREAR-LABS.md).
        # isalpha() no sirve aquí porque los "_" ya hacen que devuelva False.
        cuerpo = lab.flag[len("FLAG{"):-1]
        assert any(ch.isdigit() for ch in cuerpo), \
            f"{lab.name}: el cuerpo de la flag debería llevar leet -> {lab.flag}"
        assert lab.image == lab.image.lower(), \
            f"{lab.name}: Docker exige el nombre de imagen en minúsculas"
        assert not lab.warnings(), f"{lab.name}: {lab.warnings()}"
        assert lab.desc and lab.desc != "Sin descripción disponible.", \
            f"{lab.name}: el README necesita un heading '### Descripción'"
        assert lab.objective, f"{lab.name}: el README necesita '### Objetivo'"
        assert lab.ports, f"{lab.name}: no publica ningún puerto"


def test_descubrimiento_ignora_directorios_sin_dockerfile(tmp_path):
    (tmp_path / "Facil" / "lab-99").mkdir(parents=True)
    (tmp_path / "Facil" / "nota.txt").write_text("no es un lab")
    assert core.discover_labs(tmp_path) == []


def test_descripcion_se_Extrae_del_readme(labs):
    lab = next(l for l in labs if l.name == "lab-01")
    assert lab.desc
    assert "SSH" in lab.desc or "enumeración" in lab.desc


def test_objetivo_se_extrae_del_readme(labs):
    lab = next(l for l in labs if l.name == "lab-01")
    assert "root" in lab.objective.lower()


# ── Flags ─────────────────────────────────────────────────────────────────────

def test_todos_labs_tienen_flag(labs):
    for lab in labs:
        assert lab.flag, f"{lab.name} no tiene flag"


def test_flag_se_lee_de_content_flag_txt(labs):
    lab = next(l for l in labs if l.name == "lab-03")
    assert lab.flag.startswith("FLAG{")


def test_lab_sin_flag_devuelve_none(tmp_path):
    lab_dir = tmp_path / "Facil" / "lab-01"
    lab_dir.mkdir(parents=True)
    (lab_dir / "Dockerfile").write_text("FROM debian")
    lab = core.discover_labs(tmp_path)[0]
    assert lab.flag is None


# ── Parsing de run.sh ─────────────────────────────────────────────────────────

def test_imagen_se_lee_del_run_sh(labs):
    images = {lab.name: lab.image for lab in labs}
    assert images["lab-01"] == "warlabs/ssh-lab"
    assert images["lab-02"] == "warlabs/php-lab"
    assert images["lab-03"] == "warlabs/lfi-lab"


def test_puertos_se_leen_del_run_sh(labs):
    lab = next(l for l in labs if l.name == "lab-01")
    assert [(p.host, p.container) for p in lab.ports] == [("22", "22"), ("80", "80")]


def test_puerto_ssh_se_marca_como_ssh(labs):
    lab = next(l for l in labs if l.name == "lab-01")
    assert lab.ports[0].kind == "ssh"
    assert lab.ports[1].kind == "http"


def test_puertos_desde_flags_extra_del_run_sh():
    """Un flag con valor no puede perderlo al separarlo de los puertos."""
    tokens = ["-d", "--name", "lab-x", "--sysctl", "kernel.randomize_va_space=0",
              "-p", "22:22", "warlabs/ejemplo"]
    ports, extra = core.split_run_tokens(tokens)
    assert [p.host for p in ports] == ["22"]
    assert extra == ["--sysctl", "kernel.randomize_va_space=0"]


def test_flags_con_valor_se_conservan_enteros():
    tokens = ["--cap-add", "NET_ADMIN", "--sysctl", "net.ipv4.ip_forward=1",
              "-e", "A=1", "img"]
    _, extra = core.split_run_tokens(tokens)
    assert extra == ["--cap-add", "NET_ADMIN", "--sysctl", "net.ipv4.ip_forward=1",
                     "-e", "A=1"]


def test_run_command_incluye_flags_extra(labs):
    """El launcher ya no reconstruye el docker run a mano: usa el del run.sh."""
    lab = next(l for l in labs if l.name == "lab-01")
    cmd = core.run_command(lab)
    assert cmd[:4] == ["docker", "run", "-d", "--name"]
    assert "lab-01" in cmd
    assert cmd[-1] == "warlabs/ssh-lab"
    assert "0.0.0.0:22:22" in cmd


def test_run_command_publica_en_todas_las_interfaces(labs):
    lab = next(l for l in labs if l.name == "lab-01")
    assert all(p.arg.startswith("0.0.0.0:") for p in lab.ports)


def test_parse_sh_vars_quita_comillas():
    vars_ = core.parse_sh_vars('image_name="WarLabs/x"\nssh_port="22"\n')
    assert vars_["image_name"] == "WarLabs/x"
    assert vars_["ssh_port"] == "22"


def test_expand_resuelve_variables():
    vars_ = {"ssh_port": "2222", "image_name": "img"}
    assert core.expand("${ssh_port}:22", vars_) == "2222:22"
    assert core.expand("$image_name", vars_) == "img"


# ── Avisos de sysctl ──────────────────────────────────────────────────────────

def test_sysctl_no_namespaced_genera_aviso(tmp_path):
    lab = core.Lab(
        name="lab-x", level="Medio", path=tmp_path, desc="", readme=None,
        image="img", extra_args=["--sysctl", "kernel.randomize_va_space=0"],
    )
    warnings = lab.warnings()
    assert warnings
    assert "kernel.randomize_va_space" in warnings[0]


def test_sysctl_namespaced_no_avisa(tmp_path):
    lab = core.Lab(
        name="lab-y", level="Medio", path=tmp_path, desc="", readme=None,
        image="img", extra_args=["--sysctl", "net.ipv4.ip_forward=1"],
    )
    assert lab.warnings() == []


def test_sysctl_is_namespaced():
    assert core.sysctl_is_namespaced("net.ipv4.ip_forward")
    assert core.sysctl_is_namespaced("kernel.shm_rmid_forced")
    assert not core.sysctl_is_namespaced("kernel.randomize_va_space")
    assert not core.sysctl_is_namespaced("kernel.core_pattern")


# ── Resolución de labs ────────────────────────────────────────────────────────

def test_resolve_por_nombre_exacto(labs):
    lab, error = core.resolve_lab(labs, "lab-02")
    assert lab.name == "lab-02"
    assert error is None


def test_resolve_por_indice(labs):
    lab, error = core.resolve_lab(labs, "3")
    assert lab.name == "lab-03"
    assert error is None


def test_resolve_por_prefijo_unico(labs):
    """Con los tres labs reales `lab-0` es ambiguo: hace falta un caso sintético."""
    import dataclasses
    renombrado = [dataclasses.replace(labs[0], name="entorno-web")] + labs

    lab, error = core.resolve_lab(renombrado, "entorno")
    assert lab.name == "entorno-web"
    assert error is None


def test_resolve_ambiguo_avisa(labs):
    lab, error = core.resolve_lab(labs, "lab-0")
    assert lab is None
    assert "ambigua" in error


def test_resolve_inexistente_devuelve_error(labs):
    # Nombre que no puede existir en el repo: si alguien crea un lab llamado
    # exactamente así, este test empezaría a pasar por el motivo equivocado.
    ausente = next(f"lab-inexistente-{i}" for i in range(100)
                   if f"lab-inexistente-{i}" not in {l.name for l in labs})
    lab, error = core.resolve_lab(labs, ausente)
    assert lab is None
    assert "No se encontró" in error


def test_resolve_indice_fuera_de_rango(labs):
    lab, error = core.resolve_lab(labs, "99")
    assert lab is None
    assert "fuera de rango" in error


def test_resolve_sin_identificador(labs):
    lab, error = core.resolve_lab(labs, None)
    assert lab is None
    assert error


# ── Endpoints ─────────────────────────────────────────────────────────────────

def test_endpoints_ssh_y_http(labs):
    lab = next(l for l in labs if l.name == "lab-01")
    endpoints = lab.endpoints("10.0.0.5")
    assert endpoints[0].text == "ssh 10.0.0.5 -p 22"
    assert endpoints[0].url is None
    assert endpoints[1].text == "http://10.0.0.5:80"
    assert endpoints[1].url == "http://10.0.0.5:80"


# ── Estado de contenedores (con docker simulado) ───────────────────────────────

def test_snapshot_una_sola_llamada_a_docker(monkeypatch):
    calls = []

    def fake(cmd, **kwargs):
        calls.append(cmd)
        return fake_run(stdout="lab-01\trunning\t0.0.0.0:22->22/tcp\n")

    monkeypatch.setattr(subprocess, "run", fake)
    snap = core.snapshot(force=True)
    assert calls == [["docker", "ps", "-a", "--format",
                      "{{.Names}}\t{{.State}}\t{{.Ports}}"]]
    assert snap["lab-01"].state == "running"


def test_container_status_consulta_docker_una_sola_vez(labs, monkeypatch):
    """El motivo del cambio: antes era un `docker inspect` por lab."""
    calls = []

    def fake(cmd, **kwargs):
        calls.append(cmd)
        return fake_run(stdout="lab-01\trunning\t\n")

    monkeypatch.setattr(subprocess, "run", fake)
    snap = core.snapshot(force=True)
    for lab in labs:
        core.container_status(lab, snap)

    assert len(calls) == 1


def test_container_status_detecta_estado(labs, monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: fake_run(stdout="lab-01\trunning\t\n"))
    snap = core.snapshot(force=True)
    lab = next(l for l in labs if l.name == "lab-01")
    assert core.container_status(lab, snap) == "running"


def test_los_nombres_de_imagen_del_repo_son_validos(labs):
    """Docker exige repositorio y etiqueta en minúsculas: `build -t` falla si no.

    Regresión: una imagen se llamaba `WarLabs/SSH-Lab` y el build moría con
    `invalid tag ... repository name must be lowercase`.
    """
    import re
    valido = re.compile(
        r"^[a-z0-9]+([._-][a-z0-9]+)*"
        r"(/[a-z0-9]+([._-][a-z0-9]+)*)*"
        r"(:[a-z0-9]+([._-][a-z0-9]+)*)?$")

    for lab in labs:
        assert lab.image == lab.image.lower(), f"{lab.name}: {lab.image}"
        assert valido.match(lab.image), f"{lab.name}: tag inválido -> {lab.image}"
        assert not lab.warnings(), f"{lab.name}: {lab.warnings()}"


def test_una_imagen_con_mayusculas_avisa(labs):
    """Si alguien reintroduce mayúsculas, el aviso salta antes de construir."""
    lab = next(l for l in labs if l.name == "lab-01")
    lab.image = "WarLabs/SSH-Lab"

    avisos = lab.warnings()
    assert any("minúsculas" in a for a in avisos)
    assert "warlabs/ssh-lab" in avisos[0]


def test_container_status_sin_docker_es_desconocido(labs, monkeypatch):
    """Sin docker no se sabe el estado: inventar un `stopped` es mentir."""
    def boom(cmd, **kwargs):
        raise FileNotFoundError("docker no encontrado")

    monkeypatch.setattr(subprocess, "run", boom)
    snap = core.snapshot(force=True)
    lab = next(l for l in labs if l.name == "lab-01")

    assert core.snapshot_error(), "el fallo debe quedar registrado"
    assert core.container_status(lab, snap) == "unknown"


def test_container_status_sin_contenedores_devuelve_stopped(labs, monkeypatch):
    """Docker responde y no hay contenedores: eso sí es un `stopped` real."""
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: SimpleNamespace(returncode=0, stdout="",
                                                           stderr=""))
    lab = next(l for l in labs if l.name == "lab-01")

    assert core.container_status(lab, core.snapshot(force=True)) == "stopped"


def test_snapshot_devuelve_datos_de_puertos_publicados(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: fake_run(0, stdout="lab-01\trunning\t0.0.0.0:22->22/tcp, :::22->22/tcp\n"),
    )
    snap = core.snapshot(force=True)
    assert "22" in snap["lab-01"].published


# ── Conflictos de puertos ─────────────────────────────────────────────────────

def test_detecta_conflicto_de_puerto_entre_labs(labs, monkeypatch):
    """lab-01 y lab-03 usan ambos el 22: no pueden coexistir."""
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: fake_run(0, stdout="lab-01\trunning\t0.0.0.0:22->22/tcp\n"),
    )
    lab = next(l for l in labs if l.name == "lab-03")
    conflicts = core.port_conflicts(lab.ports, ignore=lab.name)
    assert conflicts == [("22", "lab-01")]


def test_sin_conflicto_si_el_propietario_esta_parado(labs, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: fake_run(0, stdout="lab-01\texited\t0.0.0.0:22->22/tcp\n"),
    )
    lab = next(l for l in labs if l.name == "lab-03")
    assert core.port_conflicts(lab.ports) == []


def test_sin_conflicto_ignorando_el_propio_contenedor(labs, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: fake_run(0, stdout="lab-03\trunning\t0.0.0.0:22->22/tcp\n"),
    )
    lab = next(l for l in labs if l.name == "lab-03")
    assert core.port_conflicts(lab.ports, ignore="lab-03") == []


# ── Verificación de flags ─────────────────────────────────────────────────────

def test_check_flag_sin_flag_definida(labs, monkeypatch):
    lab = next(l for l in labs if l.name == "lab-01")
    lab.flag = None
    result = core.check_flag(lab)
    assert result.state == "absent"
    assert not result.solved


def test_check_flag_con_contenedor_parado(labs, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: fake_run(0, stdout=""))
    lab = next(l for l in labs if l.name == "lab-01")
    result = core.check_flag(lab)
    assert result.state == "stopped"
    assert not result.solved


def test_check_flag_exitosa(labs, monkeypatch):
    lab = next(l for l in labs if l.name == "lab-01")

    def fake(cmd, **kwargs):
        if cmd[:2] == ["docker", "ps"]:
            return fake_run(stdout="lab-01\trunning\t\n")
        return fake_run(stdout=f"{lab.flag}\n")

    monkeypatch.setattr(subprocess, "run", fake)
    result = core.check_flag(lab)
    assert result.state == "ok"
    assert result.solved
    assert result.detail == lab.flag


def test_check_flag_sin_fichero_dentro(labs, monkeypatch):
    lab = next(l for l in labs if l.name == "lab-01")

    def fake(cmd, **kwargs):
        if cmd[:2] == ["docker", "ps"]:
            return fake_run(stdout="lab-01\trunning\t\n")
        return fake_run(returncode=1, stderr="No such file")

    monkeypatch.setattr(subprocess, "run", fake)
    result = core.check_flag(lab)
    assert result.state == "missing"
    assert not result.solved


# ── Entrega de flags y progreso ───────────────────────────────────────────────

def test_normalize_flag_quita_espacios_y_comillas():
    """Copiar con Ctrl+Shift+V mete comillas que no son parte de la flag."""
    assert core.normalize_flag('  "FLAG{x}"  \n') == "FLAG{x}"
    assert core.normalize_flag("FLAG{x}") == "FLAG{x}"
    assert core.normalize_flag("") == ""


def test_submit_flag_acepta_la_flag_correcta(labs):
    lab = next(l for l in labs if l.name == "lab-01")
    result = core.submit_flag(lab, f"  {lab.flag}  ")
    assert result.accepted
    assert result.state == "ok"
    assert result.detail == lab.flag
    assert not result.already


def test_submit_flag_rechaza_una_flag_incorrecta(labs):
    lab = next(l for l in labs if l.name == "lab-01")
    result = core.submit_flag(lab, "FLAG{no-es-esta}")
    assert not result.accepted
    assert result.state == "wrong"
    # No se filtra nada de la flag buena: el fallo no regala la respuesta.
    assert lab.flag not in result.detail
    assert not core.is_solved(lab.name)


def test_submit_flag_sin_respuesta(labs):
    lab = next(l for l in labs if l.name == "lab-01")
    result = core.submit_flag(lab, "   ")
    assert result.state == "empty"


def test_submit_flag_es_case_sensible(labs):
    """'flag{x}' no es 'FLAG{x}': acceptarlo sería abrir un agujero."""
    lab = next(l for l in labs if l.name == "lab-01")
    assert core.submit_flag(lab, lab.flag.lower()).state == "wrong"


def test_submit_flag_no_confunde_el_leet(labs):
    """Las flags van en leet (4, 3, 1, 0...), pero al entregar no se normaliza.

    Aceptar `Brute` por `Br0t3` haría el lab trivial: leer la flag tal cual está
    en el contenedor es media solución.
    """
    lab = next(l for l in labs if l.name == "lab-01")
    sin_leet = lab.flag.replace("0", "o").replace("1", "i").replace("3", "e")
    assert sin_leet != lab.flag, "el fixture debería tener leet que dehumanizar"
    assert core.submit_flag(lab, sin_leet).state == "wrong"


def test_submit_flag_sin_flag_definida(labs):
    lab = next(l for l in labs if l.name == "lab-01")
    lab.flag = None
    assert core.submit_flag(lab, "FLAG{algo}").state == "absent"


def test_submit_flag_no_necesita_docker(labs, monkeypatch):
    """Entregar la flag compara ficheros del repo: Docker no debe tocar nada."""

    def explota(*args, **kwargs):
        raise AssertionError("submit_flag no debe hablar con Docker")

    monkeypatch.setattr(subprocess, "run", explota)
    lab = next(l for l in labs if l.name == "lab-01")
    assert core.submit_flag(lab, lab.flag).accepted


def test_una_flag_aceptada_queda_anotada(labs):
    lab = next(l for l in labs if l.name == "lab-02")
    core.submit_flag(lab, lab.flag)

    assert core.is_solved(lab.name)
    entrada = core.load_progress()[lab.name]
    assert entrada["flag"] == lab.flag
    assert entrada["when"]              # debe quedar fecha
    assert not core.is_solved("otro-lab")


def test_reentregar_una_flag_ya_aceptada_lo_dice(labs):
    lab = next(l for l in labs if l.name == "lab-02")
    core.submit_flag(lab, lab.flag)
    segunda = core.submit_flag(lab, lab.flag)
    assert segunda.accepted and segunda.already


def test_reset_progress_por_lab_y_global(labs):
    lab1, lab2 = labs[0], labs[1]
    core.submit_flag(lab1, lab1.flag)
    core.submit_flag(lab2, lab2.flag)

    assert core.reset_progress([lab1.name]) == [lab1.name]
    assert not core.is_solved(lab1.name) and core.is_solved(lab2.name)

    assert sorted(core.reset_progress()) == [lab2.name]
    assert core.load_progress() == {}


def test_progreso_corrupto_no_rompe_la_herramienta(progreso_aislado):
    """Perder el historial de labs no puede impedir usar el CLI."""
    progreso_aislado.write_text("{esto no es json", encoding="utf-8")
    assert core.load_progress() == {}
    assert not core.is_solved("lab-01")

    lab = next(l for l in core.discover_labs() if l.name == "lab-01")
    assert core.submit_flag(lab, lab.flag).accepted   # y se puede seguir usando


def test_progreso_ilegible_no_revierte_la_flag_aceptada(labs, monkeypatch):
    """Si no se puede guardar, la flag sigue siendo correcta: se avisa, no se falla."""
    monkeypatch.setattr(core, "save_progress", lambda data: False)
    lab = next(l for l in labs if l.name == "lab-01")
    result = core.submit_flag(lab, lab.flag)
    assert result.accepted
    assert not result.saved


def test_progress_rows_cubre_todos_los_labs(labs):
    core.submit_flag(labs[0], labs[0].flag)
    rows = core.progress_rows(labs)

    assert [lab.name for lab, _, _ in rows] == [lab.name for lab in labs]
    assert [ok for _, ok, _ in rows] == [True] + [False] * (len(labs) - 1)


# ── Utilidades ────────────────────────────────────────────────────────────────

def test_strip_md_quita_negrita_y_codigo():
    assert core.strip_md("**básica** enumeración con `nmap`") == \
        "básica enumeración con nmap"


def test_deaccent():
    assert core.deaccent("Fácil") == " Facil".strip()
    assert core.deaccent("Difícil") == "Dificil"


def test_level_key_sin_acentos(labs):
    lab = next(l for l in labs if l.name == "lab-01")
    assert lab.level_key == "facil"
