import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { MemoryRouter } from "react-router-dom";

import AuthPage from "@/pages/AuthPage";

expect.extend(toHaveNoViolations);

vi.mock("@/lib/auth", () => ({
  authStorage: {
    getUser: () => null,
    getTokens: () => null,
  },
}));

describe("AuthPage accessibility", () => {
  it("has no obvious a11y violations", async () => {
    const { container } = render(
      <MemoryRouter>
        <AuthPage />
      </MemoryRouter>,
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
