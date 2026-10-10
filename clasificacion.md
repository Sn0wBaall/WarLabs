# WarLabs — Sistema de Clasificación

Cada laboratorio en WarLabs está clasificado según una serie de criterios técnicos que determinan su nivel de dificultad. Esta guía tiene como objetivo ayudarte a elegir el laboratorio adecuado según tus conocimientos actuales y orientarte sobre qué esperar en cada nivel.

---

## Tabla de Clasificación

| Criterio | Fácil | Medio | Difícil |
|:---------|:------|:------|:--------|
| **Enumeración** | Servicios visibles y directos | Requiere enumeración profunda | Engañosa o mínima |
| **Vector de entrada** | Único y evidente | Requiere encadenar técnicas | No evidente, requiere investigación |
| **Acceso inicial** | Credenciales expuestas o fuerza bruta dirigida | LFI, lógica de aplicación, reutilización | Cadena compleja o vector poco común |
| **Escalada de privilegios** | Misconfiguración simple (SUID, capabilities) | Varias técnicas posibles | Técnica avanzada o creativa |
| **Conocimientos** | Linux básico, herramientas comunes | Linux intermedio, scripting básico | Linux avanzado, internals del sistema |
| **Tipo de fallo** | Configuración insegura | Error de lógica o diseño | Abuso del sistema o cadena de fallos |
| **Documentación** | README detallado + Walkthrough | README con pistas, walkthrough parcial | README mínimo, sin walkthrough |

---

## Fácil

Diseñado para usuarios que están comenzando en el mundo del pentesting y el hacking ético. Los laboratorios de este nivel presentan vulnerabilidades evidentes, con un único camino de explotación y pasos bien definidos.

Se espera que el usuario sea capaz de:

- Realizar escaneos de puertos básicos con herramientas como `nmap`
- Navegar y enumerar aplicaciones web sencillas
- Ejecutar ataques de fuerza bruta dirigidos
- Identificar y explotar misconfiguraciones simples (SUID, capabilities, sudo)
- Usar herramientas comunes del ecosistema de pentesting (Burp Suite, Hydra, Gobuster, etc.)
- Enviar y recibir reverse shells básicas

Ejemplos de técnicas presentes:

- Enumeración web mediante fuerza bruta de directorios para identificar rutas o archivos sensibles
- Filtración de información sensible (usuarios, credenciales) a través de archivos expuestos
- Fuerza bruta sobre servicios de red (SSH) con usuario conocido
- Subida de archivos sin validación que deriva en ejecución remota de comandos (RCE)
- Escalada de privilegios vía capabilities en binarios (Python3, etc.)
- Escalada de privilegios mediante permisos SUID mal configurados en binarios (PHP, etc.)
- Escalada de privilegios a través de configuraciones incorrectas de sudo (tar, etc.)

---

## Medio

Orientado a usuarios con experiencia previa en CTFs o laboratorios de nivel fácil. El camino de explotación no es inmediato y puede requerir encadenar varias técnicas para lograr el acceso inicial o la escalada de privilegios.

Se espera que el usuario sea capaz de:

- Realizar enumeración más profunda y estructurada
- Investigar vulnerabilidades en bases de datos públicas (NVD, Exploit-DB)
- Identificar y explotar vulnerabilidades de lógica en aplicaciones web (LFI, SSRF, IDOR)
- Encadenar múltiples técnicas para lograr un objetivo
- Manejar entornos Linux con mayor fluidez
- Escribir o adaptar scripts básicos para automatizar pasos
- Comprender y explotar vulnerabilidades de servicios de red (condiciones de carrera, etc.)

Ejemplos de técnicas presentes:

- Local File Inclusion (LFI) para lectura de archivos del sistema y filtración de credenciales
- Reutilización de credenciales entre servicios
- Escalada vía cron jobs, binarios personalizados o configuraciones de sudo
- Investigación y explotación de CVEs en servicios de red
- Ejecución remota de código no autenticada mediante vulnerabilidades en servicios expuestos
- Análisis de condiciones de explotabilidad (ASLR, versiones de librerías, etc.)

---

## Difícil

Pensado para usuarios con sólida experiencia en pentesting y CTFs. El vector de entrada no es obvio, la enumeración puede ser engañosa y la escalada de privilegios requiere un entendimiento profundo del sistema operativo y sus mecanismos internos.

Se espera que el usuario sea capaz de:

- Identificar vectores no evidentes con mínimas pistas
- Encadenar múltiples vulnerabilidades en una sola cadena de explotación
- Comprender y abusar de mecanismos internos del sistema operativo
- Desarrollar exploits o herramientas propias cuando sea necesario
- Trabajar sin documentación de apoyo ni walkthroughs
- Aplicar técnicas de evasión y pivoting en entornos con defensas activas

Ejemplos de técnicas presentes:

- Exploits de kernel o servicios internos
- Abuso de mecanismos de autenticación complejos
- Pivoting entre servicios internos
- Técnicas de evasión o entornos con defensas activas

---

## Por dónde empezar

Si eres nuevo en el hacking ético, te recomendamos seguir este camino:

1. **Fácil** — Familiarízate con las herramientas y el flujo de trabajo
2. **Medio** — Desarrolla criterio propio y aprende a encadenar técnicas
3. **Difícil** — Pon a prueba tu creatividad y conocimiento avanzado

> Tip: Antes de ver un walkthrough, intenta resolver el laboratorio por tu cuenta.
> El proceso de intentar y fallar es parte esencial del aprendizaje.

---

*WarLabs — Aprende. Practica. Mejora.*
