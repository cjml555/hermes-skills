---
name: xbox360-ppc-recomp-android
description: "Recompila juegos Xbox 360 (PPC) a APK Android con ReXGlue."
version: 0.1.0
author: jhon, Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [android, recompilacion, rexglue, xbox360, powerpc, ndk, apk, vulkan]
    related_skills: [android-build-troubleshooting, android-device-deployment, apktool, android-native-dev]
---

# Recompilación de juegos Xbox 360 (PowerPC) a APK Android

Traduce el código PowerPC de un ejecutable `default.xex` de Xbox 360 a C++ y lo compila
para Android ARM64 (Vulkan) y PC (Xenos/D3D12) usando **ReXGlue**. Cubre el pipeline
completo: preparación del árbol, generación de código, reparación de entradas, y el APK.

**No recupera el código fuente original** y **no distribuye datos del juego**: el
`default.xex` y las carpetas `NFS`/`Movies` los aporta el usuario desde su propia copia.
Para parchear un APK ya construido usa la skill `apktool`, no esta.

## When to Use

- Recompilar un juego de Xbox 360 a un APK Android o a un ejecutable de PC.
- Retomar un proyecto ReXGlue existente: regenerar código, reparar saltos, reconstruir el APK.
- Diagnosticar un fallo del pipeline: codegen incompleto, entradas faltantes, APK que no arranca.

Don't use for:
- Editar/repackear un APK existente sin código fuente → `apktool`.
- Solo compilar un proyecto Gradle normal → `android-build-troubleshooting`.
- Instalar el APK en el teléfono → `android-device-deployment`.

## Prerequisites

Audita antes de tocar nada — este pipeline falla en silencio si falta una pieza:

```bash
for c in clang-20 clang++-20 cmake ninja python3 java adb; do
  printf '%-10s -> %s\n' "$c" "$(command -v $c || echo FALTA)"
done
python3 -c "import capstone; print('capstone', capstone.__version__)"
ls -1 "$ANDROID_HOME/ndk/"
```

Si falta `capstone`, instálalo en el *user site* del python que invocas — no en el venv de Hermes,
que es el runtime del agente:

```bash
uv pip install --target "$(python3 -m site --user-site)" "capstone==5.0.7"
python3 -c "import capstone; print(capstone.__version__)"   # criterio: 5.0.7
```

| Requisito | Versión |
| --- | --- |
| LLVM / Clang | **20** (probado 20.1.8) — el preset de Linux invoca `clang-20` exacto |
| CMake | 3.30.5 (mínimo del proyecto 3.25) |
| Ninja | cualquiera reciente |
| Python 3 + `capstone` | capstone **5.0.7** (lo usan `tools/recover_small_entries.py` y `verify_small_entries.py`) |
| JDK | 17 o superior (21 sirve) |
| Android SDK | API 35, `build-tools`, y **NDK `28.2.13676358`** exacto |
| `apksigner`, `zipalign` | vienen dentro de `build-tools/<ver>/` |

**Distribución de carpetas (obligatoria, son hermanas):**

```text
carpeta-de-trabajo/
  NFS-CARBON-360-ANDROID-RECOMP/   # proyecto ReXGlue del juego
  nfsmw-android/                   # SDK compartido + renderizador nativo
  need_for_speed_carbon/           # TU copia: default.xex, NFS/, Movies/
```

El nombre de la carpeta del juego debe coincidir **exactamente** con `game_root` del
manifest (`<juego>_manifest.toml`), en minúsculas. Linux distingue mayúsculas y el README
puede mostrar otro nombre.

## Procedure

### 0. Auditar un proyecto que ya existe

Antes de tocar nada mide el estado real: el README y los commits cuentan una historia, el
árbol y los artefactos son la verdad. Audita en este orden y separa siempre lo **verificado
ahora** de lo **documentado**:

```bash
git -C <proyecto> log --oneline -15                       # qué se hizo, y si está pusheado
git -C <proyecto> status --short --untracked-files=all
ls <proyecto>/generated/default/*.cpp | wc -l              # codegen hecho
grep -c '= { }' <proyecto>/<juego>_analysis.toml          # entradas declaradas a mano
python3 <proyecto>/scripts/huecos.py --gen <proyecto>/generated/default --salida out/huecos_now.txt
grep -c FATAL <proyecto>/out/pc/logs/<ultimo>.log          # 0 = sin crash de función sin dueño
grep -c "Creating graphics pipeline" <proyecto>/out/pc/logs/<ultimo>.log
```

El procedimiento completo —qué prueba cada comando, cómo distinguir un hueco de 4 bytes
(thunk, no bloquea) de uno de 8, cómo verificar el **contenido** del APK más allá del
`badging`, y por qué "el dispositivo no está conectado" significa *sin verificar*, no
*funciona*— está en `references/auditoria-estado.md`.

### 1. Preparar el SDK compartido

`nfsmw-android` es el SDK compartido por todos los juegos: se prepara **una vez**. Su
`sdk/thirdparty/` solo versiona los archivos que este port cambió; el resto hay que traerlo del
ReXGlue upstream.

```bash
cd ~/nfsmw-android
python3 tools/fetch_thirdparty.py          # clona el SDK upstream + submodulos y rellena lo que falta
```

Es una descarga grande (FFmpeg, SDL3, imgui, tracy, glslang, spirv-tools): minutos, no segundos.
Criterio de que terminó bien — **ningún directorio requerido vacío**:

```bash
for s in fmt utfcpp imgui sdl3 tracy cli11 tomlplusplus libmspack; do
  printf '%-16s %s entradas\n' "$s" "$(find "sdk/thirdparty/$s" -mindepth 1 | wc -l)"
done
```

Un `0 entradas` en cualquiera de ellos significa que el SDK no va a configurar, y el error de CMake
habla de «git submodule … is not initialized» — ver el pitfall correspondiente.

### 2. Verificar la copia del juego

Coloca `default.xex` + `NFS/` + `Movies/` dentro de la carpeta del manifest. Comprueba la
identidad — el launcher **rechaza** otro ejecutable porque el código recompilado y los
ganchos dependen de sus direcciones:

```bash
sha256sum need_for_speed_carbon/default.xex
# Carbon PAL: b1e423914f5feb0871c8903aded4d86852d34be3b831b42f5c6473c7c7304221
# Title ID 454107EC · Media ID 5E74E60D · Entry point 0x82943460
```

Si solo tienes un ISO, **no lo abras con `7z`**: un dump de Xbox 360 usa el sistema de archivos
XDVDFS, no ISO9660. `7z` sobre el `.iso` lista únicamente la capa DVD-vídeo (`VIDEO_TS/`,
`$SystemUpdate/`) y termina con `Errors: 1` — parece un disco corrupto y no lo es. Tampoco lo
abre si el archivo termina en `.xiso.iso`.

Usa `extract-xiso` (no está en los repos de Arch/Manjaro, se compila desde fuente en segundos):

```bash
cd "$BH_AGENT_WORKSPACE" && git clone --depth 1 https://github.com/XboxDev/extract-xiso.git
cmake -S extract-xiso -B extract-xiso/build -DCMAKE_BUILD_TYPE=Release
cmake --build extract-xiso/build --parallel 4
install -Dm755 extract-xiso/build/extract-xiso ~/.local/bin/extract-xiso

extract-xiso -l juego.iso                  # lista: debe aparecer default.xex
extract-xiso -d ~/<juego> juego.iso       # extrae (~2.5 min para 6.5 GB)
```

Criterio: `default.xex` existe y su `sha256sum` coincide con la copia soportada. Para confirmar que
es un XEX2 real y sacar su identidad (Title ID, Media ID, versión, disco) usa el script incluido —
sale distinto de cero si el archivo no es un XEX2, así que sirve de puerta:

```bash
python3 scripts/xex_info.py ~/<juego>/default.xex
```

El Title ID identifica edición y región; consérvalo, porque decide si el análisis del juego aplica.

### 2b. Crear el proyecto ReXGlue si el juego no tiene uno

El SDK trae el CLI `rexglue` (fuente en `sdk/src/rexglue/`; subcomandos `init`, `codegen`,
`test-recompiler`). Constrúyelo desde el SDK **después** de poblar `thirdparty/`:

```bash
cd ~/nfsmw-android/sdk
cmake --preset linux-amd64                 # Ninja Multi-Config; usa clang/clang++ (no clang-20)
cmake --build out/build/linux-amd64 --config Release --target rexglue --parallel 4
./out/build/linux-amd64/Release/rexglue --version      # criterio
```

Luego genera el proyecto, con el manifest apuntando a tu copia del juego:

```bash
rexglue init --project-name <juego> --xex-path ~/<juego>/default.xex --game-root ~/<juego>
rexglue codegen <juego>_manifest.toml
```

`init` acepta además `--project-root`, `--scan-dll` y `--template-dir`. Reescribe
`--xex-path` y `--game-root` como rutas **relativas a la raíz del proyecto** (`../<juego>/default.xex`),
así que pásalas absolutas y deja que él las relativice; el proyecto tiene que quedar **hermano** de
`nfsmw-android` y de la carpeta del juego para que esas relativas resuelvan después. Deja `game_root`
en minúsculas para que coincida con el directorio real.

**Verifica `rexglue --version` antes de encadenar el resto.** Estos comandos salen de los presets y
del `--help` del propio SDK; encadenarlos sobre un árbol a medio poblar da errores que no apuntan a
la causa.

### 3. Generar código (fase PC)

El codegen corre en el host, no en el teléfono. Configura y genera:

```bash
cd ~/NFS-CARBON-360-ANDROID-RECOMP
cmake -S . -B out/pc -G Ninja \
  -DCMAKE_C_COMPILER=clang-20 -DCMAKE_CXX_COMPILER=clang++-20 \
  -DREXSDK_DIR="$HOME/nfsmw-android/sdk" \
  -DCMAKE_BUILD_TYPE=Release
cmake --build out/pc --target nfscarbon_codegen --parallel 4
```

Criterio: existe `generated/default/sources.cmake`. El target se llama
`<proyecto>_codegen` (aquí `nfscarbon_codegen`).

### 3b. Resolver las llamadas huérfanas del análisis

`rexglue codegen` aborta **antes de generar nada** si el análisis deja ramas cuyo destino no
pertenece a ninguna función:

```
Analyze: found 7 errors
=== ANALYSIS ERRORS ===
UnresolvedCall (7):
  0x823F32E8 from 0x823FB7F4: b 0x823F32E8 from 0x823FB7F4 - target not in any function
Failed: Validation failed: 7 unresolved calls (after 61.9s)
```

No es un binario corrupto ni una copia mala: son ramas directas / llamadas de cola que el
descubrimiento no atribuyó a nadie. Se declaran en el **analysis TOML del proyecto**, que el
manifest tiene que listar en `includes` (si no, el archivo se ignora en silencio):

```toml
# <juego>_analysis.toml
cr_as_local = false
xer_as_local = false
ctr_as_local = false
non_volatile_as_local = false

[functions]
"0x823F32E8" = { }
```

Es **iterativo**: declarar una dirección cambia el descubrimiento de límites de las funciones
vecinas, así que la ronda siguiente reporta un destino nuevo, a menudo a pocos bytes del
anterior. No lo hagas de uno en uno a mano (~60 s por ronda, sin saber cuántas faltan):

```bash
python3 scripts/fix_orphan_branches.py ~/<proyecto>    # itera hasta que la validación pase
```

Criterio: el script sale 0 y `generated/default/` se llena con los `.cpp`. El proyecto Carbon
trae este mecanismo ya resuelto a mano en `carbon_analysis.toml` — úsalo como plantilla del
formato y del comentario por dirección.

### 3c. Triagear y declarar los huecos de codigo

Las ramas huerfanas (3b) son solo una clase de hueco. Los huecos que quedan
**sin dueno** —bloques de codigo que nadie reclama— se triagean aparte, y el
informe de `scripts/huecos.py` **no es el juez**: un hueco listado puede
tener ya su funcion (el Discover la reclamo con un tamano menor que el hueco),
y un hueco puede ser la **tabla de imports del kernel**, no codigo.

```bash
# 1. medir (el informe caduca con cada codegen: regeneralo)
python3 <proyecto>/scripts/huecos.py --gen <proyecto>/generated/default \
    --salida out/huecos_now.txt

# 2. que huecos son reales (tienen funcion? tocan la tabla de imports?)
python3 <skill>/scripts/triage_huecos.py <proyecto> --informe

# 3. declarar de a poco (piloto de 5, backup, vuelta atras si el codegen rompe)
python3 <skill>/scripts/triage_huecos.py <proyecto> --piloto
python3 <skill>/scripts/triage_huecos.py <proyecto>
```

Criterio de aceptacion de cada ronda: **codegen OK**, **el juego arranca
con los mismos pipelines**, **0 fatales**, y **el juego sigue llegando al
mismo sitio**. Un hueco declarado de mas no rompe el arranque: rompe el
avance, asi que "compila" no basta.

Como distinguir codigo de datos mirando los bytes, como volcar la imagen del
invitado, y el fallo del codegen que **no** es un hueco: `references/triage-de-huecos.md`.

### 4. Reparar saltos locales

```bash
python3 tools/fix_local_branches.py
```

Corrige los saltos locales cuyo destino ya tiene etiqueta en la misma función. Criterio:
exit 0 y el archivo generado sin cambios pendientes.

### 5. Recuperar entradas pequeñas (opcional pero recomendado)

Requiere un volcado de memoria del juego corriendo en PC. Lanza el ejecutable de PC, ciérralo
al ver los logos, y el volcado queda en `out/runtime/cache/carbon-82000000.bin`:

```bash
cmake --build out/pc --target nfscarbon --parallel 4
./out/pc/nfscarbon            # cierra la ventana al ver los logos
python3 tools/recover_small_entries.py
python3 tools/verify_small_entries.py
```

Criterio: `verify_small_entries.py` valida las entradas contra los bytes originales con
Capstone y sale 0. Si el volcado no existe, sáltate este paso — el pipeline sigue.

### 6. Reconfigurar tras el codegen

```bash
cmake -S . -B out/pc -G Ninja -DCMAKE_C_COMPILER=clang-20 -DCMAKE_CXX_COMPILER=clang++-20 \
  -DREXSDK_DIR="$HOME/nfsmw-android/sdk" -DCMAKE_BUILD_TYPE=Release
```

Reconfigurar es necesario para que CMake descubra las fuentes generadas y, si existe,
`generated/carbon_recovered_thunks.cpp`. Omitirlo produce un binario sin las entradas recuperadas.

### 7. Construir el APK

Antes de compilar, valida los mapas de registro (el script de Android lo hace y aborta si falla):

```bash
python3 tools/verify_registration_maps.py
ls generated/default/nfscarbon_pch.h generated/carbon_recovered_thunks.cpp   # criterio: ambos existen
cd android
ANDROID_HOME="$HOME/Android/sdk" ANDROID_SDK_ROOT="$HOME/Android/sdk" \
  ./gradlew assembleRelease -PrexSdkDir="$HOME/nfsmw-android/sdk"
```

Criterio: `android/app/build/outputs/apk/release/app-release.apk`.

### 8. Verificar el artefacto (no el log)

`BUILD SUCCESSFUL` no prueba que el APK sirva:

```bash
APK=android/app/build/outputs/apk/release/app-release.apk
apksigner verify --print-certs "$APK"
zipalign -c -v 4 "$APK" | tail -3
"$ANDROID_HOME/build-tools/37.0.0/aapt2" dump badging "$APK" | grep -E "package|native-code|sdkVersion"
```

Criterio: `native-code: 'arm64-v8a'`, firma válida, y el `versionName` esperado.

### 9. Instalar y probar

```bash
adb install -r "$APK"
```

En el teléfono: copia la carpeta del juego a **Memoria interna/NFSCARBON**, concede acceso a
archivos en el launcher, y pulsa **Jugar**. La primera vez genera los shaders (unos segundos).
Log de sesión: `Android/data/<paquete>/files/logs`. Argumentos extra para pruebas: cada línea
que empiece por `--` en `Android/data/<paquete>/files/args.txt`.

## Quick Reference

```bash
# toolchain
cmake --preset linux-amd64-release          # preset nativo del repo (usa clang-20)
python3 scripts/fix_orphan_branches.py ~/<proyecto>   # codegen iterativo hasta validar
cmake --build out/pc --target nfscarbon_codegen --parallel 4
# Si el codegen no se regenera al modificar el analysis, borra el stamp:
rm -f generated/default/codegen.build.stamp
# O invoca el binario directo con --ignore-stamp:
out/pc/rexglue codegen --ignore-stamp <juego>_manifest.toml
python3 tools/fix_local_branches.py
python3 tools/recover_small_entries.py && python3 tools/verify_small_entries.py
python3 tools/verify_registration_maps.py
cd android && ./gradlew assembleRelease -PrexSdkDir="$HOME/nfsmw-android/sdk"
apksigner verify --print-certs app/build/outputs/apk/release/app-release.apk
adb install -r app/build/outputs/apk/release/app-release.apk

# inspección
python3 tools/inspect_image.py 0x824DAAA0    # una dirección con el volcado local
adb logcat | grep -i <paquete>               # nfsmw-android/tools/android_logcat.sh

# validación (el juego necesita --video_driver=offscreen si no hay X server)
python3 <skill>/scripts/ab_test.py --binario out/pc/<juego> --juego-root ~/mi-juego \
    --guion "3:0x1000,6:0x1000,9:0x0010" --repeticiones 3
python3 <skill>/scripts/leer_log_corrida.py out/pc/logs --resumen
```

## Pitfalls

- **`fatal error: 'imgui.h' file not found` al compilar el ejecutable del juego.** No es que falte la
  librería: `rexruntime` linkea `imgui` como **PRIVATE** (`src/kernel/CMakeLists.txt`), así que su ruta
  de include no llega nunca al título — pero `rex_app.h` -> `rex/ui/imgui_dialog.h` -> `imgui.h` la
  necesita. El `CMakeLists.txt` que genera `rexglue init` no lo cubre. El propio SDK lo resuelve así
  para Switch en `cmake/rexglue_switch.cmake`; para Linux, linkea las dependencias de UI directo en el
  target del juego:

  ```cmake
  foreach(ui_dependency imgui renderdoc)
      if(TARGET ${ui_dependency})
          target_link_libraries(<juego> PRIVATE ${ui_dependency})
      endif()
  endforeach()
  ```

  Criterio de que hizo falta: la línea de compilación del error lista `simde`, `fmt`, `spdlog`, `sdl3`,
  `vulkan-headers`, `tomlplusplus`, `spirv-tools`… y **ninguna** ruta de `imgui`.
- **El build de PC muere en `sdk/src/core/memory.cpp` con errores SSSE3.** Síntoma: `always_inline
  function '_mm_shuffle_epi8' requires target feature 'ssse3', but would be inlined into function
  'copy_and_swap_32_aligned' that is compiled without support for 'ssse3'` (6 errores, todos en ese
  archivo). No es un problema del código generado: al configurar el proyecto del juego a mano te falta
  el `-march` que sí trae el preset del SDK. Pásalo explícito en el configure:

  ```bash
  cmake -S . -B out/pc -G Ninja -DCMAKE_C_COMPILER=clang-20 -DCMAKE_CXX_COMPILER=clang++-20 \
    -DREXSDK_DIR="$HOME/nfsmw-android/sdk" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_FLAGS=-march=x86-64-v2 -DCMAKE_CXX_FLAGS=-march=x86-64-v2
  ```

  Cambiar flags de compilación exige **reconfigurar**, no solo relanzar el build: Ninja no las
  reaplica desde la caché anterior.
- **`rexglue codegen` falla la validación con `UnresolvedCall`.** Reporta ramas cuyo destino no está en
  ninguna función («target not in any function»). La solución no es adivinar ni parchear el generador:
  declara las direcciones en un TOML de análisis y añádelo al manifest.

  ```toml
  # <juego>_analysis.toml
  cr_as_local = false
  xer_as_local = false
  ctr_as_local = false
  non_volatile_as_local = false

  [functions]
  "0x822C98B8" = { }
  ```

  ```toml
  # <juego>_manifest.toml -> [entrypoint]
  includes = ["<juego>_analysis.toml"]
  ```

  **Es iterativo**: declarar una dirección cambia el descubrimiento de límites de las funciones
  vecinas y aparece un destino nuevo. Cada ronda son ~62 s, así que automatiza el bucle:
  `python3 scripts/fix_orphan_branches.py ~/<proyecto>` (corre codegen, parsea los
  `0xADDR from 0xSRC`, añade los que falten a `[functions]`, repite). Ir de uno en uno a mano
  cuesta media hora.

  Sin la entrada en `includes` el TOML se **ignora en silencio** y el error se repite idéntico.
  No hay opción para saltarse la validación (`codegen` solo acepta `--target` e
  `--ignore-stamp`): hay que resolverla.
- **Warnings `Unexpected float16_4 pack instruction at 0x…` durante el codegen.** El generador no
  soporta el empaquetado `float16_4` de PPC. Son warnings, el codegen continúa y termina bien, pero
  esas rutas quedan sin traducir — anótalas para cuando el juego corra, porque el síntoma será
  comportamiento raro o artefactos visuales en esa zona, no un fallo de compilación. `cmake --preset …` aborta con «Git
  submodule '<lib>' is not initialized. Please run: git submodule update --init --recursive», pero
  en este port esos directorios son **snapshots vendorizados**, no submódulos reales:
  `sdk/thirdparty` solo versiona los archivos que el port modificó. `python3
  tools/fetch_thirdparty.py` los rellena, y de paso restaura los archivos que `git status` reporta
  como borrados dentro de `thirdparty/` (FFmpeg, libadrenotools).

  El script puede **abortar a mitad** con `FileNotFoundError` sobre un symlink roto del upstream
  (`thirdparty/moltenvk/Demos/Cube/include/cube`). `os.walk` recorre en orden del sistema de archivos,
  así que las librerías que quedan tras `moltenvk` (sdl3, tracy, tomlplusplus, utfcpp…) se quedan
  **vacías** y el configure vuelve a fallar igual. Síntoma exacto: traceback al final del script, unos
  directorios con contenido y otros con `0 entradas`, y exit distinto de 0. Guard antes del
  `shutil.copy2` (inicializa `skipped = 0` junto a `copied = kept = 0`):

  ```python
  if resolved_target is None and not os.path.exists(src):
      skipped += 1
      continue
  ```

  Cadena que lo rompe en silencio: `fetch_thirdparty.py` copia los archivos **excluyendo `.git`**,
  así que si el check de `sdk/thirdparty/CMakeLists.txt` es el variante estricto
  (`if(NOT EXISTS ".../${submodule}/.git")`) seguirá fallando con los directorios ya llenos. El
  upstream usa el permisivo, que además acepta snapshots:

  ```cmake
  file(GLOB submodule_contents LIST_DIRECTORIES true "${CMAKE_CURRENT_SOURCE_DIR}/${submodule}/*")
  if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/${submodule}/.git" AND NOT submodule_contents)
  ```

  Si tu copia tiene el estricto, aplica **solo ese cambio** con `patch` en vez de revertir el
  archivo entero — el resto puede llevar ajustes del port que no quieres perder.
- **`clang-20` no instalado, o instalado pero invisible.** El preset `linux-base` del repo fija
  `CMAKE_C_COMPILER=clang-20`. Dos trampas encadenadas en Arch/Manjaro: (1) el paquete se llama
  `clang20` (no `clang`), y (2) **no expone nada en `/usr/bin`** — deja los binarios en
  `/usr/lib/llvm20/bin/`, así que `command -v clang-20` falla con el paquete ya instalado y
  `pacman -Q clang20` reportando la versión. Comprueba con `pacman -Ql clang20 | grep bin` antes
  de reinstalar nada. Además el paquete trae `clang`, `clang++` y `clang-20` pero **no existe
  `clang++-20`**: enlázalo a `clang++`, no a un archivo inexistente (un symlink roto también da
  «command not found»).

  ```bash
  for b in clang-20 clang clang-cpp; do ln -sf "/usr/lib/llvm20/bin/$b" ~/.local/bin/$b; done
  ln -sf /usr/lib/llvm20/bin/clang++ ~/.local/bin/clang++-20
  clang-20 --version && clang++-20 -print-resource-dir   # criterio: 20.1.8 y la ruta del resource dir
  ```

  Al enlazar, clang resuelve su `resource dir` por el binario real, así que funciona desde
  `~/.local/bin` sin más ajustes. Verifica con un `-std=c++23` real, no solo con `--version`.
- **`capstone` ausente.** `ModuleNotFoundError: No module named 'capstone'` rompe la recuperación
  y verificación de entradas. Dos trampas al instalarlo: (1) el `python3` de un Manjaro/Arch reciente
  suele venir **sin `pip`** (`No module named pip`) y con `EXTERNALLY-MANAGED`, así que `pip install`
  falla en los dos sentidos — usa `uv pip install --target "$(python3 -m site --user-site)"`, que deja
  el paquete importable por el `python3` del shell sin activar nada; (2) no lo instales en el venv de
  Hermes ni en el Python del toolchain del agente. Los wheels de capstone son `py3-none-manylinux`
  (independientes de la versión de Python), así que funcionan en 3.14 sin compilar.
- **`Validation failed: N unresolved calls` detiene el codegen antes de generar nada.** Las
  direcciones que lista van al `<juego>_analysis.toml` bajo `[functions]`, y ese archivo **debe**
  estar en `includes` del manifest. El conteo no baja de uno en uno: declarar una función cambia
  los límites de sus vecinas y descubre otra rama huérfana.
- **Los scripts del repo son PowerShell (`build_pc.ps1`, `build_android.ps1`, `run_pc.ps1`).**
  En Linux no hay `pwsh` por defecto. Ejecuta los pasos equivalentes con `cmake`/`gradlew`
  directamente, como en el Procedure. `nfsmw-android` sí trae `build_android.sh` y `tools/codegen.sh`.
- **El nombre de la carpeta del juego es sensible a mayúsculas.** El manifest apunta a
  `../need_for_speed_carbon` (minúsculas) mientras el README escribe `Need_for_Speed_Carbon`.
  En Linux el árbol equivocado deja `default.xex` «no encontrado» sin más pista.
- **El NDK lo fija el pin del proyecto, nunca "la última instalada".** La versión la declara
  `ndkVersion` en `android/app/build.gradle` (o en `gradle.properties`): úsala **exacta**. Un
  script auxiliar que la elija con `ls -d "$SDK"/ndk/*/ | sort -V | tail -1` se salta el pin
  y compila contra otro toolchain: el resultado no es el build que Gradle haría, y el error
  de CMake no menciona el NDK. El script debe **leer el pin**, y si el paquete falta decirlo
  con el comando de `sdkmanager` en vez de caer a otra versión.

  Antes de tocar nada, averigua qué NDK usó el build **real** — está en la caché de CMake:

  ```bash
  grep -E "ANDROID_NDK|CMAKE_ANDROID_NDK" android/app/.cxx/Release/*/arm64-v8a/CMakeCache.txt
  ```

  Si ese NDK no coincide con el pin, el problema es el pin, no el APK ya construido. Y
  valida que el NDK esté completo (`source.properties` presente): uno a medias rompe el
  toolchain con un error que no lo nombra.
- **Un script de port es un camino PARALELO al build real: averigua cuál produjo el
  artefacto antes de "arreglarlo".** `scripts/port_android.sh` compila con el NDK, stagea en
  `jniLibs/` y llama a Gradle; el build que produjo el APK es `externalNativeBuild`, que
  compila el SDK como parte del proyecto y saca las `.so` de
  `app/build/intermediates/cxx/Release/<hash>/obj/arm64-v8a/`. Son dos caminos distintos:
  stagear en `jniLibs/` no es lo que hace el build real, y una discrepancia entre ellos no
  invalida el APK ya construido. Audita el script, pero reporta el desacuerdo como
  *desajuste*, no como build roto — y comprueba con `unzip -l <apk>` qué `.so` viajan.

  Un script cuyo único test es un build de 20 minutos no se puede arreglar con seguridad:
  dale un `--dry-run` que valide el toolchain (SDK, NDK, CMake, Ninja, `source.properties`)
  y salga sin compilar, y ejercítalo con SDK/NDK de mentira antes de tocar el build real.
- **Versión de CMake de Gradle.** `externalNativeBuild { cmake { version '…' } }` pide una
  versión **exacta**; si el SDK no la tiene instalada (por ejemplo solo 4.1.2 en
  `~/Android/sdk/cmake/`), Gradle aborta con un mensaje que no nombra el proyecto. Lee el pin
  del `build.gradle`, instálala con `sdkmanager "cmake;<versión>"` o cambia el pin.
- **Codegen antes de Android, siempre.** `build_android.ps1` aborta si faltan
  `generated/default/nfscarbon_pch.h` o `generated/carbon_recovered_thunks.cpp`. Compilar el APK
  primero da un error de fuentes faltantes, no un mensaje claro.
- **Nunca dos builds sobre el mismo árbol.** Gradle y el daemon de Kotlin escriben en `build/`
  y CMake en `out/`; builds solapados producen cientos de errores en archivos que nadie tocó.
  Detén el otro build (`./gradlew --stop`) antes de diagnosticar.
- **Incremental oculta cambios.** Un build lanzado antes de reescribir recursos reporta éxito sin
  verlos. Re-lanza el build después de cada edición.
- **El APK de release va firmado con la clave de depuración local.** No es una firma estable para
  publicar; genera un keystore propio antes de distribuir.
- **`assembleRelease` no sabe lo que le falta al juego.** Gradle solo compila lo que hay: si la
  vista Java del pad o su puente JNI no entraron, el APK sale igual — firmado, `arm64-v8a`,
  `BUILD SUCCESSFUL` — y el juego se queda quieto en el título. Verifica el **contenido** del
  artefacto, no el log del build: la clase dentro de `classes.dex` y los símbolos JNI dentro
  de la `.so` del juego.

  ```bash
  unzip -q -o <apk> "classes*.dex" "lib/arm64-v8a/*" -d /tmp/apkchk
  strings -a /tmp/apkchk/classes.dex | grep -i <TuClasePad>
  nm -D --defined-only /tmp/apkchk/lib/arm64-v8a/libmain.so | grep -i nativeSetState
  ```

  Regla: JNI solo se busca en las bibliotecas que la app cargó ella misma, así que el puente
  tiene que estar **dentro** de `libmain.so`, no en una `.so` aparte.
- **Las claves del analysis TOML se comparan sin distinguir mayúsculas, y el helper también.**
  El parser del SDK acepta `"0X822C9948"` igual que `"0x822C9948"`, pero un script que detecte
  lo ya declarado con una regex de `0x` en minúscula **no lo reconoce** y vuelve a declararlo
  en cada ronda: el archivo se llena de duplicados y cada ronda gasta un ciclo de codegen de
  ~60 s. Normaliza a `0x` minúscula y compara sin distinguir mayúsculas.
- **Requisitos de GPU del renderizador nativo.** Vulkan 1.1 **con descriptor indexing**; la versión
  de Vulkan sola no garantiza esas funciones. Turnip es para Adreno, PanVK para Mali. Por encima de
  720p solo con renderizador nativo (Xenos se queda en 1280×720 por la EDRAM emulada).
- **El launcher rechaza otro `default.xex`.** El código recompilado y los ganchos dependen de las
  direcciones de la copia verificada. Otra edición o región no funciona sin rehacer el análisis.
- **El juego de PC necesita un X server, y sin él falla EN SILENCIO.** Abre una ventana de
  SDL: sin `DISPLAY` muere en 0.03 s con `No available video device`, **sin log y sin crash**.
  El fallo silencioso es peligroso porque un A/B con él da números **idénticos** siempre, que
  parece un resultado. Pasa `--video_driver=offscreen` (el driver de SDL que no necesita X) y
  el juego corre sin display en cualquier terminal y en cualquier herramienta.
- **`SIGBUS` en `Memory::InitializeFunctionTable` no es un bug del juego: es `/dev/shm` agotado.**
  La arena del invitado se respalda en tmpfs (`/dev/shm/xenia_memory_*`), 4.8 GB **por ejecución**.
  Varias ejecuciones seguidas dejan archivos huérfanos y agotan los 5.8 GB de tmpfs; entonces el
  `mmap` devuelve `SIGBUS` en vez de `ENOMEM` y el crash aparece como *Bus error* dentro de libc,
  sin relación con el código. Síntoma: backtrace con `Memory::InitializeFunctionTable` →
  `FunctionDispatcher::InitializeFunctionTable` → `Runtime::Setup` y nada de ReXGlue. Cura:
  `rm -f /dev/shm/xenia_memory_*` entre ejecuciones. Automatizable en el script del ciclo.
- **El plugin de GPU no se carga solo.** Sin `config.gpu_plugin = "xenos"` en `OnPreSetup`, el
  kernel registra `no GPU emulation loaded (gpu_plugin not set); call ignored` y el juego nunca
  llega al menú. No es fatal, así que se pierde en el ruido del log. Carbon lo hace en
  `src/nfscarbon_app.h`; copiar ese hook al proyecto nuevo.
- **El codegen se ejecuta DENTRO del build.** El target del juego depende del codegen, así que
  `cmake --build` lo dispara. Si la validación falla con `UnresolvedCall`, el build falla también
  y el script nunca llega a declarar el destino huérfano. Orden correcto: codegen (con su propio
  bucle de resolución) → build → ejecución.
- **El informe de huecos caduca en cada regeneración.** `tools/huecos.py` mide el C++ **generado**;
  en cuanto el codegen reescribe las funciones, los límites cambian y el informe queda obsoleto.
  Reléelo antes de buscar el hueco de la dirección que reventó.
- **Un hueco puede contener varias funciones.** Declarar solo el inicio hace que el Discover se
  lo trague entero y el crash se *mueve* a +8, +24, +64… bytes. Declarar una entrada cada 8 bytes
  dentro del hueco que ya ha reventado.
- **Un hueco puede ser la TABLA DE IMPORTS del kernel, y declararla rompe el enlazado.** Un hueco
  grande con muchas entradas espaciadas 16 bytes no es codigo: son punteros a funciones del
  kernel (`__imp__XGetVideoMode`, `__imp__XamShowSigninUI`…). Declararlo cada 8 bytes hace que
  el codegen deje de registrarlos como imports y los registre como funciones del juego que no
  emite, y el enlace falla con N `undefined reference to sub_XXXXXXXX`. Los imports no son codigo:
  el guest llama a traves de ellos. Excluye del lote cualquier hueco que contenga una direccion
  de la tabla de imports (`{ 0xADDR, __imp__… }` en `<proyecto>_init.cpp`). La pista estatica:
  muchos huecos del **mismo tamano** separados por el **mismo intervalo** son una tabla.
  Y el gap mas caro: un hueco de 4 KB con 246 imports.
- **El informe de huecos no es el juez: lo es la tabla de funciones registradas.** El informe
  (`scripts/huecos.py`) mide el C++ generado y lista como hueco todo lo que queda entre dos
  funciones, asi que un hueco puede **tener ya su funcion**: el Discover la reclamo con un
  tamano menor que el hueco, y sigue apareciendo en la lista. Antes de declarar nada, comprueba
  si el inicio del hueco aparece ya como `sub_` en `<proyecto>_init.cpp`; si aparece, no hay nada
  que declarar. Y recuerda que el informe **caduca con cada codegen**: reléelo antes de cada
  ronda, o medirás huecos que ya no existen.
- **Un branch a una etiqueta que el propio codegen emitio NO es un hueco: es un fallo del
  clasificador del SDK.** Sintoma: `[FATAL] Unresolved branch from 0x8260C400 to 0x8260BACC`, y
  en el **mismo** fichero generado esta `loc_8260BACC:`. El codigo existe y esta traducido;
  lo que fallo es que el branch no se resolvio. Causa: el Discover parte una funcion grande en
  dos, y la segunda mitad hace branch a una etiqueta **dentro de la primera mitad**; el destino
  no es entry point ni esta en el rango de quien llama, asi que el clasificador
  (`FunctionGraph::classifyTarget` en `src/codegen/function_graph.cpp`) lo deja como `Unknown`.
  El hunting no lo encuentra porque no es un crash de "invalid or unregistered function".
  Diagnostico y sitio del arreglo: `references/triage-de-huecos.md`.
- **No todos los huecos son un problema.** El informe de `huecos.py` lista huecos de 4 bytes
  (el hueco mínimo entre dos funciones consecutivas: padding o thunk) y huecos de 8 o más
  (bloque real de código sin dueño, que es lo que dispara el crash). Prioriza los de ≥8 y deja
  los de 4 para el final: hay miles y no bloquean.
- **En Android, el runtime tiene que cargarse con `System.loadLibrary`.** El SDK busca el plugin
  de la GPU por soname (`dlopen("librexgpu-xenos.so")`), y en Android eso solo encuentra una
  biblioteca que la app ya cargo con `System.loadLibrary`: el `SDLActivity` de SDL carga por
  RUTA el `libmain.so` del juego (`nativeLibraryDir + "/libmain.so"`), en su propio namespace,
  asi que el plugin no es visible y el juego se queda esperando sin dibujar (0 pipelines, log
  corto). Arreglo: overridear `getLibraries()` para incluir el runtime —
  `return new String[]{"SDL3", "rexruntime", "main"};`. Lo mismo hace que funcionen los hooks
  `weak` entre `.so`: un simbolo `weak` definido en el juego no resuelve si el que llama se
  cargo en otro namespace.
- **La entrada que llega al free roam son exactamente 16 gestos, y la mezcla importa mas
  que la cantidad.** Con A puro no llega nunca (0 de 6): es pasarse de opcion, el D-pad
  y el START son los que mueven los menus. Y anadir gestos despues tambien rompe: el
  guardado se escribe justo cuando el ultimo gesto hace efecto, y seguir pulsando deja
  al juego en un menu que ya no avanza.
- **El stick analogico es una posicion, no un flanco, y se sostiene por TIEMPO.** El
  juego consulta el pad unas cuatro veces por segundo, asi que un sosten medido en
  consultas es apenas un segundo: suficiente para mover un cursor, demasiado poco para
  girar una rueda. El sufijo `@<segundos>` lo sostiene el tiempo pedido.
- **El `<juego>.toml` (o el `.toml` del juego) debe copiarse al `REX_APP_FOLDER`.** El SDK busca
  la configuracion en `exe_dir / <nombre>.toml`, y en Android `exe_dir` es la variable de
  entorno `REX_APP_FOLDER` (la pone la actividad). El fichero va en los assets del APK y la app
  lo copia a esa carpeta al arrancar. Sin el, los cvars (gpu_plugin, etc.) no se aplican — y la
  falta de `gpu_plugin = "xenos"` solo registra `no GPU emulation loaded (gpu plugin not set)`,
  que no es fatal y se pierde en el ruido del log.
- **En Android el SDL3 tiene que ser una libreria compartida.** El SDK lo compila estatico
  (`thirdparty/CMakeLists.txt: set(SDL_SHARED OFF ...)`), pero el `SDLActivity` carga
  `libSDL3.so` con `System.loadLibrary`: sin la compartida, "dlopen failed: library
  libSDL3.so not found".
- **Los contadores de FPS no existen en Release.** El SDK solo los compila fuera de Release
  (`add_compile_definitions($<$<NOT:$<CONFIG:Release>>:REXGLUE_ENABLE_PERF_COUNTERS>)`), asi
  que en un APK de Release el registro de fotogramas no existe; hay que habilitarlo tambien
  **en el objetivo del juego** (el SDK solo aplica el define a sus propios objetivos): son unos
  atomicos, no un perfilador. Y no escribas tu propio cronometro: el hook de swap del SDK
  (`CommandProcessor::ExecutePacketType3_XE_SWAP`) ya mide el tiempo entre swaps y lo publica
  con `PROFILE_FRAME_TIME_US()` / `PROFILE_FPS()`; el launcher lee
  `rex::perf::GetSnapshotCounter(CounterId::kFrameTimeUs)`.
- **El gamepad tactil: el SDK ya tiene la parte dificil.** `src/input/sdl/sdl_input_driver.cpp`
  crea un mando sintetico en Android (`is_touch = true`, `synthetic = true` -> usuario 0) y lo
  publica con `rex_sdl_set_touch_gamepad_state(botones, lx, ly, rx, ry, lt, rt)`. Los bits son
  los de XInput (`A = 0x1000`, `B = 0x2000`, `X = 0x4000`, `Y = 0x8000`). Lo que falta es la
  vista Java que dibuja el pad y llama a esa funcion, y necesita `setClickable(true)`: Android
  solo entrega los toques a una vista que dice que los maneja. El puente JNI va **dentro** de
  `libmain.so`: Java busca funciones JNI solo en las bibliotecas que cargo el mismo.
- **Los huecos que solo se alcanzan al pulsar los ve el input inyectado, no el ciclo automatico.**
  El ciclo de `fix_gap_crashes.py` corre el juego sin tocar nada, asi que un hueco del codigo de
  input (al pulsar A) se escapa. Inyecta el mando de prueba (ver la entrada siguiente) para que
  la corrida pulse: entonces el crash sale solo
  (`Abort message: '[FATAL] Call to invalid or unregistered function at guest address 0xADDR'`),
  se busca el hueco con `tools/huecos.py --comprobar ADDR` y se declara una entrada cada 8 bytes.

  El hunting se integra en el ciclo con un flag, para que la corrida pulse sola:
  `python3 scripts/fix_gap_crashes.py --pulsar "3:0x1000,7:0x1000,11:0x0010" --timeout 120`.
  El script de pulsaciones son pares `<segundos>:<mascara XInput>`, y los segundos se cuentan
  desde que el guest empieza a mirar el pad.

  **El ciclo tiene que leer todas las partes del log, no una.** El sink rotatorio del SDK
  escribe en `mcla_NNN.log` y al llegar a 5 MB renombra el actual a `mcla_NNN.1.log`, cuyo
  contenido es ANTERIOR: un crash temprano cae en la parte rotada y el ciclo no lo ve. Y la
  pulsacion se entrega por consulta (ver la entrada siguiente), o se pierde la mitad.

  **La rotacion tiene una segunda consecuencia: al rotar, el sink abre un log **nuevo con
  otro número**, así que el "stem" **cambia a mitad de corrida**. Por eso **contar ficheros
  no detecta una corrida nueva** (el total no crece) y **leer solo el último stem pierde lo
  anterior**. Filtra los logs por **marca de tiempo** y lee **todos** los stems de la corrida,
  en orden cronológico.
  Receta y forma de medir si el juego avanzo: `references/pulsacion-inyectada.md`.
- **El input se puede inyectar desde el proyecto, sin tocar el SDK.** `InputSystem::AddDriver`
  es publica y el `InputDriver` del SDK se puede derivar: un driver propio que publique un
  boton XInput en un temporizador entra por el camino normal del SDK, y como su dispositivo
  es `synthetic = true` el `SlotAssignment` lo manda al usuario 0 del guest — el mismo slot
  que el pad tactil en Android. Asi el PC puede pulsar, que si no no puede: el servidor X
  rechaza el teclado sintetico (`XQueryKeymap` no mueve ningun keymap) y el SDL estatico no
  deja empujar eventos desde otro proceso. Antes de escribirlo, comprueba que el runtime
  exporta lo que necesitas:

  ```bash
  nm -D --defined-only out/pc/librexruntime.so | grep -E "InputSystem::AddDriver|InputDriver::~"
  ```

  El gancho es `OnPostSetup()`: el runtime ya existe y el guest aun no consulta. La receta
  completa esta en `references/pulsacion-inyectada.md`.
- **Un guion de tiempo no puede apuntar a un estado que el juego alcanza a un momento
  variable: usa un disparador por evento.** Cuando el objetivo depende de un estado (una
  cinemática, un menú, la ciudad), el tiempo que tarda el juego en llegar ahí varía entre
  corridas, y el input que cae dentro de ese estado se pierde: una cinemática no mira
  el pad. La solución es un disparador que espere a un **fichero-señal** en vez de al reloj
  (`w:<ruta>|<timeout>|<accion>`), que un harness toca cuando ve en el log que el juego ha
  llegado. Los separadores son `|` porque tanto la ruta como la acción llevan dos puntos,
  y el `w:` va al principio de la entrada: el parser tiene que comprobarlo **antes** de
  partir por el primer `:`, porque ese colon es el propio `w:`. Receta y harness:
  `references/conduccion-y-trigger.md`.
- **El reloj de un driver inyectado arranca en la primera consulta, no al construirlo, Y la
  pulsacion se entrega por consulta, no por ventana de tiempo.** El guest no mira el pad
  hasta que llega a la pantalla de titulo, media hora larga despues de arrancar; un
  temporizador que empieza en el constructor dispara cada pulsacion antes de que nadie
  pregunte, y el script de pulsaciones parece no hacer nada. Arranca el reloj en la
  primera llamada a `GetDeviceState` y programa los tiempos relativos a ahi.

  Y una pulsacion no es una ventana de 200 ms: es una **secuencia de consultas** (el
  boton baja, el guest lo ve, el boton sube). El polling del guest no es regular —
  cuando esta ocupado (compilando shaders) se arrastra, y una ventana fija puede caer
  entera entre dos consultas, con lo que la pulsacion se pierde. Medido: 8 pulsaciones
  programadas entregaban 4. Con el modelo por consulta se entregando las 8.
- **Comparar dos corridas exige el log concatenado y el conjunto de shaders, no el
  framebuffer.** El log rota: `<nombre>.log` es la parte NUEVA y `<nombre>.1.log` la ANTIGUA,
  asi que leer solo el primero pierde el principio de la corrida y da conclusiones falsas. Y
  la textura de swap alterna entre dos (doble buffer), con lo que no dice que pantalla se
  muestra: lo que distingue una pantalla de otra es el conjunto de hashes de shader que se
  crean. Compara contra un control de la MISMA duracion y cuenta los `Creating graphics
  pipeline` que aparecen tras la pulsacion. `scripts/comparar_corridas.py` hace la
  concatenacion, la cuenta y la diferencia de conjuntos.

  La senal mas inequivoca de que el juego avanzo es **que ficheros de datos lee** (el
  kernel registra cada lectura: `leer N bytes de 'xarchive_cache.rpf'`). Un fichero que el
  control nunca lee y la corrida con pulsaciones si, es contenido nuevo, y el contenido
  nuevo es codigo nuevo. Un guion largo y variado (A, START y las cuatro flechas) es lo que
  llega a esas pantallas; uno corto se queda en el menu.
- **Un control que no controla no mide nada: el A/B tiene que cambiar UNA variable.** Si el
  driver se instala solo cuando hay guion (`if (presses.empty()) return;`), el "control sin
  pulsaciones" **no tiene pad**: el guest ve un dispositivo de juego menos. Ese A/B mide dos
  cosas a la vez. El control honesto es un guion que **instala el pad pero nunca pulsa** (un
  gesto programado más allá del final de la corrida). Mismo principio para todo lo demás:
  cambia una variable, o no puedes atribuir el efecto.
- **Compara corridas que duraron lo mismo, y mira el código de salida.** El OOM killer mata
  el juego cuando carga `.rpf` de más de un gigabyte: una corrida muerta a los 84 s
  comparada con una completa de 300 s da un "resultado" que es un artefacto (medido: "922
  contra 650" donde el 650 era una corrida truncada). `exit 124` = llegó al final, `exit 137`
  = OOM. Nunca compares contra un número guardado de otra sesión: el conteo absoluto es
  ruidoso (el mismo control dio 299, 265 y 556 en tres corridas); la **diferencia entre
  condiciones** es lo sólido.
- **El juego no es determinista: una medición no es un resultado.** La misma entrada, en los
  mismos segundos, llegó a la partida en unas corridas y en otras no, con logs idénticos.
  Repite cada condición varias veces y reporta la **distribución**, no un punto. Y para
  cazar código que solo se alcanza a veces, el hunting necesita varias rondas.
- **Un hunting que no encuentra huecos puede estar llegando a donde no debe.** Antes de
  concluir que el codigo esta limpio, comprueba que el guion de pulsaciones **llego** a
  contenido nuevo (el fichero de datos leido que el control no lee). Si no llego, no
  encontraria huecos aunque los haya: los de las pantallas profundas solo se alcanzan
  con los axes analogicos (el stick), que un guion de botones no mueve.
- **El `CMakeLists.txt` raiz lo usan las dos plataformas.** El port Android hace
  `add_subdirectory(<proyecto>)` y entra en la rama `if(ANDROID)`, con lo que una fuente que
  anades a `MCLA_SOURCES` va tambien al APK: no es un fichero "solo PC". Si el fichero es
  solo de PC, excluyelo explicitamente en la rama Android; si es portable, comprueba que
  compila para aarch64 antes de darlo por bueno:

  ```bash
  $NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/clang++ --target=aarch64-linux-android26 \
    -std=c++23 -fsyntax-only -I$SDK/include -I$SDK/thirdparty/fmt/include ... <fichero>.cpp
  ```
- **En Android el juego puede morir por el low memory killer, no por un crash del port.** Si
  aparece `Process ... exited due to signal 9 (Killed)` sin `FATAL`, es Android matando la app
  por memoria: el port usa mas de 1 GB y en un telefono con otra persona usando el dispositivo
  no sobrevive. No es un bug del port.
- **Los cuatro fallos del port Android salen uno detrás de otro y todos se ven igual**
  ("el juego no arranca"): plugin de GPU invisible para `dlopen` (namespace), `.toml` sin
  leer, rotación a vertical, SDL3 estática. Los arreglos exactos, el checklist de archivos y la
  verificación del contenido del APK están en `references/android-port.md` — léelo antes de
  tocar el port.
- **Borrar los `.cpp` generados no fuerza el codegen.** El stamp (`generated/default/codegen.build.stamp`)
  registra un fingerprint de los inputs (manifest, analysis TOML, plantillas). Si el fingerprint
  coincide, el codegen sale en 0.1 s con `0 written, N unchanged` aunque no exista ningún `.cpp`.
  Para forzar la regeneración, borra el stamp o invoca el binario directo con `--ignore-stamp`:
  
  ```bash
  rm -f generated/default/codegen.build.stamp
  # o bien:
  out/pc/rexglue codegen --ignore-stamp <juego>_manifest.toml
  ```
  
  `cmake --build out/pc --target <juego>_codegen` respeta el stamp; el target es phony y
  delega en `out/pc/rexglue codegen`.
- **`out/pc/rexglue` es el binario que CMake invoca, no `~/.local/bin/rexglue`.** El target
  `mcla_codegen` ejecuta `out/pc/rexglue codegen` (no el binario del PATH). Si acabas de
  parchear el SDK, reconstruye `rexglue` con `cmake --build out/pc --target rexglue` y
  verifica que el binario de `out/pc/` tenga los cambios antes de regenerar el codegen.
  Borrar solo `out/pc/rexglue` no basta: Ninja puede cachear el `.o` de `librexcodegen.a`.
  Si el cambio no aparece en `strings out/pc/rexglue`, elimina el objeto específico:
  
  ```bash
  rm -f out/pc/rexglue-sdk/src/codegen/CMakeFiles/rexcodegen.dir/builders/context.cpp.o \
         out/pc/sdk-archives/librexcodegen.a out/pc/rexglue
  cmake --build out/pc --target rexglue --parallel 4
  ```
  Borrar solo `out/pc/rexglue` no basta: Ninja puede cachear el `.o` de `librexcodegen.a`.
  Si el cambio no aparece en `strings out/pc/rexglue`, elimina el objeto específico:
  
  ```bash
  rm -f out/pc/rexglue-sdk/src/codegen/CMakeFiles/rexcodegen.dir/builders/context.cpp.o \
         out/pc/sdk-archives/librexcodegen.a out/pc/rexglue
  cmake --build out/pc --target rexglue --parallel 4
  ```
- **`scripts/declarar_huecos.py` necesita `out/pc/<juego>` para probar.** Después de cada
  declaración masiva de huecos, el script regenera el codegen y lanza el juego para verificar
  pipelines y fatales. Si `out/pc/<juego>` no existe (por ejemplo, porque lo borraste al
  rebuild de `rexglue`), el script falla con `FileNotFoundError`. Build del juego primero.
- **Dependencia circular entre `function_node.h` y `config.h`.** `config.h` incluye
  `function_graph.h`, que incluye `function_node.h`. No puedes incluir `config.h` desde
  `function_node.h` sin un ciclo. Si un método de `FunctionNode` necesita tipos de `config.h`
  (p. ej. `MidAsmHook`, `JumpTable`), usa forward declarations en el header y pasa los datos
  como parámetros opacos o recógelos aparte en el writer.
- **`collectEmittedLabels()` tiene que ser `const` con `mutable`.** El writer recorre las
  funciones a través de `const FunctionNode*`, así que cualquier método que muta el estado
  durante la pre-colección de labels debe declararse `const` y el miembro que llena
  (`emittedLabels_`) tiene que ser `mutable`. Olvidar el `const` en la definición out-of-line
  da "does not match any declaration"; olvidar `mutable` da "assignment of member in read-only
  object".
- **`use of undeclared label` en el C++ generado tiene una causa raíz frecuente en `classifyTarget`.** Si `isModuleLabel()` devuelve `true` para una etiqueta de otra función del mismo módulo y `classifyTarget` la clasifica como `InternalLabel`, el branch se emite como `goto loc_XXXXXXXX;` dentro de la función que hace el branch. Esa etiqueta existe en el módulo, pero **no** en el ámbito de la función que la emite, así que el compilador de C++ la declara como undeclared. Arreglo: `isModuleLabel()` solo es `InternalLabel` si la etiqueta está dentro del rango de la función que llama; en caso contrario, clasifícala como `Function` o `Unknown` y deja que `build_b` emita `emit_function_call` + `return`.
- **`use of undeclared label` en el C++ generado (continuación).** Incluso con pre-registro completo, pueden quedar labels faltantes en funciones stub (sin bloques) o fragmentos muy pequeños: `build_b` para `TargetKind::Unknown` emite `emit_function_call` + `return` en vez de `goto`, y `emit_conditional_branch` para el caso sin `CallTarget` emite la llamada directa si `classifyTarget` ya la reconoció como entry point.
- **Dos archivos de stamp controlan el codegen.** `generated/default/codegen.build.stamp`
  es el que usa el target de CMake; `generated/default/codegen.stamp` es el que
  usa `rexglue codegen` directamente. Ambos pueden impedir la regeneración:
  borra ambos, o invoca con `--ignore-stamp`.
- **Al parchear `context.cpp`, respeta la estructura existente.** El archivo tiene helpers
  como `emit_function_call_by_name` y `emit_import_call` que otros builders llaman; un
  parche que reescribe un bloque y se los salta rompe la compilación del SDK. Lee el
  bloque original completo antes de reemplazarlo.
- **`emit_function_call` necesita un fallback por dirección.** Cuando no hay
  `CallTarget` pre-resuelto, el builder debe buscar la función directamente en el
  grafo (`graph().getFunction(target.address)`) antes de rendirse: un branch a una
  dirección desconocida puede ser una función que el Discover ya creó pero que el
  clasificador no reconoció como llamada.
- **CMake puede fallar al configurar glslang con el Python incorrecto.** Síntoma:
  `Could not find Python3` o `FileNotFoundError` durante `fetch_thirdparty.py` o
  `add_subdirectory(thirdparty/glslang)`. Pasa `-DPYTHON_EXECUTABLE=$(which python3)`
  en el configure para forzar el intérprete del shell.

## References

- `references/auditoria-estado.md` — cómo medir el estado real de un port ya existente
  (identidad del XEX, git, codegen, huecos, PC, APK por contenido, dispositivo) y cómo
  escribir el informe separando lo verificado de lo documentado.
- `references/android-port.md` — checklist y arreglos del port Android: namespace del
  `dlopen`, `.toml` de configuracion, landscape, SDL3 compartida, gamepad táctil, contadores
  de FPS, verificacion del APK por contenido, pruebas en el dispositivo.
- `references/ab-y-validacion.md` — cómo validar que un cambio hizo algo: qué es un control
  que controla, no determinismo, truncado por OOM, métricas ruidosas y qué señal es fuerte.
- `references/pulsacion-inyectada.md` — como inyectar botones al guest desde el proyecto
  (sin tocar el SDK) para probar el input y cazar los huecos que solo se alcanzan al pulsar:
  el driver, el reloj que arranca en la primera consulta, y como medir si el titulo avanzo.
- `references/conduccion-y-trigger.md` — como llegar mas lejos que el titulo: el stick
  analogico sostenido por tiempo, el disparador por evento (`w:`), la entrada de 16 gestos
  que llega al free roam, y por que el juego no es determinista.
- `references/triage-de-huecos.md` — como triagear y declarar los huecos de codigo: por que
  el informe no es el juez, como detectar la tabla de imports, como volcar la imagen del
  invitado para mirar los bytes (codigo o datos), el fallo del codegen que emite un branch a
  una etiqueta que el mismo emitio, y el arreglo validado (pre-registrar labels module-wide
  antes de emitir, mas fallbacks en `build_b` y `emit_conditional_branch`) que redujo
  737 branches sin resolver a 0.
- `scripts/xex_info.py` — identidad del XEX (Title ID, Media ID, versión, sha256).
- `scripts/fix_orphan_branches.py` — bucle que declara las ramas huérfanas y reintenta el
  codegen hasta que la validación pasa.
- `scripts/comparar_corridas.py` — compara dos logs de PC (control vs con pulsacion) con el
  log rotado concatenado y la diferencia de conjuntos de shaders.
- `scripts/ab_test.py` — A/B honesto: construye el control que **tiene el pad pero no
  pulsa**, limpia el estado entre corridas, comprueba el codigo de salida (137 = OOM = la
  medicion no vale) y lee el log completo de todos los stems. Repite y reporta el reparto.
- `scripts/leer_log_corrida.py` — lee el log COMPLETO de una corrida (todos los stems, todas
  las partes, por marca de tiempo) y dice si la corrida llego (escribio el guardado) o no.
  Resuelve las tres trampas del sink rotatorio: renombrado, numero de ficheros que no
  crece, y el cambio de stem a mitad de corrida.
- `scripts/triage_huecos.py` — triagea los huecos de un port: distingue los que ya tienen
  funcion de los reales, excluye la tabla de imports, desensambla una direccion del volcado
  de memoria, y declara por tramos de 8 bytes con piloto, backup y vuelta atras.

## Verification

- [ ] `sha256sum default.xex` coincide con la copia soportada y `scripts/xex_info.py` reporta `magic: XEX2`
- [ ] Ningún directorio requerido de `sdk/thirdparty/` está vacío
- [ ] `rexglue codegen` supera la validación (ningún `unresolved calls`) y `generated/default/` tiene los `.cpp`
- [ ] `generated/default/sources.cmake` existe tras el codegen
- [ ] `fix_local_branches.py` y `verify_small_entries.py` salen 0
- [ ] `verify_registration_maps.py` sale 0
- [ ] `apksigner verify` reporta firma válida y `aapt2 dump badging` reporta `arm64-v8a`
- [ ] El APK se instala con `adb install -r` y el juego llega al menú en el dispositivo
