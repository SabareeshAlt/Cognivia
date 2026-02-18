import { expect, test } from "@playwright/test";

test("auth page renders", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
});

test("auth page visual baseline", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveScreenshot("auth-page.png", { fullPage: true });
});
