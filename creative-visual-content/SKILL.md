---
name: creative-visual-content
title: Creative Visual Content
description: Use when creating images with code; kawaii Spanish tone.
category: creative
version: 1.0.0
author: Solar Mini4
license: MIT
hermes:
  tags: [creative, visual, image-generation, python, pillow]
  related_skills: []
---

# Skill: Creative Visual Content

## When to Use
- User asks for an image, visual design, avatar, diagram, illustration, or any visual artifact to be created with code.
- User requests a profile picture, banner, diagram, or any output with pixels rather than text.

## Trigger
When the user asks for an image, visual design, avatar, diagram, illustration, or any visual artifact to be created with code.

## Stance (always-on)
- Respond in Spanish (Latin American neutral, no voseo), warm and enthusiastic.
- Use kawaii expressions: (◕‿◕), ★, ♪, ~, ✨, 💖 throughout.
- Keep replies concise but friendly — no narrating process, no restating, no filler.
- Name files with owner name + 'Imagen' + a short descriptor.

## Order
1. Confirm the deliverable is a visual artifact.
2. Check library availability: python3 -c "import PIL". Install if missing: python3 -m pip install --user Pillow.
3. Plan composition in prose (colors, layout, elements).
4. Implement with vector drawing (ellipse, rect, rounded_rectangle). Avoid per-pixel loops.
5. Verify file exists and size with ls -la.

## Pitfalls
- Never fill backgrounds pixel-by-pixel — use numpy gradient or solid color + filter.
- Import ImageFont explicitly: from PIL import ImageFont.
- Ellipse y1 must be >= y0. Use min/max when computing coordinates.
- Terminal can timeout mid-command — verify file existence before re-running.
- alpha_composite requires matching sizes; draw badge directly on main image.
- Keep loops short; batch drawing calls.
