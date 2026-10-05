---
name: nextjs-app-router
description: Next.js App Router fundamentals
applies_to: nextjs
---

# Next.js App Router

## Overview

The App Router is Next.js 13+'s file-system based router using React Server Components by default.

## Core Concepts

### File Conventions

```
app/
├── layout.tsx          # Shared UI for segment and children
├── page.tsx            # Unique UI for route, makes route publicly accessible
├── loading.tsx         # Loading UI for segment and children
├── not-found.tsx       # Not found UI for segment and children
├── error.tsx           # Error UI for segment and children
├── global-error.tsx    # Global error UI
├── route.ts            # Server-side API endpoint
├── template.tsx        # Re-rendered layout
├── default.tsx         # Parallel route fallback
└── opengraph-image.tsx # OG image generation
```

### Route Segments

```
app/
├── dashboard/           # Route segment
│   ├── page.tsx        # /dashboard
│   ├── settings/       # Nested segment
│   │   └── page.tsx    # /dashboard/settings
│   └── [id]/           # Dynamic segment
│       └── page.tsx    # /dashboard/:id
├── blog/
│   ├── page.tsx        # /blog
│   └── [...slug]/      # Catch-all segment
│       └── page.tsx    # /blog/*
└── shop/
    └── [[...slug]]/    # Optional catch-all
        └── page.tsx    # /shop or /shop/*
```

## Layout Hierarchy

### Root Layout (Required)
```tsx
// app/layout.tsx
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata = {
  title: 'My App',
  description: 'App description',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        {children}
      </body>
    </html>
  );
}
```

### Nested Layouts
```tsx
// app/dashboard/layout.tsx
import { Sidebar } from '@/components/sidebar';
import { Header } from '@/components/header';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Header />
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
```

## Page Component

### Basic Page
```tsx
// app/page.tsx
export default function HomePage() {
  return (
    <div className="container py-8">
      <h1 className="text-4xl font-bold">Welcome</h1>
    </div>
  );
}
```

### Page with Data Fetching
```tsx
// app/products/page.tsx
import { db } from '@/lib/db';

export default async function ProductsPage() {
  const products = await db.product.findMany();

  return (
    <div className="container py-8">
      <h1 className="text-3xl font-bold mb-8">Products</h1>
      <ProductList products={products} />
    </div>
  );
}
```

### Page with Params
```tsx
// app/products/[id]/page.tsx
interface ProductPageProps {
  params: { id: string };
  searchParams: { [key: string]: string | string[] | undefined };
}

export default async function ProductPage({
  params,
  searchParams,
}: ProductPageProps) {
  const product = await getProduct(params.id);

  return (
    <div className="container py-8">
      <ProductDetail product={product} />
    </div>
  );
}
```

## Loading UI

### Page-Level Loading
```tsx
// app/products/loading.tsx
import { Skeleton } from '@/components/ui/skeleton';

export default function Loading() {
  return (
    <div className="container py-8">
      <Skeleton className="h-10 w-48 mb-8" />
      <div className="grid grid-cols-4 gap-6">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-64 rounded-lg" />
        ))}
      </div>
    </div>
  );
}
```

## Error Handling

### Error Boundary
```tsx
// app/products/error.tsx
'use client';

import { useEffect } from 'react';
import { Button } from '@/components/ui/button';

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function Error({ error, reset }: ErrorProps) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="container py-16 text-center">
      <h2 className="text-xl font-semibold mb-4">Something went wrong!</h2>
      <Button onClick={reset}>Try again</Button>
    </div>
  );
}
```

### Global Error
```tsx
// app/global-error.tsx
'use client';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html>
      <body>
        <h2>Something went wrong!</h2>
        <button onClick={reset}>Try again</button>
      </body>
    </html>
  );
}
```

## Not Found

### Custom 404
```tsx
// app/not-found.tsx
import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function NotFound() {
  return (
    <div className="container py-16 text-center">
      <h2 className="text-2xl font-bold mb-4">Not Found</h2>
      <p className="text-muted-foreground mb-8">
        Could not find the requested resource
      </p>
      <Button asChild>
        <Link href="/">Return Home</Link>
      </Button>
    </div>
  );
}
```

### Programmatic Not Found
```tsx
// app/products/[id]/page.tsx
import { notFound } from 'next/navigation';

export default async function ProductPage({ params }: { params: { id: string } }) {
  const product = await getProduct(params.id);

  if (!product) {
    notFound();
  }

  return <ProductDetail product={product} />;
}
```

## Metadata

### Static Metadata
```tsx
// app/about/page.tsx
import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'About Us',
  description: 'Learn about our company',
  openGraph: {
    title: 'About Us',
    description: 'Learn about our company',
    images: ['/og-about.jpg'],
  },
};

export default function AboutPage() {
  return <div>About Us</div>;
}
```

### Dynamic Metadata
```tsx
// app/products/[id]/page.tsx
import { Metadata } from 'next';

type Props = {
  params: { id: string };
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const product = await getProduct(params.id);

  if (!product) {
    return { title: 'Product Not Found' };
  }

  return {
    title: product.name,
    description: product.description,
    openGraph: {
      title: product.name,
      images: product.imageUrl ? [product.imageUrl] : [],
    },
  };
}
```

## Best Practices

1. **Use Server Components by default** - Only add "use client" when needed
2. **Colocate related files** - Keep components near their routes
3. **Use loading.tsx** - Provide instant feedback during navigation
4. **Handle errors gracefully** - Use error.tsx at appropriate levels
5. **Optimize metadata** - Use generateMetadata for dynamic SEO
6. **Leverage layouts** - Share UI between routes efficiently
