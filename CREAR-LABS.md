# Crear un laboratorio

Guía para añadir un lab nuevo a WarLabs. La idea es que **no hay que tocar
ningún `.py`**: la CLI y la GUI descubren los labs solos, escaneando los
directorios de nivel.

Si algo de esta guía te obliga a modificar `warlabs_core.py`, `warlabs_cli.py`
o `WarLabs.py`, es que o el lab es especial o la guía se ha quedado corta.

---

## 1. Resumen: cinco ficheros y ya está

```
Facil/lab-04/                 ← o Medio/ o Dificil/
├── Dockerfile
├── run.sh
├── README.md
└── content/
    ├── flag.txt
    └── (lo que necesite el contenedor)
```

El **nombre de la carpeta del lab** es el nombre del contenedor, tal cual. El
**nombre de la carpeta del padre** es el nivel de dificultad. No hay ningún
índice, ni registro, ni lista que actualizar.

---

## 2. Elegir carpeta y nivel

Los tres directorios que el core recorre son exactamente estos:

| Directorio  | Nivel que muestra | Para quién                            |
|-------------|-------------------|---------------------------------------|
| `Facil/`    | `Fácil`            | Empieza en pentesting. Camino único.  |
| `Medio/`    | `Medio`            | Viene de CTFs. Encadena técnicas.     |
| `Dificil/`  | `Difícil`          | Vector no obvio, escaladas profundas. |

Los nombres van **sin tilde ni acento**: `Facil`, no `Fácil`. Es lo que espera
`LEVEL_DIRS` en `warlabs_core.py`. El nivel se muestra con tilde en la interfaz,
pero la carpeta es la que manda.

Si el directorio no existe, se salta sin error. Puedes tener los tres, o solo
uno, o ninguno mientras escribes el lab.

### Nombre del lab

El nombre de la carpeta es el nombre del contenedor Docker:

- **Minúsculas, guiones, nada raro**: `lab-04`, no `Lab_04` ni `lab 4`.
- Debe ser único en todo el repo, no solo dentro de su nivel. `Facil/lab-01` y
  `Medio/lab-01` colisionarían en el nombre del contenedor.

---

## 3. `run.sh` — de dónde sale la configuración

Es el fichero **más importante** y el menos intuitivo, porque es la fuente de
verdad de tres cosas a la vez: la imagen, los puertos publicados y los flags
extra de `docker run`. El core lo parsea; CLI y GUI nunca reconstruyen el
`docker run` a mano.

Copia `Facil/lab-03/run.sh` como plantilla. Lo que importa es esta parte:

```bash
lab_name=$(pwd | awk -F "/" '{print $NF}')   # el nombre sale de la carpeta
image_name="warlabs/lab-04"                  # OJO: en minúsculas

ssh_port="22"
web_port="80"

docker build -t ${image_name} .

docker run -d \
  --name ${lab_name} \
  -p ${ssh_port}:22 \
  -p ${web_port}:80 \
  ${image_name}
```

### 3.1 El nombre de la imagen

**Todo en minúsculas.** Docker lo exige y aborta el build si no:

```
invalid reference format: repository name must be lowercase
```

El core te avisa antes de construir si detecta mayúsculas (`Lab.warnings()`), y
CLI y GUI lo muestran. Pero es más fácil de evitar que de diagnosticar.

`image_name` es obligatorio en la práctica. Si falta, el core cae a
`warlabs/<nombre-de-la-carpeta>` en minúsculas como fallback, así que
funciona, pero no lo hagas explícito: el fallback no lo controlas tú.

### 3.2 Los puertos

Se leen de los `-p` del `docker run`, con las variables ya expandidas. Valen
las dos formas:

```bash
-p 22:22                    # literal
-p ${ssh_port}:22           # con variable
-p 0.0.0.0:8080:80          # con IP explícita
-p 127.0.0.1:8080:80        # solo local
```

El core **ignora** la IP y publica siempre en `0.0.0.0`, para que se pueda
acceder desde otro equipo de la red. Si escribes `-p 127.0.0.1:8080:80`, el
core lo convierte a `0.0.0.0:8080:80`. Es deliberado: los labs se resuelven
con la IP local de la máquina, no con `localhost`.

**Elige puertos pensando en los demás labs.** lab-01 y lab-03 usan ambos el 22,
así que no pueden estar en marcha a la vez. La CLI y la GUI lo detectan antes
de arrancar y te dicen qué contenedor lo ocupa, en vez de soltarte el
`port is already allocated` de Docker. Pero es mejor diseñar el lab para que
no colisione:

```bash
ssh_port="2222"    # un lab SSH nuevo que conviva con lab-01 y lab-03
```

#### Un tipo de endpoint nuevo

El tipo se decide por el puerto de **destino**, en `Port.kind`
(`warlabs_core.py`):

| Puerto de destino | Tipo      | Lo que muestra                        |
|-------------------|-----------|---------------------------------------|
| `22`              | `ssh`     | `ssh 192.168.1.5 -p 22` (no clickable) |
| cualquier otro    | `http`    | `http://192.168.1.5:80` (clickable)   |

Un MySQL, un FTP o un RDP saldrían como si fueran HTTP. Ahí sí hay que tocar
código: añade el caso a `Port.kind` y su `text`/`url` a `Endpoint`. Es el
único punto del proyecto donde un lab obliga a tocar un `.py`.

---

## 4. `Dockerfile`

No hay plantilla única, pero hay dos cosas que **no** deben faltar.

### 4.1 La flag, copiada a `/root/flag.txt` con permisos `600`

```dockerfile
COPY content/flag.txt /root/flag.txt
RUN chmod 600 /root/flag.txt
```

El `600` es lo que hace que la escalada de privilegios sea obligatoria: sin
root, `cat /root/flag.txt` da permission denied. Si lo pones en `644`, el
reto se resuelve sin escalar.

Y la ruta importa: `warlabs check <lab>` lee ese fichero por `docker exec`, así
que si la flag no está en `/root/flag.txt` el botón **⚑ Verificar flag**
dará `missing` aunque la escalada funcione perfectamente.

### 4.2 Un `CMD` que no termine

```dockerfile
CMD ["/start.sh"]              # un script tuyo en content/
CMD ["/usr/sbin/sshd", "-D"]   # un servicio
```

Lo que no puede ser es algo que salga: si el proceso principal termina, el
contenedor muere y el lab parece que "no arranca". Si tu servicio necesita
generar claves o crear usuarios al vuelo, envuélvelo en un script en
`content/` y lanza eso.

`EXPOSE` es informativo. Los puertos que de verdad importan son los `-p` del
`run.sh`.

### 4.3 `content/` como raíz de la build context

`content/` es la carpeta de la que copias cosas al contenedor. Para el html de
un lab web, un `start.sh` de arranque, credenciales de prueba, lo que
necesites:

```dockerfile
COPY content/ /var/www/html/
COPY content/start.sh /start.sh
RUN chmod +x /start.sh
```

---

## 5. `README.md` — con los headings exactos

El core busca estas cadenas literales para extraer la descripción y el
objetivo que salen en la tabla de la CLI y en la tarjeta de la GUI:

```markdown
# WarLabs - Lab 04 Mi Lab

### Nivel
Medio

### Descripción
Laboratorio diseñado para practicar ... (el primer párrafo, 3 líneas máximo)

### Objetivo
... leer la flag en `/root/flag.txt`.

### Aprendizajes
LFI · Credenciales · Escalada de privilegios
```

`### Descripción` y `### Objetivo` son **obligatorios y con ese texto exacto**.
Si el heading se llama de otra forma, el lab aparece con
*"Sin descripción disponible"* y nadie te avisa: simplemente se ve mal en la
tabla.

Del resto de secciones puedes poner las que quieras (walkthrough, hints,
pistas). El visor de README de la GUI las renderiza todas.

Las comillas y el `código` en línea de markdown se limpian solos al extraer el
texto, así que no se ven invertidos en la tabla.

---

## 6. `content/flag.txt`

Un fichero, una línea, con la forma `FLAG{...}`:

```
FLAG{Mi_Vector_De_Escalada}
```

El core lo lee del repo, así que `warlabs flag <lab>` te la enseña como clave
de solución. **Ojo:** ese comando es la respuesta del lab. Si vas a proyectar
el material o compartirlo, no lo pases en directo.

Ese mismo fichero es contra el que compara `warlabs solve <lab>`, así que es
también la clave de corrección: quien haga el lab tiene la respuesta a un `cat`
de distancia. Sirve para llevar la cuenta, no para examinar a nadie.

Una línea, sin espacios al final ni saltos de línea de más: `solve` compara
literalmente (solo recorta lo que se pega con comillas).

### Estilo leet

Las flags del repo van en leetspeak: `FLAG{M1_V3ct0r_D3_Escal4d4}`, no
`FLAG{Mi_Vector_De_Escalada}`. Es el estilo de una flag de CTF, y de paso evita
que se copien tal cual de un sitio a otro.

| Letra | Por | Letra | Por |
|:-----:|:---:|:-----:|:---:|
| a | 4 | s | 5 |
| e | 3 | t | 7 |
| i | 1 | o | 0 |
| l | 1 | b | 8 |

El prefijo `FLAG{}` se deja en mayúsculas y limpio: el core comprueba que la flag
empiece por `FLAG{` y termine en `}`, y ese es el formato que espera el resto
del tooling. El leet va dentro de las llaves.

Nombres usados hasta ahora, por si quieres mantener el estilo:

| Lab    | Flag                                          |
|--------|-----------------------------------------------|
| lab-01 | `FLAG{SSH_Br0t3_C4p4b1l1t13s_Pr1v35c}`       |
| lab-02 | `FLAG{F1l3_Upl04d_RCE_SU1D_3sc4l4t10n}`      |
| lab-03 | `FLAG{LF1_Cr3d3nt14ls_Sud0_T4r_3sc4l4t10n}`  |

---

## 7. Comprobar que funciona

```bash
# 1. ¿Lo descubre el core?
python3 warlabs_cli.py list

# 2. ¿Tiene nivel, puertos, descripción y flag?
python3 warlabs_cli.py info lab-04

# 3. ¿Los tests siguen verdes?
python3 -m pytest tests/ -q
```

El paso 3 es el que más información da. Hay un test llamado
`test_cada_lab_descubierto_cumple_las_convenciones` que comprueba, para todos
los labs del repo, que tienen README, flag con el formato correcto, imagen en
minúsculas, sin avisos, con descripción y objetivo, y al menos un puerto. Si
falla, te dice exactamente qué le falta a cuál.

Ese test **no depende del número de labs**, así que añadir un lab no rompe
ningún otro test. Si añades uno mal formado, este es el primero que se queja.

Y con Docker disponible:

```bash
python3 warlabs_cli.py start lab-04            # construye y arranca
python3 warlabs_cli.py check lab-04            # devuelve 0 si está superado
python3 warlabs_cli.py solve lab-04 -f FLAG{}  # entrega la flag: 0 si es la buena
python3 warlabs_cli.py stop lab-04
```

---

## 8. Lista de verificación

Antes de dar el lab por bueno:

- [ ] La carpeta está en `Facil/`, `Medio/` o `Dificil/` (sin tildes)
- [ ] El nombre es único en todo el repo
- [ ] Existe `Dockerfile` (sin él, el lab no aparece)
- [ ] `run.sh` tiene `image_name` **en minúsculas**
- [ ] Los puertos del `run.sh` no colisionan con los de los labs existentes
- [ ] `run.sh` tiene un `docker run` con `-p` para cada puerto que expongas
- [ ] `README.md` tiene `### Descripción` y `### Objetivo` con ese texto exacto
- [ ] `content/flag.txt` existe y tiene forma `FLAG{...}`
- [ ] El `Dockerfile` hace `COPY content/flag.txt /root/flag.txt` + `chmod 600`
- [ ] `warlabs solve <lab> -f <flag>` acepta la flag (sin espacios ni saltos de línea)
- [ ] El `CMD` no termina nunca
- [ ] `python3 -m pytest tests/ -q` en verde
- [ ] `python3 warlabs_cli.py start <lab>` arranca y `check` funciona

---

## 9. Problemas frecuentes

**El lab no aparece en `list`.**
Falta el `Dockerfile`. El core solo considera un directorio que lo tenga, y no
avisa de los que ignora.

**Sale con "Sin descripción disponible".**
El `README.md` no tiene un heading `### Descripción` (o no se llama así). Mira
que no sea `## Descripción` — tiene que ser `###`.

**El build falla con `repository name must be lowercase`.**
Hay mayúsculas en `image_name` del `run.sh`. Docker es estricto con esto, y el
aviso del core debería habértelo enseñado antes.

**El contenedor arranca y se muere enseguida.**
El `CMD` termina. Casi siempre es un servicio que necesita ejecución en primer
plano, o un script de arranque que se acabó.

**`check` dice `missing` pero la escalada funciona.**
La flag no está en `/root/flag.txt` dentro del contenedor. El `COPY` falta, se
apuntó a otra ruta, o el `chmod` impidió leerla al propio `docker exec`.

**`solve` dice siempre "flag incorrecta".**
Está comparando contra `content/flag.txt`, no contra lo que hay en el contenedor.
Revisa que el `flag.txt` del repo sea el mismo que copias al contenedor, y que no
lleve espacios ni saltos de línea de más.

**El contenedor no arranca porque el puerto está ocupado.**
Otro lab usa ese puerto. `warlabs status` te dice cuál. O para el otro con
`stop`, o cambia el puerto en el `run.sh`.

**Docker se queja de un `--sysctl`.**
Solo algunos sysctls se pueden tocar sin `--privileged`. Los que no, cambian
ajustes de **todo el host**, así que no deben usarse en un lab. El core avisa
antes de intentarlo (`Lab.warnings()`), y el mensaje de la CLI te lo recuerda
si aun así falla.

---

## Dónde mirar si algo falla

| Si falla...                                          | Mira                              |
|------------------------------------------------------|-----------------------------------|
| No descubre el lab                                   | `discover_labs()` en el core      |
| Image o puertos mal leídos del `run.sh`              | `parse_docker_run()`, `split_run_tokens()` |
| Descripción u objetivo vacíos                       | `_read_section()` en el core      |
| Faltan flags de `docker run`                         | `_VALUE_FLAGS` en el core         |
| Tipos de endpoint raros                             | `Port.kind`, `Endpoint` en el core |
| Colores o formato de la tabla                        | `cpad()` en la CLI                |
| Filtro por nivel                                     | `LEVEL_COLOR` en la CLI, `OPCIONES` en la GUI |
