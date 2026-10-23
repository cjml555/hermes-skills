## Wrapper Elimination Checklist

After creating a manager, eliminate one-line delegation wrappers from the Activity.

### Pre-flight: verify the extraction is wired
Before removing a wrapper, confirm the manager method it delegates to is actually reachable
from the Activity. A manager method with zero external references is a dead extraction, not a
working delegation:

```
grep -rn '\b<methodName>\b' app/src/main/java/ | grep -v <ManagerFile>.kt | wc -l
```

If that returns 0, stop. The manager's entry point is never called, so deleting the wrapper
removes the only path that ran — wire the manager first (see SKILL.md "Verify an Extraction
Is Wired").

### Post-elimination: sweep for newly-dead code
Removing wrappers orphans whatever only they used. Count references before deleting anything:

- unused `Regex` properties (`drawCmdRegex`, `tagCmdRegex`) left after parsing moved to a scanner
- duplicate helpers in the manager (an `encodeFiles()` nothing calls while the Activity
  delegates to another class)
- a UI build implemented in both the manager and the Activity — the Activity copy is dead

Then drop the imports that went with them: `grep -c '\b<Symbol>\b' <file>` returning 1 means
the import line is its only occurrence.

### UI helpers are wrappers too
`dp()`, `toast()`, `rounded()`, `matchWrap()` repeated across Activity/Page/Handler are the
same problem at a different scale — see SKILL.md "Deduplicating UI Helpers".

### Elimination steps
1. `grep -n "wrapperName(" <Activity>.kt` — find all call sites
2. Update each call site to use the manager method directly
3. Remove the wrapper method definition
4. Compile: `./gradlew :app:compileDebugKotlin --no-daemon -q`
5. Commit: "refactor: remove wrapper [methodName]"

### Common Wrapper Names in Ponko
| Wrapper | Delegates to | Use instead |
|---|---|---|
| buildFileBlock | chatManager.buildFileBlock | chatManager.buildFileBlock |
| encodeFiles | chatManager.encodeFiles | chatManager.encodeFiles |
| restoreFiles | attachmentHandler.restoreFiles | attachmentHandler.restoreFiles |
| estTokens | chatManager.estTokens | chatManager.estTokens |
| fitTokens | chatManager.fitTokens | chatManager.fitTokens |
| pickChatFile | attachmentHandler.pickChatFile | attachmentHandler.pickChatFile |
| pickChatImage | attachmentHandler.pickChatImage | attachmentHandler.pickChatImage |
| readTextFile | attachmentHandler.readTextFile | attachmentHandler.readTextFile |
| decodeChatImage | attachmentHandler.decodeChatImage | attachmentHandler.decodeChatImage |
| queryDisplayName | attachmentHandler.queryDisplayName | attachmentHandler.queryDisplayName |