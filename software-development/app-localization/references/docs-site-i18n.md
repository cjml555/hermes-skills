# Shipping a locale on a Jekyll/GitHub Pages docs site

## baseurl: do not write it by hand

Since Jekyll 3.3, GitHub Pages sets `site.url` and `site.baseurl` automatically
when they are UNDEFINED, fixing them to the repo name. So on a project site at
`user.github.io/my-repo/`, `{{ '/en/' | relative_url }}` already emits
`/my-repo/en/`.

Adding `baseurl: "/my-repo"` yourself duplicates the prefix to
`/my-repo/my-repo/en/` and 404s every link. Before adding one, check what the
deployed site actually emits:

```bash
curl -sL https://user.github.io/my-repo/en/ \
  | grep -oE '(href|src)="/[^"]*"' | sort -u
```

If every path already carries the repo prefix, leave the config alone. A
comment in `_config.yml` recording this beats a silent `baseurl` that future
contributors will "helpfully" duplicate.

## Build the real URL map before generating hrefs

Do not assume locales share a prefix. Under `permalink: pretty`, a page is
served at `/<dir>/<page>/` UNLESS its frontmatter sets `permalink`. An index page
that sets `permalink: /` therefore breaks the pattern, and a selector that
assumes `/<ref>/` for the default language 404s on every non-index page.

Derive the map from the files themselves (frontmatter `permalink` if present,
else pretty permalink from the path) and assert every generated link is a member
of it. `scripts/check_layout_links.py <docs_dir>` does this by rendering the
layout through `python-liquid` and diffing hrefs against the map.

## Language selector rules

- Keep the current page when switching: map `page.ref` to the same `ref` in the
  target locale, and treat `ref: index` as the special case.
- Mark the active locale with `aria-current="page"` and expose the group with
  `role="group"` + a translated `aria-label`.
- Emit `<link rel="alternate" hreflang="...">` for each locale plus `x-default`
  pointing at the root locale.
- Resolve UI strings per locale with a Liquid `assign` block; do not scatter
  `{% if page.lang == %}` ternaries through the markup.
- Translate the chrome too: `<title>`, `<html lang>`, nav labels, skip-link,
  footer, download button.
- Add per-locale Open Graph metadata plus in-page language cards, or the
  translations read as duplicate content to crawlers — see
  `references/docs-seo-per-locale.md`.

## Pages that bypass Liquid

A standalone `.html` file in the docs tree is copied verbatim — `{{ }}` renders
as literal text and no Jekyll filter is available. Use document-relative links
(`../en/`) there. They work unchanged under a repo subpath and after a later
move to a custom domain, which absolute paths do not.

## Verify visually, not just structurally

Render one page per locale to a temp file with the CSS inlined, open it, and
check the selector in both a desktop and a ~390px viewport. Set the real
viewport with CDP (`Emulation.setDeviceMetricsOverride`) — constraining a div's
width does not trigger media queries, so a "mobile" check done that way silently
tests the desktop layout.
