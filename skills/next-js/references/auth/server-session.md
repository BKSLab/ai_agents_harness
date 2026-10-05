---
name: nextjs-server-session
description: Server-side session handling in Next.js
applies_to: nextjs
---

# Server-Side Session Handling

## Overview

Access and manage user sessions in Server Components, Server Actions,
and Route Handlers using NextAuth.js v5.

## Getting Session in Server Components

### Basic Usage
```tsx
// app/dashboard/page.tsx
import { auth } from '@/lib/auth';
import { redirect } from 'next/navigation';

export default async function DashboardPage() {
  const session = await auth();

  if (!session?.user) {
    redirect('/login');
  }

  return (
    <div>
      <h1>Welcome, {session.user.name}</h1>
      <p>Email: {session.user.email}</p>
    </div>
  );
}
```

### With User Data
```tsx
// app/profile/page.tsx
import { auth } from '@/lib/auth';
import { redirect } from 'next/navigation';
import { db } from '@/lib/db';

export default async function ProfilePage() {
  const session = await auth();

  if (!session?.user) {
    redirect('/login');
  }

  // Fetch additional user data
  const user = await db.user.findUnique({
    where: { id: session.user.id },
    include: {
      profile: true,
      settings: true,
    },
  });

  return (
    <div>
      <ProfileHeader user={user} />
      <ProfileSettings settings={user?.settings} />
    </div>
  );
}
```

## Session in Server Actions

```tsx
// lib/actions/profile.ts
"use server";

import { auth } from '@/lib/auth';
import { revalidatePath } from 'next/cache';
import { db } from '@/lib/db';
import { z } from 'zod';

const updateProfileSchema = z.object({
  name: z.string().min(2).max(50),
  bio: z.string().max(500).optional(),
});

export async function updateProfile(formData: FormData) {
  const session = await auth();

  if (!session?.user) {
    return { error: 'Unauthorized' };
  }

  const validated = updateProfileSchema.safeParse({
    name: formData.get('name'),
    bio: formData.get('bio'),
  });

  if (!validated.success) {
    return { error: 'Invalid data' };
  }

  await db.user.update({
    where: { id: session.user.id },
    data: validated.data,
  });

  revalidatePath('/profile');
  return { success: true };
}
```

## Session in Route Handlers

```tsx
// app/api/user/route.ts
import { NextResponse } from 'next/server';
import { auth } from '@/lib/auth';
import { db } from '@/lib/db';

export async function GET() {
  const session = await auth();

  if (!session?.user) {
    return NextResponse.json(
      { error: 'Unauthorized' },
      { status: 401 }
    );
  }

  const user = await db.user.findUnique({
    where: { id: session.user.id },
    select: {
      id: true,
      name: true,
      email: true,
      image: true,
      createdAt: true,
    },
  });

  return NextResponse.json(user);
}

export async function PATCH(request: Request) {
  const session = await auth();

  if (!session?.user) {
    return NextResponse.json(
      { error: 'Unauthorized' },
      { status: 401 }
    );
  }

  const body = await request.json();

  const user = await db.user.update({
    where: { id: session.user.id },
    data: { name: body.name },
  });

  return NextResponse.json(user);
}
```

## Authorization Helpers

```tsx
// lib/auth-utils.ts
import { auth } from '@/lib/auth';
import { redirect } from 'next/navigation';
import { db } from '@/lib/db';

export async function requireAuth() {
  const session = await auth();

  if (!session?.user) {
    redirect('/login');
  }

  return session;
}

export async function requireAdmin() {
  const session = await auth();

  if (!session?.user) {
    redirect('/login');
  }

  const user = await db.user.findUnique({
    where: { id: session.user.id },
    select: { role: true },
  });

  if (user?.role !== 'admin') {
    redirect('/unauthorized');
  }

  return session;
}

export async function getCurrentUser() {
  const session = await auth();

  if (!session?.user) {
    return null;
  }

  return db.user.findUnique({
    where: { id: session.user.id },
  });
}

export async function checkOwnership(resourceUserId: string) {
  const session = await auth();

  if (!session?.user) {
    return false;
  }

  return session.user.id === resourceUserId;
}
```

### Using Helpers
```tsx
// app/admin/page.tsx
import { requireAdmin } from '@/lib/auth-utils';

export default async function AdminPage() {
  const session = await requireAdmin();

  return (
    <div>
      <h1>Admin Dashboard</h1>
    </div>
  );
}

// app/products/[id]/edit/page.tsx
import { requireAuth, checkOwnership } from '@/lib/auth-utils';
import { notFound, redirect } from 'next/navigation';
import { db } from '@/lib/db';

export default async function EditProductPage({
  params,
}: {
  params: { id: string };
}) {
  await requireAuth();

  const product = await db.product.findUnique({
    where: { id: params.id },
  });

  if (!product) {
    notFound();
  }

  const isOwner = await checkOwnership(product.userId);

  if (!isOwner) {
    redirect('/products');
  }

  return <ProductEditForm product={product} />;
}
```

## Session Data in Layout

```tsx
// app/(dashboard)/layout.tsx
import { auth } from '@/lib/auth';
import { redirect } from 'next/navigation';
import { Sidebar } from '@/components/sidebar';
import { Header } from '@/components/header';

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();

  if (!session?.user) {
    redirect('/login');
  }

  return (
    <div className="flex h-screen">
      <Sidebar user={session.user} />
      <div className="flex-1 flex flex-col">
        <Header user={session.user} />
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
```

## Session with Context

```tsx
// components/user-provider.tsx
"use client";

import { createContext, useContext } from 'react';
import { Session } from 'next-auth';

const UserContext = createContext<Session['user'] | null>(null);

export function UserProvider({
  user,
  children,
}: {
  user: Session['user'];
  children: React.ReactNode;
}) {
  return (
    <UserContext.Provider value={user}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  const user = useContext(UserContext);
  if (!user) {
    throw new Error('useUser must be used within UserProvider');
  }
  return user;
}

// app/(dashboard)/layout.tsx
import { auth } from '@/lib/auth';
import { redirect } from 'next/navigation';
import { UserProvider } from '@/components/user-provider';

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();

  if (!session?.user) {
    redirect('/login');
  }

  return (
    <UserProvider user={session.user}>
      {children}
    </UserProvider>
  );
}
```

## Best Practices

1. **Create auth helpers** - Reusable auth functions
2. **Handle redirects** - Use redirect() for auth failures
3. **Check ownership** - Verify resource ownership
4. **Fetch user data separately** - Session is minimal
5. **Use layouts for auth** - Check once, protect children
6. **Type sessions** - Extend NextAuth types
