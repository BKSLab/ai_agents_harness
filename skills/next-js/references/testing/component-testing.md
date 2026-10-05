---
name: nextjs-component-testing
description: Component testing strategies for Next.js
applies_to: nextjs
---

# Component Testing in Next.js

## Overview

Component testing focuses on testing React components in isolation
and in integration with other components.

## Testing Server Components

### Async Server Component Test
```tsx
// app/users/page.test.tsx
import { render, screen } from '@testing-library/react';
import UsersPage from './page';

// Mock the database
jest.mock('@/lib/db', () => ({
  db: {
    user: {
      findMany: jest.fn().mockResolvedValue([
        { id: '1', name: 'John', email: 'john@example.com' },
        { id: '2', name: 'Jane', email: 'jane@example.com' },
      ]),
    },
  },
}));

describe('UsersPage', () => {
  it('renders list of users', async () => {
    const Page = await UsersPage();
    render(Page);

    expect(screen.getByText('John')).toBeInTheDocument();
    expect(screen.getByText('Jane')).toBeInTheDocument();
  });
});
```

### Testing with Dynamic Params
```tsx
// app/products/[id]/page.test.tsx
import { render, screen } from '@testing-library/react';
import ProductPage from './page';

jest.mock('@/lib/db', () => ({
  db: {
    product: {
      findUnique: jest.fn(),
    },
  },
}));

import { db } from '@/lib/db';

describe('ProductPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders product details', async () => {
    (db.product.findUnique as jest.Mock).mockResolvedValue({
      id: '1',
      name: 'Test Product',
      price: 99.99,
      description: 'A great product',
    });

    const Page = await ProductPage({ params: { id: '1' } });
    render(Page);

    expect(screen.getByText('Test Product')).toBeInTheDocument();
    expect(screen.getByText('$99.99')).toBeInTheDocument();
  });

  it('shows not found for missing product', async () => {
    (db.product.findUnique as jest.Mock).mockResolvedValue(null);

    await expect(ProductPage({ params: { id: '999' } })).rejects.toThrow();
  });
});
```

## Testing Client Components

### Interactive Component
```tsx
// components/todo-list.test.tsx
'use client';

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TodoList } from './todo-list';

describe('TodoList', () => {
  const mockTodos = [
    { id: '1', text: 'Learn Next.js', completed: false },
    { id: '2', text: 'Build an app', completed: true },
  ];

  it('renders todos', () => {
    render(<TodoList initialTodos={mockTodos} />);

    expect(screen.getByText('Learn Next.js')).toBeInTheDocument();
    expect(screen.getByText('Build an app')).toBeInTheDocument();
  });

  it('adds a new todo', async () => {
    const user = userEvent.setup();
    render(<TodoList initialTodos={[]} />);

    await user.type(screen.getByPlaceholderText(/add todo/i), 'New Todo');
    await user.click(screen.getByRole('button', { name: /add/i }));

    expect(screen.getByText('New Todo')).toBeInTheDocument();
  });

  it('toggles todo completion', async () => {
    const user = userEvent.setup();
    render(<TodoList initialTodos={mockTodos} />);

    const checkbox = screen.getByRole('checkbox', { name: /learn next.js/i });
    await user.click(checkbox);

    expect(checkbox).toBeChecked();
  });

  it('deletes a todo', async () => {
    const user = userEvent.setup();
    render(<TodoList initialTodos={mockTodos} />);

    const deleteButtons = screen.getAllByRole('button', { name: /delete/i });
    await user.click(deleteButtons[0]);

    expect(screen.queryByText('Learn Next.js')).not.toBeInTheDocument();
  });
});
```

### Form Component with Validation
```tsx
// components/contact-form.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ContactForm } from './contact-form';

describe('ContactForm', () => {
  it('submits form with valid data', async () => {
    const user = userEvent.setup();
    const onSubmit = jest.fn();

    render(<ContactForm onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/name/i), 'John Doe');
    await user.type(screen.getByLabelText(/email/i), 'john@example.com');
    await user.type(screen.getByLabelText(/message/i), 'Hello there!');
    await user.click(screen.getByRole('button', { name: /send/i }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        name: 'John Doe',
        email: 'john@example.com',
        message: 'Hello there!',
      });
    });
  });

  it('shows validation errors for empty fields', async () => {
    const user = userEvent.setup();
    render(<ContactForm onSubmit={jest.fn()} />);

    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(screen.getByText(/name is required/i)).toBeInTheDocument();
    expect(screen.getByText(/email is required/i)).toBeInTheDocument();
    expect(screen.getByText(/message is required/i)).toBeInTheDocument();
  });

  it('shows error for invalid email', async () => {
    const user = userEvent.setup();
    render(<ContactForm onSubmit={jest.fn()} />);

    await user.type(screen.getByLabelText(/email/i), 'invalid-email');
    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(screen.getByText(/invalid email/i)).toBeInTheDocument();
  });

  it('disables submit button while submitting', async () => {
    const user = userEvent.setup();
    const onSubmit = jest.fn(() => new Promise(resolve => setTimeout(resolve, 100)));

    render(<ContactForm onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/name/i), 'John');
    await user.type(screen.getByLabelText(/email/i), 'john@example.com');
    await user.type(screen.getByLabelText(/message/i), 'Test');
    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(screen.getByRole('button', { name: /sending/i })).toBeDisabled();
  });
});
```

## Testing Components with Context

### Provider Wrapper
```tsx
// components/theme-toggle.test.tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider, ThemeToggle } from './theme';

const renderWithTheme = (ui: React.ReactElement, theme = 'light') => {
  return render(
    <ThemeProvider defaultTheme={theme}>
      {ui}
    </ThemeProvider>
  );
};

describe('ThemeToggle', () => {
  it('toggles between light and dark', async () => {
    const user = userEvent.setup();
    renderWithTheme(<ThemeToggle />);

    const button = screen.getByRole('button', { name: /toggle theme/i });

    expect(button).toHaveAttribute('aria-label', expect.stringMatching(/dark/i));

    await user.click(button);

    expect(button).toHaveAttribute('aria-label', expect.stringMatching(/light/i));
  });
});
```

### Multiple Providers
```tsx
// test/utils.tsx
import { render, RenderOptions } from '@testing-library/react';
import { ThemeProvider } from '@/components/theme';
import { AuthProvider } from '@/components/auth';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

interface WrapperProps {
  children: React.ReactNode;
}

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return function Wrapper({ children }: WrapperProps) {
    return (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ThemeProvider>
            {children}
          </ThemeProvider>
        </AuthProvider>
      </QueryClientProvider>
    );
  };
};

export const renderWithProviders = (
  ui: React.ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) => {
  return render(ui, { wrapper: createWrapper(), ...options });
};

export * from '@testing-library/react';
```

## Testing with React Query

```tsx
// components/users-list.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { UsersList } from './users-list';
import { fetchUsers } from '@/lib/api';

jest.mock('@/lib/api');

const createQueryWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
};

describe('UsersList', () => {
  it('shows loading state', () => {
    (fetchUsers as jest.Mock).mockImplementation(() => new Promise(() => {}));

    render(<UsersList />, { wrapper: createQueryWrapper() });

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('shows users after loading', async () => {
    (fetchUsers as jest.Mock).mockResolvedValue([
      { id: '1', name: 'John' },
      { id: '2', name: 'Jane' },
    ]);

    render(<UsersList />, { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(screen.getByText('John')).toBeInTheDocument();
      expect(screen.getByText('Jane')).toBeInTheDocument();
    });
  });

  it('shows error state', async () => {
    (fetchUsers as jest.Mock).mockRejectedValue(new Error('Failed to fetch'));

    render(<UsersList />, { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });
});
```

## Testing Modals and Dialogs

```tsx
// components/confirm-dialog.test.tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfirmDialog } from './confirm-dialog';

describe('ConfirmDialog', () => {
  it('calls onConfirm when confirmed', async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn();
    const onCancel = jest.fn();

    render(
      <ConfirmDialog
        open={true}
        title="Delete Item"
        message="Are you sure?"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    );

    await user.click(screen.getByRole('button', { name: /confirm/i }));

    expect(onConfirm).toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('calls onCancel when cancelled', async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn();
    const onCancel = jest.fn();

    render(
      <ConfirmDialog
        open={true}
        title="Delete Item"
        message="Are you sure?"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    );

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('closes on escape key', async () => {
    const user = userEvent.setup();
    const onCancel = jest.fn();

    render(
      <ConfirmDialog
        open={true}
        title="Delete Item"
        message="Are you sure?"
        onConfirm={jest.fn()}
        onCancel={onCancel}
      />
    );

    await user.keyboard('{Escape}');

    expect(onCancel).toHaveBeenCalled();
  });
});
```

## Snapshot Testing

```tsx
// components/card.test.tsx
import { render } from '@testing-library/react';
import { Card } from './card';

describe('Card', () => {
  it('matches snapshot', () => {
    const { container } = render(
      <Card
        title="Test Card"
        description="This is a test card"
        image="/test.jpg"
      />
    );

    expect(container).toMatchSnapshot();
  });

  it('matches snapshot with all props', () => {
    const { container } = render(
      <Card
        title="Full Card"
        description="With all props"
        image="/test.jpg"
        badge="New"
        actions={<button>Action</button>}
      />
    );

    expect(container).toMatchSnapshot();
  });
});
```

## Best Practices

1. **Test user behavior** - Not implementation details
2. **Use semantic queries** - getByRole, getByLabelText
3. **Mock sparingly** - Only external dependencies
4. **Test edge cases** - Error states, loading, empty
5. **Keep tests isolated** - No shared state
6. **Test accessibility** - ARIA roles and labels
