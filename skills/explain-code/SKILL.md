---
name: explain-code
description: "Понятное объяснение кода через краткое резюме, аналогию, ASCII-схему, пошаговый разбор и типичную ошибку. Используй, когда пользователь просит объяснить код или архитектурный фрагмент."
---

# Explain Code

Use this skill when the user asks to explain code, a stack trace, a function, a module, or a flow.

## Response Shape

1. Start with the core idea in 2-3 sentences.
2. Add a simple analogy if it makes the concept easier.
3. Include a small ASCII diagram for data flow, ownership, or call sequence when useful.
4. Walk through the code path step by step using concrete identifiers from the code.
5. Point out one common pitfall or edge case.
6. End with a short practical takeaway.

Prefer clarity over completeness. Avoid changing code unless the user explicitly asks.
