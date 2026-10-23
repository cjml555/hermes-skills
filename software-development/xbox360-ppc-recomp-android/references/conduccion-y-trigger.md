# Conducir el juego: stick analogico y disparadores por evento

Como pasar de "el juego avanza al pulsar" a "el juego llega a la ciudad y se
conduce", que es donde esta el grueso del codigo del juego.

Continua de `references/pulsacion-inyectada.md` (el driver inyectado). Aqui va
lo que se aprinio al intentar llegar mas lejos.

---

## 1. El juego necesita un X server, y sin el falla EN SILENCIO

El port abre una ventana de SDL. Sin `DISPLAY` el juego muere en **0.03 s**
con `No available video device`: no hay log, no hay crash, no hay nada. Un A/B
con ese fallo da **numeros identicos siempre**, y eso parece un resultado
(control == tratamiento, "las pulsaciones no cambian nada").

La salida es el driver de video **`offscreen`** de SDL, que no necesita X:

```bash
./out/pc/mcla ... --video_driver=offscreen
```

Es un cvar (`video_driver`), asi que tambien vale `--video_driver offscreen`.
Con el, el juego corre en cualquier `terminal` sin `DISPLAY`, y el A/B es
fiable. Todos los scripts del proyecto lo usan.

**Ojo con el entorno de las herramientas:** el kernel de `execute_code` no
hereda `DISPLAY` del shell, asi que una corrida lanzada desde ahi muere igual.
Las corridas del juego van por `terminal`.

Criterio de que arranco de verdad: en el log,
`SDL video driver: offscreen` y una linea `Creating graphics pipeline`.

## 2. El control del A/B tiene que TENER el pad

El codigo hace:

```cpp
if (presses.empty()) return;   // sin guion, el pad no se instala
```

Asi que un control de "sin pulsaciones" hecho con la variable de entorno
**vacia** es un guest que **no ve ningun dispositivo de juego**. Eso compara
dos cosas a la vez: que haya un pad conectado, y que se pulse algo.

El control justo es un guion que **instala el pad pero nunca dispara**: un
gesto programado mas alla del final de la corrida.

```bash
MCLA_PAD_PRESS="9999:0x1000"    # el pad existe, ningun boton baja
```

Medido en MCLA, con user y cache limpios antes de cada corrida:

| Corrida | pipelines | gestos |
| --- | --- | --- |
| sin pad en absoluto | 556 | 0 |
| **pad presente, no pulsa** | 554 | 0 |
| 16 pulsaciones | 643 | 16 |
| pad presente, no pulsa | 564 | 0 |
| 16 pulsaciones | 693 | 16 |
| stick 4 dir + A + START | 643 | 14 |

Tener el pad no cambia nada (556 contra 554). Las pulsaciones si (554-564
contra 643-693): del orden de 100 pipelines mas.

## 3. El conteo de pipelines es ruidoso; la diferencia es solida

La misma corrida de control dio **299, 265 y 556** pipelines en corridas
distintas. El valor absoluto no sirve para comparar contra numeros guardados
de otra sesion. Lo que vale es la **diferencia entre condiciones** dentro de
la misma sesion, y el **codigo de salida**.

Criterio de salida de cada corrida:

| Codigo | Significado |
| --- | --- |
| `124` | la corrida llego al final (la mato el `timeout`) |
| `137` / `-9` | la mato el **OOM killer**: el juego carga `.rpf` de mas de un gigabyte |

Una corrida muerta da un conteo sin sentido, y compararla con una completa
produce un resultado **falso y optimista**. Esto ya paso: "el stick sube a
922 pipelines frente a 650 del control" era un control asesinado por el OOM a
los 84 s. Con las dos corridas completas, el stick **empeoraba** el resultado
(640-658 contra 804-930).

## 4. El juego NO es determinista

La misma entrada de 16 gestos, en los mismos segundos, creo el guardado
`mc4.sav` a t+60 s en una corrida y **no lo creo** en otra. Los dos logs
muestran los mismos 16 gestos en los mismos instantes.

Por eso **ningun guion fijo es fiable**, y por eso hace falta un disparador
por evento (seccion 7).

## 5. La entrada son exactamente 16 gestos, y la MEZCLA importa mas que la cantidad

Que entrada llega al free roam, medido:

| Entrada | Llega |
| --- | --- |
| 16 gestos (A, START y D-pad en rotacion) | **si** (2 de 5 corridas) |
| 32 gestos de A puro | **nunca** (0 de 6) |
| 48 gestos de la mezcla repetida | no (0 de 2) |
| 16 + cola de mantenimiento de 12 | no (0 de 2) |

Dos cosas:

- **La mezcla importa mas que la cantidad.** Pulsar A sin mas es pasarse de
  opcion: el D-pad y el START son los que mueven los menus.
- **Anadir mas gestos despues tambien rompe.** El guardado se escribe en
  t+60 s, justo cuando el ultimo gesto de los 16 hace su efecto (t+48 s).
  Seguir pulsando deja al juego en un menu que ya no avanza.

El guion que funciona (A, START y D-pad en rotacion, cada 3 s):

```bash
ENTRADA="3:0x1000,6:0x1000,9:0x0010,12:0x1000,15:0x0008,18:0x1000,21:0x0010,24:0x1000,27:0x0001,30:0x1000,33:0x0010,36:0x1000,39:0x0008,42:0x1000,45:0x0010,48:0x1000"
```

La señal de llegada es la **creacion del guardado**: el kernel la registra
(`crear «mc4.sav»`), y su presencia significa que el juego entro en una
partida de verdad, no en un menu.

## 6. El stick analogico

El guion tambien mueve los stick, con el prefijo `s:` y los ejes como
`<lx>:<ly>` (izquierdo) o `<lx>:<ly>:<rx>:<ry>` (ambos), cada uno de -1 a 1:

```bash
MCLA_PAD_PRESS="3:s:0:-1,6:0x1000"      # stick abajo, luego A
MCLA_PAD_PRESS="3:s:0:-1:0:0"            # stick abajo
```

Los signos son los de XInput: x positivo es derecha, y positivo es arriba.
El deadzone del SDK es 7849, asi que una fraccion por encima de 0.25 ya cuenta
como deflection.

A diferencia del boton, que es un flanco, el stick es una **posicion**: el
guest puede necesitar verlo durante varios frames para mover un cursor. Por
eso se mantiene **6 consultas** en vez de una.

### Sostenlo por tiempo, no por consultas

El juego consulta el pad **unas cuatro veces por segundo** (medido: 800 polls
en 180 s). Un sosten medido en consultas es apenas un segundo: suficiente para
mover un cursor de menu, demasiado poco para girar una rueda.

El sufijo `@<segundos>` dice cuanto se mantiene, y **manda sobre las
consultas**:

```bash
MCLA_PAD_PRESS="3:s:0:-1@6"             # stick abajo 6 segundos
```

Medido: 6 s pedidos -> t=3.03s a t=9.02s; 4 s pedidos -> t=15.14s a t=19.10s;
el boton sigue siendo un toque (25.11s a 25.34s).

Registrar tambien el **release** es lo que permite comprobar si un sosten se
mantuvo entero o se corto por el camino.

## 7. El disparador por evento: `w:<ruta>|<timeout>|<accion>`

El guion de tiempos es un cronometro, y el juego no lleva el ritmo del
cronometro. El momento en que llega a la cinematica de intro cambia entre
corridas (medido: t+86 s a t+101 s), asi que un gesto fijado en un segundo
cae unas veces **dentro de la intro** (que ignora el input: un video no mira
el pad) y otras despues.

La solucion es que el gesto espere a un **fichero-señal** en vez de al reloj:

```bash
MCLA_PAD_PRESS="w:/tmp/paso0|600|s:1:0:0:0@10"
```

- El `w:` va **al principio** de la entrada, sin tiempo delante: es un
  disparador, no un momento. El parser tiene que comprobarlo **antes** de
  partir por el primer `:`, porque ese colon es el propio `w:` — si no,
  "w:/tmp/paso0" se lee como el tiempo "w" y la accion "/tmp/paso0", y la
  entrada se rechaza con `ignored malformed press entry`.
- Las partes se separan con `|`, no con `:`: tanto la ruta como la accion
  tienen dos puntos (la accion puede ser un stick, `s:1:0:0:0`), y con `:`
  no hay forma de saber donde acaba una y empieza la otra.
- El timeout es opcional (600 s por defecto, `0` es esperar para siempre) y
  la accion por defecto es el boton A.

Medido: el trigger dispara en cuanto aparece el fichero, con la accion
correcta (stick a la derecha 32767, y START 0x0010), y agota el timeout a los
8.01 s si el fichero no aparece.

## 8. El harness: conducir y cazar a la vez

`scripts/drive_with_trigger.py` lanza el juego, vigila el log buscando la
senal, y toca un fichero-señal **por gesto**:

```bash
python3 scripts/drive_with_trigger.py --timeout 480 --esperar-save --retardo 95
```

- Cada gesto necesita **su propio** fichero: si todos esperasen al mismo,
  dispararían a la vez.
- `--esperar-save` con `--retardo`: el guardado se escribe al **entrar**
  (t+60 s) pero la ciudad carga **despues** (t+155 s). El stick hay que
  darlo con la ciudad dentro, no al entrar.

Medido de punta a punta: los cinco triggers dispararon a t+151, 160, 170, 180
y 190 s — con 10 s de separacion exacta, independiente del ritmo del juego — y
el stick llego con magnitud completa. La tanda grande de shaders (142
pipelines) cae en t+154 s, justo cuando empieza el stick: **el gameplay se
ejecuta con la ciudad ya cargada**.

Para cazar huecos del gameplay, el hunting necesita el mismo disparador (un
guion de reloj no llega a la ciudad):

```bash
python3 scripts/fix_gap_crashes.py --trigger --max-rondas 6
```

Como el juego solo llega ~40 % de las veces, hacen falta varias rondas.

## 9. TRES bugs de lectura de log, todos de la misma familia

Todos estan en el mismo sitio: **el sink rotatorio del SDK**. Escribe en
`mcla_NNN.log` y, al llegar a 5 MB, renombra el actual a `mcla_NNN.1.log`
(cuyo contenido es **ANTERIOR**) y abre uno nuevo.

1. **Leer solo un archivo** pierde el principio de la corrida. Hay que
   concatenar todas las partes en orden cronologico.
2. **Contar ficheros no vale** para saber si la corrida actual escribio: al
   rotar, el numero total **no crece** (el `.1.log` se renombra a `.2.log`).
   Filtrar por **marca de tiempo**.
3. **La rotacion cambia de STEM**: `mcla_130.log` -> `mcla_130.1.log` +
   `mcla_131.log`. Leyendo solo el ultimo stem se pierden las lineas
   anteriores a la rotacion. Hay que gathering **todos** los stems de la
   corrida.

El tercero costaba un bug visible: el harness reportaba `disparos: 0` con
cinco disparos happening.

## 10. Checklist de una sesion de hunting

```bash
# 1. Que el juego corre sin X server y con el pad
MCLA_PAD_PRESS="9999:0x1000" scripts/test_pad_press.sh

# 2. Que la entrada llega (16 gestos con su mezcla)
MCLA_PAD_PRESS="3:0x1000,6:0x1000,9:0x0010" scripts/test_pad_press.sh

# 3. A/B con control real
scripts/ab_test_press.sh

# 4. Conducir y cazar el gameplay
python3 scripts/fix_gap_crashes.py --trigger --max-rondas 6
```

Antes de concluir que el codigo esta limpio, comprueba **hasta donde llego**
el juego (seccion 5: el `mc4.sav` y las tandas de shaders). Si no llego a la
ciudad, no encontraria huecos aunque los haya.
