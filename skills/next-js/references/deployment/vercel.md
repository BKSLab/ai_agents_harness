---
name: nextjs-vercel
description: Deploying Next.js to Vercel
applies_to: nextjs
---

# Vercel Deployment

## Overview

Vercel is the platform from the creators of Next.js, providing
seamless deployment with zero configuration for Next.js applications.

## Quick Start

### Deploy with Git
```bash
# Connect your repository to Vercel
# Push to main branch triggers automatic deployment
git push origin main
```

### Deploy with CLI
```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel

# Deploy to production
vercel --prod
```

## Project Configuration

### vercel.json
```json
{
  "buildCommand": "npm run build",
  "outputDirectory": ".next",
  "framework": "nextjs",
  "regions": ["iad1"],
  "functions": {
    "app/api/**/*.ts": {
      "memory": 1024,
      "maxDuration": 10
    }
  },
  "headers": [
    {
      "source": "/api/(.*)",
      "headers": [
        { "key": "Access-Control-Allow-Origin", "value": "*" },
        { "key": "Access-Control-Allow-Methods", "value": "GET,POST,PUT,DELETE,OPTIONS" }
      ]
    }
  ],
  "rewrites": [
    {
      "source": "/api/proxy/:path*",
      "destination": "https://api.example.com/:path*"
    }
  ],
  "redirects": [
    {
      "source": "/old-page",
      "destination": "/new-page",
      "permanent": true
    }
  ]
}
```

## Environment Variables

### Setting Variables
```bash
# Via CLI
vercel env add DATABASE_URL production
vercel env add NEXT_PUBLIC_API_URL preview

# Pull to local
vercel env pull .env.local
```

### Environment Types
```
Production  - Live site
Preview     - PR deployments
Development - Local development
```

### Example .env Structure
```env
# .env.local (not committed)
DATABASE_URL=postgresql://...
NEXTAUTH_SECRET=your-secret

# .env (committed, non-sensitive)
NEXT_PUBLIC_APP_NAME=My App
```

## Build Configuration

### Custom Build Command
```json
{
  "buildCommand": "prisma generate && next build",
  "installCommand": "npm ci"
}
```

### Monorepo Setup
```json
{
  "framework": "nextjs",
  "installCommand": "npm install --prefix=apps/web",
  "buildCommand": "npm run build --prefix=apps/web",
  "outputDirectory": "apps/web/.next"
}
```

## Serverless Functions

### Function Configuration
```json
{
  "functions": {
    "app/api/heavy-task/route.ts": {
      "memory": 3008,
      "maxDuration": 60
    },
    "app/api/quick/route.ts": {
      "memory": 128,
      "maxDuration": 5
    }
  }
}
```

### Edge Functions
```ts
// app/api/edge/route.ts
export const runtime = 'edge';

export async function GET() {
  return new Response('Hello from Edge!', {
    headers: { 'content-type': 'text/plain' },
  });
}
```

## Caching Configuration

### Cache Headers
```ts
// app/api/cached/route.ts
export async function GET() {
  return new Response(JSON.stringify({ data: 'cached' }), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 's-maxage=86400, stale-while-revalidate',
    },
  });
}
```

### ISR Revalidation
```ts
// app/products/[id]/page.tsx
export const revalidate = 3600; // Revalidate every hour

export default async function ProductPage({ params }) {
  const product = await getProduct(params.id);
  return <ProductView product={product} />;
}
```

## Domain Configuration

### Custom Domain
```bash
# Add domain
vercel domains add example.com

# Verify domain
vercel domains verify example.com
```

### Subdomain Routing
```json
{
  "rewrites": [
    {
      "source": "/:path*",
      "has": [{ "type": "host", "value": "app.example.com" }],
      "destination": "/app/:path*"
    },
    {
      "source": "/:path*",
      "has": [{ "type": "host", "value": "api.example.com" }],
      "destination": "/api/:path*"
    }
  ]
}
```

## Analytics & Monitoring

### Enable Analytics
```tsx
// app/layout.tsx
import { Analytics } from '@vercel/analytics/react';
import { SpeedInsights } from '@vercel/speed-insights/next';

export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        {children}
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  );
}
```

### Web Vitals
```ts
// app/api/vitals/route.ts
export async function POST(request: Request) {
  const body = await request.json();

  // Send to analytics service
  await fetch('https://analytics.example.com/vitals', {
    method: 'POST',
    body: JSON.stringify(body),
  });

  return new Response(null, { status: 204 });
}
```

## Preview Deployments

### Protect Previews
```json
{
  "github": {
    "enabled": true,
    "silent": false
  },
  "public": false
}
```

### Preview Comments
```bash
# Enable PR comments for preview URLs
# Configure in Vercel Dashboard > Settings > Git
```

## CI/CD Integration

### GitHub Actions
```yaml
# .github/workflows/preview.yml
name: Vercel Preview Deployment

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Vercel CLI
        run: npm install -g vercel

      - name: Pull Vercel Environment
        run: vercel pull --yes --environment=preview --token=${{ secrets.VERCEL_TOKEN }}

      - name: Build Project
        run: vercel build --token=${{ secrets.VERCEL_TOKEN }}

      - name: Deploy to Vercel
        run: vercel deploy --prebuilt --token=${{ secrets.VERCEL_TOKEN }}
```

## Database Integration

### Vercel Postgres
```ts
// lib/db.ts
import { sql } from '@vercel/postgres';

export async function getUsers() {
  const { rows } = await sql`SELECT * FROM users`;
  return rows;
}
```

### Vercel KV (Redis)
```ts
// lib/kv.ts
import { kv } from '@vercel/kv';

export async function getCache(key: string) {
  return await kv.get(key);
}

export async function setCache(key: string, value: any, ttl = 3600) {
  await kv.set(key, value, { ex: ttl });
}
```

### Vercel Blob
```ts
// app/api/upload/route.ts
import { put } from '@vercel/blob';
import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  const form = await request.formData();
  const file = form.get('file') as File;

  const blob = await put(file.name, file, {
    access: 'public',
  });

  return NextResponse.json(blob);
}
```

## Best Practices

1. **Use environment variables** - Never commit secrets
2. **Enable preview deployments** - Test before production
3. **Configure caching** - Optimize performance
4. **Monitor with Analytics** - Track Web Vitals
5. **Use Edge when possible** - Lower latency
6. **Set proper regions** - Deploy close to users
