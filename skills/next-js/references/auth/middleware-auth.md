---
name: nextjs-middleware-auth
description: Authentication middleware in Next.js
applies_to: nextjs
---

# Authentication Middleware

## Overview

Middleware provides a central place to handle authentication,
protecting routes before they're rendered.

## Basic Auth Middleware

```tsx
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';

// Routes that don't require authentication
const publicRoutes = ['/', '/login', '/register', '/forgot-password'];

// Routes that authenticated users shouldn't access
const authRoutes = ['/login', '/register'];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Get the token from the session
  const token = await getToken({
    req: request,
    secret: process.env.NEXTAUTH_SECRET,
  });

  const isPublicRoute = publicRoutes.includes(pathname);
  const isAuthRoute = authRoutes.includes(pathname);

  // Redirect authenticated users away from auth pages
  if (token && isAuthRoute) {
    return NextResponse.redirect(new URL('/dashboard', request.url));
  }

  // Redirect unauthenticated users to login
  if (!token && !isPublicRoute) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('callbackUrl', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};
```

## Role-Based Access

```tsx
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';

const roleRoutes = {
  admin: ['/admin', '/admin/:path*'],
  moderator: ['/mod', '/mod/:path*'],
};

function matchesPattern(pathname: string, pattern: string): boolean {
  if (pattern.endsWith(':path*')) {
    const base = pattern.replace(':path*', '');
    return pathname.startsWith(base);
  }
  return pathname === pattern;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const token = await getToken({
    req: request,
    secret: process.env.NEXTAUTH_SECRET,
  });

  // Check admin routes
  const isAdminRoute = roleRoutes.admin.some(pattern =>
    matchesPattern(pathname, pattern)
  );

  if (isAdminRoute) {
    if (!token) {
      return NextResponse.redirect(new URL('/login', request.url));
    }

    if (token.role !== 'admin') {
      return NextResponse.redirect(new URL('/unauthorized', request.url));
    }
  }

  // Check moderator routes
  const isModRoute = roleRoutes.moderator.some(pattern =>
    matchesPattern(pathname, pattern)
  );

  if (isModRoute) {
    if (!token) {
      return NextResponse.redirect(new URL('/login', request.url));
    }

    if (!['admin', 'moderator'].includes(token.role as string)) {
      return NextResponse.redirect(new URL('/unauthorized', request.url));
    }
  }

  return NextResponse.next();
}
```

## API Route Protection

```tsx
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Protect API routes
  if (pathname.startsWith('/api')) {
    // Skip auth endpoints
    if (pathname.startsWith('/api/auth')) {
      return NextResponse.next();
    }

    // Skip public API endpoints
    const publicApiRoutes = ['/api/products', '/api/categories'];
    if (publicApiRoutes.some(route => pathname.startsWith(route))) {
      if (request.method === 'GET') {
        return NextResponse.next();
      }
    }

    // Require auth for all other API calls
    const token = await getToken({
      req: request,
      secret: process.env.NEXTAUTH_SECRET,
    });

    if (!token) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      );
    }
  }

  return NextResponse.next();
}
```

## With Custom Claims

```tsx
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';

interface CustomToken {
  id: string;
  email: string;
  role: 'user' | 'admin' | 'moderator';
  permissions: string[];
  organizationId?: string;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const token = await getToken({
    req: request,
    secret: process.env.NEXTAUTH_SECRET,
  }) as CustomToken | null;

  // Organization-specific routes
  if (pathname.startsWith('/org/')) {
    if (!token) {
      return NextResponse.redirect(new URL('/login', request.url));
    }

    const orgId = pathname.split('/')[2];

    if (token.organizationId !== orgId) {
      return NextResponse.redirect(new URL('/dashboard', request.url));
    }
  }

  // Permission-based routes
  if (pathname.startsWith('/settings/billing')) {
    if (!token?.permissions?.includes('billing:manage')) {
      return NextResponse.redirect(new URL('/settings', request.url));
    }
  }

  return NextResponse.next();
}
```

## Multi-Tenant Middleware

```tsx
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';

export async function middleware(request: NextRequest) {
  const hostname = request.headers.get('host') || '';
  const { pathname } = request.nextUrl;

  // Extract tenant from subdomain
  const subdomain = hostname.split('.')[0];
  const isMainDomain = subdomain === 'www' || subdomain === 'app';

  if (!isMainDomain) {
    // Tenant-specific routes
    const token = await getToken({
      req: request,
      secret: process.env.NEXTAUTH_SECRET,
    });

    if (!token) {
      return NextResponse.redirect(
        new URL(`/login?tenant=${subdomain}`, request.url)
      );
    }

    // Verify user belongs to tenant
    if (token.tenantId !== subdomain) {
      return NextResponse.redirect(new URL('/unauthorized', request.url));
    }
  }

  return NextResponse.next();
}
```

## Combining with Rate Limiting

```tsx
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';

// Simple in-memory rate limit (use Redis in production)
const rateLimit = new Map<string, { count: number; timestamp: number }>();

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Rate limit login attempts
  if (pathname === '/api/auth/callback/credentials' && request.method === 'POST') {
    const ip = request.ip ?? 'anonymous';
    const now = Date.now();
    const window = 60 * 1000; // 1 minute
    const maxAttempts = 5;

    const record = rateLimit.get(ip);

    if (record) {
      if (now - record.timestamp < window) {
        if (record.count >= maxAttempts) {
          return NextResponse.json(
            { error: 'Too many login attempts. Please try again later.' },
            { status: 429 }
          );
        }
        record.count++;
      } else {
        record.count = 1;
        record.timestamp = now;
      }
    } else {
      rateLimit.set(ip, { count: 1, timestamp: now });
    }
  }

  // Continue with auth check
  const token = await getToken({
    req: request,
    secret: process.env.NEXTAUTH_SECRET,
  });

  // ... rest of auth logic

  return NextResponse.next();
}
```

## Best Practices

1. **Keep middleware fast** - Runs on every request
2. **Use JWT strategy** - Enables edge middleware
3. **Handle edge cases** - API routes, public routes
4. **Add rate limiting** - Protect auth endpoints
5. **Use matcher** - Only run on necessary paths
6. **Test thoroughly** - Auth bugs affect all users
