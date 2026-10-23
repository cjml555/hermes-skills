# Android resource-lookup pitfalls when removing hardcoded UI text

Mechanics specific to moving a displayed string into `res/values*/strings.xml` in a
Kotlin/Compose Android app. Distinct from the gate-trust rules in SKILL.md.

## An enum cannot call `stringResource`

An `enum class` is not `@Composable`, so its label cannot be a `stringResource` call.
Keep the plain string AND add a resource id, then resolve at the use site:

```kotlin
enum class RiskType(val displayName: String, val displayRes: Int) {
    DD("dd disk write", R.string.risk_dd_disk_write),
    /* ... */;

    fun display(context: Context): String =
        try { context.getString(displayRes) } catch (e: RuntimeException) { displayName }
}
```

The `try`/`catch` fallback is deliberate: in a JVM unit test `android.jar` is stubbed
and `getString` throws `"not mocked"`. Without the fallback, a test exercising this path
fails by timeout with no stated cause.

### Split consumers by rendered vs transported, before changing a signature

Grep every read of the label and classify each one:

- **Rendered on screen** → use the localized getter.
- **Transported as data** → keep the plain string. A socket server shipping the label to
  a client, or a judge comparing it against model output, must not receive a
  locale-dependent value: the comparison happens elsewhere and would break.

The same shape applies to `fun`-returning-String maps (permission names, risk levels).
Those need `Context` threaded in as a parameter, which means every call site is an edit.
Enumerate the call sites first — they are usually a handful of composables, each needing
its own `LocalContext.current` if it does not already have one.

## `import com.termux.R` is needed in subpackages

The generated `R` lives in the app's root package (`com.termux`), not in
`com.termux.app.compose` or `com.termux.app.plugin`. A file in a subpackage cannot see it
unqualified. Copy the import from a sibling file in the same package instead of assuming
the package resolves it.

## A BOM defeats `^`-anchored patches

Files under `plugin/` carry a UTF-8 BOM. A regex anchored on `^package` or `^import`
matches nothing on such a file and fails **silently** — the script reports success while
the edit is absent. Check for `\ufeff` at byte 0 when an edit you can see in the diff
never lands. Compiling is the only reliable detector.

## Composable vs non-composable, per call style

| Site | Call |
|---|---|
| directly inside `@Composable` body | `stringResource(R.string.x)` |
| `onClick`, `LaunchedEffect`, plain fn with `Context` | `context.getString(R.string.x)` |
| non-`@Composable` lambda in a `LazyListScope` builder | hoist to a `val` in the enclosing composable first |
| function whose parameter list has no `Context` | add one, or hoist — a lambda being inside a composable does not make it composable |

## Verify each batch

```bash
./gradlew :app:compileDebugKotlin --console=plain   # syntax, imports, composable misuse
./gradlew :app:testDebugUnitTest --console=plain    # runtime paths — not optional
```

Then sweep every non-target locale for source-script leakage, and confirm the values
actually landed in the right file rather than only that the key exists.