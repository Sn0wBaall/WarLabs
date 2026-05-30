# WarLabs - Lab 04 RegreSSHion

### Nivel

**Medio**

### Descripción

Laboratorio basado en **CVE-2024-6387**, también conocida como **RegreSSHion**, una vulnerabilidad crítica en OpenSSH que consiste en una condición de carrera en el manejador de señales **SIGALRM** dentro de `sshd`. Esto permite que un atacante remoto sin autenticación ejecute código como **root** en sistemas con glibc.

La vulnerabilidad afecta a OpenSSH en el rango **8.5p1 hasta 9.7p1** (regresión de CVE-2006-5051). El servidor SSH en este laboratorio ejecuta **OpenSSH 8.9p1** sobre **Ubuntu 22.04**, por lo que es vulnerable.

### Objetivo

Identificar la versión vulnerable de OpenSSH mediante enumeración, investigar la CVE correspondiente y explotar la condición de carrera para obtener una shell como **root** y leer la flag en `/root/flag.txt`.

### Aprendizajes

- Enumeración de servicios y detección de versiones con herramientas como **nmap** y **netcat**.
- Investigación de vulnerabilidades en bases de datos públicas (NVD, Exploit-DB).
- Comprensión de la vulnerabilidad de condición de carrera en el manejador SIGALRM de OpenSSH.
- Uso de exploits públicos para vulnerabilidades críticas.
- Análisis de condiciones de explotabilidad (ASLR, glibc, glibc-2.35).
- Escalada de privilegios mediante ejecución remota de código no autenticada.
- Técnicas de debugging y análisis de fallos en servicios de red.
