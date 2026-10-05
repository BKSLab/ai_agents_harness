---
name: nextjs-tailwind-css
description: Tailwind CSS in Next.js
applies_to: nextjs
---

# Tailwind CSS in Next.js

## Setup

### Installation
```bash
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

### Configuration
```js
// tailwind.config.ts
import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
};

export default config;
```

### Global Styles
```css
/* app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --radius: 0.5rem;
  }

  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --card: 222.2 84% 4.9%;
    --card-foreground: 210 40% 98%;
    --primary: 210 40% 98%;
    --primary-foreground: 222.2 47.4% 11.2%;
    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 210 40% 98%;
    --border: 217.2 32.6% 17.5%;
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

## cn Utility

```ts
// lib/utils.ts
import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

Usage:
```tsx
import { cn } from '@/lib/utils';

function Button({ className, variant, ...props }) {
  return (
    <button
      className={cn(
        'px-4 py-2 rounded-md font-medium',
        variant === 'primary' && 'bg-primary text-primary-foreground',
        variant === 'secondary' && 'bg-secondary text-secondary-foreground',
        className
      )}
      {...props}
    />
  );
}
```

## Common Patterns

### Responsive Design
```tsx
<div className="
  grid
  grid-cols-1
  sm:grid-cols-2
  md:grid-cols-3
  lg:grid-cols-4
  gap-4 md:gap-6
">
  {/* items */}
</div>
```

### Dark Mode
```tsx
<div className="bg-white dark:bg-gray-900 text-gray-900 dark:text-white">
  <p className="text-gray-600 dark:text-gray-400">
    Muted text
  </p>
</div>
```

### Hover and Focus States
```tsx
<button className="
  bg-primary
  hover:bg-primary/90
  focus:outline-none
  focus:ring-2
  focus:ring-primary
  focus:ring-offset-2
  transition-colors
">
  Click me
</button>
```

### Container
```tsx
<div className="container mx-auto px-4 md:px-6 lg:px-8">
  {/* content */}
</div>
```

### Card Pattern
```tsx
<div className="
  rounded-lg
  border
  bg-card
  text-card-foreground
  shadow-sm
  p-6
">
  <h3 className="text-lg font-semibold">Card Title</h3>
  <p className="text-muted-foreground">Card content</p>
</div>
```

### Form Layout
```tsx
<form className="space-y-4">
  <div className="space-y-2">
    <label className="text-sm font-medium">Email</label>
    <input
      type="email"
      className="
        w-full
        px-3 py-2
        border rounded-md
        bg-background
        focus:outline-none
        focus:ring-2
        focus:ring-primary
      "
    />
  </div>

  <button
    type="submit"
    className="
      w-full
      px-4 py-2
      bg-primary
      text-primary-foreground
      rounded-md
      font-medium
      hover:bg-primary/90
    "
  >
    Submit
  </button>
</form>
```

## Component Variants with CVA

```tsx
// components/ui/button.tsx
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-md px-3',
        lg: 'h-11 rounded-md px-8',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

function Button({ className, variant, size, ...props }: ButtonProps) {
  return (
    <button
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
```

## Best Practices

1. **Use CSS variables** - Easier theming
2. **Use cn utility** - Merge classes safely
3. **Use CVA** - Type-safe variants
4. **Mobile-first** - Start with base, add responsive
5. **Extract components** - Reuse common patterns
6. **Use design tokens** - Consistent spacing/colors
