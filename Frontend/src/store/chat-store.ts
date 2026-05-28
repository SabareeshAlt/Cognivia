import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  ragScore?: number;
  ragConfidence?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
}

interface ChatState {
  chats: ChatSession[];
  activeChatId: string | null;
  createChat: () => string;
  setActiveChat: (chatId: string) => void;
  deleteChat: (chatId: string) => void;
  appendMessage: (chatId: string, message: ChatMessage) => void;
  updateMessage: (
    chatId: string,
    messageId: string,
    content: string,
    ragScore?: number,
    ragConfidence?: string
  ) => void;
  updateTitleIfNew: (chatId: string, sourceText: string) => void;
  reset: () => void;
}

const introMessage: ChatMessage = {
  id: "intro",
  role: "assistant",
  content: "AcademeRAG Ready. Ask me about your uploaded documents!",
};

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      chats: [],
      activeChatId: null,
      createChat: () => {
        const id = Date.now().toString();
        const chat: ChatSession = {
          id,
          title: "New Chat",
          messages: [introMessage],
        };
        set((state) => ({
          chats: [chat, ...state.chats],
          activeChatId: id,
        }));
        return id;
      },
      setActiveChat: (chatId) => set({ activeChatId: chatId }),
      deleteChat: (chatId) => {
        const remaining = get().chats.filter((chat) => chat.id !== chatId);
        set({
          chats: remaining,
          activeChatId: remaining.length ? remaining[0].id : null,
        });
      },
      appendMessage: (chatId, message) => {
        set((state) => ({
          chats: state.chats.map((chat) =>
            chat.id === chatId
              ? {
                  ...chat,
                  messages: [...chat.messages, message],
                }
              : chat,
          ),
        }));
      },
      updateMessage: (chatId, messageId, content, ragScore, ragConfidence) => {
        set((state) => ({
          chats: state.chats.map((chat) =>
            chat.id === chatId
              ? {
                  ...chat,
                  messages: chat.messages.map((message) =>
                    message.id === messageId
                      ? {
                          ...message,
                          content,
                          ...(ragScore !== undefined ? { ragScore } : {}),
                          ...(ragConfidence !== undefined ? { ragConfidence } : {}),
                        }
                      : message,
                  ),
                }
              : chat,
          ),
        }));
      },
      updateTitleIfNew: (chatId, sourceText) => {
        set((state) => ({
          chats: state.chats.map((chat) => {
            if (chat.id !== chatId || chat.title !== "New Chat") {
              return chat;
            }
            return {
              ...chat,
              title: sourceText.slice(0, 30) + (sourceText.length > 30 ? "..." : ""),
            };
          }),
        }));
      },
      reset: () => set({ chats: [], activeChatId: null }),
    }),
    {
      name: "rag_chat_state",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ chats: state.chats, activeChatId: state.activeChatId }),
    },
  ),
);
