---
name: next-js
description: "Разработка и ревью приложений Next.js App Router: архитектура, рендеринг, данные, маршруты, авторизация, тесты и развёртывание."
---

Сначала прочитай зависимости и соглашения проекта, затем только относящиеся к задаче references. Примеры не предписывают обновлять Next.js, менять библиотеку авторизации или развёртывать приложение.

## Материалы по задаче

| Область | References |
|---|---|
| Архитектура | [App Router](references/architecture/app-router.md), [структура проекта](references/architecture/project-structure.md), [route groups](references/architecture/route-groups.md) |
| Рендеринг | [server components](references/rendering/server-components.md), [client components](references/rendering/client-components.md), [static/dynamic](references/rendering/static-dynamic.md), [streaming](references/rendering/streaming.md) |
| Данные | [server fetching](references/data-fetching/server-fetching.md), [server actions](references/data-fetching/server-actions.md), [cache/revalidation](references/data-fetching/cache-revalidation.md), [порядок запросов](references/data-fetching/parallel-sequential.md) |
| Маршруты | [dynamic routes](references/routing/dynamic-routes.md), [route handlers](references/routing/route-handlers.md), [middleware](references/routing/middleware.md), [intercepting routes](references/routing/intercepting-routes.md) |
| Стили | [Tailwind](references/styling/tailwind-css.md), [CSS Modules](references/styling/css-modules.md), [шрифты и изображения](references/styling/fonts-images.md) |
| Авторизация | [NextAuth](references/auth/next-auth.md), [middleware auth](references/auth/middleware-auth.md), [server session](references/auth/server-session.md) |
| Тесты | [component testing](references/testing/component-testing.md), [Jest](references/testing/jest-testing.md), [Playwright](references/testing/playwright.md) |
| Развёртывание | [Vercel](references/deployment/vercel.md), [Docker](references/deployment/docker.md), [Edge Runtime](references/deployment/edge-runtime.md) |

## Применение

Сохраняй границы Server Components; добавляй Client Components для состояния браузера, эффектов и обработчиков событий. Взаимозависимые запросы выполняй последовательно, независимые можно выполнять параллельно.

Поведение кеша, маршрутов и API зависит от версии. Когда это влияет на решение, сверь примеры с установленными зависимостями и официальной документацией. Команды установки, публикации и работы с окружением в references — примеры для соответствующей задачи, а не самостоятельное разрешение на внешнее действие.
