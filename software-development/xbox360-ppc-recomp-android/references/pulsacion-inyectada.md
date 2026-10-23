# Inyectar pulsaciones en el port, sin movil

Como mandar botones al guest desde el PC, para probar el input y cazar los huecos
que solo se alcanzan al pulsar.

Referencia rapida: `references/auditoria-estado.md` (como medir el estado de un port
ya existente).

---

## 1. Por que hace falta

El juego llega a la pantalla de titulo y se queda ahi: el "PRESS >" no avanza. En el
movil eso se prueba tocando la pantalla, pero el movil tiene dos problemas como banco
de pruebas: con otra app en primer plano Android mata el port por memoria (~1.3 GB), y
el ciclo de hunting de huecos no puede tocar nada.

En el PC no hay atajo por el teclado:

- El **servidor X rechaza el teclado sintetico**. `XTestFakeKeyEvent` no mueve el
  keymap del servidor, y el evento no llega a ninguna ventana:

  ```bash
  #asi se comprueba, sin asumir nada
  XTestFakeKeyEvent(d, kc, True, 0); XSync(d, False);
  XQueryKeymap(d, keys);   # el bit de la tecla sigue en 0 -> el servidor no lo acepto
  ```

- El **SDL del proyecto es estatico** (`thirdparty/CMakeLists.txt` compila SDL3 con
  `SDL_SHARED OFF` en PC), asi que `SDL_PushEvent` desde otro proceso no llega a la
  cola de eventos del juego.

La salida es **inyectar el input en el sitio donde el juego lo lee**: el input system
del SDK.

## 2. El mecanismo

`rex::input::InputDriver` es una clase publica del SDK con metodos virtuales, y
`InputSystem::AddDriver` es publico. El proyecto puede registrar un driver propio
**sin tocar el SDK**:

```cpp
#include <rex/input/device.h>
#include <rex/input/input.h>
#include <rex/input/input_driver.h>
#include <rex/input/input_system.h>

// Los codigos de estado del SDK viven en el namespace rex.
using rex::X_RESULT;
using rex::X_STATUS;

namespace mcla {

// Un id de dispositivo propio: los drivers del SDK usan ids de su propio espacio
// (el de teclado es 0x4D4E4B00), asi que no puede colisionar.
constexpr rex::input::DeviceId kScriptedDevice = static_cast<rex::input::DeviceId>(0x53435250);

class ScriptedGamepadDriver final : public rex::input::InputDriver {
 public:
  explicit ScriptedGamepadDriver(std::vector<Press> presses)
      : InputDriver(nullptr, 0), presses_(std::move(presses)) {}

  X_STATUS Setup() override { return X_STATUS_SUCCESS; }

  void EnumerateDevices(std::vector<rex::input::DeviceInfo>& out) override {
    rex::input::DeviceInfo info;
    info.id = kScriptedDevice;
    info.name = "MCLA Scripted Gamepad";
    info.guid = "mcla-scripted-gamepad";
    // Sintetico: el SlotAssignment del SDK lo manda al usuario 0 del guest, el
    // mismo slot que el pad tactil en Android.
    info.synthetic = true;
    out.push_back(info);
  }

  X_RESULT GetDeviceState(rex::input::DeviceId id,
                          rex::input::X_INPUT_STATE* out_state) override {
    if (id != kScriptedDevice) {
      return X_ERROR_DEVICE_NOT_CONNECTED;
    }
    // El reloj arranca en la PRIMERA consulta (ver seccion 4).
    if (!started_) {
      started_ = true;
      start_ = std::chrono::steady_clock::now();
    }
    const double elapsed =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - start_).count();

    // Cada pulsacion avanza UNA consulta, no por reloj: el boton baja, el
    // guest lo ve, el boton sube (ver seccion 4).
    uint16_t buttons = 0;
    for (Scheduled& scheduled : schedule_) {
      switch (scheduled.state) {
        case PressState::kPending:
          if (elapsed >= scheduled.press.at_seconds) {
            scheduled.state = PressState::kDown;
            buttons |= scheduled.press.buttons;
          }
          break;
        case PressState::kDown:
          scheduled.state = PressState::kUp;   // el guest ya lo vio pulsado
          break;
        case PressState::kUp:
          scheduled.state = PressState::kDone;  // ya se reporto la subida
          break;
        case PressState::kDone:
          break;
      }
    }
    if (buttons != last_buttons_) {
      last_buttons_ = buttons;
      packet_number_++;   // el guest detecta el cambio por el numero de paquete
    }
    if (out_state) {
      out_state->packet_number = packet_number_;
      out_state->gamepad.buttons = buttons;
      // sticks y gatillos a cero
    }
    return X_ERROR_SUCCESS;
  }

  X_RESULT GetDeviceCapabilities(rex::input::DeviceId id, uint32_t flags,
                                 rex::input::X_INPUT_CAPABILITIES* out_caps) override { /* ... */ }
  X_RESULT SetDeviceVibration(rex::input::DeviceId id,
                              rex::input::X_INPUT_VIBRATION* vibration) override { /* ... */ }
  X_RESULT GetDeviceKeystroke(rex::input::DeviceId id, uint32_t flags,
                               rex::input::X_INPUT_KEYSTROKE* out_keystroke) override {
    return X_ERROR_INVALID_PARAMETER;   // no hay teclas, solo botones
  }

 private:
  // El estado de una pulsacion programada. Una pulsacion no es una ventana
  // de tiempo, es una secuencia de consultas (ver seccion 4).
  enum class PressState { kPending, kDown, kUp, kDone };

  struct Scheduled {
    Press press;
    PressState state = PressState::kPending;
  };

  std::vector<Scheduled> schedule_;
  std::chrono::steady_clock::time_point start_{};
  bool started_ = false;
  uint16_t last_buttons_ = 0;
  uint32_t packet_number_ = 0;
};

}  // namespace mcla
```

Instalacion, en el hook de la app. `OnPostSetup()` es el sitio: el runtime ya esta
construido (con su input system) y el guest aun no ha consultado el pad.

```cpp
// src/<juego>_app.h
void OnPostSetup() override {
  mcla::InstallScriptedGamepad(runtime()->input_system());
}
```

El `runtime()` da un `IInputSystem*`; el cast al `InputSystem` concreto (el que conoce
los drivers) va **dentro** de la funcion de instalacion, no en el llamante:

```cpp
void InstallScriptedGamepad(rex::system::IInputSystem* input_system) {
  if (!input_system) return;
  auto* presses = ReadPressScript();     // vacio -> no se instala nada
  if (presses.empty()) return;
  auto* concrete = static_cast<rex::input::InputSystem*>(input_system);
  concrete->AddDriver(std::make_unique<ScriptedGamepadDriver>(std::move(*presses)));
}
```

## 3. Comprobar que el runtime exporta lo que necesitas

Antes de escribir el driver, comprueba que la clase base se puede derivar desde el
ejecutable:

```bash
nm -D --defined-only out/pc/librexruntime.so | grep -E "InputSystem::AddDriver|InputDriver::~"
```

Deben salir `InputSystem::AddDriver`, los dos `InputDriver::~InputDriver`, el vtable y
el typeinfo. Si `~InputDriver` no estuviera exportado, la clase no se podria derivar
fuera del SDK.

## 4. El reloj arranca en la primera consulta, y la pulsacion se entrega por consulta

**Este es el error que hace que el script "no haga nada".** El guest no mira el pad
hasta que llega a la pantalla de titulo: en una corrida real, el driver se instalo en
`t+0` y la primera consulta llego en `t+38`. Un temporizador que arranca al construir el
driver dispara cada pulsacion en el hueco, antes de que nadie pregunte.

Arranca el reloj en la primera llamada a `GetDeviceState`, y programa los tiempos
relativos a ahi. Con eso, "2:0x1000" significa "pulsa A dos segundos despues de que el
juego mire el mando por primera vez", que es lo que uno quiere decir.

Los tiempos de la pulsacion se verifican en el log: si aparece
`pressing 0x1000 at t=2.02s`, el reloj y el script estan bien.

### La pulsacion se entrega POR CONSULTA, no por ventana de tiempo

La segunda mitad del error, mas sutil: **una ventana fija de tiempo pierde pulsaciones.**
Medido: con 8 pulsaciones programadas y una ventana de 200 ms, **solo se entregaban 4**.

El motivo es que el polling del guest no es regular: cuando esta ocupado (compilando
shaders, cargando una pantalla nueva) se ralentiza hasta arrastrarse, y una ventana de
200 ms puede caer **entera entre dos consultas**. El boton se bajo y subio sin que nadie
lo mirara, y el juego no se entero.

La solucion es que la pulsacion avance **de consulta en consulta**: el boton baja, el
guest lo ve en la siguiente consulta, y el boton sube en la siguiente a esa. Asi la
pulsacion no se pierde nunca; un polling lento solo retrasa la subida.

```cpp
enum class PressState { kPending, kDown, kUp, kDone };

// dentro de GetDeviceState, por cada pulsacion programada:
switch (scheduled.state) {
  case PressState::kPending:
    if (elapsed >= scheduled.press.at_seconds) {
      scheduled.state = PressState::kDown;
      buttons |= scheduled.press.buttons;   // el guest lo vera bajando
    }
    break;
  case PressState::kDown:
    scheduled.state = PressState::kUp;       // ya lo vio: suelta
    break;
  case PressState::kUp:
    scheduled.state = PressState::kDone;     // ya se reporto la subida
    break;
  case PressState::kDone:
    break;
}
```

Con este modelo, 8 pulsaciones programadas se entregan **8**.

## 5. Los botones son bits de XInput

Los mismos que usa el overlay tactil en Android:

| Boton | Mascara |
| --- | --- |
| A | `0x1000` |
| B | `0x2000` |
| X | `0x4000` |
| Y | `0x8000` |
| START | `0x0010` |
| BACK | `0x0020` |
| D-pad arriba/abajo/izq/der | `0x0001` / `0x0002` / `0x0004` / `0x0008` |

Un script de pulsaciones se lee de una variable de entorno (para no ensuciar el
registro de cvars con un knob de pruebas): `MCLA_PAD_PRESS=2:0x1000,8:0x1000`.

## 6. Medir si el juego avanzo

Un contador de pipelines que sube no prueba nada: el titulo tambien crea pipelines
mientras carga. Lo que dice si el juego **cambio de pantalla** es el conjunto de hashes
de shader que crea.

**Cuidado con dos trampas al comparar dos corridas:**

1. **El log rota.** `<nombre>.log` es la parte **nueva** y `<nombre>.1.log` la
   **antigua**. Leer solo la nueva pierde el principio de la corrida. Concatena en orden
   cronologico antes de comparar.
2. **La textura de swap alterna** entre dos direcciones (doble buffer), con lo que no
   identifica la pantalla.

El metodo que funciona:

- Corrida **con** pulsacion y corrida **control** sin pulsacion, de la **misma
  duracion** (el tiempo total de ejecucion cambia el resultado: una corrida mas larga
  carga mas pipelines por el solo hecho de seguir viva).
- Extrae los hashes de vertex shader de las lineas `Creating graphics pipeline state
  with VS <hash>` y compara los **conjuntos**.
- La corrida con pulsacion carga un conjunto de shaders que el control **nunca** carga,
  y adelanta la tanda que ambos comparten.

Medido en MCLA: control 280 pipelines, una pulsacion de A 286 (con 12 shaders que el
control nunca carga y la tanda comun 15 s antes), tres pulsaciones 421 pipelines, todo
con **0 errores fatales** — y el hueco `0x82554080`, que colgaba al pulsar en el movil,
ya no aparece.

`scripts/comparar_corridas.py` hace la concatenacion del log, la cuenta y la diferencia
de conjuntos:

```bash
python3 <skill>/scripts/comparar_corridas.py out/pc/logs/mcla_046.log out/pc/logs/mcla_047.log
```

### La senal mas fuerte: los ficheros de datos que lee el juego

El conjunto de shaders dice que el juego *cambio de pantalla*, pero la senal mas
inequivoca es **que ficheros de datos del juego lee**. El kernel registra cada lectura
del sistema de ficheros virtual (`leer N bytes de 'xarchive_cache.rpf'`), asi que se
puede comparar el conjunto de ficheros leidos entre la corrida con pulsaciones y el
control.

Medido en MCLA: con 16 pulsaciones el juego lee **`xarchive_audlo.rpf`** (0.3 MB), un
fichero que **el control no lee nunca** (0 lecturas, A/B limpio). El juego llego a
contenido nuevo, y el contenido nuevo es codigo nuevo — que es donde puede haber un
hueco.

```bash
grep -oE "leer [0-9]+ bytes de '[^']+'" out/pc/logs/mcla_XXX.log | sort -u
```

Un guion largo y variado (A, START y las cuatro flechas) es lo que llega a esas
pantallas; uno corto se queda en el menu.

## 6b. Mas alla del boton: stick, disparadores y conduccion

Este fichero se queda en **inyectar botones** (el driver, el reloj, la
pulsacion por consulta). Todo lo que viene despues —el **stick analogico**
sostenido por tiempo, el **disparador por evento** (`w:<ruta>|<timeout>|<accion>`),
la entrada de 16 gestos que llega al free roam, y el harness que conduce el
juego— esta en `references/conduccion-y-trigger.md`.

La regla minima: un boton es un **flanco** y va por consulta; un stick es una
**posicion** y se sostiene por **tiempo** (`@<segundos>`), porque el juego
consulta el pad unas cuatro veces por segundo y un sosten medido en consultas
es apenas un segundo.

## 7. Con esto se cazan los huecos que solo se alcanzan al pulsar

El ciclo de `fix_gap_crashes.py` corre el juego sin tocar nada, asi que los huecos del
codigo de input se le escapan. Con el mando inyectado la corrida **pulsa**, y si el
codigo cae en un hueco sin dueno sale solo:

```
[FATAL] Call to invalid or unregistered function at guest address 0x82554080
```

Esa direccion se busca con `tools/huecos.py --comprobar 0x82554080` y se declara una
entrada cada 8 bytes dentro del hueco, en el analysis TOML.

### El ciclo necesita un flag de pulsaciones

El hunting se integra en el ciclo con un flag, para que la corrida pulse sola:

```bash
python3 scripts/fix_gap_crashes.py --pulsar "3:0x1000,7:0x1000,11:0x0010" --timeout 120
```

El script de pulsaciones son pares `<segundos>:<mascara XInput>` separados por comas, y
los segundos se cuentan desde que el guest empieza a mirar el pad. El ciclo pasa
`MCLA_PAD_PRESS` al entorno del juego.

### Dos bugs del ciclo que hacian perder crashes

Ambos seanggang solo cuando el juego tarda en arrancar o la corrida es larga:

1. **El log rota y el ciclo leia un solo archivo.** El sink rotatorio del SDK escribe
   en `mcla_NNN.log` y al llegar a 5 MB renombra el actual a `mcla_NNN.1.log`, cuyo
   contenido es **ANTERIOR**. Un crash temprano cae en la parte rotada y el ciclo no lo
   ve. El ciclo tiene que leer **todas** las partes, en orden cronologico.
2. **El paso de estado de la pulsacion** (seccion 4): con una ventana fija se perdian
   la mitad de las pulsaciones, y el hunting llegaba a pantallas menos profundas de
   las que debia.

### Que el hunting no encuentre huecos es un resultado, no un fallo

Medido en MCLA: el hunting con 6 pulsaciones **no encontro ningun hueco** — el codigo de
input esta limpio. Los 633 huecos de >=8 bytes que quedan en el informe **no** se tocan
con pulsaciones de menu: hacen falta los **axes analogicos** (el stick) para elegir
opciones y llegar al free-roam, que es donde esta el grueso del juego. Un guion de
pulsaciones de boton no llega ahi.

Distingue "no hay huecos" de "no has llegado": mira si el juego leyo ficheros de datos
nuevos (seccion 6). Si no leyo ninguno, el guion no ha llevado el juego a ninguna parte
nueva.

## 8. Con el movil, la misma mecanica en otro sitio

En Android el input ya llega por el overlay tactil (`rex_sdl_set_touch_gamepad_state`),
pero el **mismo mando inyectado** sirve para lo que el movil no puede: automatizar la
prueba de la pulsacion sin depender de que alguien toque la pantalla y sin que otra app
mata el port por memoria. El overlay tactil y el mando inyectado son dos rutas al
mismo `SlotAssignment` (usuario 0).
