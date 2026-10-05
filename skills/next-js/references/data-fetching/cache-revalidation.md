---
name: nextjs-cache-revalidation
description: Caching and revalidation in Next.js
applies_to: nextjs
---

# Caching and Revalidation

## Overview

Next.js provides multiple caching layers for optimal performance:
- Data Cache (fetch results)
- Full Route Cache (rendered pages)
- Router Cache (client-side)

## Fetch Cache Options

### Default (Cached)
```tsx
// Cached indefinitely
const data = await fetch('https://api.example.com/data');
```

### Time-Based Revalidation
```tsx
// Revalidate every hour
const data = await fetch('https://api.example.com/data', {
  next: { revalidate: 3600 },
});
```

### No Cache
```tsx
// Never cache, always fresh
const data = await fetch('https://api.example.com/data', {
  cache: 'no-store',
});
```

### Tag-Based
```tsx
// Cache with tags for targeted revalidation
const data = await fetch('https://api.example.com/products', {
  next: { tags: ['products'] },
});

const product = await fetch(`https://api.example.com/products/${id}`, {
  next: { tags: ['products', `product-${id}`] },
});
```

## Route Segment Config

```tsx
// app/products/page.tsx

// Force static rendering
export const dynamic = 'force-static';

// Force dynamic rendering
export const dynamic = 'force-dynamic';

// Revalidate every hour
export const revalidate = 3600;

// No revalidation (always fresh)
export const revalidate = 0;

// Runtime environment
export const runtime = 'nodejs'; // or 'edge'
```

## Revalidation Methods

### revalidatePath
```tsx
// lib/actions/products.ts
"use server";

import { revalidatePath } from 'next/cache';

export async function createProduct(data: ProductData) {
  await db.product.create({ data });

  // Revalidate specific path
  revalidatePath('/products');

  // Revalidate with layout
  revalidatePath('/products', 'layout');

  // Revalidate specific product page
  revalidatePath(`/products/${data.id}`);
}
```

### revalidateTag
```tsx
// lib/actions/products.ts
"use server";

import { revalidateTag } from 'next/cache';

export async function updateProduct(id: string, data: ProductData) {
  await db.product.update({ where: { id }, data });

  // Revalidate all products
  revalidateTag('products');

  // Revalidate specific product
  revalidateTag(`product-${id}`);
}
```

### On-Demand Revalidation API
```tsx
// app/api/revalidate/route.ts
import { revalidatePath, revalidateTag } from 'next/cache';
import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  const { path, tag, secret } = await request.json();

  // Verify secret
  if (secret !== process.env.REVALIDATION_SECRET) {
    return NextResponse.json({ error: 'Invalid secret' }, { status: 401 });
  }

  try {
    if (path) {
      revalidatePath(path);
    }
    if (tag) {
      revalidateTag(tag);
    }

    return NextResponse.json({
      revalidated: true,
      now: Date.now(),
    });
  } catch (error) {
    return NextResponse.json({ error: 'Failed to revalidate' }, { status: 500 });
  }
}
```

## Webhook Integration

```tsx
// app/api/webhooks/cms/route.ts
import { revalidateTag } from 'next/cache';
import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  const body = await request.json();

  // Verify webhook signature
  const signature = request.headers.get('x-webhook-signature');
  if (!verifySignature(body, signature)) {
    return NextResponse.json({ error: 'Invalid signature' }, { status: 401 });
  }

  // Revalidate based on event type
  switch (body.event) {
    case 'product.created':
    case 'product.updated':
    case 'product.deleted':
      revalidateTag('products');
      if (body.productId) {
        revalidateTag(`product-${body.productId}`);
      }
      break;

    case 'category.updated':
      revalidateTag('categories');
      break;
  }

  return NextResponse.json({ success: true });
}
```

## Cache Patterns

### Fetch with Tags
```tsx
// lib/data/products.ts
import { cache } from 'react';

export const getProducts = cache(async () => {
  const res = await fetch('https://api.example.com/products', {
    next: { tags: ['products'] },
  });
  return res.json();
});

export const getProduct = cache(async (id: string) => {
  const res = await fetch(`https://api.example.com/products/${id}`, {
    next: { tags: ['products', `product-${id}`] },
  });
  return res.json();
});
```

### Database with Revalidation
```tsx
// lib/data/products.ts
import { unstable_cache } from 'next/cache';
import { db } from '@/lib/db';

export const getProducts = unstable_cache(
  async () => {
    return db.product.findMany({
      where: { status: 'active' },
      orderBy: { createdAt: 'desc' },
    });
  },
  ['products'],
  {
    tags: ['products'],
    revalidate: 3600,
  }
);

export const getProduct = unstable_cache(
  async (id: string) => {
    return db.product.findUnique({
      where: { id },
      include: { category: true },
    });
  },
  ['product'],
  {
    tags: ['products'],
    revalidate: 3600,
  }
);
```

## Router Cache

### Client-Side Navigation
```tsx
// The router cache stores visited routes on the client
// Use router.refresh() to force server re-render

"use client";

import { useRouter } from 'next/navigation';

export function RefreshButton() {
  const router = useRouter();

  return (
    <button onClick={() => router.refresh()}>
      Refresh Data
    </button>
  );
}
```

## Debugging Cache

```tsx
// next.config.js
module.exports = {
  logging: {
    fetches: {
      fullUrl: true,
    },
  },
};
```

## Best Practices

1. **Use tags** - Enable granular revalidation
2. **Revalidate after mutations** - Keep data fresh
3. **Use appropriate time** - Balance freshness and performance
4. **Secure webhooks** - Verify signatures
5. **Cache at the right level** - Route vs fetch level
6. **Monitor cache behavior** - Use logging in development
