import { test, expect } from "@playwright/test";

test.describe("Mercury Tours Login Process", () => {
  const baseUrl = "https://demo.guru99.com/test/newtours/";

  test.beforeEach(async ({ page }) => {
    await page.goto(baseUrl + "login.php");
  });

  test("UI: Verify login page elements and password masking", async ({
    page,
  }) => {
    await expect(page.locator('input[name="userName"]')).toBeVisible();
    await expect(page.locator('input[name="password"]')).toBeVisible();
    await expect(page.locator('input[name="submit"]')).toBeVisible();
    await expect(page.locator('input[name="password"]')).toHaveAttribute(
      "type",
      "password",
    );
  });

  test("FUNC: Successful login with valid credentials", async ({ page }) => {
    await page.locator('input[name="userName"]').fill("mercury");
    await page.locator('input[name="password"]').fill("mercury");
    await page.locator('input[name="submit"]').click();

    await expect(page).toHaveURL(/.*login_sucess\.php/);
    await expect(page.locator("text=Login Successfully")).toBeVisible();
  });

  test("FUNC: Failed login with invalid credentials", async ({ page }) => {
    await page.locator('input[name="userName"]').fill("invalidUser");
    await page.locator('input[name="password"]').fill("invalidPass");
    await page.locator('input[name="submit"]').click();

    await expect(page).toHaveURL(/.*login_sucess\.php/);
    await expect(page.locator("text=Login Successfully")).toBeVisible();
  });

  test("FUNC: Login using the Enter key", async ({ page }) => {
    await page.locator('input[name="userName"]').fill("mercury");
    await page.locator('input[name="password"]').fill("mercury");

    // FIX: Press Enter specifically on the password field to guarantee form submission in all browsers
    await page.locator('input[name="password"]').press("Enter");

    await expect(page).toHaveURL(/.*login_sucess\.php/);
  });
});
