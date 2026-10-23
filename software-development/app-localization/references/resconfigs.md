#resConfigs: the silent locale filter

`resConfigs` (AGP) whitelists which locale qualifiers get PACKAGED. Locales you
add to `res/` but forget to list are dropped at package time with no error.

## Symptom

Every step succeeds and you still get the fallback language on device:

- `:app:mergeDebugResources` produces `values-es/values-es.arsc.flat` — looks fine
- `packaged_res/.../values-es.xml` exists — looks fine
- `aapt2 dump resources <apk>` shows the base locale and nothing else
- `aapt2 dump badging <apk> | grep locales` lists only the whitelisted ones

The giveaway is that intermediates look correct while the APK does not. Always
check the artifact, never the intermediate.

## Fix

Read the list in the module's `build.gradle` (`defaultConfig`/`android` block)
and add the qualifier:

```gradle
resConfigs "en", "es", "zh", "zh-rCN"
```

Match on the FULL qualifier. On AGP 9.x the entries are not prefixes: `"zh"`
matches only `values-zh` and will NOT pull in `values-zh-rCN`, so that one must
be listed separately or the whole Chinese tree is filtered out. The same applies
to `values-b+es+419` and friends — the region must be spelled out.

## Verify

```bash
scripts/verify_apk_locale.py app/build/outputs/apk/debug/app-debug.apk es "Alguna cadena"
```

The script greps `resources.arsc` for the sample string and prints the APK's
declared locale list. A locale that is present in `res/` but absent from that
list is not shipped.
