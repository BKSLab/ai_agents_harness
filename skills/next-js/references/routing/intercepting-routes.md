---
name: nextjs-intercepting-routes
description: Intercepting and parallel routes in Next.js
applies_to: nextjs
---

# Intercepting and Parallel Routes

## Overview

Intercepting routes allow showing a route within the current layout (e.g., modals).
Parallel routes render multiple pages in the same layout simultaneously.

## Intercepting Routes

### Convention
- `(.)` - Intercept same level
- `(..)` - Intercept one level up
- `(..)(..)` - Intercept two levels up
- `(...)` - Intercept from root

### Modal Pattern Structure
```
app/
├── @modal/
│   ├── (.)products/[id]/
│   │   └── page.tsx          # Intercepts /products/[id] as modal
│   └── default.tsx           # Required fallback
├── products/
│   ├── page.tsx              # /products (list)
│   └── [id]/
│       └── page.tsx          # /products/[id] (full page)
└── layout.tsx                # Root layout with modal slot
```

### Root Layout with Modal Slot
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

### Modal Page (Intercepting)
```tsx
// app/@modal/(.)products/[id]/page.tsx
'use client';

import { useRouter } from 'next/navigation';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ProductDetail } from '@/components/product-detail';

export default function ProductModal({
  params,
}: {
  params: { id: string };
}) {
  const router = useRouter();

  return (
    <Dialog open onOpenChange={() => router.back()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-auto">
        <DialogHeader>
          <DialogTitle>Product Details</DialogTitle>
        </DialogHeader>
        <ProductDetail id={params.id} />
      </DialogContent>
    </Dialog>
  );
}
```

### Default Fallback
```tsx
// app/@modal/default.tsx
export default function ModalDefault() {
  return null; // No modal when not intercepting
}
```

### Full Page (Direct Access)
```tsx
// app/products/[id]/page.tsx
import { notFound } from 'next/navigation';
import { getProduct } from '@/lib/data';
import { ProductDetail } from '@/components/product-detail';

export default async function ProductPage({
  params,
}: {
  params: { id: string };
}) {
  const product = await getProduct(params.id);

  if (!product) {
    notFound();
  }

  return (
    <div className="container py-8">
      <ProductDetail id={params.id} />
    </div>
  );
}
```

## Parallel Routes

### Dashboard with Parallel Sections
```
app/dashboard/
├── @analytics/
│   ├── page.tsx              # Analytics panel
│   └── default.tsx
├── @team/
│   ├── page.tsx              # Team panel
│   └── default.tsx
├── @notifications/
│   ├── page.tsx              # Notifications panel
│   └── default.tsx
├── layout.tsx                # Dashboard layout
└── page.tsx                  # Main content
```

### Dashboard Layout
```tsx
// app/dashboard/layout.tsx
export default function DashboardLayout({
  children,
  analytics,
  team,
  notifications,
}: {
  children: React.ReactNode;
  analytics: React.ReactNode;
  team: React.ReactNode;
  notifications: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-12 gap-6 p-6">
      <main className="col-span-8 space-y-6">
        {children}
        {analytics}
      </main>
      <aside className="col-span-4 space-y-6">
        {team}
        {notifications}
      </aside>
    </div>
  );
}
```

### Parallel Route Pages
```tsx
// app/dashboard/@analytics/page.tsx
import { getAnalytics } from '@/lib/data';

export default async function AnalyticsPanel() {
  const analytics = await getAnalytics();

  return (
    <div className="rounded-lg border bg-card p-6">
      <h2 className="text-lg font-semibold mb-4">Analytics</h2>
      <AnalyticsCharts data={analytics} />
    </div>
  );
}

// app/dashboard/@team/page.tsx
import { getTeamMembers } from '@/lib/data';

export default async function TeamPanel() {
  const members = await getTeamMembers();

  return (
    <div className="rounded-lg border bg-card p-6">
      <h2 className="text-lg font-semibold mb-4">Team</h2>
      <TeamList members={members} />
    </div>
  );
}
```

## Conditional Parallel Routes

### Different Routes per Slot
```
app/dashboard/
├── @sidebar/
│   ├── settings/
│   │   └── page.tsx          # Settings sidebar
│   ├── page.tsx              # Default sidebar
│   └── default.tsx
├── settings/
│   └── page.tsx              # Settings main content
├── layout.tsx
└── page.tsx                  # Dashboard main
```

### Layout with Conditional Slots
```tsx
// app/dashboard/layout.tsx
export default function DashboardLayout({
  children,
  sidebar,
}: {
  children: React.ReactNode;
  sidebar: React.ReactNode;
}) {
  return (
    <div className="flex">
      <aside className="w-64 shrink-0">
        {sidebar}
      </aside>
      <main className="flex-1 p-6">
        {children}
      </main>
    </div>
  );
}
```

## Loading and Error States

### Per-Slot Loading
```tsx
// app/dashboard/@analytics/loading.tsx
export default function AnalyticsLoading() {
  return (
    <div className="rounded-lg border bg-card p-6">
      <div className="h-6 w-32 bg-muted animate-pulse rounded mb-4" />
      <div className="h-64 bg-muted animate-pulse rounded" />
    </div>
  );
}
```

### Per-Slot Error
```tsx
// app/dashboard/@analytics/error.tsx
'use client';

export default function AnalyticsError({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div className="rounded-lg border bg-card p-6 text-center">
      <p className="text-destructive mb-4">Failed to load analytics</p>
      <button onClick={reset}>Retry</button>
    </div>
  );
}
```

## Photo Gallery Example

```
app/
├── @modal/
│   ├── (.)photos/[id]/
│   │   └── page.tsx          # Photo modal
│   └── default.tsx
├── photos/
│   ├── page.tsx              # Photo grid
│   └── [id]/
│       └── page.tsx          # Full photo page
└── layout.tsx
```

### Photo Grid with Links
```tsx
// app/photos/page.tsx
import Link from 'next/link';
import Image from 'next/image';

export default async function PhotosPage() {
  const photos = await getPhotos();

  return (
    <div className="grid grid-cols-4 gap-4">
      {photos.map((photo) => (
        <Link key={photo.id} href={`/photos/${photo.id}`}>
          <Image
            src={photo.thumbnail}
            alt={photo.title}
            width={300}
            height={300}
            className="rounded-lg hover:opacity-80 transition"
          />
        </Link>
      ))}
    </div>
  );
}
```

## Best Practices

1. **Always add default.tsx** - Required for unmatched parallel routes
2. **Use for modals** - Intercepting routes perfect for modal patterns
3. **Independent loading** - Each slot can have its own loading state
4. **Soft navigation** - Intercepts preserve current page state
5. **Hard navigation** - Direct URL access shows full page
6. **Keep slots focused** - Each parallel route has one responsibility
