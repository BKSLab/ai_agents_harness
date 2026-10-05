---
name: nextjs-parallel-sequential
description: Parallel and sequential data fetching patterns
applies_to: nextjs
---

# Parallel and Sequential Data Fetching

## Overview

Choose between parallel and sequential fetching based on data dependencies.
Parallel fetching improves performance when data is independent.

## Parallel Fetching

### Using Promise.all
```tsx
// app/dashboard/page.tsx
async function getStats() {
  const res = await fetch('https://api.example.com/stats');
  return res.json();
}

async function getOrders() {
  const res = await fetch('https://api.example.com/orders');
  return res.json();
}

async function getNotifications() {
  const res = await fetch('https://api.example.com/notifications');
  return res.json();
}

export default async function DashboardPage() {
  // All requests start simultaneously
  const [stats, orders, notifications] = await Promise.all([
    getStats(),
    getOrders(),
    getNotifications(),
  ]);

  return (
    <div className="grid grid-cols-12 gap-6">
      <StatsCards stats={stats} />
      <OrdersList orders={orders} />
      <NotificationList notifications={notifications} />
    </div>
  );
}
```

### With Error Handling
```tsx
export default async function DashboardPage() {
  const results = await Promise.allSettled([
    getStats(),
    getOrders(),
    getNotifications(),
  ]);

  const [statsResult, ordersResult, notificationsResult] = results;

  return (
    <div className="grid grid-cols-12 gap-6">
      {statsResult.status === 'fulfilled' ? (
        <StatsCards stats={statsResult.value} />
      ) : (
        <ErrorCard message="Failed to load stats" />
      )}

      {ordersResult.status === 'fulfilled' ? (
        <OrdersList orders={ordersResult.value} />
      ) : (
        <ErrorCard message="Failed to load orders" />
      )}

      {notificationsResult.status === 'fulfilled' ? (
        <NotificationList notifications={notificationsResult.value} />
      ) : (
        <ErrorCard message="Failed to load notifications" />
      )}
    </div>
  );
}
```

## Sequential Fetching

### When Data Depends on Previous Result
```tsx
// app/products/[id]/page.tsx
export default async function ProductPage({
  params,
}: {
  params: { id: string };
}) {
  // First: Get the product
  const product = await getProduct(params.id);

  if (!product) {
    notFound();
  }

  // Second: Get related data based on product
  const [reviews, relatedProducts] = await Promise.all([
    getProductReviews(product.id),
    getRelatedProducts(product.categoryId, product.id),
  ]);

  return (
    <div>
      <ProductDetail product={product} />
      <Reviews reviews={reviews} />
      <RelatedProducts products={relatedProducts} />
    </div>
  );
}
```

### Waterfall Pattern
```tsx
// When each request depends on the previous
async function getOrderWithDetails(orderId: string) {
  // Step 1: Get order
  const order = await getOrder(orderId);

  // Step 2: Get user (needs order.userId)
  const user = await getUser(order.userId);

  // Step 3: Get payment (needs order.paymentId)
  const payment = await getPayment(order.paymentId);

  return { order, user, payment };
}
```

## Mixed Patterns

### Parallel Within Sequential
```tsx
export default async function UserProfilePage({
  params,
}: {
  params: { id: string };
}) {
  // Sequential: Need user first
  const user = await getUser(params.id);

  if (!user) {
    notFound();
  }

  // Parallel: These can run together once we have user
  const [posts, followers, following] = await Promise.all([
    getUserPosts(user.id),
    getUserFollowers(user.id),
    getUserFollowing(user.id),
  ]);

  return (
    <div>
      <UserHeader user={user} />
      <div className="grid grid-cols-3 gap-6">
        <PostsList posts={posts} />
        <FollowersList followers={followers} />
        <FollowingList following={following} />
      </div>
    </div>
  );
}
```

## Using Suspense for Parallel Streaming

### Independent Loading States
```tsx
// app/dashboard/page.tsx
import { Suspense } from 'react';

async function StatsSection() {
  const stats = await getStats();
  return <StatsCards stats={stats} />;
}

async function OrdersSection() {
  const orders = await getOrders();
  return <OrdersList orders={orders} />;
}

async function NotificationsSection() {
  const notifications = await getNotifications();
  return <NotificationList notifications={notifications} />;
}

export default function DashboardPage() {
  return (
    <div className="grid grid-cols-12 gap-6">
      {/* Each section loads independently */}
      <Suspense fallback={<StatsSkeleton />}>
        <StatsSection />
      </Suspense>

      <Suspense fallback={<OrdersSkeleton />}>
        <OrdersSection />
      </Suspense>

      <Suspense fallback={<NotificationsSkeleton />}>
        <NotificationsSection />
      </Suspense>
    </div>
  );
}
```

### Grouped Suspense
```tsx
export default function DashboardPage() {
  return (
    <div className="grid grid-cols-12 gap-6">
      {/* Main content loads together */}
      <Suspense fallback={<MainContentSkeleton />}>
        <div className="col-span-8">
          <StatsSection />
          <OrdersSection />
        </div>
      </Suspense>

      {/* Sidebar loads independently */}
      <Suspense fallback={<SidebarSkeleton />}>
        <div className="col-span-4">
          <NotificationsSection />
        </div>
      </Suspense>
    </div>
  );
}
```

## Database Queries

### Parallel with Prisma
```tsx
// app/products/page.tsx
export default async function ProductsPage({
  searchParams,
}: {
  searchParams: { category?: string };
}) {
  const where = searchParams.category
    ? { categoryId: searchParams.category, status: 'active' }
    : { status: 'active' };

  // Parallel database queries
  const [products, categories, total] = await Promise.all([
    db.product.findMany({
      where,
      include: { category: true },
      take: 20,
    }),
    db.category.findMany(),
    db.product.count({ where }),
  ]);

  return (
    <div>
      <CategoryFilter categories={categories} />
      <ProductList products={products} total={total} />
    </div>
  );
}
```

### Transaction for Related Data
```tsx
// When data consistency matters
async function getProductWithInventory(id: string) {
  return db.$transaction(async (tx) => {
    const product = await tx.product.findUnique({
      where: { id },
    });

    if (!product) return null;

    const inventory = await tx.inventory.findFirst({
      where: { productId: id },
    });

    return { product, inventory };
  });
}
```

## Decision Matrix

| Scenario | Pattern | Reason |
|----------|---------|--------|
| Independent data sources | Parallel (Promise.all) | Faster total time |
| Data depends on previous | Sequential | Can't parallelize |
| Mixed dependencies | Hybrid | Optimize what you can |
| Need independent loading | Suspense | Better UX |
| Need atomic data | Transaction | Data consistency |

## Best Practices

1. **Default to parallel** - Unless there's a dependency
2. **Use Promise.allSettled** - When partial success is acceptable
3. **Combine patterns** - Parallel within sequential chains
4. **Use Suspense** - For independent loading states
5. **Batch database queries** - Reduce round trips
6. **Profile performance** - Measure actual improvements
