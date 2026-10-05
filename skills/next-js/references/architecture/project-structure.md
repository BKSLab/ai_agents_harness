---
name: nextjs-project-structure
description: Next.js project organization patterns
applies_to: nextjs
---

# Next.js Project Structure

## Recommended Structure

```
my-app/
├── app/                          # App Router
│   ├── (auth)/                   # Auth route group
│   │   ├── login/
│   │   │   └── page.tsx
│   │   ├── register/
│   │   │   └── page.tsx
│   │   └── layout.tsx
│   ├── (dashboard)/              # Dashboard route group
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   ├── settings/
│   │   │   └── page.tsx
│   │   └── analytics/
│   │       └── page.tsx
│   ├── (marketing)/              # Marketing pages group
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   ├── about/
│   │   │   └── page.tsx
│   │   └── pricing/
│   │       └── page.tsx
│   ├── api/                      # API routes
│   │   ├── auth/[...nextauth]/
│   │   │   └── route.ts
│   │   ├── products/
│   │   │   ├── route.ts
│   │   │   └── [id]/
│   │   │       └── route.ts
│   │   └── webhooks/
│   │       └── stripe/
│   │           └── route.ts
│   ├── layout.tsx                # Root layout
│   ├── loading.tsx               # Root loading
│   ├── error.tsx                 # Root error
│   ├── not-found.tsx             # 404 page
│   └── globals.css               # Global styles
│
├── components/                   # Shared components
│   ├── ui/                       # Base UI components (shadcn/ui)
│   │   ├── button.tsx
│   │   ├── input.tsx
│   │   ├── card.tsx
│   │   └── ...
│   ├── forms/                    # Form components
│   │   ├── login-form.tsx
│   │   ├── register-form.tsx
│   │   └── product-form.tsx
│   ├── layouts/                  # Layout components
│   │   ├── header.tsx
│   │   ├── footer.tsx
│   │   ├── sidebar.tsx
│   │   └── nav.tsx
│   └── shared/                   # Other shared components
│       ├── logo.tsx
│       ├── theme-toggle.tsx
│       └── user-avatar.tsx
│
├── lib/                          # Core utilities
│   ├── actions/                  # Server actions
│   │   ├── auth.ts
│   │   ├── users.ts
│   │   └── products.ts
│   ├── db.ts                     # Database client
│   ├── auth.ts                   # Auth configuration
│   ├── utils.ts                  # Utility functions
│   ├── validations.ts            # Zod schemas
│   └── constants.ts              # App constants
│
├── hooks/                        # Custom React hooks
│   ├── use-debounce.ts
│   ├── use-local-storage.ts
│   └── use-media-query.ts
│
├── types/                        # TypeScript types
│   ├── index.ts                  # Re-exports
│   ├── api.ts                    # API types
│   └── database.ts               # Database types
│
├── config/                       # Configuration files
│   ├── site.ts                   # Site configuration
│   ├── dashboard.ts              # Dashboard config
│   └── marketing.ts              # Marketing config
│
├── public/                       # Static assets
│   ├── images/
│   ├── fonts/
│   └── favicon.ico
│
├── prisma/                       # Database (if using Prisma)
│   ├── schema.prisma
│   └── migrations/
│
├── __tests__/                    # Tests
│   ├── components/
│   ├── actions/
│   └── api/
│
├── e2e/                          # E2E tests (Playwright)
│   ├── auth.spec.ts
│   └── products.spec.ts
│
├── .env.local                    # Local environment
├── .env.example                  # Environment template
├── next.config.js                # Next.js config
├── tailwind.config.ts            # Tailwind config
├── tsconfig.json                 # TypeScript config
├── package.json
└── README.md
```

## Organization Patterns

### Feature-Based Organization

```
app/
├── (features)/
│   ├── products/
│   │   ├── page.tsx
│   │   ├── [id]/
│   │   │   └── page.tsx
│   │   ├── components/           # Feature-specific components
│   │   │   ├── product-card.tsx
│   │   │   ├── product-list.tsx
│   │   │   └── product-filters.tsx
│   │   ├── actions/              # Feature-specific actions
│   │   │   └── products.ts
│   │   └── types.ts              # Feature-specific types
│   │
│   └── orders/
│       ├── page.tsx
│       ├── [id]/
│       │   └── page.tsx
│       ├── components/
│       │   ├── order-card.tsx
│       │   └── order-list.tsx
│       └── actions/
│           └── orders.ts
```

### Route Group Organization

```
app/
├── (auth)/                       # No /auth in URL
│   ├── login/page.tsx           # /login
│   ├── register/page.tsx        # /register
│   └── layout.tsx               # Auth-specific layout
│
├── (dashboard)/                  # No /dashboard in URL
│   ├── page.tsx                 # /
│   ├── settings/page.tsx        # /settings
│   └── layout.tsx               # Dashboard layout with sidebar
│
├── (marketing)/
│   ├── page.tsx                 # /
│   ├── about/page.tsx           # /about
│   └── layout.tsx               # Marketing layout
```

## File Naming Conventions

### Components
```
components/
├── product-card.tsx              # kebab-case for files
├── ProductCard.tsx               # PascalCase also acceptable
└── index.ts                      # Re-export file
```

### Utilities and Hooks
```
lib/utils.ts                      # lowercase
hooks/use-debounce.ts             # use- prefix for hooks
```

### Types
```
types/
├── index.ts
└── product.ts                    # Entity name
```

## Import Aliases

```json
// tsconfig.json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./*"],
      "@/components/*": ["components/*"],
      "@/lib/*": ["lib/*"],
      "@/hooks/*": ["hooks/*"],
      "@/types/*": ["types/*"]
    }
  }
}
```

Usage:
```tsx
import { Button } from '@/components/ui/button';
import { db } from '@/lib/db';
import { useDebounce } from '@/hooks/use-debounce';
import type { Product } from '@/types';
```

## Colocation Strategy

### Route-Specific Components
```
app/products/
├── page.tsx
├── loading.tsx
├── error.tsx
├── product-list.tsx              # Colocated, only used here
├── product-filters.tsx           # Colocated, only used here
└── [id]/
    ├── page.tsx
    └── product-detail.tsx        # Colocated
```

### Shared Components
```
components/
└── product-card.tsx              # Used across multiple routes
```

## Environment Variables

```bash
# .env.local
DATABASE_URL="postgresql://..."
NEXTAUTH_SECRET="..."
NEXTAUTH_URL="http://localhost:3000"

# Public variables (available in browser)
NEXT_PUBLIC_APP_URL="http://localhost:3000"
NEXT_PUBLIC_API_URL="/api"
```

## Configuration Files

### next.config.js
```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'images.unsplash.com',
      },
    ],
  },
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
};

module.exports = nextConfig;
```

### Site Configuration
```ts
// config/site.ts
export const siteConfig = {
  name: 'My App',
  description: 'App description',
  url: process.env.NEXT_PUBLIC_APP_URL,
  ogImage: '/og.jpg',
  links: {
    twitter: 'https://twitter.com/myapp',
    github: 'https://github.com/myapp',
  },
};
```

## Best Practices

1. **Use route groups** to organize without affecting URLs
2. **Colocate related files** within route directories
3. **Keep shared components** in `/components`
4. **Keep server logic** in `/lib/actions` and `/lib`
5. **Use TypeScript path aliases** for clean imports
6. **Separate concerns**: UI, logic, types
7. **Use barrel exports** (index.ts) for cleaner imports
