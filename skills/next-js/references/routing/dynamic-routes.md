---
name: nextjs-dynamic-routes
description: Dynamic route segments in Next.js
applies_to: nextjs
---

# Dynamic Routes

## Overview

Dynamic routes allow creating pages that respond to dynamic parameters.
Use brackets `[]` to define dynamic segments.

## Route Segment Types

| Pattern | Example | Matches |
|---------|---------|---------|
| `[id]` | `/products/[id]` | `/products/123` |
| `[...slug]` | `/blog/[...slug]` | `/blog/a/b/c` |
| `[[...slug]]` | `/shop/[[...slug]]` | `/shop` or `/shop/a/b` |

## Single Dynamic Segment

### Basic Usage
```tsx
// app/products/[id]/page.tsx
interface ProductPageProps {
  params: { id: string };
}

export default async function ProductPage({ params }: ProductPageProps) {
  const product = await getProduct(params.id);

  if (!product) {
    notFound();
  }

  return <ProductDetail product={product} />;
}
```

### With Search Params
```tsx
// app/products/[id]/page.tsx
interface ProductPageProps {
  params: { id: string };
  searchParams: { variant?: string; color?: string };
}

export default async function ProductPage({
  params,
  searchParams,
}: ProductPageProps) {
  const product = await getProduct(params.id);
  const selectedVariant = searchParams.variant;

  return (
    <ProductDetail
      product={product}
      selectedVariant={selectedVariant}
    />
  );
}
```

## Multiple Dynamic Segments

```tsx
// app/shop/[category]/[product]/page.tsx
interface ShopProductPageProps {
  params: {
    category: string;
    product: string;
  };
}

export default async function ShopProductPage({
  params,
}: ShopProductPageProps) {
  const { category, product } = params;

  const data = await getProductInCategory(category, product);

  return <ProductDetail data={data} />;
}
```

## Catch-All Segments

### Required Catch-All
```tsx
// app/blog/[...slug]/page.tsx
// Matches: /blog/a, /blog/a/b, /blog/a/b/c
// Does NOT match: /blog

interface BlogPostPageProps {
  params: { slug: string[] };
}

export default async function BlogPostPage({ params }: BlogPostPageProps) {
  // slug is an array: ['a', 'b', 'c']
  const path = params.slug.join('/');
  const post = await getPostByPath(path);

  return <BlogPost post={post} />;
}
```

### Optional Catch-All
```tsx
// app/docs/[[...slug]]/page.tsx
// Matches: /docs, /docs/a, /docs/a/b

interface DocsPageProps {
  params: { slug?: string[] };
}

export default async function DocsPage({ params }: DocsPageProps) {
  // slug is undefined for /docs
  // slug is ['getting-started'] for /docs/getting-started
  const path = params.slug?.join('/') ?? 'index';
  const doc = await getDocByPath(path);

  return <Documentation doc={doc} />;
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
  // ...
}
```

### Multiple Segments
```tsx
// app/shop/[category]/[product]/page.tsx
export async function generateStaticParams() {
  const products = await db.product.findMany({
    include: { category: true },
  });

  return products.map((product) => ({
    category: product.category.slug,
    product: product.slug,
  }));
}
```

### Catch-All Static Params
```tsx
// app/blog/[...slug]/page.tsx
export async function generateStaticParams() {
  const posts = await getAllPosts();

  return posts.map((post) => ({
    slug: post.path.split('/'), // ['2024', '01', 'my-post']
  }));
}
```

## Dynamic Segment Config

### Dynamic vs Static
```tsx
// Force static generation (error if can't be static)
export const dynamicParams = false;

// Allow dynamic generation (default)
export const dynamicParams = true;
```

### Revalidation
```tsx
// Revalidate static pages every hour
export const revalidate = 3600;

// Always dynamic
export const revalidate = 0;
```

## Metadata

### Static Metadata
```tsx
// app/products/[id]/page.tsx
export const metadata = {
  title: 'Product',
};
```

### Dynamic Metadata
```tsx
// app/products/[id]/page.tsx
import { Metadata } from 'next';

export async function generateMetadata({
  params,
}: {
  params: { id: string };
}): Promise<Metadata> {
  const product = await getProduct(params.id);

  if (!product) {
    return { title: 'Product Not Found' };
  }

  return {
    title: product.name,
    description: product.description,
    openGraph: {
      title: product.name,
      images: product.image ? [product.image] : [],
    },
  };
}
```

## Best Practices

1. **Use generateStaticParams** - Pre-render common pages
2. **Handle not found** - Use notFound() for missing resources
3. **Type params properly** - Define interfaces for params
4. **Set dynamicParams** - Control fallback behavior
5. **Use meaningful slugs** - Better URLs for SEO
6. **Validate params** - Ensure params are valid before use
