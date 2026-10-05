---
name: nextjs-playwright
description: Playwright E2E testing for Next.js
applies_to: nextjs
---

# Playwright E2E Testing

## Overview

Playwright enables reliable end-to-end testing for Next.js applications
with cross-browser support and powerful automation capabilities.

## Setup

### Installation
```bash
npm init playwright@latest
```

### Configuration
```ts
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

## Basic Tests

### Navigation Test
```ts
// e2e/navigation.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Navigation', () => {
  test('should navigate to home page', async ({ page }) => {
    await page.goto('/');

    await expect(page).toHaveTitle(/My App/);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });

  test('should navigate between pages', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('link', { name: /about/i }).click();

    await expect(page).toHaveURL('/about');
    await expect(page.getByRole('heading', { name: /about/i })).toBeVisible();
  });
});
```

### Form Test
```ts
// e2e/login.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Login', () => {
  test('should login with valid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('password123');
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page).toHaveURL('/dashboard');
    await expect(page.getByText(/welcome/i)).toBeVisible();
  });

  test('should show error for invalid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.getByLabel(/email/i).fill('wrong@example.com');
    await page.getByLabel(/password/i).fill('wrongpassword');
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page.getByText(/invalid credentials/i)).toBeVisible();
    await expect(page).toHaveURL('/login');
  });

  test('should show validation errors', async ({ page }) => {
    await page.goto('/login');

    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page.getByText(/email is required/i)).toBeVisible();
    await expect(page.getByText(/password is required/i)).toBeVisible();
  });
});
```

## Authentication Tests

### With Auth State
```ts
// e2e/auth.setup.ts
import { test as setup, expect } from '@playwright/test';

const authFile = 'playwright/.auth/user.json';

setup('authenticate', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel(/email/i).fill('test@example.com');
  await page.getByLabel(/password/i).fill('password123');
  await page.getByRole('button', { name: /sign in/i }).click();

  await expect(page).toHaveURL('/dashboard');

  await page.context().storageState({ path: authFile });
});
```

```ts
// playwright.config.ts
export default defineConfig({
  projects: [
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'playwright/.auth/user.json',
      },
      dependencies: ['setup'],
    },
  ],
});
```

### Protected Routes
```ts
// e2e/dashboard.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test('should display user dashboard', async ({ page }) => {
    // Uses authenticated state from setup
    await page.goto('/dashboard');

    await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible();
    await expect(page.getByText(/test@example.com/i)).toBeVisible();
  });

  test('should allow user to update profile', async ({ page }) => {
    await page.goto('/dashboard/settings');

    await page.getByLabel(/name/i).clear();
    await page.getByLabel(/name/i).fill('Updated Name');
    await page.getByRole('button', { name: /save/i }).click();

    await expect(page.getByText(/settings saved/i)).toBeVisible();
  });
});
```

## API Testing

### Testing API Routes
```ts
// e2e/api.spec.ts
import { test, expect } from '@playwright/test';

test.describe('API Routes', () => {
  test('GET /api/users returns users', async ({ request }) => {
    const response = await request.get('/api/users');

    expect(response.ok()).toBeTruthy();

    const users = await response.json();
    expect(Array.isArray(users)).toBeTruthy();
  });

  test('POST /api/users creates user', async ({ request }) => {
    const response = await request.post('/api/users', {
      data: {
        name: 'New User',
        email: 'new@example.com',
      },
    });

    expect(response.status()).toBe(201);

    const user = await response.json();
    expect(user.name).toBe('New User');
  });

  test('DELETE /api/users/:id deletes user', async ({ request }) => {
    const response = await request.delete('/api/users/1');

    expect(response.status()).toBe(204);
  });
});
```

## Visual Testing

### Screenshot Comparison
```ts
// e2e/visual.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Visual Tests', () => {
  test('homepage matches snapshot', async ({ page }) => {
    await page.goto('/');

    await expect(page).toHaveScreenshot('homepage.png');
  });

  test('dark mode matches snapshot', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /toggle theme/i }).click();

    await expect(page).toHaveScreenshot('homepage-dark.png');
  });

  test('component matches snapshot', async ({ page }) => {
    await page.goto('/components/button');

    const button = page.getByRole('button', { name: /primary/i });
    await expect(button).toHaveScreenshot('button-primary.png');
  });
});
```

## Accessibility Testing

```ts
// e2e/accessibility.spec.ts
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Accessibility', () => {
  test('homepage has no accessibility violations', async ({ page }) => {
    await page.goto('/');

    const accessibilityScanResults = await new AxeBuilder({ page }).analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('form has proper labels', async ({ page }) => {
    await page.goto('/contact');

    const accessibilityScanResults = await new AxeBuilder({ page })
      .include('form')
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });
});
```

## Page Object Pattern

### Page Object
```ts
// e2e/pages/login-page.ts
import { Page, Locator, expect } from '@playwright/test';

export class LoginPage {
  readonly page: Page;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.emailInput = page.getByLabel(/email/i);
    this.passwordInput = page.getByLabel(/password/i);
    this.submitButton = page.getByRole('button', { name: /sign in/i });
    this.errorMessage = page.getByRole('alert');
  }

  async goto() {
    await this.page.goto('/login');
  }

  async login(email: string, password: string) {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.submitButton.click();
  }

  async expectError(message: string) {
    await expect(this.errorMessage).toContainText(message);
  }
}
```

### Using Page Object
```ts
// e2e/login-po.spec.ts
import { test, expect } from '@playwright/test';
import { LoginPage } from './pages/login-page';

test.describe('Login with Page Object', () => {
  test('should login successfully', async ({ page }) => {
    const loginPage = new LoginPage(page);

    await loginPage.goto();
    await loginPage.login('test@example.com', 'password123');

    await expect(page).toHaveURL('/dashboard');
  });

  test('should show error for invalid login', async ({ page }) => {
    const loginPage = new LoginPage(page);

    await loginPage.goto();
    await loginPage.login('wrong@example.com', 'wrong');

    await loginPage.expectError('Invalid credentials');
  });
});
```

## Test Fixtures

### Custom Fixtures
```ts
// e2e/fixtures.ts
import { test as base } from '@playwright/test';
import { LoginPage } from './pages/login-page';
import { DashboardPage } from './pages/dashboard-page';

type MyFixtures = {
  loginPage: LoginPage;
  dashboardPage: DashboardPage;
};

export const test = base.extend<MyFixtures>({
  loginPage: async ({ page }, use) => {
    const loginPage = new LoginPage(page);
    await use(loginPage);
  },
  dashboardPage: async ({ page }, use) => {
    const dashboardPage = new DashboardPage(page);
    await use(dashboardPage);
  },
});

export { expect } from '@playwright/test';
```

### Using Fixtures
```ts
// e2e/with-fixtures.spec.ts
import { test, expect } from './fixtures';

test('should access dashboard after login', async ({ loginPage, dashboardPage, page }) => {
  await loginPage.goto();
  await loginPage.login('test@example.com', 'password123');

  await dashboardPage.expectWelcomeMessage('Welcome');
});
```

## Best Practices

1. **Use locators** - Prefer role, label, text over test IDs
2. **Isolate tests** - Each test should be independent
3. **Use Page Objects** - Organize and reuse selectors
4. **Test critical paths** - Focus on user journeys
5. **Run in CI** - Automated testing on every commit
6. **Visual regression** - Catch unintended UI changes
