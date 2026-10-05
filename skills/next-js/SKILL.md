---
name: next-js
description: "Next.js App Router reference skill for architecture, rendering, data fetching, routing, styling, auth, testing, and deployment. Use when building or reviewing Next.js applications."
---

# Next.js

Use this skill for Next.js App Router work. Read only the relevant references for the user's task before acting.

## Reference Routing

Architecture:
- `references/architecture/app-router.md`
- `references/architecture/project-structure.md`
- `references/architecture/route-groups.md`

Rendering:
- `references/rendering/server-components.md`
- `references/rendering/client-components.md`
- `references/rendering/static-dynamic.md`
- `references/rendering/streaming.md`

Data fetching:
- `references/data-fetching/server-fetching.md`
- `references/data-fetching/server-actions.md`
- `references/data-fetching/cache-revalidation.md`
- `references/data-fetching/parallel-sequential.md`

Routing:
- `references/routing/dynamic-routes.md`
- `references/routing/route-handlers.md`
- `references/routing/middleware.md`
- `references/routing/intercepting-routes.md`

Styling:
- `references/styling/tailwind-css.md`
- `references/styling/css-modules.md`
- `references/styling/fonts-images.md`

Authentication:
- `references/auth/next-auth.md`
- `references/auth/middleware-auth.md`
- `references/auth/server-session.md`

Testing:
- `references/testing/component-testing.md`
- `references/testing/jest-testing.md`
- `references/testing/playwright.md`

Deployment:
- `references/deployment/vercel.md`
- `references/deployment/docker.md`
- `references/deployment/edge-runtime.md`

## Working Rules

- Prefer existing project conventions over generic examples.
- Preserve Server Component boundaries; add Client Components only where browser state, effects, or event handlers are needed.
- Treat current framework behavior as time-sensitive; when exact Next.js version behavior matters, verify with local dependencies or official docs.
