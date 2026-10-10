"""
Tests de la CLI: argumentos, códigos de salida y renderizado sin tocar Docker.

    python3 -m pytest tests/ -v
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import warlabs_cli as cli  # noqa: E402
import warlabs_core as core  # noqa: E402


def reset_snapshot():
    """Vacia la caché de `docker ps -a` entre tests."""
    core._snapshot_cache.clear()
    core._snapshot_time = 0.0
    core._snapshot_error = None


def docker_caido(monkeypatch, motivo="permission denied while trying to connect"):
    """Simula el caso real: el demonio arranca pero el socket no es accesible."""
    reset_snapshot()

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["docker", "ps"]:
            return SimpleNamespace(returncode=1, stdout="",
                                  stderr=f"permission denied while trying to "
                                         f"connect to the docker API at "
                                         f"unix:///var/run/docker.sock: {motivo}")
        return SimpleNamespace(returncode=1, stdout="", stderr=motivo)

    monkeypatch.setattr(subprocess, "run", fake_run)
    core.snapshot(force=True)      # llena el error real, no uno de mentira


def patch_docker(monkeypatch, name, func):
    """Sustituye una función del core tanto en el core como en la CLI.

    warlabs_cli hace `from warlabs_core import start_container`, así que cada
    módulo tiene su propia referencia: parchear solo una deja la real en pie.
    """
    monkeypatch.setattr(core, name, func)
    if hasattr(cli, name):
        monkeypatch.setattr(cli, name, func)


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch, tmp_path):
    """Ni la pantalla se limpia ni se consulta Docker al ejecutar."""
    monkeypatch.setattr(cli.os, "system", lambda cmd: None)  # clear_screen no-op
    monkeypatch.setattr(cli, "print_banner", lambda *a, **kw: None)
    monkeypatch.setattr(cli, "docker_problem", lambda: None)
    # El progreso se escribe en disco: a un temporal, nunca al del usuario.
    monkeypatch.setenv("WARLABS_SOLVED", str(tmp_path / "solved.json"))
    reset_snapshot()
    yield
    reset_snapshot()


# ── Parser ────────────────────────────────────────────────────────────────────

def test_comandos_aceptan_ayuda():
    for args in (["--help"], ["list", "--help"], ["start", "--help"]):
        with pytest.raises(SystemExit) as exc:
            cli.main(args)
        assert exc.value.code == 0


def test_comando_desconocido_no_crasha():
    with pytest.raises(SystemExit):
        cli.main(["comando-que-no-existe"])


def test_help_lista_flag_y_check():
    text = cli.build_parser().format_help()
    for command in ("list", "info", "start", "stop", "restart", "status",
                    "logs", "shell", "readme", "flag", "check", "solve",
                    "progress", "reset", "watch"):
        assert command in text


def test_stop_sin_argumento_devuelve_codigo_de_uso(capsys):
    code = cli.main(["stop"])
    assert code == cli.EXIT_USAGE
    assert "Especifica un laboratorio" in capsys.readouterr().out


# ── list / status ─────────────────────────────────────────────────────────────

def test_list_json_devuelve_labs(monkeypatch, capsys):
    reset_snapshot()
    patch_docker(monkeypatch, "snapshot", lambda force=False: {})

    assert cli.main(["list", "--json"]) == cli.EXIT_OK

    import json
    data = json.loads(capsys.readouterr().out)
    # El recuento se deriva del repo: añadir un lab no debe romper el test.
    esperados = {lab.name for lab in core.discover_labs()}
    assert {lab["name"] for lab in data["labs"]} == esperados
    assert len(data["labs"]) == len(esperados)
    assert all(lab["flag"] for lab in data["labs"])
    assert data["docker_error"] is None


def test_status_json(monkeypatch, capsys):
    reset_snapshot()
    patch_docker(monkeypatch, "snapshot", lambda force=False: {})

    assert cli.main(["status", "--json"]) == cli.EXIT_OK

    import json
    data = json.loads(capsys.readouterr().out)
    assert data["running"] == []
    assert data["stopped"] == sorted(lab.name for lab in core.discover_labs())
    assert data["unknown"] == []


def test_list_filtra_por_nivel(monkeypatch, capsys):
    """El filtro devuelve exactamente los labs de ese nivel, y solo ellos."""
    reset_snapshot()
    patch_docker(monkeypatch, "snapshot", lambda force=False: {})

    assert cli.main(["list", "Fácil", "--json"]) == cli.EXIT_OK

    import json
    data = json.loads(capsys.readouterr().out)
    esperados = [lab.name for lab in core.discover_labs() if lab.level == "Fácil"]
    assert [lab["name"] for lab in data["labs"]] == esperados
    assert esperados, "el repo debe tener labs de nivel Fácil"


def test_list_filtra_por_nivel_sin_acentos(monkeypatch, capsys):
    """`Facil` y `Fácil` tienen que dar exactamente el mismo resultado."""
    reset_snapshot()
    patch_docker(monkeypatch, "snapshot", lambda force=False: {})

    assert cli.main(["list", "Facil", "--json"]) == cli.EXIT_OK

    import json
    con_tilde = [lab.name for lab in core.discover_labs() if lab.level == "Fácil"]
    assert [lab["name"] for lab in json.loads(capsys.readouterr().out)["labs"]] == con_tilde


def test_list_nivel_inexistente_falla(monkeypatch, capsys):
    assert cli.main(["list", "Imposible"]) == cli.EXIT_ERR
    assert "Ningún lab de nivel" in capsys.readouterr().out


def test_list_nivel_sin_labs_falla(monkeypatch, capsys):
    """Un nivel que existe en el proyecto pero no tiene labs debe decirlo."""
    reset_snapshot()
    patch_docker(monkeypatch, "snapshot", lambda force=False: {})

    assert cli.main(["list", "Difícil"]) == cli.EXIT_ERR
    assert "Ningún lab de nivel" in capsys.readouterr().out


# ── flag / check ──────────────────────────────────────────────────────────────

def test_flag_muestra_la_flag(monkeypatch, capsys):
    assert cli.main(["flag", "lab-03"]) == cli.EXIT_OK
    # La flag se lee del lab, no se fija aquí: cambiarla no debe romper el test.
    assert flag_de("lab-03") in capsys.readouterr().out


def test_check_sin_contenedor_no_supera(monkeypatch, capsys):
    reset_snapshot()
    patch_docker(monkeypatch, "snapshot", lambda force=False: {})

    assert cli.main(["check", "lab-01"]) == cli.EXIT_ERR
    assert "no está en ejecución" in capsys.readouterr().out


def test_check_con_flag_correcta_supera(monkeypatch, capsys):
    lab = next(l for l in core.discover_labs() if l.name == "lab-03")

    def fake_run(cmd, **kwargs):
        result = SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:2] == ["docker", "ps"]:
            result.stdout = "lab-03\trunning\t\n"
        else:
            result.stdout = f"{lab.flag}\n"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cli.main(["check", "lab-03"]) == cli.EXIT_OK
    assert "Lab superado" in capsys.readouterr().out


# ── solve / progress / reset ──────────────────────────────────────────────────

def flag_de(nombre):
    return next(l.flag for l in core.discover_labs() if l.name == nombre)


def test_solve_con_flag_correcta_supera(monkeypatch, capsys):
    assert cli.main(["solve", "lab-01", "-f", flag_de("lab-01")]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "lab-01 superado" in out
    assert core.is_solved("lab-01")


def test_solve_con_flag_incorrecta_no_supera(monkeypatch, capsys):
    assert cli.main(["solve", "lab-01", "-f", "FLAG{inventada}"]) == cli.EXIT_ERR
    assert "Flag incorrecta" in capsys.readouterr().out
    assert not core.is_solved("lab-01")


def test_solve_con_la_flag_antigua_ya_no_sirve(monkeypatch, capsys):
    """Las flags se cambiaron a leet: la clave anterior debe fallar.

    Regresión: si alguien tiene un progreso guardado de antes del cambio, esto
    documenta que la entrega se rechaza en vez de darse por buena.
    """
    assert cli.main(["solve", "lab-01", "-f", "FLAG{SSH_Brute_Capabilities_Privesc}"]) \
        == cli.EXIT_ERR
    assert not core.is_solved("lab-01")


def test_las_flags_del_repo_llevan_leet():
    """El estilo de CREAR-LABS.md: dígitos dentro de las llaves."""
    for lab in core.discover_labs():
        cuerpo = lab.flag[len("FLAG{"):-1]
        assert any(ch.isdigit() for ch in cuerpo), \
            f"{lab.name}: la flag debería ir en leet -> {lab.flag}"


def test_solve_no_dice_que_supera_al_rendirse(monkeypatch, capsys):
    """Con la flag buena entregada pero sin poder guardarla, se avisa."""
    monkeypatch.setattr(core, "save_progress", lambda data: False)
    assert cli.main(["solve", "lab-01", "-f", flag_de("lab-01")]) == cli.EXIT_OK
    assert "no se pudo guardar" in capsys.readouterr().out


def test_solve_sin_flag_devuelve_codigo_de_uso(monkeypatch, capsys):
    assert cli.main(["solve", "lab-01", "-f", ""]) == cli.EXIT_USAGE
    assert "ninguna flag" in capsys.readouterr().out


def test_solve_lab_inexistente_falla(monkeypatch, capsys):
    assert cli.main(["solve", "lab-inexistente", "-f", "FLAG{x}"]) == cli.EXIT_ERR
    assert "No se encontró" in capsys.readouterr().out


def test_solve_acepta_la_flag_por_tuberia(monkeypatch, capsys):
    """`cat /root/flag.txt | warlabs solve lab-01`: el flujo normal de un script."""
    import io
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(f"{flag_de('lab-02')}\n"))

    assert cli.main(["solve", "lab-02"]) == cli.EXIT_OK
    assert core.is_solved("lab-02")


def test_solve_cancelado_no_es_error_de_flag(monkeypatch, capsys):
    """Ctrl+D al preguntar la flag cancela, no cuenta como flag incorrecta."""
    import io

    def eof(prompt=""):
        raise EOFError

    # stdin con tty: si no, se leería por tubería y no se preguntaría nada.
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", eof)
    monkeypatch.setattr(cli, "RICH", False)

    assert cli.main(["solve", "lab-01"]) == cli.EXIT_USAGE
    assert "cancelada" in capsys.readouterr().out


def test_list_marca_los_labs_superados(monkeypatch, capsys):
    import json
    assert cli.main(["list", "--json"]) == cli.EXIT_OK
    assert all(not lab["superado"] for lab in json.loads(capsys.readouterr().out)["labs"])

    cli.main(["solve", "lab-01", "-f", flag_de("lab-01")])
    capsys.readouterr()
    assert cli.main(["list", "--json"]) == cli.EXIT_OK
    labs = {l["name"]: l for l in json.loads(capsys.readouterr().out)["labs"]}
    assert labs["lab-01"]["superado"] is True
    assert labs["lab-02"]["superado"] is False


def test_progress_json_cuenta_los_superados(monkeypatch, capsys):
    import json
    cli.main(["solve", "lab-01", "-f", flag_de("lab-01")])
    capsys.readouterr()

    assert cli.main(["progress", "--json"]) == cli.EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert data["superados"] == ["lab-01"]
    assert data["resueltos"] == 1
    assert data["total"] == len(core.discover_labs())
    assert "lab-01" in data["pendientes"] or len(data["pendientes"]) == data["total"] - 1


def test_progress_se_pinta_sin_docker(monkeypatch, capsys):
    """`progress` es lo de menos: tiene que funcionar sin Docker, como `list`."""
    assert cli.main(["progress"]) == cli.EXIT_OK
    assert "labs superados" in capsys.readouterr().out


def test_reset_olvida_un_lab(monkeypatch, capsys):
    cli.main(["solve", "lab-01", "-f", flag_de("lab-01")])
    capsys.readouterr()

    assert cli.main(["reset", "lab-01", "-f"]) == cli.EXIT_OK
    assert "olvidado" in capsys.readouterr().out
    assert not core.is_solved("lab-01")


def test_reset_olvida_todos(monkeypatch, capsys):
    cli.main(["solve", "lab-01", "-f", flag_de("lab-01")])
    capsys.readouterr()

    assert cli.main(["reset", "--all", "-f"]) == cli.EXIT_OK
    assert core.load_progress() == {}


def test_reset_sin_argumento_devuelve_codigo_de_uso(monkeypatch, capsys):
    assert cli.main(["reset"]) == cli.EXIT_USAGE
    assert "--all" in capsys.readouterr().out


# ── info ──────────────────────────────────────────────────────────────────────

def test_info_json_no_imprime_readme(monkeypatch, capsys):
    assert cli.main(["info", "lab-01", "--json"]) == cli.EXIT_OK

    import json
    data = json.loads(capsys.readouterr().out)
    assert data["name"] == "lab-01"
    assert data["objetivo"]
    assert data["flag"].startswith("FLAG{")
    assert data["endpoints"][0].startswith("ssh ")


def test_info_lab_inexistente_falla(monkeypatch, capsys):
    existente = {lab.name for lab in core.discover_labs()}
    ausente = next(f"lab-inexistente-{i}" for i in range(100)
                   if f"lab-inexistente-{i}" not in existente)

    assert cli.main(["info", ausente]) == cli.EXIT_ERR
    assert "No se encontró" in capsys.readouterr().out


# ── start / stop con docker simulado ──────────────────────────────────────────

@pytest.fixture
def docker_ok(monkeypatch):
    """Simula Docker: build correcto, run correcto y sin conflictos de puertos."""
    reset_snapshot()
    patch_docker(monkeypatch, "snapshot", lambda force=False: {})
    patch_docker(monkeypatch, "port_conflicts", lambda ports, ignore=None: [])
    patch_docker(monkeypatch, "remove_container", lambda name: None)
    patch_docker(monkeypatch, "local_ip", lambda: "10.0.0.5")
    patch_docker(monkeypatch, "build_image",
                 lambda lab, on_line=None: core.BuildResult(True, "", lab.image))
    patch_docker(monkeypatch, "start_container", lambda lab, force=True: (True, "id"))
    patch_docker(monkeypatch, "stop_container", lambda lab: (True, ""))
    yield


def test_start_funciona(monkeypatch, capsys, docker_ok):
    assert cli.main(["start", "lab-01"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "en ejecución" in out
    assert "ssh 10.0.0.5 -p 22" in out


def test_start_con_conflicto_de_puerto_explica(monkeypatch, capsys, docker_ok):
    patch_docker(monkeypatch, "port_conflicts",
                 lambda ports, ignore=None: [("22", "lab-01")])

    assert cli.main(["start", "lab-03"]) == cli.EXIT_ERR
    out = capsys.readouterr().out
    assert "22" in out and "lab-01" in out
    assert "Detén el otro" in out


def test_start_con_build_fallido_devuelve_error(monkeypatch, capsys, docker_ok):
    patch_docker(monkeypatch, "build_image",
                 lambda lab, on_line=None: core.BuildResult(
                     False, "ERROR: no space left on device", lab.image))

    assert cli.main(["start", "lab-01"]) == cli.EXIT_ERR
    assert "Error al construir" in capsys.readouterr().out


def test_start_con_run_fallido_muestra_el_error_de_docker(monkeypatch, capsys,
                                                           docker_ok):
    """El error de Docker se enseña tal cual, con pista si es interpretable.

    El aviso sale del mensaje del demonio, no de la config del lab, así que
    funciona con cualquiera.
    """
    patch_docker(monkeypatch, "start_container",
                 lambda lab, force=True: (False, 'sysctl "net.foo" is not allowed in hosts'))

    assert cli.main(["start", "lab-01"]) == cli.EXIT_ERR
    out = capsys.readouterr().out
    assert "not allowed" in out
    assert "--sysctl" in out      # el launcher señala la causa real


def test_restart_no_revienta(monkeypatch, capsys, docker_ok):
    """Regresión: `restart` reventaba con TypeError al sombrear la función `c`."""
    assert cli.main(["restart", "lab-01"]) == cli.EXIT_OK
    assert "en ejecución" in capsys.readouterr().out


def test_restart_sin_rich_tampoco_revienta(monkeypatch, capsys, docker_ok):
    """El fallo original solo se disparaba en la ruta sin rich."""
    monkeypatch.setattr(cli, "RICH", False)

    assert cli.main(["restart", "lab-01"]) == cli.EXIT_OK
    assert "en ejecución" in capsys.readouterr().out


def test_restart_usa_el_mismo_launch_que_start(monkeypatch, capsys, docker_ok):
    """start y restart deben compartir flujo (antes divergían y solo uno fallaba)."""
    monkeypatch.setattr(cli, "RICH", False)
    codes = {command: cli.main([command, "lab-01"]) for command in ("start", "restart")}
    assert set(codes.values()) == {cli.EXIT_OK}


def test_stop_parado_avisa_sin_error(monkeypatch, capsys, docker_ok):
    assert cli.main(["stop", "lab-01", "-f"]) == cli.EXIT_OK
    assert "no está en ejecución" in capsys.readouterr().out


def test_stop_con_contenedor_corriendo(monkeypatch, capsys, docker_ok):
    info = core.ContainerInfo("lab-01", "running", ("22",))
    patch_docker(monkeypatch, "snapshot", lambda force=False: {"lab-01": info})

    assert cli.main(["stop", "lab-01", "-f"]) == cli.EXIT_OK
    assert "detenido y eliminado" in capsys.readouterr().out


def test_stop_all(monkeypatch, capsys, docker_ok):
    info = core.ContainerInfo("lab-01", "running", ("22",))
    patch_docker(monkeypatch, "snapshot", lambda force=False: {"lab-01": info})

    assert cli.main(["stop", "--all", "-f"]) == cli.EXIT_OK
    assert "lab-01" in capsys.readouterr().out


def test_preflight_de_docker_bloquea_el_start(monkeypatch, capsys):
    monkeypatch.setattr(cli, "docker_problem",
                        lambda: "El demonio de Docker no responde")

    assert cli.main(["start", "lab-01"]) == cli.EXIT_ERR
    assert "Docker no responde" in capsys.readouterr().out


def test_preflight_no_bloquea_los_comandos_de_lectura(monkeypatch, capsys):
    """`list` debe funcionar sin Docker: es el comando de diagnóstico."""
    monkeypatch.setattr(cli, "docker_problem", lambda: "El demonio no responde")
    assert cli.main(["list", "--json"]) == cli.EXIT_OK


# ── Docker inaccesible: no hay que fingir que los labs están parados ──────────

def test_snapshot_registra_el_error_de_docker(monkeypatch):
    """`docker ps` con socket inaccesible = returncode 1, no un `stopped`."""
    docker_caido(monkeypatch)
    assert core.snapshot(force=True) == {}
    assert "permission denied" in core.snapshot_error()


def test_sin_docker_el_estado_es_desconocido_no_stopped(monkeypatch):
    """Regresión: sin Docker se pintaba todo como "detenido", que es falso."""
    docker_caido(monkeypatch)
    lab = next(l for l in core.discover_labs() if l.name == "lab-01")

    assert core.container_status(lab) == "unknown"


def test_sin_contenedores_de_verdad_el_estado_es_stopped(monkeypatch):
    """Docker OK y cero contenedores sí es un dato: `stopped`."""
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    lab = next(l for l in core.discover_labs() if l.name == "lab-01")

    assert core.snapshot(force=True) == {}
    assert core.snapshot_error() is None
    assert core.container_status(lab) == "stopped"


def test_list_avisa_que_los_estados_no_son_fiables(monkeypatch, capsys):
    docker_caido(monkeypatch)

    assert cli.main(["list"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "No se pudo consultar Docker" in out
    assert "no son fiables" in out
    assert "sin datos" in out
    assert "stopped" not in out, "no debe afirmar que están parados"


def test_el_json_de_list_no_va_contaminado(monkeypatch, capsys):
    """`--json` tiene que emitir JSON puro: banner y avisos van a stderr.

    Regresión: el banner iba a stdout y `warlabs list --json | jq` fallaba con
    un error de parseo, que es justo para lo que sirve el modo JSON.
    """
    docker_caido(monkeypatch)

    assert cli.main(["list", "--json"]) == cli.EXIT_OK

    import json
    captured = capsys.readouterr()
    data = json.loads(captured.out)                # stdout: solo JSON
    assert "permission denied" in data["docker_error"]


@pytest.mark.parametrize("con_rich", [True, False])
def test_el_banner_no_contamina_stdout_en_json(monkeypatch, capsys, con_rich):
    monkeypatch.setattr(cli, "RICH", con_rich)
    reset_snapshot()
    patch_docker(monkeypatch, "snapshot", lambda force=False: {})

    cli.main(["list", "--json"])
    captured = capsys.readouterr()

    assert "██" not in captured.out, "el banner se colaría en stdout"
    assert captured.out.lstrip().startswith("{")


def test_el_modo_legible_muestra_el_aviso(monkeypatch, capsys):
    docker_caido(monkeypatch)

    cli.main(["status"])       # modo legible: aquí sí debe avisar

    captured = capsys.readouterr()
    assert "No se pudo consultar Docker" in captured.out
    assert "permission denied" in captured.out


def test_list_json_informa_del_error(monkeypatch, capsys):
    import json
    docker_caido(monkeypatch)

    cli.main(["list", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert all(lab["estado"] == "unknown" for lab in data["labs"])
    assert "permission denied" in data["docker_error"]


def test_status_separa_los_sin_datos(monkeypatch, capsys):
    import json
    docker_caido(monkeypatch)

    assert cli.main(["status", "--json"]) == cli.EXIT_OK
    data = json.loads(capsys.readouterr().out)
    assert data["running"] == [] and data["stopped"] == []
    assert data["unknown"] == sorted(lab.name for lab in core.discover_labs())


def test_check_no_dice_que_el_lab_esta_parado_si_no_sabe(monkeypatch, capsys):
    """`check` con el socket inaccesible no puede afirmar que está parado."""
    docker_caido(monkeypatch)

    assert cli.main(["check", "lab-01"]) == cli.EXIT_ERR
    out = capsys.readouterr().out
    assert "No se pudo consultar Docker" in out
    assert "no está en ejecución" not in out


# ── REPL ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def repl(monkeypatch):
    """Ejecuta el REPL con `entrada` y devuelve los prompts que se pidieron."""
    monkeypatch.setattr(cli, "_save_history", lambda: None)
    monkeypatch.setattr(cli, "_setup_readline", lambda labs: None)

    def correr(entrada, rich=True):
        monkeypatch.setattr(cli, "RICH", rich)
        lineas, prompts = iter(entrada), []

        def fake_input(prompt=""):
            prompts.append(prompt)
            try:
                return next(lineas)
            except StopIteration:
                raise EOFError

        monkeypatch.setattr("builtins.input", fake_input)
        return cli.interactive_mode(), prompts

    return correr


def test_repl_lee_las_lineas_y_sale(repl, capsys):
    """El REPL tiene que consumir la entrada y terminar.

    Regresión: el prompt se imprimía aparte y el `input()` solo existía en la
    rama sin rich, así que con rich instalado el bucle pedía entrada sin leerla
    y pintaba el prompt indefinidamente.
    """
    code, _ = repl(["list Facil", "flag lab-02", "salir"])

    assert code == cli.EXIT_OK
    out = capsys.readouterr().out
    assert flag_de("lab-02") in out
    assert "laboratorio(s) encontrado(s)" in out


def test_repl_pide_una_linea_por_vuelta(repl):
    """Cada iteración lee exactamente una línea; la vacía no cierra el bucle."""
    code, prompts = repl(["", "", "salir"])

    assert code == cli.EXIT_OK
    assert len(prompts) == 3
    assert all(prompts), "el prompt debe llegar a input(), no imprimirse aparte"


def test_repl_sale_con_ctrl_d(repl, capsys):
    """EOF (Ctrl+D) cierra el REPL con su mensaje, sin propagar la excepción."""
    code, _ = repl([])

    assert code == cli.EXIT_OK
    assert "Saliendo" in capsys.readouterr().out


def test_repl_avisa_de_comando_desconocido(repl, capsys):
    repl(["esto-no-existe", "salir"])
    assert "Comando desconocido" in capsys.readouterr().out


def test_repl_filtra_por_nivel_sin_acentos(repl, capsys):
    repl(["list Facil", "salir"])
    out = capsys.readouterr().out
    esperados = sum(1 for lab in core.discover_labs() if lab.level == "Fácil")
    assert f"{esperados} laboratorio(s) encontrado(s)" in out


def test_repl_pregunta_la_flag_sin_comerse_el_bucle(repl, capsys):
    """Dentro del REPL la pregunta tiene que ir por input(), no leyendo stdin.

    Leer stdin entero aquí se comería las líneas de comando siguientes: el bucle
    pediría la flag y se tragaría el resto de la sesión.
    """
    code, prompts = repl(["solve lab-01", flag_de("lab-01"), "progress", "salir"])

    assert code == cli.EXIT_OK
    assert "lab-01 superado" in capsys.readouterr().out
    assert core.is_solved("lab-01")


def test_repl_entrega_la_flag_escrita(repl, capsys):
    """En el REPL la flag va detrás del lab, sin flags de argparse."""
    repl([f"solve lab-01 {flag_de('lab-01')}", "salir"])
    assert "lab-01 superado" in capsys.readouterr().out
    assert core.is_solved("lab-01")


def test_repl_muestra_el_progreso(repl, capsys):
    repl([f"solve lab-01 {flag_de('lab-01')}", "progress", "salir"])
    assert "1/3 labs superados" in capsys.readouterr().out


def test_el_completado_no_reventa_al_montar_el_repl(monkeypatch):
    """Regresión: `("a", "b").split()` parte la tupla, no la cadena."""
    cli._setup_readline(core.discover_labs())     # no debe lanzar AttributeError

    # El completer decide entre labs y comandos según lo que hay en la línea.
    monkeypatch.setattr("readline.get_line_buffer", lambda: "lab-0", raising=False)
    completer = cli._completer(core.discover_labs())
    assert completer("lab-0", 0) == "lab-01"
    assert completer("lab-0", 9) is None           # se agota la lista

    monkeypatch.setattr("readline.get_line_buffer", lambda: "", raising=False)
    assert cli._completer([])("fl", 0) == "flag"  # sin argumentos, comandos


def test_el_autocompletado_incluye_los_comandos_nuevos():
    completer = cli._completer([])
    assert completer("fl", 0) == "flag"
    assert completer("ch", 0) == "check"
    assert completer("so", 0) == "solve"
    assert completer("prog", 0) == "progress"


# ── utils ─────────────────────────────────────────────────────────────────────

def test_cpad_alinea_contando_el_texto_visible(monkeypatch):
    """El relleno debe aplicarse antes de colorear, no después.

    Ajustar la cadena ya coloreada hace que los códigos ANSI se coman el
    relleno y las columnas salgan descuadradas.
    """
    import re
    monkeypatch.setattr(cli, "RICH", False)

    plain = re.sub(r"\033\[[0-9;]*m", "", cli.cpad("lab-01", 10, cli.C.CYAN))
    assert plain == "lab-01    "
    assert len(plain) == 10
    assert cli.cpad("lab-01", 4, cli.C.CYAN) != plain   # trunca, no desborda


def test_clear_screen_solo_si_es_tty(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.os, "system", lambda cmd: calls.append(cmd))

    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: False)
    cli.clear_screen()
    assert calls == []

    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    cli.clear_screen()
    assert len(calls) == 1
