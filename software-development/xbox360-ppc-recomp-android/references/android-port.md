# Port Android de un proyecto ReXGlue

Checklist y arreglos del port a APK Android. Los fallos aparecen **uno detrás de otro** y
todos se ven igual desde fuera ("el juego no arranca"), así que auítalos en este orden y
no arregles el síntoma equivocado.

Referencia rápida: `references/auditoria-estado.md` (cómo medir el estado de un port ya
existente antes de tocarlo).

---

## 1. Estructura mínima del port

```text
android/
  app/build.gradle                    ndkVersion, abiFilters, cmake version, externalNativeBuild
  app/src/main/AndroidManifest.xml
  app/src/main/assets/<juego>.toml    configuracion que la app copia a REX_APP_FOLDER
  app/src/main/cpp/CMakeLists.txt    add_subdirectory(<proyecto>), target_link_libraries del plugin GPU
  app/src/main/cpp/<juego>_entry.cpp  entrada: registra el app creator con el SDL main del SDK
  app/src/main/cpp/<juego>_performance.cpp   lectura del contador de FPS del SDK
  app/src/main/cpp/android_touchpad.cpp     puente JNI del pad tactil
  app/src/main/java/com/<juego>/android/
    MainActivity.java        launcher: elegir/instalar la carpeta del juego, opciones, logs
    GameActivity.java        actividad de SDL: carga las libs, copia el .toml, fija orientacion
    TouchPadView.java        vista del pad tactil
```

En `app/build.gradle` el proyecto del juego entra por `externalNativeBuild` (CMake propio en
`src/main/cpp`), **no** por `jniLibs/`: el SDK se compila como parte del proyecto y de ahí
salen `libmain.so`, `librexruntime.so` y `librexgpu-xenos.so`. Por eso los binarios
intermedios viven en `app/build/intermediates/cxx/Release/<hash>/obj/arm64-v8a/`.

## 2. Los cuatro fallos, en orden

### 2.1 El plugin de GPU no se encuentra (0 pipelines, log corto)

El SDK busca el plugin por soname (`dlopen("librexgpu-xenos.so")`). En Android eso solo
encuentra una biblioteca que **la app ya cargó con `System.loadLibrary`**: el `SDLActivity`
carga el `libmain.so` del juego **por ruta** (`nativeLibraryDir + "/libmain.so"`), en su
propio namespace, así que el plugin no es visible desde ahí y el juego se queda esperando
sin dibujar.

Arreglo: incluir el runtime en `getLibraries()` de la actividad.

```java
@Override
protected String[] getLibraries() {
    return new String[]{"SDL3", "rexruntime", "main"};
}
```

Con `librexruntime.so` en el namespace de la app, el `dlopen` del plugin desde dentro sí
lo encuentra. Lo mismo hace que funcionen los hooks `weak` entre `.so`: un símbolo `weak`
definido en el juego no resuelve si el que llama se cargó en otro namespace.

### 2.2 El `<juego>.toml` no se lee

El SDK busca la configuración en `exe_dir / <nombre>.toml`, y en Android `exe_dir` es la
variable de entorno `REX_APP_FOLDER` (la pone la actividad). Sin ese fichero no se aplican
los cvars — y sin `gpu_plugin = "xenos"` el kernel registra `no GPU emulation loaded (gpu
plugin not set); call ignored`, que **no es fatal** y por eso se pierde en el ruido del log.

El fichero va en `assets/` y la app lo copia a `REX_APP_FOLDER` al arrancar.

```toml
gpu_plugin = "xenos"
present_letterbox = false
async_shader_compilation = true
vulkan_pipeline_creation_threads = 2
vulkan_require_geometry_shader = false
vulkan_require_fill_mode_non_solid = false
vulkan_native_shader_features = false
render_target_path_vulkan = "fbo"
user_language = 1
```

### 2.3 El teléfono rota a vertical y rompe la superficie

SDL pide `FULL_USER` al crear la ventana (redimensionable, sin hint) y la superficie llega
en 1080x2400 cuando el swapchain se hizo en 2400x1080: el juego espera un fotograma que no
llega. Arreglo: forzar landscape en la actividad con `setRequestedOrientation`.

### 2.4 SDL3 tiene que ser una librería compartida

El SDK la compila estática (`thirdparty/CMakeLists.txt: set(SDL_SHARED OFF ...)`), pero el
`SDLActivity` carga `libSDL3.so` con `System.loadLibrary`: sin la compartida, el juego muere
al arrancar con `dlopen failed: library "libSDL3.so" not found`. En el `CMakeLists.txt` del
port: `set(SDL_SHARED ON ...)` y `set(SDL_STATIC OFF ...)`.

## 3. Gamepad táctil

El SDK ya trae la parte difícil: `src/input/sdl/sdl_input_driver.cpp` crea un mando
sintético en Android (`is_touch = true`, `synthetic = true` → usuario 0) y publica su
estado con `rex_sdl_set_touch_gamepad_state(botones, lx, ly, rx, ry, lt, rt)`. Los bits
son los de XInput (`A = 0x1000`, `B = 0x2000`, `X = 0x4000`, `Y = 0x8000`).

Lo que falta es **la vista Java** que dibuja el pad (sticks, cruceta, A B X Y, LT/RT, LB/RB,
L3/R3, BACK/START) y llama a esa función. Dos detalles que costaron:

- La vista necesita `setClickable(true)`: Android solo entrega los toques a una vista que
  dice que los maneja.
- El puente JNI tiene que estar **dentro de `libmain.so`** (`android_touchpad.cpp` se
  compila en el target del juego): Java busca funciones JNI solo en las bibliotecas que
  cargó él mismo.

Ejes: la vista manda −1..1 con abajo y derecha positivos; XInput tiene la Y hacia arriba, así
que el puente invierte la Y. Disparadores: la vista manda 0..1, XInput quiere 0..255.

## 4. Contadores de FPS

El SDK solo compila los contadores fuera de Release
(`add_compile_definitions($<$<NOT:$<CONFIG:Release>>:REXGLUE_ENABLE_PERF_COUNTERS>)`), y el
APK es Release. Hay que habilitarlos **también en el target del juego** (el SDK solo los
aplica a sus propios objetivos): son unos atómicos, no un perfilador.

No escribas tu propio cronómetro: el hook de swap del SDK
(`CommandProcessor::ExecutePacketType3_XE_SWAP`) mide el tiempo entre swaps y lo publica con
`PROFILE_FRAME_TIME_US()` / `PROFILE_FPS()`. El launcher lee
`rex::perf::GetSnapshotCounter(rex::perf::CounterId::kFrameTimeUs)`.

## 5. Verificar el APK por contenido

`assembleRelease` no sabe lo que le falta al juego: una vista Java o un puente JNI
ausentes producen un APK perfecto y un juego quieto en el título. Verifica el artefacto:

```bash
APK=android/app/build/outputs/apk/release/app-release.apk
~/Android/sdk/build-tools/37.0.0/apksigner verify --print-certs "$APK"
~/Android/sdk/build-tools/37.0.0/aapt2 dump badging "$APK" | grep -E "^package|native-code|versionName"
unzip -l "$APK" | grep -E "\.so$|assets/"

cd /tmp && rm -rf apkchk && mkdir apkchk && cd apkchk
unzip -q -o "$APK" "classes*.dex" "lib/arm64-v8a/*"
strings -a classes*.dex | grep -i TouchPadView
nm -D --defined-only lib/arm64-v8a/libmain.so | grep -i nativeSetState
```

Criterio: la clase del pad está en `classes.dex` y el símbolo JNI en `libmain.so`.

## 6. En el dispositivo

- El juego lee de `<sdcard>/<JUEGO>`; el launcher instala o copia la carpeta.
- Con otra app en primer plano, Android mata el port por memoria (~1.3 GB): el proceso
  muere con `signal 9 (Killed)` y **sin** `FATAL`. Eso **no** es un crash del port.
- Un hueco de codigo que solo se alcanza **al pulsar** (por ejemplo el del input) no lo ve
  el ciclo automatico de huecos, porque el juego corre sin tocar nada. Se puede injectar un
  mando de prueba en el input system del SDK **desde el proyecto**, sin tocar el SDK, para
  que la corrida pulse sola: la receta esta en `references/pulsacion-inyectada.md`. Cuando
  el juego se cuelgue al pulsar, lee la direccion del crash
  (`Abort message: '[FATAL] Call to invalid or unregistered function at guest address 0xADDR'`),
  busca el hueco con `tools/huecos.py --comprobar ADDR` y declara una entrada cada 8 bytes.
- Log de sesión: `Android/data/<paquete>/files/logs`; argumentos extra: cada línea que
  empiece por `--` en `Android/data/<paquete>/files/args.txt`.

## 7. Requisitos de GPU

Vulkan 1.1 **con descriptor indexing** (la versión sola no garantiza las funciones).
Turnip para Adreno, PanVK para Mali. El Xenos emulado se queda en 1280×720 por la EDRAM
emulada; por encima de 720p solo con renderizador nativo.
