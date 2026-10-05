---
name: nextjs-static-dynamic
description: Static vs Dynamic rendering in Next.js
applies_to: nextjs
---

# Static vs Dynamic Rendering

## Overview

Next.js automatically chooses between static and dynamic rendering based on the code patterns used.

## Rendering Modes

| Mode | When | Benefit |
|------|------|---------|
| Static | Build time | Fast, cacheable at CDN |
| Dynamic | Request time | Fresh data, personalization |
| Streaming | Request time | Progressive loading |

## Static Rendering (Default)

### Basic Static Page
```tsx
// app/about/page.tsx
// Rendered at build time
export default function AboutPage() {
  return (
    <div className="container py-8">
      <h1>About Us</h1>
      <p>Static content that never changes</p>
    </div>
  );
}
```

### Static with Data
```tsx
// app/products/page.tsx
// Static because fetch is cached by default
export default async function ProductsPage() {
  const products = await fetch('https://api.example.com/products');

  return <ProductList products={products} />;
}
```

### generateStaticParams
```tsx
// app/products/[id]/page.tsx
import { db } from '@/lib/db';

// Generate static pages at build time
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
  return <ProductDetail product={product} />;
}
```

## Dynamic Rendering

### Triggers for Dynamic Rendering

Dynamic rendering is triggered by:
- `cookies()` or `headers()`
- `searchParams` in page
- `fetch` with `cache: 'no-store'`
- `dynamic = 'force-dynamic'`
- `revalidate = 0`

### Using cookies/headers
```tsx
// app/dashboard/page.tsx
import { cookies, headers } from 'next/headers';

// Automatically dynamic because of cookies()
export default async function DashboardPage() {
  const cookieStore = cookies();
  const token = cookieStore.get('auth-token');

  const user = await getUser(token);

  return <Dashboard user={user} />;
}
```

### Using searchParams
```tsx
// app/products/page.tsx
// Dynamic because searchParams can change per request
export default async function ProductsPage({
  searchParams,
}: {
  searchParams: { page?: string; q?: string };
}) {
  const products = await getProducts(searchParams);

  return <ProductList products={products} />;
}
```

### Force Dynamic
```tsx
// app/live/page.tsx
// Force dynamic rendering
export const dynamic = 'force-dynamic';

export default async function LivePage() {
  const liveData = await fetch('https://api.example.com/live');
  return <LiveFeed data={liveData} />;
}
```

### No-Store Fetch
```tsx
// Always fresh data
async function getCurrentPrice() {
  const res = await fetch('https://api.example.com/price', {
    cache: 'no-store',
  });
  return res.json();
}
```

## Incremental Static Regeneration (ISR)

### Time-Based Revalidation
```tsx
// app/news/page.tsx
// Revalidate every hour
export const revalidate = 3600;

export default async function NewsPage() {
  const news = await fetch('https://api.example.com/news');
  return <NewsList news={news} />;
}
```

### Fetch-Level Revalidation
```tsx
async function getProducts() {
  const res = await fetch('https://api.example.com/products', {
    next: { revalidate: 3600 }, // Revalidate every hour
  });
  return res.json();
}
```

### On-Demand Revalidation
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

  if (path) {
    revalidatePath(path);
  }

  if (tag) {
    revalidateTag(tag);
  }

  return NextResponse.json({ revalidated: true, now: Date.now() });
}
```

### Tag-Based Revalidation
```tsx
// Fetch with tag
async function getProduct(id: string) {
  const res = await fetch(`https://api.example.com/products/${id}`, {
    next: { tags: ['products', `product-${id}`] },
  });
  return res.json();
}

// Server Action to revalidate
'use server';

import { revalidateTag } from 'next/cache';

export async function updateProduct(id: string, data: ProductData) {
  await db.product.update({ where: { id }, data });

  // Revalidate specific product
  revalidateTag(`product-${id}`);

  // Or revalidate all products
  revalidateTag('products');
}
```

## Route Segment Config

```tsx
// Force static
export const dynamic = 'force-static';

// Force dynamic
export const dynamic = 'force-dynamic';

// Auto (default)
export const dynamic = 'auto';

// Revalidation time
export const revalidate = 3600; // seconds

// No revalidation (always dynamic)
export const revalidate = 0;

// Runtime
export const runtime = 'nodejs'; // or 'edge'
```

## Deciding Between Static and Dynamic

### Use Static When
- Content is the same for all users
- Data doesn't change frequently
- SEO is important
- Performance is critical

### Use Dynamic When
- Content is personalized
- Data changes frequently
- Real-time data needed
- Using authentication

### Use ISR When
- Content updates periodically
- Want static performance with fresh data
- Can tolerate slightly stale content

## Best Practices

1. **Default to static** - Let Next.js auto-detect
2. **Be explicit** - Use config when behavior must be certain
3. **Use ISR** - Balance performance and freshness
4. **Tag fetches** - Enable granular revalidation
5. **Avoid unnecessary dynamic** - Don't use cookies() if not needed
6. **Segment dynamic parts** - Use Suspense to mix static/dynamic
