<p align="center">
  <img src="https://img.shields.io/badge/WarLabs-v1.0-3fb950?style=for-the-badge">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white">
  <img src="https://img.shields.io/badge/Licencia-MIT-3fb950?style=for-the-badge">
</p>

---

# ⬡ WarLabs

**Plataforma auto-alojada de laboratorios de hacking ético**

WarLabs es un proyecto enfocado en el desarrollo de laboratorios en **Docker** para la práctica de **pentesting / hacking ético**. Nuestra misión es **divulgar, enseñar y concienciar** sobre la ciberseguridad desde un enfoque **teórico y práctico**, con el objetivo de generar un mayor impacto en la sociedad.

---

## Tabla de contenido

- [¿Quiénes somos?](#quienes-somos)
- [Laboratorios disponibles](#laboratorios-disponibles)
- [Flags](#flags)
- [Requisitos](#requisitos)
- [Instalación](#instalacion)
- [Uso](#uso)
  - [Interfaz gráfica (GUI)](#interfaz-grafica-gui)
  - [Interfaz de línea de comandos (CLI)](#interfaz-de-linea-de-comandos-cli)
  - [Tests](#tests)
- [Arquitectura](#arquitectura)
- [Componentes y puertos](#componentes-y-puertos)
- [Valores](#valores)
- [Equipo](#equipo)

---

## ¿Quiénes somos?

Somos un equipo apasionado por la ciberseguridad que cree en el aprendizaje práctico como la mejor forma de formar profesionales éticos en seguridad informática.

WarLabs proporciona una plataforma auto-alojada de laboratorios orientados al aprendizaje del **pentesting / hacking ético**, donde los usuarios desarrollan habilidades de **enumeración, explotación y escalada de privilegios** en entornos controlados y aislados.

---

## Laboratorios disponibles

### Nivel Fácil

| # | Laboratorio | Imagen Docker | Puertos | Técnica principal | Flag |
|:-:|:-----------|:--------------|:-------:|:-----------------|:-----|
| 1 | **lab-01** -- SSH Brute Force | `warlabs/ssh-lab` | 22, 80 | Fuerza bruta SSH + Capabilities Python3 | Sí |
| 2 | **lab-02** -- File Upload RCE | `warlabs/php-lab` | 80 | Subida de archivos -> RCE + SUID PHP | Sí |
| 3 | **lab-03** -- LFI | `warlabs/lfi-lab` | 22, 80 | Local File Inclusion + Sudo Tar | Sí |

#### lab-01 -- SSH
> Laboratorio diseñado para practicar técnicas básicas de enumeración de puertos y enumeración web que permite la lectura de datos sensibles así como la obtención de usuarios. Una vez obtenido el acceso al sistema, introduce una **capability** en el binario de python3, lo que permite una escalada de privilegios a root.

**Aprendizajes:** Enumeración web · Filtración de usuarios · Fuerza bruta SSH · Capabilities Linux · Escalada de privilegios

#### lab-02 -- PHP
> Laboratorio diseñado para practicar la identificación y explotación de una vulnerabilidad de **subida de archivos** en una aplicación web, que permite ejecución remota de comandos (RCE). Una vez obtenido el acceso, introduce una **mala configuración de permisos SUID** en el binario de PHP.

**Aprendizajes:** File Upload · RCE · Reverse Shell · SUID misconfiguration · Escalada de privilegios

#### lab-03 -- LFI
> Laboratorio diseñado para practicar la identificación y explotación de una vulnerabilidad de **Local File Inclusion (LFI)** en una aplicación web. Una vez obtenido el acceso, introduce una **mala configuración de permisos sudo** en el binario de `tar`.

**Aprendizajes:** LFI · Filtración de credenciales · SSH · Sudo misconfiguration · Escalada de privilegios

### Nivel Medio

_Sin laboratorios por ahora._

> ¿Quieres añadir uno? La guía completa está en **[CREAR-LABS.md](CREAR-LABS.md)**:
> cinco ficheros en la carpeta del nivel y ningún `.py` que tocar.

---

## Flags

Cada lab tiene su flag en `content/flag.txt`, que es la **única fuente de
verdad**: el `Dockerfile` la copia a `/root/flag.txt` con permisos `600`, así que
solo se lee con **root** (todos los labs terminan en escalada de privilegios).

Van en leetspeak, como las de un CTF: `FLAG{SSH_Br0t3_C4p4b1l1t13s_Pr1v35c}`.

| Comando | Qué hace |
|---------|:---------|
| Comando | Qué hace |
|---------|:---------|
| `warlabs flag lab-01` | Muestra la flag del lab (clave de solución) |
| `warlabs check lab-01` | Comprueba la flag **dentro del contenedor en marcha** |
| `warlabs solve lab-01` | **Entrega** la flag: te dice si has superado el lab |
| `warlabs progress` | Qué labs has superado |
| `warlabs reset lab-01` | Olvida el progreso de un lab (o `reset --all`) |

`check` devuelve código de salida `0` si el lab está superado y `1` si no, así que
sirve para scripts. En la GUI es el botón **⚑ Verificar flag**.

> `check` y `solve` no son lo mismo. `check` pregunta *"¿está el lab bien montado?"*
> (que `/root/flag.txt` exista y se lea en el contenedor). `solve` pregunta
> *"¿la has resuelto?"*: comparan la flag que entregas con la del repo. No necesita
> Docker, así que también sirve con el contenedor parado.

### Entregar la flag

```bash
warlabs solve lab-01                  # te la pide por teclado
warlabs solve lab-01 -f 'FLAG{...}'   # o la pasas directamente
cat /root/flag.txt | warlabs solve lab-01   # o por tubería
```

Si aciertas, el lab queda anotado como superado en `~/.warlabs_solved.json` y sale
una barra de progreso. El estado es tuyo, no del repo: cada máquina lleva el suyo.
En `warlabs list` y `warlabs watch` la columna `✓` marca lo que llevas.

> **Ojo con `warlabs flag`:** es la clave de solución. Si enseñas el material, no
> la proyectes ni la compartas con quien está resolviendo los labs. Y recuerda que
> `solve` compara contra esa misma clave: mide tu disciplina, no tu seguridad.

---

## Requisitos

- **Docker** (obligatorio para ejecutar los laboratorios)
- **Python 3.10+** (para los gestores GUI y CLI)
- **Raspberry Pi 4Gb** (opcional -- ideal para despliegue 24/7)

---

## Instalación

```bash
# Clonar el repositorio
git clone https://github.com/Sn0wBaall/WarLabs.git
cd WarLabs

# Instalar dependencias de Python
pip install -r requirements.txt
```

---

## Uso

### Interfaz gráfica (GUI)

```bash
python3 WarLabs.py
```

Interfaz moderna con `customtkinter` que incluye:
- Sidebar con buscador y filtro por nivel (Fácil/Medio/Difícil)
- Panel de información detallada con los endpoints del lab (clicsables)
- Botones **Lanzar** / **Detener** / **Reiniciar** por lab y **Detener todos**
- Terminal integrado con la **salida del build en directo** (en un Pi el build
  tarda: antes la GUI se quedaba congelada sin decir nada)
- Botón **⚑ Verificar flag** que comprueba la flag dentro del contenedor
- **✓** en la tarjeta de cada lab superado, y botón **↺ Limpiar progreso** para
  olvidarlos todos (pregunta antes; no toca los contenedores)
- Visor de README con formato Markdown y zoom (Ctrl++ / Ctrl+-)

### Interfaz de línea de comandos (CLI)

```bash
python3 warlabs_cli.py
```

Sin argumentos entra en **modo interactivo REPL** (con historial y completado con
Tab). También admite comandos directos con la forma
`python3 warlabs_cli.py <comando> [opciones]`; en las tablas de abajo se abrevia
como `warlabs <comando>`:

| Comando | Descripción |
|---------|:-----------|
| `warlabs list` | Lista todos los laboratorios |
| `warlabs list Fácil` | Filtra por nivel (también `Facil`, sin tilde) |
| `warlabs list --json` | Salida JSON, para scripts |
| `warlabs info lab-01` | Muestra información detallada y el README |
| `warlabs start lab-01` | Construye y lanza un laboratorio |
| `warlabs stop lab-01` | Detiene y elimina un laboratorio |
| `warlabs stop --all` | Detiene todos los laboratorios activos |
| `warlabs restart lab-01` | Reconstruye y reinicia |
| `warlabs status` | Estado de todos los contenedores (`--json` disponible) |
| `warlabs logs lab-01 -f` | Sigue los logs en tiempo real |
| `warlabs shell lab-01` | Abre una shell en el contenedor |
| `warlabs readme lab-01` | Muestra el README del laboratorio |
| `warlabs flag lab-01` | Muestra la flag del lab (clave de solución) |
| `warlabs check lab-01` | Verifica la flag dentro del contenedor |
| `warlabs solve lab-01 [-f FLAG{...}]` | Entrega la flag y comprueba si has superado el lab |
| `warlabs progress` | Labs superados, con barra de progreso (`--json` disponible) |
| `warlabs reset <lab>\|--all` | Olvida el progreso de un lab o de todos |
| `warlabs watch` | Monitoreo en tiempo real |

Códigos de salida: `0` correcto · `1` error · `2` uso incorrecto.

> **Nota:** La CLI usa `rich` para mostrar tablas, paneles y resaltado de sintaxis. Si no está instalado, funciona con colores ANSI básicos.

> ¿Quieres el comando `warlabs` en el PATH? Un alias:
> `alias warlabs='python3 /ruta/a/WarLabs/warlabs_cli.py'`.

### Tests

```bash
python3 -m pytest tests/ -v
```

Cubren el núcleo compartido (parseo de `run.sh`, descubrimiento de labs,
conflictos de puertos, verificación y entrega de flags, progreso persistido) y la
CLI, incluidos tests de regresión de los bugs corregidos. **No necesitan Docker**:
`subprocess` está simulado, así que se ejecutan en cualquier máquina. El progreso
se escribe en un temporal, nunca en tu `~/.warlabs_solved.json`.

Un test en concreto, `test_cada_lab_descubierto_cumple_las_convenciones,
comprueba que **todos** los labs del repo cumplen lo que pide
[CREAR-LABS.md](CREAR-LABS.md): README con los headings correctos, flag con el
formato adecuado, imagen en minúsculas, al menos un puerto. Si añades un lab mal
formado, ese es el que se queja.

---

## Arquitectura

```
warlabs_core.py    Núcleo compartido: labs, parsing de run.sh, Docker
├── warlabs_cli.py     CLI (argparse + rich)
└── WarLabs.py         GUI (customtkinter)
```

El `docker run` de cada lab se deriva de su propio `run.sh`, no se reconstruye a
mano en cada interfaz. Así, si un lab necesita `--cap-add` o `--sysctl`, CLI y GUI
lo respetan igual; y si el lab usa un `--sysctl` que Docker va a rechazar, ambas
avisan antes de intentarlo en vez de fallar en silencio.

## Componentes y puertos

Cada lab publica en los puertos declarados en su `run.sh`. Ojo: **lab-01 y
lab-03 usan ambos el 22**, así que no pueden estar en marcha a la vez. La CLI y la
GUI lo detectan antes de arrancar y te dicen qué contenedor lo ocupa, en lugar de
dejarte el `port is already allocated` de Docker.

---

## Valores

- **Aprendizaje práctico** -- Creemos en aprender haciendo
- **Ética** -- Conocimiento para proteger, no para dañar
- **Divulgación** -- Compartir conocimiento para construir una comunidad más fuerte

---

## Equipo

| Miembro | Rol |
|:--------|:----|
| **Sinuhe Nieves Rico** ([Sn0wBaall](https://github.com/Sn0wBaall)) | Desarrollador |
| **Axel Vázquez Pérez** ([Leevyeo](https://github.com/Leevyeo)) | Desarrollador |

---

