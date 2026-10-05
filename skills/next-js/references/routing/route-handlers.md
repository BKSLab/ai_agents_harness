---
name: nextjs-route-handlers
description: API Route Handlers in Next.js
applies_to: nextjs
---

# Route Handlers

## Overview

Route Handlers allow creating API endpoints using the Web Request and Response APIs.
Define them in `route.ts` files within the `app` directory.

## Basic Route Handler

### GET Request
```tsx
// app/api/products/route.ts
import { NextResponse } from 'next/server';
import { db } from '@/lib/db';

export async function GET() {
  const products = await db.product.findMany({
    where: { status: 'active' },
    orderBy: { createdAt: 'desc' },
  });

  return NextResponse.json(products);
}
```

### POST Request
```tsx
// app/api/products/route.ts
import { NextResponse } from 'next/server';
import { z } from 'zod';
import { db } from '@/lib/db';

const createProductSchema = z.object({
  name: z.string().min(2).max(100),
  price: z.number().min(0),
  categoryId: z.string().uuid(),
});

export async function POST(request: Request) {
  try {
    const body = await request.json();

    const validated = createProductSchema.safeParse(body);

    if (!validated.success) {
      return NextResponse.json(
        { error: 'Validation failed', details: validated.error.flatten() },
        { status: 400 }
      );
    }

    const product = await db.product.create({
      data: validated.data,
    });

    return NextResponse.json(product, { status: 201 });
  } catch (error) {
    console.error('POST /api/products error:', error);
    return NextResponse.json(
      { error: 'Internal Server Error' },
      { status: 500 }
    );
  }
}
```

## Dynamic Route Handlers

```tsx
// app/api/products/[id]/route.ts
import { NextResponse } from 'next/server';
import { db } from '@/lib/db';

interface RouteContext {
  params: { id: string };
}

export async function GET(request: Request, { params }: RouteContext) {
  const product = await db.product.findUnique({
    where: { id: params.id },
  });

  if (!product) {
    return NextResponse.json(
      { error: 'Product not found' },
      { status: 404 }
    );
  }

  return NextResponse.json(product);
}

export async function PATCH(request: Request, { params }: RouteContext) {
  const body = await request.json();

  try {
    const product = await db.product.update({
      where: { id: params.id },
      data: body,
    });

    return NextResponse.json(product);
  } catch (error) {
    return NextResponse.json(
      { error: 'Product not found' },
      { status: 404 }
    );
  }
}

export async function DELETE(request: Request, { params }: RouteContext) {
  try {
    await db.product.delete({
      where: { id: params.id },
    });

    return new NextResponse(null, { status: 204 });
  } catch (error) {
    return NextResponse.json(
      { error: 'Product not found' },
      { status: 404 }
    );
  }
}
```

## Request Handling

### URL and Search Params
```tsx
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const page = Number(searchParams.get('page')) || 1;
  const limit = Number(searchParams.get('limit')) || 10;
  const search = searchParams.get('q') || '';

  const skip = (page - 1) * limit;

  const products = await db.product.findMany({
    where: search
      ? { name: { contains: search, mode: 'insensitive' } }
      : undefined,
    skip,
    take: limit,
  });

  return NextResponse.json(products);
}
```

### Headers
```tsx
export async function GET(request: Request) {
  const authHeader = request.headers.get('authorization');

  if (!authHeader?.startsWith('Bearer ')) {
    return NextResponse.json(
      { error: 'Unauthorized' },
      { status: 401 }
    );
  }

  const token = authHeader.split(' ')[1];
  // Verify token...

  return NextResponse.json({ message: 'Authenticated' });
}
```

### Cookies
```tsx
import { cookies } from 'next/headers';

export async function GET() {
  const cookieStore = cookies();
  const token = cookieStore.get('auth-token');

  return NextResponse.json({ hasToken: !!token });
}

export async function POST() {
  const cookieStore = cookies();

  cookieStore.set('session', 'value', {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 7, // 1 week
  });

  return NextResponse.json({ success: true });
}
```

## Response Types

### JSON Response
```tsx
return NextResponse.json({ data: 'value' });
return NextResponse.json({ error: 'message' }, { status: 400 });
```

### Redirect
```tsx
import { redirect } from 'next/navigation';
import { NextResponse } from 'next/server';

export async function GET() {
  // Option 1: Using redirect (throws)
  redirect('/new-location');

  // Option 2: Using NextResponse
  return NextResponse.redirect(new URL('/new-location', request.url));
}
```

### Stream Response
```tsx
export async function GET() {
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      for (let i = 0; i < 10; i++) {
        const data = encoder.encode(`data: ${JSON.stringify({ count: i })}\n\n`);
        controller.enqueue(data);
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      controller.close();
    },
  });

  return new NextResponse(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  });
}
```

## File Upload

```tsx
// app/api/upload/route.ts
import { writeFile } from 'fs/promises';
import { join } from 'path';
import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  const formData = await request.formData();
  const file = formData.get('file') as File;

  if (!file) {
    return NextResponse.json(
      { error: 'No file provided' },
      { status: 400 }
    );
  }

  const bytes = await file.arrayBuffer();
  const buffer = Buffer.from(bytes);

  const filename = `${Date.now()}-${file.name}`;
  const path = join(process.cwd(), 'public/uploads', filename);

  await writeFile(path, buffer);

  return NextResponse.json({ url: `/uploads/${filename}` });
}
```

## Route Segment Config

```tsx
// Force dynamic
export const dynamic = 'force-dynamic';

// Revalidation
export const revalidate = 3600;

// Runtime
export const runtime = 'edge'; // or 'nodejs'

// Max duration (serverless)
export const maxDuration = 30;
```

## Best Practices

1. **Validate input** - Use Zod for request body validation
2. **Handle errors** - Return appropriate status codes
3. **Use try/catch** - Catch and log errors
4. **Type responses** - Define response interfaces
5. **Set headers** - CORS, caching as needed
6. **Prefer Server Actions** - For form mutations
