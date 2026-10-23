# Per-locale SEO metadata for a multi-language docs site

Adding a locale to a docs site without metadata makes the pages look like
duplicate content to crawlers. This is the minimum per-locale set, and the
reason each field exists.

## Open Graph / Twitter

Emit per page, driven by `page.lang`:

```liquid
{% if cur == 'es' %}
  {% assign site_title = "Documentación de Termux Ultra" %}
  {% assign og_locale = "es_ES" %}
  {% assign og_locale_alt = "zh_CN" %}
{% elsif cur == 'en' %}
  {% assign site_title = "Termux Ultra Documentation" %}
  {% assign og_locale = "en_US" %}
  {% assign og_locale_alt = "zh_CN" %}
{% else %}
  {% assign site_title = "Termux Ultra 文档" %}
  {% assign og_locale = "zh_CN" %}
  {% assign og_locale_alt = "es_ES" %}
{% endif %}
<meta property="og:site_name" content="{{ site_title }}">
<meta property="og:title" content="{% if page.title and r != 'index' %}{{ page.title }} · {% endif %}{{ site_title }}">
<meta property="og:description" content="{{ page.description | default: site.description }}">
<meta property="og:type" content="website">
<meta property="og:locale" content="{{ og_locale }}">
<meta property="og:locale:alternate" content="{{ og_locale_alt }}">
<meta property="og:url" content="{{ page.url | absolute_url }}">
<meta name="twitter:card" content="summary">
```

- **`og:locale` is the field that matters.** Without it every translation is
  announced identically and crawlers treat them as the same text repeated.
- Format is `lang_REGION` with an underscore (`es_ES`), unlike the `hreflang`
  attribute which uses BCP-47 with a hyphen (`es`). Mixing them up is a common
  silent error — they are NOT the same syntax.
- `og:locale:alternate` takes one value; list the locales in `hreflang` instead.
- Reuse the single `assign` block for `og_locale` rather than scattering
  `{% if %}` through the `<head>`.

## Give every locale a real route, not just a selector code

A top-bar selector showing only `EN` / `ES` is compact but undiscoverable. Add
descriptive cards on each landing page linking to the sibling locales, skipping
the current one:

```html
## Otros idiomas

<div class="cards">
  <a class="card" href="{{ '/' | relative_url }}">
    <span class="card-title">🇨🇳 中文</span>
    <span class="card-desc">用户手册、功能讲解与插件开发文档（简体中文）。</span>
  </a>
</div>
```

Place the block with the other card grids (before the dashboards section) so it
inherits their styling, and verify the rendered result visually — a card grid
that only appears below the fold is easy to declare correct from the DOM alone.

## Leave `lang:` in _config.yml alone

`lang:` names the language served at `/`. It is the site default, not a leftover
to "fix" when adding locales — changing it makes the root announce the wrong
locale. Which locale should own `/` is a product decision; ask rather than
picking, and say who should decide.

## READMEs: language selector and where to anchor it

A short centered HTML block after the badge row:

```html
<div align="center">

[ <a href="./README.es.md">**Español**</a> · <a href="./README.md">**中文**</a> · <a href="https://host/repo/">Docs</a> ]

</div>
```

- Put the current language first in its own file and last in the others.
- In the translated file, point the Docs link at that locale's docs subpath
  (`/es/`) so it lands on the translation.
- Verify: `<div>` tags balanced, every href target exists, BOM and code blocks
  untouched.
- **Anchor the insert on a unique string, not on the first `# ` heading.** A
  long README has many `## ` headings and the first match is often a
  mid-document section, so a heading-based anchor silently lands the selector
  in the wrong place. Not every README has a Docs badge; fall back to the title
  line for those, and re-read the surrounding context after inserting.

Repo URLs inside READMEs may point at a different account than `git remote` if
the deployed Pages site lives upstream. Check both hosts before repointing — see
`git-history-and-verification.md`.