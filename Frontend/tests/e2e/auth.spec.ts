import { expect, test } from "@playwright/test";

test("auth page renders", async ({ page }) => {
  await page.goto("/");
  const signInSection = page.getByRole("region", { name: "Sign in" });
  await expect(signInSection.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(signInSection.getByRole("button", { name: "Sign In" })).toBeVisible();
});

test("auth page sign-up panel renders", async ({ page }) => {
  await page.goto("/");
  const signUpSection = page.getByRole("region", { name: "Sign up" });
  await expect(signUpSection.getByRole("heading", { name: "Create Account" })).toBeVisible();
  await expect(signUpSection.getByRole("button", { name: "Sign Up" })).toBeVisible();
});
