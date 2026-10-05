---
name: nextjs-middleware
description: Next.js Middleware for request interception
applies_to: nextjs
---

# Middleware

## Overview

Middleware runs before a request is completed, allowing you to modify the response
by rewriting, redirecting, modifying headers, or responding directly.

## Basic Middleware

```tsx
// middleware.ts (in project root)
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  // Continue to the requested page
  return NextResponse.next();
}

// Configure which paths middleware runs on
export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public folder
     */
    '/((?!_next/static|_next/image|favicon.ico|.*\\..*|api).*)',
  ],
};
```

## Authentication Middleware

```tsx
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';

const publicPaths = ['/login', '/register', '/forgot-password'];
const authPaths = ['/login', '/register'];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Check if path is public
  const isPublicPath = publicPaths.some(path =>
    pathname.startsWith(path)
  );

  // Get session token
  const token = await getToken({
    req: request,
    secret: process.env.NEXTAUTH_SECRET,
  });

  // Redirect authenticated users away from auth pages
  if (token && authPaths.some(path => pathname.startsWith(path))) {
    return NextResponse.redirect(new URL('/dashboard', request.url));
  }

  // Redirect unauthenticated users to login
  if (!token && !isPublicPath) {
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

## Matcher Patterns

```tsx
export const config = {
  matcher: [
    // Match all paths
    '/(.*)',

    // Match specific paths
    '/dashboard/:path*',
    '/api/:path*',

    // Exclude static files
    '/((?!_next/static|_next/image|favicon.ico).*)',

    // Match with regex
    '/blog/:slug([a-z0-9-]+)',
  ],
};
```

## Conditional Middleware

### By Path
```tsx
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith('/api')) {
    // API-specific logic
    return handleApiRequest(request);
  }

  if (pathname.startsWith('/admin')) {
    // Admin-specific logic
    return handleAdminRequest(request);
  }

  return NextResponse.next();
}
```

### By Method
```tsx
export function middleware(request: NextRequest) {
  if (request.method === 'POST') {
    // Validate CSRF token
    const csrfToken = request.headers.get('x-csrf-token');
    if (!csrfToken) {
      return NextResponse.json(
        { error: 'Missing CSRF token' },
        { status: 403 }
      );
    }
  }

  return NextResponse.next();
}
```

## Modifying Responses

### Adding Headers
```tsx
export function middleware(request: NextRequest) {
  const response = NextResponse.next();

  // Add security headers
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('Referrer-Policy', 'origin-when-cross-origin');

  return response;
}
```

### Setting Cookies
```tsx
export function middleware(request: NextRequest) {
  const response = NextResponse.next();

  // Set a cookie
  response.cookies.set('visited', 'true', {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 24, // 1 day
  });

  return response;
}
```

## Rewrites and Redirects

### Rewrite (Same URL, Different Content)
```tsx
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // A/B testing - rewrite to different page
  if (pathname === '/pricing') {
    const variant = request.cookies.get('variant')?.value || 'a';
    return NextResponse.rewrite(
      new URL(`/pricing-${variant}`, request.url)
    );
  }

  return NextResponse.next();
}
```

### Redirect
```tsx
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Redirect old URLs
  const redirects: Record<string, string> = {
    '/old-page': '/new-page',
    '/legacy': '/modern',
  };

  if (redirects[pathname]) {
    return NextResponse.redirect(
      new URL(redirects[pathname], request.url)
    );
  }

  return NextResponse.next();
}
```

## Rate Limiting

```tsx
// Simple in-memory rate limiting (use Redis in production)
const rateLimit = new Map<string, { count: number; timestamp: number }>();

export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname.startsWith('/api')) {
    const ip = request.ip ?? 'anonymous';
    const now = Date.now();
    const windowMs = 60 * 1000; // 1 minute
    const maxRequests = 100;

    const current = rateLimit.get(ip);

    if (current) {
      if (now - current.timestamp < windowMs) {
        if (current.count >= maxRequests) {
          return NextResponse.json(
            { error: 'Too many requests' },
            { status: 429 }
          );
        }
        current.count++;
      } else {
        current.count = 1;
        current.timestamp = now;
      }
    } else {
      rateLimit.set(ip, { count: 1, timestamp: now });
    }
  }

  return NextResponse.next();
}
```

## Geolocation

```tsx
export function middleware(request: NextRequest) {
  const country = request.geo?.country || 'US';
  const city = request.geo?.city || 'Unknown';

  const response = NextResponse.next();

  // Pass geo data to the page
  response.headers.set('x-user-country', country);
  response.headers.set('x-user-city', city);

  // Redirect based on country
  if (country === 'DE' && !request.nextUrl.pathname.startsWith('/de')) {
    return NextResponse.redirect(new URL('/de', request.url));
  }

  return response;
}
```

## Best Practices

1. **Keep middleware fast** - Runs on every matched request
2. **Use matcher** - Only run on necessary paths
3. **Don't access database** - Use Edge-compatible solutions
4. **Handle errors** - Middleware errors affect all requests
5. **Test thoroughly** - Middleware affects entire application
6. **Use environment variables** - For secrets and configuration
