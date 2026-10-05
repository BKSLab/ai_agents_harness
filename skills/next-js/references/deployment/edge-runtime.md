---
name: nextjs-edge-runtime
description: Edge Runtime deployment in Next.js
applies_to: nextjs
---

# Edge Runtime

## Overview

Edge Runtime enables running Next.js code at the network edge,
closer to users for reduced latency and improved performance.

## Edge API Routes

### Basic Edge Route
```ts
// app/api/edge/route.ts
export const runtime = 'edge';

export async function GET(request: Request) {
  return new Response('Hello from the Edge!');
}
```

### With Request Data
```ts
// app/api/geo/route.ts
export const runtime = 'edge';

export async function GET(request: Request) {
  // Access geo data (Vercel)
  const country = request.headers.get('x-vercel-ip-country') || 'Unknown';
  const city = request.headers.get('x-vercel-ip-city') || 'Unknown';

  return Response.json({
    country,
    city,
    timestamp: new Date().toISOString(),
  });
}
```

### Edge with Cache
```ts
// app/api/cached/route.ts
export const runtime = 'edge';

export async function GET() {
  const data = await fetchExternalAPI();

  return new Response(JSON.stringify(data), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'public, s-maxage=60, stale-while-revalidate=300',
    },
  });
}
```

## Edge Middleware

### Authentication Middleware
```ts
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export const config = {
  matcher: ['/dashboard/:path*', '/api/protected/:path*'],
};

export function middleware(request: NextRequest) {
  const token = request.cookies.get('auth-token');

  if (!token) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  // Verify JWT at the edge
  try {
    const payload = verifyJWT(token.value);
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set('x-user-id', payload.userId);

    return NextResponse.next({
      request: { headers: requestHeaders },
    });
  } catch {
    return NextResponse.redirect(new URL('/login', request.url));
  }
}

function verifyJWT(token: string) {
  // Edge-compatible JWT verification
  // Use jose library for Edge runtime
  return { userId: '123' };
}
```

### Geo-Based Routing
```ts
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const country = request.geo?.country || 'US';

  // Redirect based on country
  if (country === 'JP' && !request.nextUrl.pathname.startsWith('/ja')) {
    return NextResponse.redirect(new URL('/ja' + request.nextUrl.pathname, request.url));
  }

  if (country === 'DE' && !request.nextUrl.pathname.startsWith('/de')) {
    return NextResponse.redirect(new URL('/de' + request.nextUrl.pathname, request.url));
  }

  return NextResponse.next();
}
```

### A/B Testing
```ts
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const response = NextResponse.next();

  // Check for existing bucket
  let bucket = request.cookies.get('ab-bucket')?.value;

  if (!bucket) {
    // Assign random bucket
    bucket = Math.random() < 0.5 ? 'control' : 'experiment';
    response.cookies.set('ab-bucket', bucket, {
      maxAge: 60 * 60 * 24 * 30, // 30 days
    });
  }

  // Add bucket to headers for page to read
  response.headers.set('x-ab-bucket', bucket);

  return response;
}
```

## Edge-Compatible Libraries

### Using jose for JWT
```ts
// lib/auth-edge.ts
import { jwtVerify, SignJWT } from 'jose';

const secret = new TextEncoder().encode(process.env.JWT_SECRET);

export async function verifyToken(token: string) {
  try {
    const { payload } = await jwtVerify(token, secret);
    return payload;
  } catch {
    return null;
  }
}

export async function createToken(payload: object) {
  return await new SignJWT({ ...payload })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime('1h')
    .sign(secret);
}
```

### Edge-Compatible Database (Planetscale)
```ts
// lib/db-edge.ts
import { Client } from '@planetscale/database';

const client = new Client({
  host: process.env.DATABASE_HOST,
  username: process.env.DATABASE_USERNAME,
  password: process.env.DATABASE_PASSWORD,
});

export async function queryEdge(sql: string, params?: any[]) {
  const conn = client.connection();
  const result = await conn.execute(sql, params);
  return result.rows;
}
```

### Edge-Compatible KV (Vercel KV)
```ts
// app/api/edge-kv/route.ts
import { kv } from '@vercel/kv';

export const runtime = 'edge';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const key = searchParams.get('key');

  if (!key) {
    return Response.json({ error: 'Key required' }, { status: 400 });
  }

  const value = await kv.get(key);
  return Response.json({ value });
}

export async function POST(request: Request) {
  const { key, value, ttl } = await request.json();

  await kv.set(key, value, { ex: ttl || 3600 });
  return Response.json({ success: true });
}
```

## Edge Streaming

### Streaming Response
```ts
// app/api/stream/route.ts
export const runtime = 'edge';

export async function GET() {
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      for (let i = 0; i < 10; i++) {
        controller.enqueue(encoder.encode(`data: ${i}\n\n`));
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  });
}
```

### AI Streaming (OpenAI)
```ts
// app/api/ai/route.ts
import OpenAI from 'openai';

export const runtime = 'edge';

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

export async function POST(request: Request) {
  const { prompt } = await request.json();

  const response = await openai.chat.completions.create({
    model: 'gpt-4',
    messages: [{ role: 'user', content: prompt }],
    stream: true,
  });

  const stream = new ReadableStream({
    async start(controller) {
      for await (const chunk of response) {
        const text = chunk.choices[0]?.delta?.content || '';
        controller.enqueue(new TextEncoder().encode(text));
      }
      controller.close();
    },
  });

  return new Response(stream, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
```

## Edge Limitations

### Not Supported in Edge Runtime
```ts
// These APIs are NOT available in Edge:
// - Node.js APIs (fs, path, etc.)
// - Native Node modules
// - eval() and new Function()
// - Some npm packages

// Use Web APIs instead:
// - fetch() ✓
// - Request/Response ✓
// - URL ✓
// - Headers ✓
// - TextEncoder/TextDecoder ✓
// - crypto.subtle ✓
```

### Fallback to Node.js
```ts
// app/api/node/route.ts
// This route uses Node.js runtime (default)
export const runtime = 'nodejs';

import fs from 'fs';
import path from 'path';

export async function GET() {
  // Can use Node.js APIs
  const filePath = path.join(process.cwd(), 'data', 'file.json');
  const data = fs.readFileSync(filePath, 'utf-8');

  return Response.json(JSON.parse(data));
}
```

## Performance Optimization

### Edge Caching Strategy
```ts
// app/api/products/route.ts
export const runtime = 'edge';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const category = searchParams.get('category');

  // Check edge cache
  const cacheKey = `products:${category}`;
  const cached = await kv.get(cacheKey);

  if (cached) {
    return Response.json(cached, {
      headers: { 'X-Cache': 'HIT' },
    });
  }

  // Fetch from origin
  const products = await fetchProducts(category);

  // Cache at edge
  await kv.set(cacheKey, products, { ex: 300 });

  return Response.json(products, {
    headers: { 'X-Cache': 'MISS' },
  });
}
```

## Best Practices

1. **Use Edge for latency-sensitive routes** - Auth, geo-routing
2. **Check library compatibility** - Not all npm packages work
3. **Use Web APIs** - Standard web platform APIs
4. **Cache aggressively** - Leverage edge caching
5. **Stream when possible** - Better perceived performance
6. **Fallback to Node.js** - For incompatible operations
