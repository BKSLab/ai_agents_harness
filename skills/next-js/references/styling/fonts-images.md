---
name: nextjs-fonts-images
description: Font and image optimization in Next.js
applies_to: nextjs
---

# Font and Image Optimization

## Overview

Next.js provides built-in optimization for fonts and images,
improving performance and Core Web Vitals.

## Font Optimization

### Using next/font/google
```tsx
// app/layout.tsx
import { Inter, Roboto_Mono } from 'next/font/google';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap',
});

const robotoMono = Roboto_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${robotoMono.variable}`}>
      <body className="font-sans">
        {children}
      </body>
    </html>
  );
}
```

### Tailwind Configuration
```ts
// tailwind.config.ts
import type { Config } from 'tailwindcss';

const config: Config = {
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'monospace'],
      },
    },
  },
};

export default config;
```

### Local Fonts
```tsx
// app/layout.tsx
import localFont from 'next/font/local';

const myFont = localFont({
  src: [
    {
      path: '../public/fonts/MyFont-Regular.woff2',
      weight: '400',
      style: 'normal',
    },
    {
      path: '../public/fonts/MyFont-Bold.woff2',
      weight: '700',
      style: 'normal',
    },
  ],
  variable: '--font-custom',
  display: 'swap',
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={myFont.variable}>
      <body>{children}</body>
    </html>
  );
}
```

## Image Optimization

### Basic Image
```tsx
import Image from 'next/image';

export function ProductImage({ src, alt }: { src: string; alt: string }) {
  return (
    <Image
      src={src}
      alt={alt}
      width={400}
      height={400}
      className="rounded-lg"
    />
  );
}
```

### Fill Container
```tsx
import Image from 'next/image';

export function HeroImage({ src, alt }: { src: string; alt: string }) {
  return (
    <div className="relative aspect-video w-full">
      <Image
        src={src}
        alt={alt}
        fill
        className="object-cover rounded-lg"
        priority // Load immediately for LCP images
      />
    </div>
  );
}
```

### Responsive Images
```tsx
import Image from 'next/image';

export function ResponsiveImage({ src, alt }: { src: string; alt: string }) {
  return (
    <Image
      src={src}
      alt={alt}
      width={800}
      height={600}
      sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
      className="w-full h-auto"
    />
  );
}
```

### Remote Images
```js
// next.config.js
/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'images.unsplash.com',
        port: '',
        pathname: '/**',
      },
      {
        protocol: 'https',
        hostname: 'avatars.githubusercontent.com',
        port: '',
        pathname: '/**',
      },
      {
        protocol: 'https',
        hostname: '*.amazonaws.com',
        port: '',
        pathname: '/**',
      },
    ],
  },
};

module.exports = nextConfig;
```

### Image with Fallback
```tsx
'use client';

import Image from 'next/image';
import { useState } from 'react';

interface ImageWithFallbackProps {
  src: string;
  fallbackSrc: string;
  alt: string;
  width: number;
  height: number;
}

export function ImageWithFallback({
  src,
  fallbackSrc,
  alt,
  width,
  height,
}: ImageWithFallbackProps) {
  const [imgSrc, setImgSrc] = useState(src);

  return (
    <Image
      src={imgSrc}
      alt={alt}
      width={width}
      height={height}
      onError={() => setImgSrc(fallbackSrc)}
    />
  );
}
```

### Avatar Component
```tsx
import Image from 'next/image';

interface AvatarProps {
  src?: string | null;
  name: string;
  size?: 'sm' | 'md' | 'lg';
}

const sizes = {
  sm: 32,
  md: 40,
  lg: 64,
};

export function Avatar({ src, name, size = 'md' }: AvatarProps) {
  const pixelSize = sizes[size];
  const initials = name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  if (src) {
    return (
      <Image
        src={src}
        alt={name}
        width={pixelSize}
        height={pixelSize}
        className="rounded-full object-cover"
      />
    );
  }

  return (
    <div
      className="rounded-full bg-primary flex items-center justify-center text-primary-foreground font-medium"
      style={{ width: pixelSize, height: pixelSize }}
    >
      {initials}
    </div>
  );
}
```

### Image Gallery
```tsx
import Image from 'next/image';

interface ImageGalleryProps {
  images: { src: string; alt: string }[];
}

export function ImageGallery({ images }: ImageGalleryProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      {images.map((image, index) => (
        <div key={index} className="relative aspect-square">
          <Image
            src={image.src}
            alt={image.alt}
            fill
            sizes="(max-width: 768px) 50vw, (max-width: 1200px) 33vw, 25vw"
            className="object-cover rounded-lg hover:opacity-90 transition-opacity cursor-pointer"
          />
        </div>
      ))}
    </div>
  );
}
```

## Loading States

```tsx
import Image from 'next/image';
import { useState } from 'react';

export function ImageWithLoading({
  src,
  alt,
  width,
  height,
}: {
  src: string;
  alt: string;
  width: number;
  height: number;
}) {
  const [isLoading, setIsLoading] = useState(true);

  return (
    <div className="relative" style={{ width, height }}>
      {isLoading && (
        <div className="absolute inset-0 bg-muted animate-pulse rounded-lg" />
      )}
      <Image
        src={src}
        alt={alt}
        width={width}
        height={height}
        onLoad={() => setIsLoading(false)}
        className={`rounded-lg transition-opacity duration-300 ${
          isLoading ? 'opacity-0' : 'opacity-100'
        }`}
      />
    </div>
  );
}
```

## Best Practices

1. **Use next/font** - Self-hosted fonts, no layout shift
2. **Set priority** - For above-the-fold images
3. **Use sizes** - Optimal image loading
4. **Configure remotePatterns** - Security for remote images
5. **Use fill with relative parent** - For unknown dimensions
6. **Add alt text** - Accessibility
7. **Use placeholder** - Better perceived performance
