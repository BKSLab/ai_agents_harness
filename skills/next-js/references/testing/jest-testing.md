---
name: nextjs-jest-testing
description: Jest testing setup and patterns for Next.js
applies_to: nextjs
---

# Jest Testing in Next.js

## Overview

Jest with Testing Library provides unit and integration testing
for Next.js applications with full TypeScript support.

## Setup

### Installation
```bash
npm install -D jest jest-environment-jsdom @testing-library/react @testing-library/jest-dom @types/jest
```

### Configuration
```js
// jest.config.js
const nextJest = require('next/jest');

const createJestConfig = nextJest({
  dir: './',
});

const customJestConfig = {
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  testEnvironment: 'jest-environment-jsdom',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/$1',
  },
  testPathIgnorePatterns: ['<rootDir>/e2e/'],
  collectCoverageFrom: [
    'app/**/*.{js,jsx,ts,tsx}',
    'components/**/*.{js,jsx,ts,tsx}',
    'lib/**/*.{js,jsx,ts,tsx}',
    '!**/*.d.ts',
    '!**/node_modules/**',
  ],
};

module.exports = createJestConfig(customJestConfig);
```

### Setup File
```js
// jest.setup.js
import '@testing-library/jest-dom';

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter() {
    return {
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      back: jest.fn(),
      forward: jest.fn(),
    };
  },
  useSearchParams() {
    return new URLSearchParams();
  },
  usePathname() {
    return '/';
  },
  useParams() {
    return {};
  },
}));

// Mock next/image
jest.mock('next/image', () => ({
  __esModule: true,
  default: (props) => {
    // eslint-disable-next-line @next/next/no-img-element
    return <img {...props} />;
  },
}));
```

## Testing Patterns

### Testing Client Components
```tsx
// components/counter.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { Counter } from './counter';

describe('Counter', () => {
  it('renders initial count', () => {
    render(<Counter initialCount={5} />);
    expect(screen.getByText('Count: 5')).toBeInTheDocument();
  });

  it('increments count on button click', () => {
    render(<Counter initialCount={0} />);

    fireEvent.click(screen.getByRole('button', { name: /increment/i }));

    expect(screen.getByText('Count: 1')).toBeInTheDocument();
  });

  it('decrements count on button click', () => {
    render(<Counter initialCount={5} />);

    fireEvent.click(screen.getByRole('button', { name: /decrement/i }));

    expect(screen.getByText('Count: 4')).toBeInTheDocument();
  });
});
```

### Testing with User Events
```tsx
// components/login-form.test.tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LoginForm } from './login-form';

describe('LoginForm', () => {
  it('submits form with entered values', async () => {
    const user = userEvent.setup();
    const onSubmit = jest.fn();

    render(<LoginForm onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/email/i), 'test@example.com');
    await user.type(screen.getByLabelText(/password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /submit/i }));

    expect(onSubmit).toHaveBeenCalledWith({
      email: 'test@example.com',
      password: 'password123',
    });
  });

  it('shows validation errors', async () => {
    const user = userEvent.setup();

    render(<LoginForm onSubmit={jest.fn()} />);

    await user.click(screen.getByRole('button', { name: /submit/i }));

    expect(screen.getByText(/email is required/i)).toBeInTheDocument();
    expect(screen.getByText(/password is required/i)).toBeInTheDocument();
  });
});
```

### Testing Async Components
```tsx
// components/user-profile.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { UserProfile } from './user-profile';

// Mock fetch
global.fetch = jest.fn();

describe('UserProfile', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows loading state', () => {
    (fetch as jest.Mock).mockImplementation(() => new Promise(() => {}));

    render(<UserProfile userId="1" />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('displays user data', async () => {
    (fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ name: 'John Doe', email: 'john@example.com' }),
    });

    render(<UserProfile userId="1" />);

    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeInTheDocument();
      expect(screen.getByText('john@example.com')).toBeInTheDocument();
    });
  });

  it('handles error state', async () => {
    (fetch as jest.Mock).mockRejectedValue(new Error('Failed to fetch'));

    render(<UserProfile userId="1" />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });
});
```

### Testing Custom Hooks
```tsx
// hooks/use-counter.test.ts
import { renderHook, act } from '@testing-library/react';
import { useCounter } from './use-counter';

describe('useCounter', () => {
  it('initializes with default value', () => {
    const { result } = renderHook(() => useCounter());
    expect(result.current.count).toBe(0);
  });

  it('initializes with custom value', () => {
    const { result } = renderHook(() => useCounter(10));
    expect(result.current.count).toBe(10);
  });

  it('increments count', () => {
    const { result } = renderHook(() => useCounter(0));

    act(() => {
      result.current.increment();
    });

    expect(result.current.count).toBe(1);
  });

  it('decrements count', () => {
    const { result } = renderHook(() => useCounter(5));

    act(() => {
      result.current.decrement();
    });

    expect(result.current.count).toBe(4);
  });

  it('resets count', () => {
    const { result } = renderHook(() => useCounter(10));

    act(() => {
      result.current.increment();
      result.current.reset();
    });

    expect(result.current.count).toBe(10);
  });
});
```

### Mocking Modules
```tsx
// components/data-display.test.tsx
import { render, screen } from '@testing-library/react';
import { DataDisplay } from './data-display';
import { fetchData } from '@/lib/api';

// Mock the module
jest.mock('@/lib/api', () => ({
  fetchData: jest.fn(),
}));

describe('DataDisplay', () => {
  it('displays fetched data', async () => {
    (fetchData as jest.Mock).mockResolvedValue({
      items: [
        { id: 1, name: 'Item 1' },
        { id: 2, name: 'Item 2' },
      ],
    });

    render(<DataDisplay />);

    expect(await screen.findByText('Item 1')).toBeInTheDocument();
    expect(screen.getByText('Item 2')).toBeInTheDocument();
  });
});
```

## Testing Server Actions

```tsx
// lib/actions/user.test.ts
import { createUser, updateUser } from './user';
import { db } from '@/lib/db';

// Mock Prisma
jest.mock('@/lib/db', () => ({
  db: {
    user: {
      create: jest.fn(),
      update: jest.fn(),
      findUnique: jest.fn(),
    },
  },
}));

describe('User Actions', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('createUser', () => {
    it('creates user with valid data', async () => {
      const mockUser = { id: '1', name: 'John', email: 'john@example.com' };
      (db.user.create as jest.Mock).mockResolvedValue(mockUser);

      const formData = new FormData();
      formData.append('name', 'John');
      formData.append('email', 'john@example.com');

      const result = await createUser({}, formData);

      expect(result.success).toBe(true);
      expect(db.user.create).toHaveBeenCalledWith({
        data: { name: 'John', email: 'john@example.com' },
      });
    });

    it('returns error for invalid data', async () => {
      const formData = new FormData();
      formData.append('name', '');
      formData.append('email', 'invalid-email');

      const result = await createUser({}, formData);

      expect(result.success).toBe(false);
      expect(result.errors).toBeDefined();
    });
  });
});
```

## Testing Utilities

### Custom Render
```tsx
// test/utils.tsx
import { render, RenderOptions } from '@testing-library/react';
import { SessionProvider } from 'next-auth/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const AllTheProviders = ({ children }: { children: React.ReactNode }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return (
    <SessionProvider session={null}>
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    </SessionProvider>
  );
};

const customRender = (
  ui: React.ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) => render(ui, { wrapper: AllTheProviders, ...options });

export * from '@testing-library/react';
export { customRender as render };
```

### Test Data Factories
```tsx
// test/factories.ts
export function createUser(overrides?: Partial<User>): User {
  return {
    id: '1',
    name: 'Test User',
    email: 'test@example.com',
    image: null,
    createdAt: new Date(),
    ...overrides,
  };
}

export function createProduct(overrides?: Partial<Product>): Product {
  return {
    id: '1',
    name: 'Test Product',
    price: 99.99,
    description: 'A test product',
    ...overrides,
  };
}
```

## Best Practices

1. **Use Testing Library queries** - getByRole, getByLabelText over getByTestId
2. **Test behavior** - Not implementation details
3. **Mock at boundaries** - External APIs, databases
4. **Use userEvent** - More realistic than fireEvent
5. **Clean up mocks** - beforeEach/afterEach
6. **Test accessibility** - Use getByRole for semantic queries
