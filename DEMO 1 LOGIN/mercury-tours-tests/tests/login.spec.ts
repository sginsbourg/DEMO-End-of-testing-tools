import { test, expect } from '@playwright/test';

test.describe('Mercury Tours Login Process', () => {
    
    // Base URL for the application
    const baseUrl = 'https://demo.guru99.com/test/newtours/';

    // Navigate to the login page before every test
    test.beforeEach(async ({ page }) => {
        await page.goto(`${baseUrl}login.php`);
    });

    test('UI: Verify login page elements and password masking', async ({ page }) => {
        // Check if username, password, and submit elements are visible
        await expect(page.locator('input[name="userName"]')).toBeVisible();
        await expect(page.locator('input[name="password"]')).toBeVisible();
        await expect(page.locator('input[name="submit"]')).toBeVisible();
        
        // Verify the password field is actually masked
        await expect(page.locator('input[name="password"]')).toHaveAttribute('type', 'password');
    });

    test('FUNC: Successful login with valid credentials', async ({ page }) => {
        // Fill in valid credentials
        await page.locator('input[name="userName"]').fill('mercury');
        await page.locator('input[name="password"]').fill('mercury');
        
        // Click submit
        await page.locator('input[name="submit"]').click();

        // Verify successful redirect to the Find Flights page
        await expect(page).toHaveURL(/.*findFlights\.php/);
        await expect(page.locator('text=Find Flights')).toBeVisible();
    });

    test('FUNC: Failed login with invalid credentials', async ({ page }) => {
        // Fill in invalid credentials
        await page.locator('input[name="userName"]').fill('invalidUser');
        await page.locator('input[name="password"]').fill('invalidPass');
        
        // Click submit
        await page.locator('input[name="submit"]').click();

        // Verify it stays on the login page (URL remains login.php)
        await expect(page).toHaveURL(/.*login\.php/);
        // Verify the login form is still present
        await expect(page.locator('input[name="userName"]')).toBeVisible();
    });

    test('FUNC: Login using the Enter key', async ({ page }) => {
        // Fill in valid credentials
        await page.locator('input[name="userName"]').fill('mercury');
        await page.locator('input[name="password"]').fill('mercury');
        
        // Press Enter on the keyboard instead of clicking the button
        await page.keyboard.press('Enter');

        // Verify successful redirect
        await expect(page).toHaveURL(/.*findFlights\.php/);
    });

});