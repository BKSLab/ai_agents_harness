---
name: nextjs-server-components
description: React Server Components in Next.js
applies_to: nextjs
---

# Server Components

## Overview

Server Components render on the server, reducing client JavaScript bundle size.
They can directly access backend resources like databases and file systems.

## Benefits

- **Zero client JS** for the component
- **Direct backend access** (database, file system, secrets)
- **Automatic code splitting**
- **Streaming support**
- **Improved SEO** (fully rendered HTML)

## Basic Server Component

```tsx
// app/products/page.tsx
// Server Component by default (no "use client")
import { db } from '@/lib/db';

export default async function ProductsPage() {
  // Direct database access - no API needed
  const products = await db.product.findMany({
    where: { status: 'active' },
    include: { category: true },
    orderBy: { createdAt: 'desc' },
  });

  return (
    <div className="container py-8">
      <h1 className="text-3xl font-bold mb-8">Products</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {products.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
    </div>
  );
}
```

## Data Fetching Patterns

### Using fetch with Caching
```tsx
// Default: Cached indefinitely
async function getProducts() {
  const res = await fetch('https://api.example.com/products');
  return res.json();
}

// Cache for 1 hour
async function getProducts() {
  const res = await fetch('https://api.example.com/products', {
    next: { revalidate: 3600 },
  });
  return res.json();
}

// No caching (always fresh)
async function getProducts() {
  const res = await fetch('https://api.example.com/products', {
    cache: 'no-store',
  });
  return res.json();
}
```

### Using React Cache
```tsx
import { cache } from 'react';
import { db } from '@/lib/db';

// Memoize for the request duration
export const getProduct = cache(async (id: string) => {
  return db.product.findUnique({
    where: { id },
    include: { category: true },
  });
});

// Can be called multiple times - only executes once per request
export default async function ProductPage({ params }: { params: { id: string } }) {
  const product = await getProduct(params.id);
  // ...
}

export async function generateMetadata({ params }: { params: { id: string } }) {
  const product = await getProduct(params.id); // Same cached result
  // ...
}
```

### Parallel Data Fetching
```tsx
export default async function DashboardPage() {
  // All start simultaneously
  const [stats, orders, notifications] = await Promise.all([
    getStats(),
    getRecentOrders(),
    getNotifications(),
  ]);

  return (
    <div className="grid grid-cols-12 gap-6">
      <StatsCards stats={stats} />
      <OrdersList orders={orders} />
      <NotificationList notifications={notifications} />
    </div>
  );
}
```

## Composing with Client Components

### Server Component Wrapper
```tsx
// app/products/page.tsx (Server Component)
import { db } from '@/lib/db';
import { ProductFilters } from './product-filters'; // Client Component
import { ProductList } from './product-list';       // Server Component

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: { category?: string };
}) {
  const categories = await db.category.findMany();

  const products = await db.product.findMany({
    where: searchParams.category
      ? { categoryId: searchParams.category }
      : undefined,
  });

  return (
    <div className="container py-8">
      {/* Client Component for interactivity */}
      <ProductFilters categories={categories} />

      {/* Server Component with data */}
      <ProductList products={products} />
    </div>
  );
}
```

### Passing Server Data to Client
```tsx
// app/products/page.tsx
import { ProductCard } from './product-card'; // Client Component

export default async function ProductsPage() {
  const products = await getProducts();

  return (
    <div className="grid gap-6">
      {products.map((product) => (
        // Serializable data passed to Client Component
        <ProductCard
          key={product.id}
          product={{
            id: product.id,
            name: product.name,
            price: product.price,
          }}
        />
      ))}
    </div>
  );
}
```

## Server-Only Code

### Marking Code as Server-Only
```tsx
// lib/db.ts
import 'server-only';
import { PrismaClient } from '@prisma/client';

const globalForPrisma = global as unknown as { prisma: PrismaClient };

export const db = globalForPrisma.prisma || new PrismaClient();

if (process.env.NODE_ENV !== 'production') {
  globalForPrisma.prisma = db;
}
```

### Accessing Server-Only Resources
```tsx
// Only works in Server Components
import { cookies, headers } from 'next/headers';

export default async function Page() {
  const cookieStore = cookies();
  const token = cookieStore.get('token');

  const headersList = headers();
  const userAgent = headersList.get('user-agent');

  return <div>...</div>;
}
```

## Static Generation

### generateStaticParams
```tsx
// app/products/[id]/page.tsx
import { db } from '@/lib/db';

export async function generateStaticParams() {
  const products = await db.product.findMany({
    select: { id: true },
    where: { status: 'active' },
  });

  return products.map((product) => ({
    id: product.id,
  }));
}

export default async function ProductPage({
  params,
}: {
  params: { id: string };
}) {
  const product = await getProduct(params.id);
  // ...
}
```

### Dynamic Segments
```tsx
// Force dynamic rendering
export const dynamic = 'force-dynamic';

// Or force static
export const dynamic = 'force-static';

// Configure revalidation
export const revalidate = 3600; // Revalidate every hour
```

## Error Handling

```tsx
// app/products/page.tsx
import { notFound } from 'next/navigation';

export default async function ProductPage({
  params,
}: {
  params: { id: string };
}) {
  const product = await getProduct(params.id);

  if (!product) {
    notFound();
  }

  return <ProductDetail product={product} />;
}
```

## Best Practices

1. **Default to Server Components** - Only use Client when needed
2. **Fetch data at the leaf** - Fetch where data is used
3. **Use React cache** - Deduplicate requests in single render
4. **Parallel fetch** - Use Promise.all for independent data
5. **Use server-only** - Prevent accidental client imports
6. **Keep components small** - Better for streaming
7. **Handle errors** - Use notFound() and error boundaries
