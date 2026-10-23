# Auditar el estado real de un port ReXGlue

Procedimiento para medir el estado de un proyecto de recompilación **ya existente** (PC y/o
Android) y escribir un informe verificado. La regla de oro: **el árbol y los artefactos son la
verdad; el README y los commits cuentan una historia**. Separa siempre lo *verificado ahora*
de lo *documentado*, y nunca declares algo que no pudiste comprobar en esta sesión.

Orden: identidad → git → codegen/análisis → huecos → PC → APK → dispositivo → informe.

---

## 1. Identidad del juego

El launcher rechaza cualquier otro `default.xex`; las direcciones declaradas en el analysis
TOML son de **una** copia concreta.

```bash
sha256sum ~/midnight-club-la/default.xex
python3 <skill>/scripts/xex_info.py ~/midnight-club-la/default.xex
```

Criterio: el hash coincide con el documentado en el README del proyecto y `magic: XEX2`.
Un hash distinto = otro build = hay que rehacer el análisis, no "arreglar un hueco".

## 2. Git

```bash
git -C <proyecto> log --oneline -15
git -C <proyecto> log --format="%h %ad %s" --date=relative -3
git -C <proyecto> status --short --untracked-files=all
git -C <proyecto> log origin/master..HEAD --oneline    # commits sin pushear
git -C <proyecto> remote -v
```

Criterio: saber qué se hizo, qué está pusheado y qué quedó sin versionar (típico: un
`tools/*.toml` de referencia que el `.gitignore` no cubre).

## 3. Codegen y analysis TOML

```bash
ls <proyecto>/generated/default/*.cpp | wc -l        # ~121 .cpp para un juego de PC
ls <proyecto>/generated/default/sources.cmake
grep -c '= { }' <proyecto>/<juego>_analysis.toml    # entradas declaradas a mano
grep -n '"0X' <proyecto>/<juego>_analysis.toml       # claves con prefijo en mayúscula
grep -n 'includes' <proyecto>/<juego>_manifest.toml  # el TOML debe estar listado aquí
```

Criterio:
- el analysis TOML **tiene que estar** en `includes` del manifest; si no, el archivo se
  ignora en silencio y el error de validación se repite idéntico;
- sin claves `0X`/`0x` mezcladas (el parser las acepta, pero los helpers no).

## 4. Huecos

El informe mide el C++ **generado**: caduca en cuanto el codegen reescribe las funciones.
Reléelo antes de buscar el hueco de una dirección.

```bash
python3 <proyecto>/scripts/huecos.py --gen <proyecto>/generated/default --salida out/huecos_now.txt
grep -E "0x[0-9A-F]{8} +([89]|[0-9]{2,}) bytes" out/huecos_now.txt | wc -l   # ≥8 bytes
grep -E "0x[0-9A-F]{8} +4 bytes" out/huecos_now.txt | wc -l                   # padding
python3 <proyecto>/scripts/huecos.py --comprobar 0x82554080                    # una dirección
```

Criterio: **4 bytes = el hueco mínimo entre dos funciones** (padding/thunk), no bloquea.
**≥8 bytes = bloque de código sin dueño**, que es lo que revienta con «Call to invalid or
unregistered function». Prioriza los ≥8.

## 5. PC

```bash
ls -t <proyecto>/out/pc/logs/ | head -3                 # último log
grep -c FATAL <proyecto>/out/pc/logs/<ultimo>.log        # 0 = sin crash de función
grep -c "Creating graphics pipeline" <proyecto>/out/pc/logs/<ultimo>.log
grep -iE "menu|title|Initializing shader storage" <proyecto>/out/pc/logs/<ultimo>.log | head
tail -25 <proyecto>/out/pc/logs/<ultimo>.log
```

Criterio: **0 FATAL** y un contador de pipelines **creciendo** (o al menos alto). Un log con
muchos pipelines y 0 FATAL significa que el juego llegó a la pantalla de título y se mantiene
vivo. Las líneas periódicas de audio (`[apu] SDL en 10 s`) y de EDRAM prueban que el juego
sigue vivo y no congelado en un fotograma.

**Un contador alto NO prueba que el juego haya avanzado de pantalla.** Para eso hay que
inyectar una pulsación y comparar contra un control: ver `references/pulsacion-inyectada.md`.
El criterio de "avanzó" es que la corrida con pulsación cargue un **conjunto de shaders que
el control nunca carga**, no que tenga más pipelines (el título también los crea mientras
carga). Para comparar dos logs: `scripts/comparar_corridas.py`, que concatena el log rotado
(`.1.log` es la parte antigua) y devuelve la diferencia de conjuntos.

## 6. APK

```bash
APK=<proyecto>/android/app/build/outputs/apk/release/app-release.apk
~/Android/sdk/build-tools/37.0.0/apksigner verify --print-certs "$APK"
~/Android/sdk/build-tools/37.0.0/aapt2 dump badging "$APK" | grep -E "^package|native-code|versionName"
unzip -l "$APK" | grep -E "\.so$|assets/"
```

Criterio: firma V2 válida, `native-code: 'arm64-v8a'`, y el paquete/librerías que esperabas.

**Y el contenido, no solo la firma.** `assembleRelease` no sabe lo que le falta al juego: una
vista Java o un puente JNI ausentes producen un APK perfecto y un juego quieto. Extrae y
comprueba:

```bash
cd /tmp && rm -rf apkchk && mkdir apkchk && cd apkchk
unzip -q -o "$APK" "classes*.dex" "lib/arm64-v8a/*"
strings -a classes*.dex | grep -i <TuClasePad>          # la vista Java está
nm -D --defined-only lib/arm64-v8a/libmain.so | grep -i nativeSetState   # el puente JNI está
```

El puente JNI tiene que estar **dentro de `libmain.so`**: Java solo busca símbolos JNI en las
bibliotecas que cargó ella misma.

## 7. Dispositivo

```bash
adb devices -l
```

Si la lista está vacía, el paso en dispositivo está **sin verificar**: dilo así. No lo des
por bueno porque el README lo afirme. Si el dispositivo está delante pero con otra app en
primer plano, Android mata el port por memoria (~1.3 GB) — el proceso muere con `signal 9
(Killed)` y **sin** `FATAL`, lo que no es un crash del port.

## 7b. Qué camino de build produjo el artefacto

Antes de juzgar un script de port, averigua **qué camino construye de verdad** el APK
que está en el árbol. Un proyecto Gradle con `externalNativeBuild` compila el SDK como parte
del proyecto; un script que stagea `.so` en `jniLibs/` es un camino **paralelo**, no el que
produjo el artefacto.

```bash
# el camino real: las .so salen del build nativo de Gradle
ls android/app/build/intermediates/cxx/Release/*/obj/arm64-v8a/*.so
# el NDK que usó de verdad, leído de la caché de CMake del propio build
grep -E "ANDROID_NDK|CMAKE_ANDROID_NDK" android/app/.cxx/Release/*/arm64-v8a/CMakeCache.txt
# qué .so viajan en el APK
unzip -l <apk> | grep -E "\.so$"
```

Criterio: si el NDK de la caché no coincide con el pin de `ndkVersion`, el **pin** es lo que
hay que arreglar, y el APK existente sigue siendo válido. Reporta la discrepancia entre el
script y el build real como *desajuste*, no como build roto: son rutas distintas y una no
invalida a la otra.

## 8. Informe

Estructura que funciona para el usuario:

- **Lo que funciona**, con el artefacto y la evidencia de esta sesión (hash del XEX, versión
  del APK, símbolos dentro del `.so`, contadores del log).
- **Lo que falta**, con el bloqueo concreto: la dirección, el hueco, o "falta el dispositivo
  para probarlo".
- **Cuentas del pipeline** (entradas declaradas, huecos ≥8, estado de `/dev/shm`).
- **Desajustes detectados en el código** que no son bloqueos pero engañan: un script que
  elige el NDK equivocado, una ruta de stageo que no es la que usa el build real, un typo de
  formato en un TOML. Aclara siempre si el desajuste **rompe el artefacto que ya existe**
  o solo afecta a un camino de build que no se ha usado.
- **El siguiente paso**, en una frase, y una pregunta de una decisión.
