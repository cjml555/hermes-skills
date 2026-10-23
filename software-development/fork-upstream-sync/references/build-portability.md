# Dependencies that resolve from one machine and nowhere else

A build that succeeds locally proves the toolchain on this machine, not that
the dependency is obtainable anywhere else. The gap appears only when someone
else — CI, a fresh clone, a worktree — tries to resolve it.

## Finding them

Read the build files for coordinates that are not obviously first-party:

```bash
rg -n 'implementation "|api "' build.gradle */build.gradle
```

Then ask whether each one actually exists where it claims to. The signal is a
coordinate whose group is a person, not an organisation:

```groovy
implementation "io.github.awkox:libterminal:4.0.0"
```

`io.github.<user>:<repo>` implies a GitHub-published package. If the repository
does not exist or is private, nothing can resolve it except a private registry
or a local publish.

Checks, in order of usefulness:

```bash
gh repo view <owner>/<repo> --json name,owner        # 404 => not public
curl -s 'https://search.maven.org/solrsearch/select?q=g:<group>&wt=json'   # indexed?
ls ~/.m2/repository/<group-path>/                     # published locally?
find ~/.gradle/caches/modules-2/files-2.1 -maxdepth 1 -name '<group>*'
```

A cache hit alongside empty results is only a *hypothesis*. Confirm it before
reporting, because every one of those checks can miss an artifact that is
genuinely published.

**The check that settles it is a direct fetch of the artifact path**, which is
not in the list above because it is the one that is easy to skip in favour of
searching a repository index:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  https://repo1.maven.org/maven2/<group-with-slashes>/<artifact>/<version>/<artifact>-<version>.pom
```

`200` means a clean CI build resolves it and there is no portability problem at
all. An index search returning nothing — a 404 on the GitHub repo, an empty
Solr result, a missing `~/.m2` entry — proves nothing on its own: publishers
publish to the repository without being indexed by it, and `io.github.<user>`
coordinates do get released to Maven Central.

Treat a false portability claim as expensive: it sends the maintainer looking
for a registry to publish to, and it may go into a commit message where it
outlives the session. Verify with the `curl` above, not by inference.

## Corroborate before reporting

A cached artifact is strong evidence but not proof of the mechanism — check
whether a private registry is configured before concluding:

```bash
rg -n 'maven|url "' build.gradle | head     # mavenLocal() explains local resolution
```

If `mavenLocal()` is in the repository list and `~/.m2` is also empty, the
resolution came from somewhere else, and you should not guess which. Say what
you observed and what it implies.

## What it means, stated precisely

Report the two consequences separately, because they differ in urgency:

- **Reproducibility.** A clean CI build cannot resolve it. Any workflow that
  does not prime the cache fails, and the failure looks like a network or
  repository error rather than a missing artifact.
- **Upstream currency.** A fork cannot pick up engine updates on its own. If
  this is a terminal emulator's core, security fixes land wherever the artifact
  is published, and this repo only sees them when someone remembers.

The second is the one worth raising: the first is a nuisance, the second is an
unattended security surface.

## What to report

State the coordinate, which checks came back empty, and the two consequences.
Offer the options — publish the artifact properly, vendor the code in-tree, or
accept and document it — and let the maintainer choose. Do not attempt to
republish someone else's artifact, and do not treat a single missing cache entry
as proof of the whole pattern.

When a dependency turns out to be portable after being reported otherwise, say
so plainly and correct the record in the commit that carries the claim.