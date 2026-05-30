# WarLabs - Lab 03 LFI

### Nivel

**Fácil**

### Descripción

Laboratorio diseñado para practicar la identificación y explotación de una vulnerabilidad de **Local File Inclusion (LFI)** en una aplicación web, que permite la lectura de archivos internos del sistema.

Una vez obtenido el acceso al sistema, el laboratorio introduce una **mala configuración de permisos sudo** en el binario de `tar`, lo que permite una escalada de privilegios a root.

### Objetivo

Obtener acceso al sistema mediante las **credenciales filtradas** a través del LFI y posteriormente escalar privilegios a root.

### Aprendizajes

- Identificación de vulnerabilidades de **Local File Inclusion (LFI)** en aplicaciones web.
- Lectura de archivos sensibles del sistema mediante **LFI**.
- Filtración de **credenciales** a través de archivos internos.
- Acceso al sistema mediante **SSH**.
- Enumeración de binarios con permisos especiales en Linux.
- Escalada de privilegios mediante una **mala configuración de permisos sudo**.
