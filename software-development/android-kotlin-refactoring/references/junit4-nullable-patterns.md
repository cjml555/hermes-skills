# JUnit4 Nullable Kotlin Patterns

Rules for writing unit tests against nullable-returning Kotlin code in JUnit4.

## Assertion function calls

| Situation | Correct | Wrong |
|-----------|---------|-------|
| Assert non-null result exists | `assertNotNull("msg", result)` | `assertEquals(0, result == null)` |
| Assert result is null | `assertNull("msg", result)` | `assertTrue(result == null)` |
| Compare nullable boolean | `result?.inAnswer == true` | `result?.inAnswer` |

## Why nullable Boolean breaks assertEquals/assertTrue

`assertEquals(expected, actual)` requires both types non-null. When comparing
a `Boolean?` to a `Boolean`, the compiler rejects it. Using `== true/false`
makes both sides `Boolean` and the comparison works.

Example that fails:
```kotlin
assertTrue("inAnswer should be true", result?.inAnswer)  // COMPILE ERROR
// actual type is Boolean? but assertTrue expects Boolean
```

Example that works:
```kotlin
assertTrue("inAnswer should be true", result?.inAnswer == true)
```

## assertTrue argument order

JUnit4 `assertTrue(message, condition)` — message FIRST, condition SECOND.
If you swap, Kotlin complains about uninitialized variable.

```kotlin
// Wrong: message is actually a String boolean
assertTrue(condition, "message")  // Type mismatch

// Right
assertTrue("message", condition)
```
