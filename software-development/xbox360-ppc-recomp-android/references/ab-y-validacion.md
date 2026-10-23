# Validar que un cambio hace algo (A/B honesto)

Como responder "¿este cambio hizo que el juego avanzara?" con un numero que
signifique algo. Un port no determinista y un host con recursos finitos
producen mediciones que mienten si no se controlling.

Referencia rapida: `references/pulsacion-inyectada.md` (inyectar input),
`references/auditoria-estado.md` (medir el estado de un port ya existente).

---

## 1. El host tiene que poder ejecutar el juego

El juego abre una ventana de SDL. Sin `DISPLAY` (o sin un X server) **muere
en 0.03 s con `No available video device`**: sin log, sin crash, sin nada.

Ese es el fallo mas peligroso de esta guia, porque es **silencioso**: un A/B
cuyo harness corre en un entorno sin display da numeros **identicos siempre**,
que parece un resultado ("las pulsaciones no cambian nada").

Always pasa `--video_driver=offscreen` (el driver de SDL que no necesita X):

```bash
./out/pc/<juego> --game_data_root=... --video_driver=offscreen
```

Y en el harness, comprueba que la corrida **vivo** antes de medir: si el
numero de pipelines es 0, la corrida no arranco.

## 2. El control tiene que controlar

Un control mal construido mide mas de una variable a la vez.

Si el driver inyectado se instala **solo cuando hay guion**
(`if (presses.empty()) return;`), entonces el "control sin pulsaciones" es un
guest que **no ve ningun dispositivo de juego**: el control y el tratamiento
difieren en (a) que haya un pad conectado y (b) que se pulse algo.

El control honesto es un guion que **instala el pad pero nunca pulsa**: un
gesto programado mas alla del final de la corrida.

```bash
# control: pad presente, ningun boton baja nunca
MCLA_PAD_PRESS="9999:0x1000" ...
# tratamiento: el mismo pad, con pulsaciones
MCLA_PAD_PRESS="3:0x1000,6:0x1000,9:0x0010" ...
```

Regla general: **cambia una variable, o no puedes atribuir el efecto.** Si
necesitas mas de una condicion, haz una corrida por condicion.

## 3. Las dos corridas tienen que durar lo mismo

El tiempo total de ejecucion cambia el resultado por si solo (una corrida mas
larga carga mas pipelines por seguir viva). Y hay un final mas sutil: **el OOM
killer mata el juego** cuando carga `.rpf` de mas de un gigabyte, asi que una
corrida puede morir a los 84 s mientras otra llega a los 300 s.

Comparar "922 contra 650" donde el 650 era una corrida **asesinada** produce
un resultado falso y muy convincente. **Mira siempre el codigo de salida**:

| codigo | significado |
| --- | --- |
| 124 | `timeout` lo mato: llego al final de la ventana |
| 137 | OOM killer (SIGKILL): **la medicion no vale** |
| 0 | el juego termino solo |

## 4. El conteo absoluto es ruidoso; la diferencia es solida

La misma corrida de control, repetida, dio **299, 265 y 556** pipelines en
sesiones distintas. Comparar el conteo de hoy contra un numero guardado de
ayer no significa nada.

Lo que si es solido es la **diferencia entre condiciones en la misma sesion**,
repetida varias veces, y el **conjunto** de shaders (no el total): lo que
distingue una pantalla de otra es que shaders se crean, no cuantos.

```bash
# dos runs del mismo binario, para ver el ruido del propio control
for i in 1 2 3; do <corrida de control>; done
```

Reporta la distribucion, no un punto.

## 5. El juego no es determinista

La misma entrada de 16 pulsaciones, en los mismos segundos, con el mismo
numero de gestos en el log, **llego a la partida en unas corridas y en otras
no**. No es un bug del port: es que el juego tiene caminos que dependen del
tiempo.

Consecuencias practicas:

- Una medicion no es un resultado: **repite cada condicion** y reporta cuantos
  intentos llegaron.
- Un hunting que no encuentra nada en una ronda no demuestra que no haya
  nada: puede que la ronda no llegara. Varias rondas, y distingue "no llego"
  de "llego y no habia hueco".
- **Ningun guion por tiempo puede apuntar a un estado que el juego alcanza a
  un momento variable.** Para eso estan los disparadores por evento (seccion 6
  de `references/pulsacion-inyectada.md`).

## 6. La senal fuerte, y como distinguir "no llego" de "llego y no habia hueco"

Cuenta de pipelines: no prueba nada (el titulo tambien crea pipelines).

En orden de fiabilidad:

1. **El juego escribio un fichero de guardado** (p.ej. `mc4.sav`): entro en
   una partida de verdad. Es la senal inequivoca de que llego.
2. **Leyó ficheros de datos que el control no lee**: es contenido nuevo, y el
   contenido nuevo es codigo nuevo.
3. **El conjunto de shaders** que crea, comparado con el control.

Y el contrapaso: si el hunting no encuentra huecos, **comprueba que la corrida
llego** antes de concluir que el codigo esta limpio. Si no llego, no
encontraria huecos aunque los haya.

## 7. Checklist antes de publicar un numero

- [ ] La corrida arranco (pipelines > 0) y no fueectinada por el OOM (exit != 137)
- [ ] El control y el tratamiento difieren en **una** variable
- [ ] Ambas corridas duraron lo mismo
- [ ] La condicion se repitio varias veces, y se reporta el reparto, no un punto
- [ ] El numero se compara **dentro** de la sesion, contra un control de la misma sesion
- [ ] La senal de "llego" esta verificada (guardado escrito, o ficheros nuevos leidos)
- [ ] El log se leyo **completo**: todas las partes, de todos los stems, por marca de tiempo
