---
name: nextjs-css-modules
description: CSS Modules patterns in Next.js
applies_to: nextjs
---

# CSS Modules in Next.js

## Overview

CSS Modules provide locally scoped CSS by default, preventing class name collisions.
Files use `.module.css` extension.

## Basic Usage

### Component with CSS Module
```tsx
// components/button/button.tsx
import styles from './button.module.css';

interface ButtonProps {
  children: React.ReactNode;
  variant?: 'primary' | 'secondary';
  size?: 'sm' | 'md' | 'lg';
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
}: ButtonProps) {
  return (
    <button
      className={`
        ${styles.button}
        ${styles[variant]}
        ${styles[size]}
      `}
    >
      {children}
    </button>
  );
}
```

```css
/* components/button/button.module.css */
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.375rem;
  font-weight: 500;
  transition: all 0.2s;
}

.button:focus {
  outline: none;
  ring: 2px solid var(--ring-color);
}

.button:disabled {
  opacity: 0.5;
  pointer-events: none;
}

/* Variants */
.primary {
  background-color: var(--primary);
  color: var(--primary-foreground);
}

.primary:hover {
  background-color: var(--primary-hover);
}

.secondary {
  background-color: var(--secondary);
  color: var(--secondary-foreground);
}

.secondary:hover {
  background-color: var(--secondary-hover);
}

/* Sizes */
.sm {
  height: 2rem;
  padding: 0 0.75rem;
  font-size: 0.875rem;
}

.md {
  height: 2.5rem;
  padding: 0 1rem;
  font-size: 1rem;
}

.lg {
  height: 3rem;
  padding: 0 1.5rem;
  font-size: 1.125rem;
}
```

## Composing Classes

### Multiple Class Names
```tsx
// Using clsx or classnames
import clsx from 'clsx';
import styles from './card.module.css';

interface CardProps {
  children: React.ReactNode;
  elevated?: boolean;
  interactive?: boolean;
}

export function Card({ children, elevated, interactive }: CardProps) {
  return (
    <div
      className={clsx(
        styles.card,
        elevated && styles.elevated,
        interactive && styles.interactive
      )}
    >
      {children}
    </div>
  );
}
```

```css
/* components/card/card.module.css */
.card {
  border-radius: 0.5rem;
  border: 1px solid var(--border);
  background-color: var(--card);
  padding: 1.5rem;
}

.elevated {
  box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
}

.interactive {
  cursor: pointer;
  transition: all 0.2s;
}

.interactive:hover {
  border-color: var(--border-hover);
  box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
}
```

## Composition (composes)

```css
/* components/alert/alert.module.css */
.base {
  padding: 1rem;
  border-radius: 0.5rem;
  border: 1px solid;
}

.info {
  composes: base;
  background-color: var(--info-bg);
  border-color: var(--info-border);
  color: var(--info-text);
}

.warning {
  composes: base;
  background-color: var(--warning-bg);
  border-color: var(--warning-border);
  color: var(--warning-text);
}

.error {
  composes: base;
  background-color: var(--error-bg);
  border-color: var(--error-border);
  color: var(--error-text);
}

.success {
  composes: base;
  background-color: var(--success-bg);
  border-color: var(--success-border);
  color: var(--success-text);
}
```

```tsx
// components/alert/alert.tsx
import styles from './alert.module.css';

type AlertVariant = 'info' | 'warning' | 'error' | 'success';

interface AlertProps {
  children: React.ReactNode;
  variant?: AlertVariant;
}

export function Alert({ children, variant = 'info' }: AlertProps) {
  return (
    <div className={styles[variant]}>
      {children}
    </div>
  );
}
```

## Global and Local Mixing

```css
/* components/layout/layout.module.css */
.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1rem;
}

/* Use :global() for global classes */
.container :global(.prose) {
  max-width: none;
}

/* Or define global classes */
:global(.sr-only) {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
```

## With CSS Variables

```css
/* app/globals.css */
:root {
  --primary: #3b82f6;
  --primary-hover: #2563eb;
  --primary-foreground: #ffffff;
  --secondary: #f1f5f9;
  --secondary-hover: #e2e8f0;
  --secondary-foreground: #0f172a;
  --border: #e2e8f0;
  --card: #ffffff;
}

.dark {
  --primary: #60a5fa;
  --primary-hover: #93c5fd;
  --primary-foreground: #0f172a;
  --secondary: #1e293b;
  --secondary-hover: #334155;
  --secondary-foreground: #f8fafc;
  --border: #334155;
  --card: #0f172a;
}
```

## Responsive Styles

```css
/* components/grid/grid.module.css */
.grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: 1fr;
}

@media (min-width: 640px) {
  .grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 768px) {
  .grid {
    grid-template-columns: repeat(3, 1fr);
    gap: 1.5rem;
  }
}

@media (min-width: 1024px) {
  .grid {
    grid-template-columns: repeat(4, 1fr);
  }
}
```

## Combined with Tailwind

```tsx
// Use CSS Modules for complex styles, Tailwind for utilities
import styles from './complex-component.module.css';

export function ComplexComponent() {
  return (
    <div className={`${styles.wrapper} p-4 md:p-6`}>
      <div className={`${styles.animation} flex items-center gap-4`}>
        {/* content */}
      </div>
    </div>
  );
}
```

```css
/* complex-component.module.css */
.wrapper {
  /* Complex animations or styles that are verbose in Tailwind */
}

.animation {
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

## Best Practices

1. **Use for complex styles** - Animations, pseudo-elements
2. **Name files consistently** - `component.module.css`
3. **Use CSS variables** - Easier theming
4. **Use clsx** - Clean class composition
5. **Combine with Tailwind** - Best of both worlds
6. **Keep modules small** - One component per module
