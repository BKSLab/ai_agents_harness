---
name: nextjs-server-fetching
description: Server-side data fetching in Next.js
applies_to: nextjs
---

# Server-Side Data Fetching

## Overview

Next.js extends the native `fetch` API with caching and revalidation options.
Data can be fetched directly in Server Components.

## Basic Fetch

### Simple Fetch
```tsx
// app/products/page.tsx
async function getProducts() {
  const res = await fetch('https://api.example.com/products');

  if (!res.ok) {
    throw new Error('Failed to fetch products');
  }

  return res.json();
}

export default async function ProductsPage() {
  const products = await getProducts();

  return <ProductList products={products} />;
}
```

### Fetch with Error Handling
```tsx
async function getProduct(id: string) {
  const res = await fetch(`https://api.example.com/products/${id}`);

  if (!res.ok) {
    if (res.status === 404) {
      return null;
    }
    throw new Error(`Failed to fetch product: ${res.statusText}`);
  }

  return res.json();
}

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

## Database Access

### Direct Database Query
```tsx
// app/products/page.tsx
import { db } from '@/lib/db';

export default async function ProductsPage() {
  const products = await db.product.findMany({
    where: { status: 'active' },
    include: {
      category: true,
      _count: { select: { reviews: true } },
    },
    orderBy: { createdAt: 'desc' },
  });

  return <ProductList products={products} />;
}
```

### With Filters and Pagination
```tsx
// app/products/page.tsx
interface SearchParams {
  page?: string;
  q?: string;
  category?: string;
  sort?: string;
}

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const page = Number(searchParams.page) || 1;
  const limit = 12;
  const skip = (page - 1) * limit;

  const where = {
    status: 'active' as const,
    ...(searchParams.q && {
      OR: [
        { name: { contains: searchParams.q, mode: 'insensitive' as const } },
        { description: { contains: searchParams.q, mode: 'insensitive' as const } },
      ],
    }),
    ...(searchParams.category && {
      categoryId: searchParams.category,
    }),
  };

  const orderBy = searchParams.sort === 'price'
    ? { price: 'asc' as const }
    : { createdAt: 'desc' as const };

  const [products, total] = await Promise.all([
    db.product.findMany({
      where,
      include: { category: true },
      orderBy,
      skip,
      take: limit,
    }),
    db.product.count({ where }),
  ]);

  return (
    <ProductList
      products={products}
      pagination={{ page, limit, total }}
    />
  );
}
```

## Caching Strategies

### Default Caching (Static)
```tsx
// Cached indefinitely (at build time)
async function getCategories() {
  const res = await fetch('https://api.example.com/categories');
  return res.json();
}
```

### Time-Based Revalidation
```tsx
// Revalidate every hour
async function getProducts() {
  const res = await fetch('https://api.example.com/products', {
    next: { revalidate: 3600 },
  });
  return res.json();
}
```

### No Caching (Dynamic)
```tsx
// Always fresh
async function getCurrentUser() {
  const res = await fetch('https://api.example.com/me', {
    cache: 'no-store',
  });
  return res.json();
}
```

### Tag-Based Caching
```tsx
// Fetch with tags for targeted revalidation
async function getProduct(id: string) {
  const res = await fetch(`https://api.example.com/products/${id}`, {
    next: { tags: ['products', `product-${id}`] },
  });
  return res.json();
}
```

## Request Deduplication

### Using React Cache
```tsx
// lib/data.ts
import { cache } from 'react';
import { db } from '@/lib/db';

// Memoized for the request duration
export const getProduct = cache(async (id: string) => {
  return db.product.findUnique({
    where: { id },
    include: { category: true },
  });
});

// Called multiple times, only executes once per request
// app/products/[id]/page.tsx
export default async function ProductPage({ params }: { params: { id: string } }) {
  const product = await getProduct(params.id);
  // ...
}

// Uses cached result
export async function generateMetadata({ params }: { params: { id: string } }) {
  const product = await getProduct(params.id);
  return { title: product?.name };
}
```

## External API Integration

### With Headers
```tsx
async function getAuthenticatedData() {
  const session = await auth();

  const res = await fetch('https://api.example.com/protected', {
    headers: {
      Authorization: `Bearer ${session?.accessToken}`,
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
  });

  return res.json();
}
```

### With Timeout
```tsx
async function fetchWithTimeout(url: string, timeout = 5000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const res = await fetch(url, {
      signal: controller.signal,
    });
    return res.json();
  } finally {
    clearTimeout(timeoutId);
  }
}
```

## Data Functions Pattern

```tsx
// lib/data/products.ts
import { db } from '@/lib/db';
import { cache } from 'react';

export const getProducts = cache(async (options?: {
  category?: string;
  limit?: number;
}) => {
  return db.product.findMany({
    where: {
      status: 'active',
      ...(options?.category && { categoryId: options.category }),
    },
    take: options?.limit ?? 20,
    orderBy: { createdAt: 'desc' },
  });
});

export const getProduct = cache(async (id: string) => {
  return db.product.findUnique({
    where: { id },
    include: { category: true, reviews: true },
  });
});

export const getCategories = cache(async () => {
  return db.category.findMany({
    orderBy: { name: 'asc' },
  });
});
```

## Best Practices

1. **Colocate data fetching** - Fetch where data is used
2. **Use React cache** - Deduplicate requests in single render
3. **Handle errors** - Check response status, throw or return null
4. **Set appropriate caching** - Match data freshness requirements
5. **Use tags** - Enable granular revalidation
6. **Type responses** - Define TypeScript types for API responses
