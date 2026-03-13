import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import ChatPage from "@/pages/ChatPage";
import { useChatStore } from "@/store/chat-store";

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
  },
}));

vi.mock("@/lib/api-client", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    code: string;

    constructor(message: string, status = 500, code = "API_ERROR") {
      super(message);
      this.status = status;
      this.code = code;
    }
  },
  apiClient: {
    askStream: vi.fn(),
    getActiveBaseUrl: vi.fn(() => "http://127.0.0.1:8000"),
  },
}));

describe("ChatPage offline behavior", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    useChatStore.getState().reset();

    localStorage.setItem(
      "rag_user",
      JSON.stringify({ id: 1, email: "offline@example.com", name: "Offline User" }),
    );

    Object.defineProperty(window.navigator, "onLine", {
      configurable: true,
      get: () => false,
    });
  });

  it("keeps local chat input enabled when the browser is offline", async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );

    expect(await screen.findByLabelText("Ask a question")).toBeEnabled();
    expect(screen.getByRole("button", { name: /logout/i })).toBeInTheDocument();
    expect(
      screen.getByText(/local academerag requests can still run/i),
    ).toBeInTheDocument();
  });
});
