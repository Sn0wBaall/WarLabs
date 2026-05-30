# WarLabs - Lab 02 PHP
### Nivel

**Fácil**

### Descripción

Laboratorio diseñado para practicar la identificación y explotación de una vulnerabilidad de **subida de archivos en una aplicación web**, que permite ejecución remota de comandos (**RCE - Remote Command Execution**).

Una vez obtenido el acceso al sistema, el laboratorio introduce una **mala configuración de permisos SUID** en el binario de PHP, lo que permite una escalada de privilegios a root.

### Objetivo

Obtener acceso al sistema mediante una **reverse shell** y posteriormente escalar privilegios a root.

### Aprendizajes

- Identificación de vulnerabilidades de **subida de archivos** en aplicaciones web.
- Ejecución remota de comandos (**RCE**) mediante archivos PHP.
- Obtención de acceso al sistema a través de **reverse shells**.
- Enumeración de binarios con permisos especiales en Linux.
- Escalada de privilegios mediante una **mala configuración de permisos SUID**.
