# Runtime Surfaces That Are Hard to Test (topic depth)

Four refactor shapes whose rules are only needed when you hit that shape.
They live here, not in SKILL.md, because they are depth rather than
always-on rules.

## 1. Moving a deeply coupled method as an extension

`doSend`/`runRound` (250–300 lines, ~30 Activity members) have a clean shape
— a host interface — and a cheap one: move them out **unchanged as
extensions on the Activity**.

```kotlin
// ChatSend.kt — same body, same state, zero call-site edits
internal fun MainActivity.doSend() { … }
internal suspend fun MainActivity.runRound(…): RoundOut { … }
```

The file shrinks and the flow gets its own home; the coupling remains, so
treat it as a waypoint rather than real separation.

- **Open only what the compiler names.** Build once, parse every
  `Cannot access 'X': it is private in 'MainActivity'` out of the log, and
  regex-patch those declarations to `internal` in a single pass. Two passes
  normally finish it. The pattern must allow `lateinit`:
  `private lateinit var inputEdit` does not match `private var`.
- **A property plus a same-named setter collide at the JVM level.** Opening
  `busy` to `internal` while `fun setBusy(b: Boolean)` exists yields
  `Platform declaration clash … setBusy$app(Z)V`; rename the function
  (`applyBusy`). The property's generated setter cannot be renamed.
- **Qualify duplicated class names.** With a top-level `AiArea` and a nested
  `MainActivity.AiArea`, the moved code resolves the wrong one:
  `Argument type mismatch: actual type is 'MainActivity.AiArea'`. Write
  `MainActivity.AiArea` in the extension signature.
- Extract by brace matching from the signature, not by line range, and confirm
  the moved text still resolves `this@MainActivity` and its local `fun`s.
- **Verify with a live round**, not only a build: load a model, send a
  message, read the reply and the tok/s footnote. The characterization rule
  in SKILL.md still governs *changing* the logic; this pattern only moves it.

## 2. Characterizing a streaming parser (marker-based splitters)

A parser that watches for a marker in a stream of chunks (LLM reasoning vs
answer, SSE frames, protocol headers) is pure logic and deserves the same
treatment — but it has three bug classes that ordinary string handling hides,
because the marker can arrive **split across chunks**:

1. **Searching a trimmed string for a marker that starts with whitespace.**
   `val core = s.trimStart()` then `core.contains(" thinking")` can never
   match: the marker's leading space was just removed. Search the
   **untrimmed** text.
2. **Deleting buffer content that was never emitted.** Emitting only the
   leading whitespace (`if (lead > 0) onAnswer(s.substring(0, lead))`) and
   then deleting the buffer up to the end of the marker **discards the prefix
   silently**. Emit `s.substring(0, hit.first)` — everything before the
   marker, not just the whitespace.
3. **Comparing mismatched quantities in the retention predicate.** A
   "how many trailing chars could be a marker prefix" helper computed over
   the full string compared against the length of the *trimmed* string never
   matches, so the buffer never retains a partial marker and the marker is
   emitted as text. Compare like with like.

- **Test the chunk boundary explicitly.** Feed the marker split at every
  position (`"<chan" + "nel>"`), and feed a chunk that *ends* mid-marker with
  text before it (`"Hola<|chan"`) — that is the case that exposes the
  retention bug.
- **A retention predicate must emit the safe prefix.** The correct shape is
  "keep the suffix that could still become a marker, emit everything before
  it", not "emit nothing unless the whole buffer is a marker prefix".
- **Write the characterization test first, and let it report the bugs.** In
  this codebase the first run of the characterization tests failed 4 of 18 —
  and all four failures were real defects in the parser, not wrong
  expectations. **Commit the failing expectations as the baseline** (with the
  current behavior asserted and the bug named in the test comment), then fix
  the parser in a second commit. That keeps "what it did" and "what it
  should do" as two reviewable steps. (See also "When a Characterization
  Test Fails" in SKILL.md: the probe is how you tell a real bug from a wrong
  expectation — here the probe was the printed buffer contents.)
- **Verify on-device with the real model**, not only in the unit test: the
  visible symptom is the "reasoning" collapsible staying empty, which no
  unit test of the splitter can show.

## 3. Testing a handler that launches coroutines

A handler that does `scope.launch { … }` needs the coroutines test artifact
and an explicit drain, or every assertion sees an empty world:

```kotlin
// app/build.gradle.kts — test classpath only
testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.11.0")
```

```kotlin
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest

@Test
fun theImportFollowsTheExpectedOrder() = runTest {
    imp.import(uri, importFile = { _, _, _ -> null }, …)
    advanceUntilIdle()   // <- without this the launch body never runs
    assertEquals(listOf("setBusy(true)", "setBusy(false)", …), host.calls)
}
```

- **`runTest` uses a queued dispatcher**: the body of `launch` runs when the
  test yields. Without `advanceUntilIdle()` the assertions run first and fail
  with a confusing "expected null but was …" — the symptom of an empty state,
  not of wrong logic.
- **Assert the ORDER, not just the final state.** A handler's sequence
  (occupy → progress → work → release → result) is what breaks silently in a
  refactor. Compare the full recorded call list; it pins "release happens
  after the work" and "the success toast does not fire on error" in one
  assertion.
- **Make the class generic in the payload type** (`class Importer<T>`) so the
  test does not need an Android type. `android.net.Uri` is a stub in
  `android.jar` (`Method parse in android.net.Uri not mocked`) and its
  constructor is package-private, so it can be neither parsed nor subclassed
  in a plain JVM test — a `String` payload is the way through.
- A `SharedPreferences` fake, a `Uri` fake and an `org.json` real
  implementation are the three stubs a JVM test of an Android manager hits
  first. Add them to the test classpath once and they serve every test file.

## 4. The API contract is a public surface: extract and pin it

A local HTTP API that advertises itself as OpenAI-compatible has a **public
contract**: Hermes, OpenWebUI, Continue and LangChain all depend on the exact
JSON shape. A silent change breaks agents that look fine in the app.

- Extract the contract into a pure object that only builds and reads JSON —
  no sockets. Then a JVM test can pin the shape without a network:
  ```kotlin
  object OpenAiApi {
      fun chatCompletion(...): JSONObject
      fun chatChunk(..., role: String? = null): JSONObject
      fun sseEvent(json: JSONObject): String = "data: $json\n\n"
      const val SSE_DONE = "data: [DONE]\n\n"
      fun error(message: String, type: String): JSONObject
      object ErrorType { const val INVALID_REQUEST = "invalid_request_error" /* ... */ }
  }
  ```
- **Unify the error bodies.** A hand-written API repeats
  `JSONObject().put("error", JSONObject().put("message", …).put("type", …))`
  in every branch. Replace all of them with one helper — and confirm the
  output is **byte-identical** (same key, same order) so no client sees a
  difference.
- **Name the error types.** `ErrorType.INVALID_REQUEST` beats the string
  literal `"invalid_request_error"` repeated 5 times, and it gives the
  compiler something to check.
- **A regex rewrite can rename identifiers it did not mean to.** Converting
  `"invalid_request_error"` to `ErrorType.INVALID_REQUEST_ERROR` compiles
  against nothing; map the snake_case wire value to the Kotlin constant name
  explicitly and check the constant list before compiling.
- **Verify against the real device, not only the unit tests.** The definitive
  check is the actual HTTP round-trip against the phone:
  ```bash
  curl -s http://<phone-ip>:<port>/health
  curl -s http://<phone-ip>:<port>/v1/models
  curl -sN -X POST http://<phone-ip>:<port>/v1/chat/completions \
       -H 'Content-Type: application/json' -d '{"messages":[…],"stream":true}'
  ```
  Look at the raw SSE bytes: the first chunk must carry `delta.role`, the
  middle ones only `delta.content` with `finish_reason: null`, the last one
  `delta: {}` with `finish_reason: "stop"`, and the stream must end with
  `data: [DONE]`.
