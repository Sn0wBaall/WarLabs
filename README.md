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
- [Requisitos](#requisitos)
- [Instalación](#instalacion)
- [Uso](#uso)
  - [Interfaz gráfica (GUI)](#interfaz-grafica-gui)
  - [Interfaz de línea de comandos (CLI)](#interfaz-de-linea-de-comandos-cli)
- [Valores](#valores)
- [Equipo](#equipo)

---

## ¿Quiénes somos?

Somos un equipo apasionado por la ciberseguridad que cree en el aprendizaje práctico como la mejor forma de formar profesionales éticos en seguridad informática.

WarLabs proporciona una plataforma auto-alojada de laboratorios orientados al aprendizaje del **pentesting / hacking ético**, donde los usuarios desarrollan habilidades de **enumeración, explotación y escalada de privilegios** en entornos controlados y aislados.

---

## Laboratorios disponibles

### Nivel Fácil

| # | Laboratorio | Imagen Docker | Puertos | Técnica principal |
|:-:|:-----------|:--------------|:-------:|:-----------------|
| 1 | **lab-01** -- SSH Brute Force | `WarLabs/ssh-lab` | 22, 80 | Fuerza bruta SSH + Capabilities Python3 |
| 2 | **lab-02** -- File Upload RCE | `WarLabs/php-lab` | 80 | Subida de archivos -> RCE + SUID PHP |
| 3 | **lab-03** -- LFI | `WarLabs/lfi-lab` | 22, 80 | Local File Inclusion + Sudo Tar |

#### lab-01 -- SSH
> Laboratorio diseñado para practicar técnicas básicas de enumeración de puertos y enumeración web que permite la lectura de datos sensibles así como la obtención de usuarios. Una vez obtenido el acceso al sistema, introduce una **capability** en el binario de python3, lo que permite una escalada de privilegios a root.

**Aprendizajes:** Enumeración web · Filtración de usuarios · Fuerza bruta SSH · Capabilities Linux · Escalada de privilegios

#### lab-02 -- PHP
> Laboratorio diseñado para practicar la identificación y explotación de una vulnerabilidad de **subida de archivos** en una aplicación web, que permite ejecución remota de comandos (RCE). Una vez obtenido el acceso, introduce una **mala configuración de permisos SUID** en el binario de PHP.

**Aprendizajes:** File Upload · RCE · Reverse Shell · SUID misconfiguration · Escalada de privilegios

#### lab-03 -- LFI
> Laboratorio diseñado para practicar la identificación y explotación de una vulnerabilidad de **Local File Inclusion (LFI)** en una aplicación web. Una vez obtenido el acceso, introduce una **mala configuración de permisos sudo** en el binario de `tar`.

**Aprendizajes:** LFI · Filtración de credenciales · SSH · Sudo misconfiguration · Escalada de privilegios

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
- Panel de información detallada del laboratorio seleccionado
- Botones **Lanzar** / **Detener** para gestionar contenedores Docker
- Terminal integrado con logs en tiempo real
- Visor de README con formato Markdown y zoom (Ctrl++ / Ctrl+-)

### Interfaz de línea de comandos (CLI)

```bash
python3 warlabs_cli.py
```

Sin argumentos entra en **modo interactivo REPL**. También admite comandos directos:

| Comando | Descripción |
|---------|:-----------|
| `warlabs list` | Lista todos los laboratorios |
| `warlabs list Fácil` | Filtra por nivel |
| `warlabs info lab-01` | Muestra información detallada |
| `warlabs start lab-01` | Construye y lanza un laboratorio |
| `warlabs stop lab-01` | Detiene y elimina un laboratorio |
| `warlabs stop --all` | Detiene todos los laboratorios activos |
| `warlabs restart lab-01` | Reconstruye y reinicia |
| `warlabs status` | Estado de todos los contenedores |
| `warlabs logs lab-01 -f` | Sigue los logs en tiempo real |
| `warlabs shell lab-01` | Abre una shell en el contenedor |
| `warlabs readme lab-01` | Muestra el README del laboratorio |
| `warlabs watch` | Monitoreo en tiempo real |

> **Nota:** La CLI usa `rich` para mostrar tablas, paneles y resaltado de sintaxis. Si no está instalado, funciona con colores ANSI básicos.

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
| **Axel Vázquez Pérez** (Aragorn) | Desarrollador |

---

