---
name: nextjs-streaming
description: Streaming and Suspense in Next.js
applies_to: nextjs
---

# Streaming and Suspense

## Overview

Streaming allows progressively rendering UI from the server.
Use Suspense to show fallback content while components load.

## Basic Streaming

### Page-Level Loading
```tsx
// app/dashboard/loading.tsx
import { Skeleton } from '@/components/ui/skeleton';

export default function Loading() {
  return (
    <div className="container py-8">
      <Skeleton className="h-10 w-48 mb-8" />
      <div className="grid grid-cols-4 gap-6">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-32 rounded-lg" />
        ))}
      </div>
    </div>
  );
}
```

### Component-Level Suspense
```tsx
// app/dashboard/page.tsx
import { Suspense } from 'react';
import { StatsCards } from './stats-cards';
import { RecentOrders } from './recent-orders';
import { StatsSkeleton, OrdersSkeleton } from './skeletons';

export default function DashboardPage() {
  return (
    <div className="container py-8">
      <h1 className="text-3xl font-bold mb-8">Dashboard</h1>

      {/* Each section streams independently */}
      <Suspense fallback={<StatsSkeleton />}>
        <StatsCards />
      </Suspense>

      <Suspense fallback={<OrdersSkeleton />}>
        <RecentOrders />
      </Suspense>
    </div>
  );
}
```

## Streaming Patterns

### Independent Sections
```tsx
// app/dashboard/page.tsx
import { Suspense } from 'react';

async function SlowComponent() {
  const data = await fetch('https://api.example.com/slow', {
    cache: 'no-store',
  });
  return <div>{/* ... */}</div>;
}

async function FastComponent() {
  const data = await fetch('https://api.example.com/fast');
  return <div>{/* ... */}</div>;
}

export default function Page() {
  return (
    <div className="grid grid-cols-2 gap-6">
      {/* Fast component renders first */}
      <Suspense fallback={<div>Loading fast...</div>}>
        <FastComponent />
      </Suspense>

      {/* Slow component streams in later */}
      <Suspense fallback={<div>Loading slow...</div>}>
        <SlowComponent />
      </Suspense>
    </div>
  );
}
```

### Nested Suspense
```tsx
// app/products/page.tsx
import { Suspense } from 'react';

export default function ProductsPage() {
  return (
    <div className="container">
      {/* Outer suspense for the whole section */}
      <Suspense fallback={<ProductsSectionSkeleton />}>
        <section>
          <h2 className="text-2xl font-bold mb-4">Products</h2>

          {/* Inner suspense for product grid */}
          <Suspense fallback={<ProductGridSkeleton />}>
            <ProductGrid />
          </Suspense>

          {/* Another inner suspense for recommendations */}
          <Suspense fallback={<RecommendationsSkeleton />}>
            <Recommendations />
          </Suspense>
        </section>
      </Suspense>
    </div>
  );
}
```

### Sequential Streaming
```tsx
// When order matters
export default async function Page() {
  // This data must load first
  const user = await getUser();

  return (
    <div>
      <UserHeader user={user} />

      {/* This can stream after user loads */}
      <Suspense fallback={<OrdersSkeleton />}>
        <UserOrders userId={user.id} />
      </Suspense>
    </div>
  );
}
```

## Skeleton Components

### Card Skeleton
```tsx
// components/skeletons/product-card-skeleton.tsx
import { Skeleton } from '@/components/ui/skeleton';

export function ProductCardSkeleton() {
  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <Skeleton className="aspect-square w-full" />
      <div className="p-4 space-y-3">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-6 w-1/4" />
      </div>
    </div>
  );
}
```

### Grid Skeleton
```tsx
// components/skeletons/product-grid-skeleton.tsx
import { ProductCardSkeleton } from './product-card-skeleton';

export function ProductGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
      {Array.from({ length: count }).map((_, i) => (
        <ProductCardSkeleton key={i} />
      ))}
    </div>
  );
}
```

### Table Skeleton
```tsx
// components/skeletons/table-skeleton.tsx
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {Array.from({ length: cols }).map((_, i) => (
            <TableHead key={i}>
              <Skeleton className="h-4 w-20" />
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {Array.from({ length: rows }).map((_, i) => (
          <TableRow key={i}>
            {Array.from({ length: cols }).map((_, j) => (
              <TableCell key={j}>
                <Skeleton className="h-4 w-full" />
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

## Streaming with Search Params

```tsx
// app/products/page.tsx
import { Suspense } from 'react';
import { ProductList } from './product-list';
import { ProductListSkeleton } from './product-list-skeleton';

export default function ProductsPage({
  searchParams,
}: {
  searchParams: { page?: string; q?: string };
}) {
  // Key changes when search params change, triggering new Suspense
  const key = JSON.stringify(searchParams);

  return (
    <div className="container py-8">
      <Suspense key={key} fallback={<ProductListSkeleton />}>
        <ProductList searchParams={searchParams} />
      </Suspense>
    </div>
  );
}
```

## Loading UI Best Practices

### Match Layout Structure
```tsx
// Skeleton should match actual component layout
export function DashboardSkeleton() {
  return (
    <div className="grid grid-cols-12 gap-6">
      {/* Match the actual dashboard grid */}
      <div className="col-span-8">
        <Skeleton className="h-64 mb-6" />
        <Skeleton className="h-96" />
      </div>
      <div className="col-span-4">
        <Skeleton className="h-48 mb-6" />
        <Skeleton className="h-48" />
      </div>
    </div>
  );
}
```

### Avoid Layout Shift
```tsx
// Reserve space to prevent content jumping
export function ProductCardSkeleton() {
  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      {/* Fixed aspect ratio prevents layout shift */}
      <div className="aspect-square bg-muted" />
      <div className="p-4 space-y-3">
        {/* Fixed heights prevent shift */}
        <div className="h-4 bg-muted rounded w-1/3" />
        <div className="h-5 bg-muted rounded w-3/4" />
      </div>
    </div>
  );
}
```

## Best Practices

1. **Add loading.tsx** to all data-fetching routes
2. **Use Suspense boundaries** for independent sections
3. **Key Suspense** on search params for proper re-rendering
4. **Match skeleton layout** to prevent content shift
5. **Stream slow data** - fast content shows immediately
6. **Nest Suspense** for granular loading states
7. **Use animations** - subtle fade-in for streamed content
