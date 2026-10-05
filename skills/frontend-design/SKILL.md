---
name: frontend-design
description: "Практические правила для создания выразительного, аккуратного и production-ready интерфейса. Используй при проектировании или доработке UI, если нет более строгого проектного дизайн-гайда."
---

# Frontend Design

Use this skill when building or reviewing user-facing UI. Follow repository conventions and active developer instructions first; use this skill to fill gaps.

## Core Principles

- Build the actual usable experience, not a marketing placeholder.
- Match the product domain: operational tools should be dense, restrained, and efficient; games and creative tools can be more expressive.
- Use real controls for real operations: icon buttons for tools, segmented controls for modes, toggles for binary settings, sliders or numeric inputs for values, tabs for views.
- Keep cards for repeated items, modals, and genuinely framed tools. Do not nest cards.
- Keep typography stable and readable. Do not scale font size directly with viewport width.
- Make layout resilient with explicit dimensions, aspect ratios, grid tracks, and responsive constraints.
- Check that text never overlaps or overflows its container on desktop and mobile.

## Visual Direction

- Avoid one-note palettes dominated by a single hue family.
- Avoid decorative gradient blobs, bokeh, or unrelated visual noise.
- Use relevant images or real product/place/object visuals when a website needs assets.
- Use existing icon libraries when present; prefer `lucide` icons where available.

## Verification

Before finishing UI work, run the app when feasible and inspect desktop and mobile states. Verify that controls are reachable, content fits, and important states are represented.
