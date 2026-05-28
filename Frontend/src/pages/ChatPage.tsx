import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Rocket, X, MessageSquare, Plus, LogOut, Menu, AlertTriangle, Square } from "lucide-react";
import { toast } from "sonner";
import DOMPurify from "dompurify";

import ConfirmDialog from "@/components/ConfirmDialog";
import { authStorage } from "@/lib/auth";
import { apiClient, ApiError } from "@/lib/api-client";
import { config } from "@/lib/config";
import { logTelemetry, getTelemetryEvents } from "@/lib/telemetry";
import { sanitizeText } from "@/lib/sanitize";
import { useChatStore } from "@/store/chat-store";

function escapeHtml(input: string): string {
  return input
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderInlineMarkdown(input: string): string {
  let text = escapeHtml(input);
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  return text;
}

function stripSubjectCodes(input: string): string {
  return input
    .replace(/\b\d{2,}[A-Z]{2,}\d{2,}[A-Z]?\b/g, " ")
    .replace(/\b[A-Z]{2,}\d{3,}[A-Z]?\b/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function isLikelyCourseCatalogLine(input: string): boolean {
  const text = input.trim();
  if (!text) return false;
  const numberTokens = (text.match(/\b\d{1,3}\b/g) || []).length;
  const titleCaseWords = (text.match(/\b[A-Z][a-zA-Z]+\b/g) || []).length;
  const hasCodeLikeToken = /\b(?:\d{2,}[A-Z]{2,}\d{2,}[A-Z]?|[A-Z]{2,}\d{3,}[A-Z]?)\b/.test(text);
  return hasCodeLikeToken || (numberTokens >= 2 && titleCaseWords >= 2);
}

function stripNumericNoise(input: string): string {
  let text = input.trim();
  // Remove repeated list/index prefixes like "1 1 ...", "1 21 ...", "2) 2) ..."
  text = text.replace(/^(?:(?:\d+|[ivxlcdm]+)\s*[.):-]?\s+){1,4}/i, "");
  if (isLikelyCourseCatalogLine(text)) {
    text = text.replace(/\b\d{1,3}\b/g, " ");
  }
  return text.replace(/\s{2,}/g, " ").trim();
}

function normalizeAssistantListItem(input: string): string {
  let text = input.trim();
  text = stripNumericNoise(text);
  // Remove semester prefixes when user asks for subject names only.
  text = text.replace(/^(?:semester|sem)\s*(?:no\.?|number)?\s*(?:\d+|[ivxlcdm]+)\s*[:-]\s*/i, "");
  text = stripSubjectCodes(text);
  text = stripNumericNoise(text);
  return text;
}

function normalizeAssistantParagraph(input: string): string {
  let text = input.trim();
  text = text.replace(/^(?:semester|sem)\s*(?:no\.?|number)?\s*(?:\d+|[ivxlcdm]+)\s*[:-]\s*/i, "");
  text = stripSubjectCodes(text);
  text = stripNumericNoise(text);
  return text;
}

export function markdownToSafeHtml(input: string, cleanAcademicNoise = false): string {
  const lines = input.split("\n");
  const chunks: string[] = [];
  let inCodeBlock = false;
  let codeBuffer: string[] = [];
  let listMode: "ul" | "ol" | null = null;

  const closeListIfOpen = () => {
    if (listMode === "ul") chunks.push("</ul>");
    if (listMode === "ol") chunks.push("</ol>");
    listMode = null;
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (line.startsWith("```")) {
      closeListIfOpen();
      if (inCodeBlock) {
        chunks.push(`<pre><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`);
        codeBuffer = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeBuffer.push(rawLine);
      continue;
    }

    if (!line.trim()) {
      closeListIfOpen();
      continue;
    }

    if (line.startsWith("### ")) {
      closeListIfOpen();
      chunks.push(`<h3>${renderInlineMarkdown(line.slice(4))}</h3>`);
      continue;
    }
    if (line.startsWith("## ")) {
      closeListIfOpen();
      chunks.push(`<h2>${renderInlineMarkdown(line.slice(3))}</h2>`);
      continue;
    }
    if (line.startsWith("# ")) {
      closeListIfOpen();
      chunks.push(`<h1>${renderInlineMarkdown(line.slice(2))}</h1>`);
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      if (listMode !== "ol") {
        closeListIfOpen();
        chunks.push("<ol>");
        listMode = "ol";
      }
      const itemText = cleanAcademicNoise
        ? normalizeAssistantListItem(line.replace(/^\d+\.\s+/, ""))
        : line.replace(/^\d+\.\s+/, "").trim();
      if (itemText) {
        chunks.push(`<li>${renderInlineMarkdown(itemText)}</li>`);
      }
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      if (listMode !== "ul") {
        closeListIfOpen();
        chunks.push("<ul>");
        listMode = "ul";
      }
      const itemText = cleanAcademicNoise
        ? normalizeAssistantListItem(line.replace(/^[-*]\s+/, ""))
        : line.replace(/^[-*]\s+/, "").trim();
      if (itemText) {
        chunks.push(`<li>${renderInlineMarkdown(itemText)}</li>`);
      }
      continue;
    }

    closeListIfOpen();
    const paragraphText = cleanAcademicNoise ? normalizeAssistantParagraph(line) : line.trim();
    if (paragraphText) {
      chunks.push(`<p>${renderInlineMarkdown(paragraphText)}</p>`);
    }
  }

  if (inCodeBlock && codeBuffer.length) {
    chunks.push(`<pre><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`);
  }
  closeListIfOpen();

  return DOMPurify.sanitize(chunks.join(""), {
    ALLOWED_TAGS: ["h1", "h2", "h3", "p", "ul", "ol", "li", "code", "pre", "strong", "em", "a", "br"],
    ALLOWED_ATTR: ["href", "target", "rel"],
  });
}

const ChatPage = () => {
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showLogoutDialog, setShowLogoutDialog] = useState(false);
  const [deleteChatId, setDeleteChatId] = useState<string | null>(null);
  const [isInternetOffline, setIsInternetOffline] = useState(!navigator.onLine);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  const chats = useChatStore((state) => state.chats);
  const activeChatId = useChatStore((state) => state.activeChatId);
  const createChat = useChatStore((state) => state.createChat);
  const setActiveChat = useChatStore((state) => state.setActiveChat);
  const deleteChat = useChatStore((state) => state.deleteChat);
  const appendMessage = useChatStore((state) => state.appendMessage);
  const updateMessage = useChatStore((state) => state.updateMessage);
  const updateTitleIfNew = useChatStore((state) => state.updateTitleIfNew);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const scrollRafRef = useRef<number | null>(null);
  const streamReaderRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  const streamTokenRef = useRef(0);
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
    const onOnline = () => setIsInternetOffline(false);
    const onOffline = () => setIsInternetOffline(true);

    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);

    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  useEffect(() => {
    return () => {
      if (scrollRafRef.current !== null) {
        cancelAnimationFrame(scrollRafRef.current);
      }
      streamAbortRef.current?.abort();
      streamReaderRef.current?.cancel().catch(() => undefined);
    };
  }, []);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container || !shouldAutoScrollRef.current) {
      return;
    }

    if (scrollRafRef.current !== null) {
      cancelAnimationFrame(scrollRafRef.current);
    }

    scrollRafRef.current = requestAnimationFrame(() => {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: isLoading ? "auto" : "smooth",
      });
      scrollRafRef.current = null;
    });
  }, [activeChat?.messages, isLoading]);

  useEffect(() => {
    const composer = composerRef.current;
    if (!composer) return;
    composer.style.height = "auto";
    composer.style.height = `${Math.min(composer.scrollHeight, 220)}px`;
  }, [input]);

  const handleNewChat = () => {
    createChat();
  };

  const stopStreaming = async () => {
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    if (streamReaderRef.current) {
      await streamReaderRef.current.cancel().catch(() => undefined);
      streamReaderRef.current = null;
    }
    setIsLoading(false);
  };

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!activeChatId) return;

    if (isLoading) {
      await stopStreaming();
    }
    if (!input.trim()) return;

    const currentInput = sanitizeText(input);
    setInput("");
    setIsLoading(true);
    const streamToken = ++streamTokenRef.current;

    appendMessage(activeChatId, { id: Date.now().toString(), role: "user", content: currentInput });
    updateTitleIfNew(activeChatId, currentInput);

    const botMsgId = `${Date.now()}-assistant`;
    appendMessage(activeChatId, { id: botMsgId, role: "assistant", content: "" });

    try {
      const controller = new AbortController();
      streamAbortRef.current = controller;
      const response = await apiClient.askStream(currentInput, { signal: controller.signal });
      if (!response.body) {
        throw new ApiError("No response body", 500, "NO_RESPONSE_BODY");
      }

      const reader = response.body.getReader();
      streamReaderRef.current = reader;
      const decoder = new TextDecoder();
      let botText = "";
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          if (trimmed.startsWith("data:")) {
            const dataStr = trimmed.slice(5).trim();
            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.type === "token") {
                botText += parsed.content;
                updateMessage(activeChatId, botMsgId, sanitizeText(botText));
              } else if (parsed.type === "error") {
                throw new ApiError(parsed.content || "An unexpected error occurred.", 500, "STREAM_ERROR");
              }
            } catch (e) {
              if (e instanceof ApiError) throw e;
            }
          }
        }
      }

      if (buffer.trim()) {
        const line = buffer.trim();
        if (line.startsWith("data:")) {
          const dataStr = line.slice(5).trim();
          try {
            const parsed = JSON.parse(dataStr);
            if (parsed.type === "token") {
              botText += parsed.content;
              updateMessage(activeChatId, botMsgId, sanitizeText(botText));
            } else if (parsed.type === "error") {
              throw new ApiError(parsed.content || "An unexpected error occurred.", 500, "STREAM_ERROR");
            }
          } catch (e) {
            // ignore
          }
        }
      }

      if (streamTokenRef.current !== streamToken) {
        return;
      }
      logTelemetry("chat.response_complete", {
        chatId: activeChatId,
        length: botText.length,
      });
    } catch (error) {
      const apiError = error instanceof ApiError ? error : new ApiError("Unknown error", 500, "UNKNOWN");
      const isAbort =
        apiError.code === "REQUEST_ABORTED" || (error instanceof DOMException && error.name === "AbortError");
      if (isAbort || streamTokenRef.current !== streamToken) {
        return;
      }

      if (apiError.status === 401 || apiError.code === "NO_REFRESH_TOKEN") {
        authStorage.clearAll();
        navigate("/");
        return;
      }

      toast.error(apiError.traceId ? `${apiError.message} (trace: ${apiError.traceId})` : apiError.message);
      updateMessage(
        activeChatId,
        botMsgId,
        sanitizeText(`⚠️ ${apiError.message}\n\nCheck server availability at ${apiClient.getActiveBaseUrl()}.`),
      );

      logTelemetry("chat.error", {
        status: apiError.status,
        code: apiError.code,
        traceId: apiError.traceId,
      });
    } finally {
      if (streamTokenRef.current === streamToken) {
        streamAbortRef.current = null;
        streamReaderRef.current = null;
        setIsLoading(false);
      }
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

        {(isInternetOffline || !config.featureFlags.chatEnabled) && (
          <div className="mx-6 mt-4 flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="status">
            <AlertTriangle size={16} />
            {isInternetOffline
              ? "Internet appears offline. AcademeRAG requests can still work until you're back online"
              : "Chat is disabled by feature flag kill-switch."}
          </div>
        )}

        <div
          ref={scrollContainerRef}
          onScroll={(event) => {
            const container = event.currentTarget;
            const distanceToBottom = container.scrollHeight - (container.scrollTop + container.clientHeight);
            shouldAutoScrollRef.current = distanceToBottom <= 120;
          }}
          className="flex-1 overflow-y-auto px-6 py-8 pb-32"
        >
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
                  <div
                    className="markdown-content text-inherit [&_a]:underline [&_a]:decoration-current [&_a:hover]:opacity-80 [&_code]:rounded [&_code]:bg-black/10 [&_code]:px-1.5 [&_code]:py-0.5 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-black/10 [&_pre]:p-3 [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_h1]:mb-3 [&_h1]:mt-1 [&_h1]:text-xl [&_h1]:font-bold [&_h2]:mb-2 [&_h2]:mt-1 [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:mb-2 [&_h3]:mt-1 [&_h3]:text-base [&_h3]:font-semibold [&_li]:mb-1 [&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-6 [&_p]:mb-3 [&_p:last-child]:mb-0 [&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-6"
                    dangerouslySetInnerHTML={{ __html: markdownToSafeHtml(msg.content, msg.role === "assistant") }}
                  />
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
              <textarea
                ref={composerRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void handleSend();
                  }
                }}
                placeholder={config.featureFlags.chatEnabled ? "Ask about your documents..." : "Chat temporarily disabled"}
                disabled={!config.featureFlags.chatEnabled}
                rows={1}
                className="flex-1 resize-none overflow-y-auto overflow-x-hidden bg-transparent px-6 py-4 text-base text-foreground placeholder:text-muted-foreground outline-none"
                aria-label="Ask a question"
              />
              {isLoading && (
                <button
                  type="button"
                  onClick={() => {
                    stopStreaming().catch(() => undefined);
                  }}
                  className="rounded-full bg-destructive p-4 text-destructive-foreground transition-all hover:opacity-90"
                  aria-label="Stop streaming"
                  title="Stop streaming"
                >
                  <Square size={20} />
                </button>
              )}
              <button
                type="submit"
                disabled={!input.trim() || !config.featureFlags.chatEnabled}
                className={`rounded-full p-4 text-primary-foreground transition-all hover:scale-105 ${
                  !input.trim() || !config.featureFlags.chatEnabled
                    ? "cursor-not-allowed bg-muted"
                    : "bg-gradient-to-r from-primary to-primary/80 shadow-lg"
                }`}
              >
                <Rocket size={24} />
              </button>
            </form>
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

