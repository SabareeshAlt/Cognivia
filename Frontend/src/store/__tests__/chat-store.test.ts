import { beforeEach, describe, expect, it } from "vitest";

import { useChatStore } from "@/store/chat-store";

describe("chat store", () => {
  beforeEach(() => {
    localStorage.clear();
    useChatStore.getState().reset();
  });

  it("creates and deletes chats", () => {
    const id = useChatStore.getState().createChat();
    expect(useChatStore.getState().chats.length).toBe(1);
    expect(useChatStore.getState().activeChatId).toBe(id);

    useChatStore.getState().deleteChat(id);
    expect(useChatStore.getState().chats.length).toBe(0);
  });

  it("appends and updates messages", () => {
    const id = useChatStore.getState().createChat();
    useChatStore.getState().appendMessage(id, { id: "m1", role: "user", content: "hello" });
    useChatStore.getState().updateMessage(id, "m1", "updated");

    const chat = useChatStore.getState().chats.find((c) => c.id === id);
    expect(chat?.messages.some((message) => message.content === "updated")).toBe(true);
  });
});
