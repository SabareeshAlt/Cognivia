import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Rocket, X, MessageSquare, Plus, LogOut, Menu } from "lucide-react";
import ConfirmDialog from "@/components/ConfirmDialog";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface Chat {
  id: string;
  title: string;
  messages: Message[];
}

const ChatPage = () => {
  const navigate = useNavigate();
  const [chats, setChats] = useState<Chat[]>([
    {
      id: "1",
      title: "What are mandatory disclo...",
      messages: [
        { id: "w", role: "assistant", content: "AcademeRAG Ready. Ask about your uploaded documents!" },
      ],
    },
  ]);
  const [activeChatId, setActiveChatId] = useState("1");
  const [input, setInput] = useState("");
  const [showLogoutDialog, setShowLogoutDialog] = useState(false);
  const [deleteChatId, setDeleteChatId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeChat = chats.find((c) => c.id === activeChatId);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeChat?.messages]);

  const handleNewChat = () => {
    const newChat: Chat = {
      id: Date.now().toString(),
      title: "New Chat",
      messages: [
        { id: "w", role: "assistant", content: "AcademeRAG Ready. Ask about your uploaded documents!" },
      ],
    };
    setChats([newChat, ...chats]);
    setActiveChatId(newChat.id);
  };

  const handleSend = () => {
    if (!input.trim() || !activeChat) return;
    const userMsg: Message = { id: Date.now().toString(), role: "user", content: input };
    const botMsg: Message = {
      id: (Date.now() + 1).toString(),
      role: "assistant",
      content: "I'm a frontend demo. Connect a backend to enable RAG-powered responses!",
    };

    setChats((prev) =>
      prev.map((c) => {
        if (c.id !== activeChatId) return c;
        const updated = { ...c, messages: [...c.messages, userMsg, botMsg] };
        if (c.title === "New Chat") updated.title = input.slice(0, 30) + (input.length > 30 ? "..." : "");
        return updated;
      })
    );
    setInput("");
  };

  const handleDeleteChat = () => {
    if (!deleteChatId) return;
    const remaining = chats.filter((c) => c.id !== deleteChatId);
    if (remaining.length === 0) {
      handleNewChat();
    } else {
      setChats(remaining);
      if (activeChatId === deleteChatId) setActiveChatId(remaining[0].id);
    }
    setDeleteChatId(null);
  };

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside
        className={`${sidebarOpen ? "w-72" : "w-0"} flex flex-col overflow-hidden transition-all duration-300`}
        style={{ background: "linear-gradient(180deg, hsl(234 72% 55%), hsl(224 80% 42%))" }}
      >
        <div className="flex-shrink-0 px-6 pt-6 pb-4">
          <h1 className="text-xl font-extrabold tracking-wide text-sidebar-foreground">ACADEME RAG</h1>
        </div>

        <div className="px-4">
          <button
            onClick={handleNewChat}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-sidebar-accent py-3 text-sm font-semibold text-sidebar-foreground transition-all hover:opacity-90"
          >
            <Plus size={16} /> New Chat
          </button>
        </div>

        <div className="mt-6 flex-1 overflow-y-auto px-4">
          <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-sidebar-foreground/60">
            Previous Chats
          </p>
          {chats.map((chat) => (
            <div
              key={chat.id}
              className={`group mb-1 flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2.5 text-sm transition-all ${
                chat.id === activeChatId
                  ? "bg-sidebar-foreground/15 text-sidebar-foreground"
                  : "text-sidebar-foreground/80 hover:bg-sidebar-foreground/10"
              }`}
              onClick={() => setActiveChatId(chat.id)}
            >
              <MessageSquare size={14} className="flex-shrink-0" />
              <span className="flex-1 truncate">{chat.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleteChatId(chat.id);
                }}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-sidebar-foreground/60 hover:text-sidebar-foreground"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>

        <div className="flex-shrink-0 p-4">
          <button
            onClick={() => setShowLogoutDialog(true)}
            className="flex w-full items-center justify-center gap-2 rounded-lg py-3 text-sm font-semibold uppercase tracking-wider text-sidebar-foreground transition-all hover:bg-sidebar-foreground/10"
          >
            <LogOut size={16} /> Logout
          </button>
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex flex-1 flex-col">
        {/* Top bar */}
        <div className="flex items-center gap-3 border-b border-border bg-card px-4 py-3">
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="text-muted-foreground hover:text-foreground">
            <Menu size={20} />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {activeChat?.messages.map((msg) => (
            <div key={msg.id} className={`mb-4 flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              {msg.role === "assistant" && (
                <div className="mr-3 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                  <Bot size={18} />
                </div>
              )}
              <div
                className={`max-w-[70%] rounded-2xl px-5 py-3 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-card text-card-foreground shadow-md border border-border"
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-border bg-card px-6 py-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-center gap-3 rounded-2xl border border-border bg-card px-4 py-2 shadow-sm"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your documents..."
              className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
            />
            <button type="submit" className="text-primary hover:opacity-80 transition-opacity">
              <Rocket size={22} />
            </button>
          </form>
        </div>
      </main>

      {/* Logout Dialog */}
      <ConfirmDialog
        open={showLogoutDialog}
        onClose={() => setShowLogoutDialog(false)}
        onConfirm={() => {
          setShowLogoutDialog(false);
          navigate("/");
        }}
        title="Logout?"
        description="Are you sure you want to exit?"
      />

      {/* Delete Chat Dialog */}
      <ConfirmDialog
        open={!!deleteChatId}
        onClose={() => setDeleteChatId(null)}
        onConfirm={handleDeleteChat}
        title="Delete Chat?"
        description="This conversation will be permanently removed."
      />
    </div>
  );
};

export default ChatPage;
