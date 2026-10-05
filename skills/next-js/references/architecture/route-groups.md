---
name: nextjs-route-groups
description: Route groups and layouts in Next.js
applies_to: nextjs
---

# Route Groups and Layouts

## Route Groups

Route groups allow organizing routes without affecting the URL path structure.

### Basic Route Groups
```
app/
├── (marketing)/                  # Group name in parentheses
│   ├── layout.tsx               # Marketing layout
│   ├── page.tsx                 # / (home page)
│   ├── about/
│   │   └── page.tsx             # /about
│   └── pricing/
│       └── page.tsx             # /pricing
│
├── (dashboard)/
│   ├── layout.tsx               # Dashboard layout
│   ├── page.tsx                 # /dashboard (can conflict!)
│   └── settings/
│       └── page.tsx             # /settings
│
└── (auth)/
    ├── layout.tsx               # Auth layout
    ├── login/
    │   └── page.tsx             # /login
    └── register/
        └── page.tsx             # /register
```

### Multiple Root Layouts
```
app/
├── (marketing)/
│   ├── layout.tsx               # Marketing root layout
│   └── page.tsx
│
└── (app)/
    ├── layout.tsx               # App root layout (different!)
    └── dashboard/
        └── page.tsx
```

## Layout Types

### Root Layout
```tsx
// app/layout.tsx
import { Inter } from 'next/font/google';
import { Providers } from '@/components/providers';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
```

### Nested Layout
```tsx
// app/(dashboard)/layout.tsx
import { Sidebar } from '@/components/sidebar';
import { Header } from '@/components/header';
import { auth } from '@/lib/auth';
import { redirect } from 'next/navigation';

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();

  if (!session?.user) {
    redirect('/login');
  }

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header user={session.user} />
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
```

### Auth Layout
```tsx
// app/(auth)/layout.tsx
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/50">
      <div className="mx-auto w-full max-w-md space-y-6 p-6">
        {children}
      </div>
    </div>
  );
}
```

## Parallel Routes

Render multiple pages in the same layout simultaneously.

### Structure
```
app/
├── @analytics/
│   ├── page.tsx
│   └── default.tsx
├── @team/
│   ├── page.tsx
│   └── default.tsx
├── layout.tsx                    # Receives both as props
└── page.tsx
```

### Layout with Parallel Routes
```tsx
// app/layout.tsx
export default function Layout({
  children,
  analytics,
  team,
}: {
  children: React.ReactNode;
  analytics: React.ReactNode;
  team: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-12 gap-6">
      <div className="col-span-8">
        {children}
      </div>
      <div className="col-span-4 space-y-6">
        {analytics}
        {team}
      </div>
    </div>
  );
}
```

### Default Fallback
```tsx
// app/@analytics/default.tsx
export default function AnalyticsDefault() {
  return null; // Or loading placeholder
}
```

## Intercepting Routes

Intercept routes to show in the current layout (e.g., modals).

### Convention
- `(.)` - Same level
- `(..)` - One level up
- `(..)(..)` - Two levels up
- `(...)` - Root

### Modal Pattern
```
app/
├── products/
│   ├── page.tsx                  # /products (list)
│   └── [id]/
│       └── page.tsx              # /products/123 (detail page)
├── @modal/
│   ├── (.)products/[id]/
│   │   └── page.tsx              # Intercepts /products/123 as modal
│   └── default.tsx
└── layout.tsx
```

### Layout with Modal Slot
```tsx
// app/layout.tsx
export default function RootLayout({
  children,
  modal,
}: {
  children: React.ReactNode;
  modal: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        {children}
        {modal}
      </body>
    </html>
  );
}
```

### Modal Page
```tsx
// app/@modal/(.)products/[id]/page.tsx
'use client';

import { useRouter } from 'next/navigation';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { ProductDetail } from '@/components/product-detail';

export default function ProductModal({
  params,
}: {
  params: { id: string };
}) {
  const router = useRouter();

  return (
    <Dialog open onOpenChange={() => router.back()}>
      <DialogContent className="max-w-3xl">
        <ProductDetail id={params.id} />
      </DialogContent>
    </Dialog>
  );
}
```

## Templates vs Layouts

### Template (Re-renders)
```tsx
// app/template.tsx
export default function Template({
  children,
}: {
  children: React.ReactNode;
}) {
  // Re-renders on each navigation
  return (
    <div className="animate-fade-in">
      {children}
    </div>
  );
}
```

### Layout (Persists)
```tsx
// app/layout.tsx
export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Does NOT re-render on navigation
  // State is preserved
  return <div>{children}</div>;
}
```

## Common Patterns

### Dashboard with Multiple Sections
```
app/(dashboard)/
├── layout.tsx                    # Dashboard shell
├── page.tsx                      # Dashboard home
├── @stats/
│   └── page.tsx                  # Stats panel
├── @recent/
│   └── page.tsx                  # Recent activity
└── @notifications/
    └── page.tsx                  # Notifications panel
```

### Multi-Tenant App
```
app/
├── [tenant]/                     # Dynamic tenant
│   ├── layout.tsx               # Tenant-specific layout
│   ├── page.tsx                 # Tenant home
│   └── settings/
│       └── page.tsx             # Tenant settings
└── layout.tsx                    # Root layout
```

### Admin vs User Areas
```
app/
├── (user)/                       # Regular user area
│   ├── layout.tsx
│   └── dashboard/
│       └── page.tsx
│
└── (admin)/                      # Admin area
    ├── layout.tsx               # Admin layout with different nav
    └── dashboard/
        └── page.tsx
```

## Best Practices

1. **Use route groups** for logical organization without URL impact
2. **Keep layouts focused** - one responsibility per layout
3. **Use parallel routes** for independent page sections
4. **Use intercepting routes** for modal patterns
5. **Prefer layouts** over templates for performance
6. **Add default.tsx** for parallel routes to handle unmatched routes
7. **Authenticate in layouts** for protected route groups
