---
name: nextjs-server-actions
description: Server Actions for mutations in Next.js
applies_to: nextjs
---

# Server Actions

## Overview

Server Actions are async functions that run on the server.
They can be called from Client Components for form handling and mutations.

## Basic Server Action

### Define Action
```tsx
// lib/actions/products.ts
"use server";

import { revalidatePath } from 'next/cache';
import { z } from 'zod';
import { db } from '@/lib/db';
import { auth } from '@/lib/auth';

const createProductSchema = z.object({
  name: z.string().min(2).max(100),
  description: z.string().max(1000).optional(),
  price: z.coerce.number().min(0),
  categoryId: z.string().uuid(),
});

export async function createProduct(formData: FormData) {
  // Auth check
  const session = await auth();
  if (!session?.user) {
    throw new Error('Unauthorized');
  }

  // Validate
  const validatedFields = createProductSchema.safeParse({
    name: formData.get('name'),
    description: formData.get('description'),
    price: formData.get('price'),
    categoryId: formData.get('categoryId'),
  });

  if (!validatedFields.success) {
    return { error: 'Invalid fields' };
  }

  // Create
  await db.product.create({
    data: {
      ...validatedFields.data,
      userId: session.user.id,
    },
  });

  // Revalidate
  revalidatePath('/products');
}
```

### Use in Form
```tsx
// app/products/new/page.tsx
import { createProduct } from '@/lib/actions/products';

export default function NewProductPage() {
  return (
    <form action={createProduct}>
      <input name="name" required />
      <textarea name="description" />
      <input name="price" type="number" step="0.01" required />
      <button type="submit">Create</button>
    </form>
  );
}
```

## With useFormState

### Action with State
```tsx
// lib/actions/products.ts
"use server";

export type ProductActionState = {
  success: boolean;
  message: string;
  errors?: Record<string, string[]>;
};

export async function createProduct(
  prevState: ProductActionState,
  formData: FormData
): Promise<ProductActionState> {
  const session = await auth();
  if (!session?.user) {
    return { success: false, message: 'Unauthorized' };
  }

  const validatedFields = createProductSchema.safeParse({
    name: formData.get('name'),
    description: formData.get('description'),
    price: formData.get('price'),
    categoryId: formData.get('categoryId'),
  });

  if (!validatedFields.success) {
    return {
      success: false,
      message: 'Validation failed',
      errors: validatedFields.error.flatten().fieldErrors,
    };
  }

  try {
    await db.product.create({
      data: {
        ...validatedFields.data,
        userId: session.user.id,
      },
    });

    revalidatePath('/products');
    return { success: true, message: 'Product created successfully' };
  } catch (error) {
    return { success: false, message: 'Failed to create product' };
  }
}
```

### Form Component
```tsx
// components/product-form.tsx
"use client";

import { useFormState, useFormStatus } from 'react-dom';
import { createProduct, type ProductActionState } from '@/lib/actions/products';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const initialState: ProductActionState = {
  success: false,
  message: '',
};

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending}>
      {pending ? 'Creating...' : 'Create Product'}
    </Button>
  );
}

export function ProductForm() {
  const [state, formAction] = useFormState(createProduct, initialState);

  return (
    <form action={formAction} className="space-y-4">
      {state.message && (
        <div className={state.success ? 'text-green-600' : 'text-red-600'}>
          {state.message}
        </div>
      )}

      <div>
        <Input name="name" placeholder="Product name" required />
        {state.errors?.name && (
          <p className="text-sm text-red-500">{state.errors.name[0]}</p>
        )}
      </div>

      <div>
        <Input name="price" type="number" step="0.01" placeholder="Price" required />
        {state.errors?.price && (
          <p className="text-sm text-red-500">{state.errors.price[0]}</p>
        )}
      </div>

      <SubmitButton />
    </form>
  );
}
```

## Bound Arguments

### Update with ID
```tsx
// lib/actions/products.ts
export async function updateProduct(
  id: string,
  prevState: ProductActionState,
  formData: FormData
): Promise<ProductActionState> {
  // ...validation and update logic
}

// components/edit-product-form.tsx
"use client";

import { updateProduct } from '@/lib/actions/products';

export function EditProductForm({ product }: { product: Product }) {
  const updateProductWithId = updateProduct.bind(null, product.id);
  const [state, formAction] = useFormState(updateProductWithId, initialState);

  return (
    <form action={formAction}>
      <input name="name" defaultValue={product.name} />
      <button type="submit">Update</button>
    </form>
  );
}
```

## Non-Form Actions

### Direct Call
```tsx
// lib/actions/products.ts
export async function deleteProduct(id: string) {
  const session = await auth();
  if (!session?.user) {
    throw new Error('Unauthorized');
  }

  await db.product.delete({ where: { id } });
  revalidatePath('/products');
}

// components/delete-button.tsx
"use client";

import { useTransition } from 'react';
import { deleteProduct } from '@/lib/actions/products';

export function DeleteButton({ id }: { id: string }) {
  const [isPending, startTransition] = useTransition();

  const handleDelete = () => {
    startTransition(async () => {
      await deleteProduct(id);
    });
  };

  return (
    <button onClick={handleDelete} disabled={isPending}>
      {isPending ? 'Deleting...' : 'Delete'}
    </button>
  );
}
```

### Toggle Action
```tsx
// lib/actions/favorites.ts
export async function toggleFavorite(productId: string) {
  const session = await auth();
  if (!session?.user) {
    throw new Error('Unauthorized');
  }

  const existing = await db.favorite.findUnique({
    where: {
      userId_productId: {
        userId: session.user.id,
        productId,
      },
    },
  });

  if (existing) {
    await db.favorite.delete({ where: { id: existing.id } });
  } else {
    await db.favorite.create({
      data: {
        userId: session.user.id,
        productId,
      },
    });
  }

  revalidatePath(`/products/${productId}`);
}
```

## Optimistic Updates

```tsx
// components/like-button.tsx
"use client";

import { useOptimistic, useTransition } from 'react';
import { toggleLike } from '@/lib/actions/likes';

export function LikeButton({
  postId,
  initialLiked,
  initialCount,
}: {
  postId: string;
  initialLiked: boolean;
  initialCount: number;
}) {
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
    <button onClick={handleClick} disabled={isPending}>
      {optimisticState.liked ? '❤️' : '🤍'} {optimisticState.count}
    </button>
  );
}
```

## Best Practices

1. **Always validate** - Use Zod for input validation
2. **Check auth** - Verify user is authenticated
3. **Check ownership** - Verify user owns the resource
4. **Handle errors** - Return meaningful error messages
5. **Revalidate** - Update cache after mutations
6. **Type actions** - Define state types for useFormState
