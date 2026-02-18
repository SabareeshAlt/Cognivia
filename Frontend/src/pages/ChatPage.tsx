import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Rocket, X, MessageSquare, Plus, LogOut, Menu, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

import ConfirmDialog from "@/components/ConfirmDialog";
import { authStorage } from "@/lib/auth";
import { apiClient, ApiError } from "@/lib/api-client";
import { config } from "@/lib/config";
import { logTelemetry, getTelemetryEvents } from "@/lib/telemetry";
import { sanitizeText } from "@/lib/sanitize";
import { useChatStore } from "@/store/chat-store";

const ChatPage = () => {
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showLogoutDialog, setShowLogoutDialog] = useState(false);
  const [deleteChatId, setDeleteChatId] = useState<string | null>(null);
  const [isOffline, setIsOffline] = useState(!navigator.onLine);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  const chats = useChatStore((state) => state.chats);
  const activeChatId = useChatStore((state) => state.activeChatId);
  const createChat = useChatStore((state) => state.createChat);
  const setActiveChat = useChatStore((state) => state.setActiveChat);
  const deleteChat = useChatStore((state) => state.deleteChat);
  const appendMessage = useChatStore((state) => state.appendMessage);
  const updateMessage = useChatStore((state) => state.updateMessage);
  const updateTitleIfNew = useChatStore((state) => state.updateTitleIfNew);
  const resetChats = useChatStore((state) => state.reset);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const activeChat = useMemo(() => chats.find((chat) => chat.id === activeChatId), [chats, activeChatId]);
  const isWaitingForFirstChunk = Boolean(
    isLoading &&
      activeChat?.messages.length &&
      activeChat.messages[activeChat.messages.length - 1].role === "assistant" &&
      activeChat.messages[activeChat.messages.length - 1].content.trim() === "",
  );

  useEffect(() => {
    if (!authStorage.getUser()) {
      navigate("/");
      return;
    }

    if (!activeChatId) {
      createChat();
    }
  }, [activeChatId, createChat, navigate]);

  useEffect(() => {
    const onOnline = () => setIsOffline(false);
    const onOffline = () => setIsOffline(true);

    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);

    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeChat?.messages, isLoading]);

  const handleNewChat = () => {
    createChat();
  };

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || !activeChatId) return;

    const currentInput = sanitizeText(input);
    setInput("");
    setIsLoading(true);

    appendMessage(activeChatId, { id: Date.now().toString(), role: "user", content: currentInput });
    updateTitleIfNew(activeChatId, currentInput);

    if (isOffline) {
      appendMessage(activeChatId, {
        id: `${Date.now()}-offline`,
        role: "assistant",
        content: "⚠️ You appear to be offline. Reconnect and try again.",
      });
      setIsLoading(false);
      return;
    }

    const botMsgId = `${Date.now()}-assistant`;
    appendMessage(activeChatId, { id: botMsgId, role: "assistant", content: "" });

    try {
      const response = await apiClient.askStream(currentInput);
      if (!response.body) {
        throw new ApiError("No response body", 500, "NO_RESPONSE_BODY");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let botText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        botText += decoder.decode(value, { stream: true });
        updateMessage(activeChatId, botMsgId, sanitizeText(botText));
      }

      logTelemetry("chat.response_complete", {
        chatId: activeChatId,
        length: botText.length,
      });
    } catch (error) {
      const apiError = error instanceof ApiError ? error : new ApiError("Unknown error", 500, "UNKNOWN");

      if (apiError.status === 401 || apiError.code === "NO_REFRESH_TOKEN") {
        authStorage.clearAll();
        navigate("/");
        return;
      }

      toast.error(apiError.traceId ? `${apiError.message} (trace: ${apiError.traceId})` : apiError.message);
      updateMessage(
        activeChatId,
        botMsgId,
        sanitizeText(`⚠️ ${apiError.message}\n\nCheck server availability at ${config.apiBaseUrl}.`),
      );

      logTelemetry("chat.error", {
        status: apiError.status,
        code: apiError.code,
        traceId: apiError.traceId,
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteChat = () => {
    if (!deleteChatId) return;

    deleteChat(deleteChatId);
    if (activeChatId === deleteChatId && chats.length <= 1) {
      createChat();
    }
    setDeleteChatId(null);
  };

  const handleLogout = () => {
    authStorage.clearAll();
    resetChats();
    setShowLogoutDialog(false);
    navigate("/");
  };

  return (
    <div className="flex h-screen bg-background text-foreground">
      <aside
        className={`${sidebarOpen ? "w-[340px]" : "w-0"} z-20 flex flex-col overflow-hidden border-r border-border transition-all duration-300`}
        style={{ background: "linear-gradient(180deg, hsl(var(--brand-start)) 0%, hsl(var(--brand-end)) 100%)" }}
      >
        <div className="flex-shrink-0 px-8 pb-8 pt-10">
          <h1 className="text-2xl font-extrabold tracking-wide text-primary-foreground">ACADEME RAG</h1>
        </div>

        <div className="px-6">
          <button
            onClick={handleNewChat}
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/10 py-4 text-base font-bold text-primary-foreground transition-all hover:bg-white/20"
          >
            <Plus size={20} /> New Chat
          </button>
        </div>

        <div className="mt-8 flex-1 overflow-y-auto px-6">
          <p className="mb-4 px-2 text-xs font-bold uppercase tracking-wider text-white/60">Previous Chats</p>
          {chats.map((chat) => (
            <button
              key={chat.id}
              className={`group mb-3 flex w-full items-center gap-3 rounded-xl px-4 py-4 text-left text-sm transition-all ${
                chat.id === activeChatId ? "bg-white/20 font-semibold text-white" : "text-white/80 hover:bg-white/10"
              }`}
              onClick={() => setActiveChat(chat.id)}
            >
              <MessageSquare size={18} className="opacity-70" />
              <span className="flex-1 truncate text-base">{chat.title}</span>
              <span
                onClick={(event) => {
                  event.stopPropagation();
                  setDeleteChatId(chat.id);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setDeleteChatId(chat.id);
                  }
                }}
                className="opacity-0 transition-opacity group-hover:opacity-100"
                role="button"
                tabIndex={0}
                aria-label={`Delete ${chat.title}`}
              >
                <X size={16} />
              </span>
            </button>
          ))}
        </div>

        <div className="flex-shrink-0 border-t border-white/10 p-6">
          {config.featureFlags.diagnosticsPanel && (
            <button
              onClick={() => setShowDiagnostics((current) => !current)}
              className="mb-3 w-full rounded-xl border border-white/20 py-3 text-sm font-bold uppercase tracking-wider text-primary-foreground hover:bg-white/10"
            >
              Diagnostics
            </button>
          )}
          <button
            onClick={() => setShowLogoutDialog(true)}
            className="flex w-full items-center justify-center gap-2 rounded-xl py-4 text-sm font-bold uppercase tracking-wider text-primary-foreground/90 transition-all hover:bg-red-500/20 hover:text-white"
          >
            <LogOut size={18} /> Logout
          </button>
        </div>
      </aside>

      <main className="relative flex h-screen flex-1 flex-col bg-background">
        {!sidebarOpen && (
          <div className="absolute left-4 top-4 z-50">
            <button
              onClick={() => setSidebarOpen(true)}
              className="rounded-full bg-card p-2 text-foreground shadow-md ring-1 ring-border hover:text-primary"
            >
              <Menu size={24} />
            </button>
          </div>
        )}

        {(isOffline || !config.featureFlags.chatEnabled) && (
          <div className="mx-6 mt-4 flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="status">
            <AlertTriangle size={16} />
            {isOffline
              ? "Offline mode: requests are paused until your connection is restored."
              : "Chat is disabled by feature flag kill-switch."}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 py-8 pb-32">
          <div className="mx-auto max-w-[1000px] space-y-8" role="log" aria-live="polite" aria-relevant="additions text">
            {activeChat?.messages.map((msg) => (
              msg.role === "assistant" && msg.content.trim() === "" ? null :
              <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                {msg.role === "assistant" && (
                  <div className="mr-4 mt-1 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg">
                    <Bot size={24} />
                  </div>
                )}

                <div
                  className={`max-w-[80%] rounded-[24px] px-8 py-5 text-[16px] leading-relaxed shadow-md ${
                    msg.role === "user"
                      ? "rounded-br-sm bg-primary text-primary-foreground"
                      : "rounded-bl-sm border border-border bg-card text-card-foreground"
                  }`}
                >
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                </div>
              </div>
            ))}

            {isWaitingForFirstChunk && (
              <div className="flex justify-start">
                <div className="mr-4 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg">
                  <Bot size={24} />
                </div>
                <div className="flex items-center gap-2 rounded-[24px] border border-border bg-card px-8 py-5 shadow-md">
                  <div className="h-2.5 w-2.5 animate-bounce rounded-full bg-primary"></div>
                  <div className="h-2.5 w-2.5 animate-bounce rounded-full bg-primary delay-100"></div>
                  <div className="h-2.5 w-2.5 animate-bounce rounded-full bg-primary delay-200"></div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="absolute bottom-8 left-0 right-0 px-6">
          <div className="mx-auto max-w-[1000px]">
            <form
              onSubmit={handleSend}
              className="flex items-center gap-4 rounded-full border border-border bg-card p-2 shadow-elevated transition-all focus-within:ring-2 focus-within:ring-ring"
            >
              <input
                type="text"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder={config.featureFlags.chatEnabled ? "Ask about your documents..." : "Chat temporarily disabled"}
                disabled={isLoading || !config.featureFlags.chatEnabled || isOffline}
                className="flex-1 bg-transparent px-6 py-4 text-base text-foreground placeholder:text-muted-foreground outline-none"
                aria-label="Ask a question"
              />
              <button
                type="submit"
                disabled={isLoading || !input.trim() || !config.featureFlags.chatEnabled || isOffline}
                className={`rounded-full p-4 text-primary-foreground transition-all hover:scale-105 ${
                  isLoading || !input.trim() || !config.featureFlags.chatEnabled || isOffline
                    ? "cursor-not-allowed bg-muted"
                    : "bg-gradient-to-r from-primary to-primary/80 shadow-lg"
                }`}
              >
                <Rocket size={24} className={isLoading ? "animate-pulse" : ""} />
              </button>
            </form>
            <p className="mt-3 text-center text-xs font-medium text-muted-foreground">AcademeRAG can make mistakes. Verify important information.</p>
          </div>
        </div>

        {showDiagnostics && config.featureFlags.diagnosticsPanel && (
          <div className="absolute right-6 top-20 z-30 max-h-[40vh] w-[420px] overflow-auto rounded-xl border border-border bg-card p-4 shadow-2xl">
            <h3 className="mb-3 text-sm font-semibold">Client Diagnostics</h3>
            <pre className="text-xs text-muted-foreground">{JSON.stringify(getTelemetryEvents().slice(-20), null, 2)}</pre>
          </div>
        )}
      </main>

      {showLogoutDialog && (
        <ConfirmDialog
          open={showLogoutDialog}
          onClose={() => setShowLogoutDialog(false)}
          onConfirm={handleLogout}
          title="Sign Out"
          description="Are you sure you want to sign out of your account?"
        />
      )}

      {deleteChatId && (
        <ConfirmDialog
          open={Boolean(deleteChatId)}
          onClose={() => setDeleteChatId(null)}
          onConfirm={handleDeleteChat}
          title="Delete Chat"
          description="This will permanently delete your conversation history."
        />
      )}
    </div>
  );
};

export default ChatPage;
