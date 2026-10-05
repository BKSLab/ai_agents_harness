---
name: nextjs-client-components
description: React Client Components in Next.js
applies_to: nextjs
---

# Client Components

## Overview

Client Components enable interactivity using React hooks, event handlers, and browser APIs.
Add `"use client"` directive at the top of the file.

## When to Use Client Components

| Need | Use |
|------|-----|
| Event listeners (onClick, onChange) | Client |
| Hooks (useState, useEffect, useContext) | Client |
| Browser APIs (localStorage, window) | Client |
| Custom hooks with state | Client |
| Class components | Client |
| Static display, data fetching | Server |

## Basic Client Component

```tsx
// components/counter.tsx
"use client";

import { useState } from 'react';
import { Button } from '@/components/ui/button';

export function Counter() {
  const [count, setCount] = useState(0);

  return (
    <div className="flex items-center gap-4">
      <Button onClick={() => setCount((c) => c - 1)}>-</Button>
      <span className="text-2xl font-bold">{count}</span>
      <Button onClick={() => setCount((c) => c + 1)}>+</Button>
    </div>
  );
}
```

## Form Handling

### Basic Form
```tsx
// components/login-form.tsx
"use client";

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export function LoginForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      // Handle login
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </div>
      <div>
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>
      <Button type="submit" disabled={isLoading} className="w-full">
        {isLoading ? 'Loading...' : 'Sign In'}
      </Button>
    </form>
  );
}
```

### Form with Server Action
```tsx
// components/contact-form.tsx
"use client";

import { useFormState, useFormStatus } from 'react-dom';
import { submitContact } from '@/lib/actions/contact';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Loader2 } from 'lucide-react';

function SubmitButton() {
  const { pending } = useFormStatus();

  return (
    <Button type="submit" disabled={pending}>
      {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
      {pending ? 'Sending...' : 'Send Message'}
    </Button>
  );
}

export function ContactForm() {
  const [state, formAction] = useFormState(submitContact, {
    success: false,
    message: '',
  });

  return (
    <form action={formAction} className="space-y-4">
      {state.message && (
        <div className={state.success ? 'text-green-600' : 'text-red-600'}>
          {state.message}
        </div>
      )}
      <Input name="email" type="email" placeholder="Email" required />
      <Input name="message" placeholder="Message" required />
      <SubmitButton />
    </form>
  );
}
```

## Navigation Hooks

```tsx
// components/search-input.tsx
"use client";

import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { useTransition } from 'react';
import { Input } from '@/components/ui/input';

export function SearchInput() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  const handleSearch = (term: string) => {
    const params = new URLSearchParams(searchParams);

    if (term) {
      params.set('q', term);
    } else {
      params.delete('q');
    }

    startTransition(() => {
      router.push(`${pathname}?${params.toString()}`);
    });
  };

  return (
    <div className="relative">
      <Input
        type="search"
        placeholder="Search..."
        defaultValue={searchParams.get('q') ?? ''}
        onChange={(e) => handleSearch(e.target.value)}
        className={isPending ? 'opacity-50' : ''}
      />
    </div>
  );
}
```

## Optimistic Updates

```tsx
// components/like-button.tsx
"use client";

import { useOptimistic, useTransition } from 'react';
import { toggleLike } from '@/lib/actions/likes';
import { Heart } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LikeButtonProps {
  postId: string;
  initialLiked: boolean;
  initialCount: number;
}

export function LikeButton({ postId, initialLiked, initialCount }: LikeButtonProps) {
  const [isPending, startTransition] = useTransition();

  const [optimisticState, addOptimistic] = useOptimistic(
    { liked: initialLiked, count: initialCount },
    (state, newLiked: boolean) => ({
      liked: newLiked,
      count: newLiked ? state.count + 1 : state.count - 1,
    })
  );

  const handleClick = () => {
    startTransition(async () => {
      addOptimistic(!optimisticState.liked);
      await toggleLike(postId);
    });
  };

  return (
    <button
      onClick={handleClick}
      disabled={isPending}
      className="flex items-center gap-2"
    >
      <Heart
        className={cn(
          'h-5 w-5 transition-colors',
          optimisticState.liked && 'fill-red-500 text-red-500'
        )}
      />
      <span>{optimisticState.count}</span>
    </button>
  );
}
```

## Browser APIs

```tsx
// components/theme-toggle.tsx
"use client";

import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function ThemeToggle() {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem('theme') as 'light' | 'dark' | null;
    if (stored) {
      setTheme(stored);
      document.documentElement.classList.toggle('dark', stored === 'dark');
    }
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
    document.documentElement.classList.toggle('dark', newTheme === 'dark');
  };

  // Prevent hydration mismatch
  if (!mounted) {
    return <Button variant="ghost" size="icon" disabled />;
  }

  return (
    <Button variant="ghost" size="icon" onClick={toggleTheme}>
      {theme === 'light' ? (
        <Moon className="h-5 w-5" />
      ) : (
        <Sun className="h-5 w-5" />
      )}
    </Button>
  );
}
```

## Context Providers

```tsx
// components/providers.tsx
"use client";

import { ThemeProvider } from 'next-themes';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}
```

## Composition with Server Components

```tsx
// app/products/page.tsx (Server Component)
import { ProductFilters } from './product-filters'; // Client
import { ProductList } from './product-list';       // Server

export default async function ProductsPage() {
  const products = await getProducts();
  const categories = await getCategories();

  return (
    <div>
      {/* Interactive filters - Client Component */}
      <ProductFilters categories={categories} />

      {/* Static list - Server Component */}
      <ProductList products={products} />
    </div>
  );
}
```

## Best Practices

1. **Keep "use client" at the boundary** - Push client components down
2. **Pass serializable props** - Server → Client props must be serializable
3. **Handle hydration** - Use mounted state for browser-only features
4. **Minimize client components** - Only use when interactivity is needed
5. **Use Server Actions** - Instead of API routes for mutations
6. **Avoid prop drilling** - Use context or Server Components
