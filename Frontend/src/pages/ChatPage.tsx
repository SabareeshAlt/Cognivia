import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Rocket, X, MessageSquare, Plus, LogOut, Menu, User } from "lucide-react";
import { toast } from "sonner";
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
  const [chats, setChats] = useState<Chat[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showLogoutDialog, setShowLogoutDialog] = useState(false);
  const [deleteChatId, setDeleteChatId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const activeChat = chats.find((c) => c.id === activeChatId);

  useEffect(() => {
    if (!localStorage.getItem("rag_user")) {
      navigate("/");
      return;
    }
    const saved = localStorage.getItem("rag_chats");
    if (saved) {
      const parsed = JSON.parse(saved);
      setChats(parsed);
      if (parsed.length > 0) setActiveChatId(parsed[0].id);
      else handleNewChat();
    } else {
      handleNewChat();
    }
  }, [navigate]);

  useEffect(() => {
    if (chats.length > 0) {
      localStorage.setItem("rag_chats", JSON.stringify(chats));
    }
  }, [chats]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeChat?.messages, isLoading]);

  const handleNewChat = () => {
    const newChat: Chat = {
      id: Date.now().toString(),
      title: "New Chat",
      messages: [
        { id: "intro", role: "assistant", content: "AcademeRAG Ready. Ask me about your uploaded documents!" },
      ],
    };
    setChats((prev) => [newChat, ...prev]);
    setActiveChatId(newChat.id);
  };

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || !activeChatId) return;

    const currentInput = input;
    setInput("");
    setIsLoading(true);

    const userMsg: Message = { id: Date.now().toString(), role: "user", content: currentInput };

    setChats((prev) =>
      prev.map((c) => {
        if (c.id !== activeChatId) return c;
        const updatedMsgs = [...c.messages, userMsg];
        let newTitle = c.title;
        if (c.title === "New Chat") {
           newTitle = currentInput.slice(0, 30) + (currentInput.length > 30 ? "..." : "");
        }
        return { ...c, title: newTitle, messages: updatedMsgs };
      })
    );

    try {
      const response = await fetch("http://127.0.0.1:8000/api/ask/stream/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: currentInput }),
      });

      if (!response.ok) throw new Error("Network error");
      if (!response.body) throw new Error("No response body");

      const botMsgId = (Date.now() + 1).toString();
      setChats((prev) =>
        prev.map((c) => 
          c.id === activeChatId 
            ? { ...c, messages: [...c.messages, { id: botMsgId, role: "assistant", content: "" }] } 
            : c
        )
      );

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let botText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        botText += decoder.decode(value, { stream: true });
        setChats((prev) =>
          prev.map((c) => {
            if (c.id !== activeChatId) return c;
            return {
              ...c,
              messages: c.messages.map((m) =>
                m.id === botMsgId ? { ...m, content: botText } : m
              ),
            };
          })
        );
      }

    } catch (error) {
      const errMsg = error instanceof Error ? error.message : "Unknown error";
      toast.error("Failed to connect to RAG server: " + errMsg);
      setChats((prev) =>
        prev.map((c) => 
          c.id === activeChatId 
            ? { ...c, messages: [...c.messages, { id: Date.now().toString(), role: "assistant", content: `⚠️ Connection Error: ${errMsg}\n\nCheck: Is the Django server running on http://127.0.0.1:8000?` }] } 
            : c
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteChat = () => {
    if (!deleteChatId) return;
    const remaining = chats.filter((c) => c.id !== deleteChatId);
    setChats(remaining);
    localStorage.setItem("rag_chats", JSON.stringify(remaining));
    if (remaining.length === 0) handleNewChat();
    else if (activeChatId === deleteChatId) setActiveChatId(remaining[0].id);
    setDeleteChatId(null);
  };

  const handleLogout = () => {
    localStorage.removeItem("rag_user");
    setShowLogoutDialog(false);
    navigate("/");
  };

  return (
    <div className="flex h-screen bg-gray-50 font-sans text-gray-900">
      {/* Sidebar */}
      <aside
        className={`${sidebarOpen ? "w-[340px]" : "w-0"} flex flex-col overflow-hidden transition-all duration-300 shadow-2xl z-20`}
        style={{ background: "linear-gradient(180deg, #355CDE 0%, #1a2a6c 100%)" }}
      >
        <div className="flex-shrink-0 px-8 pt-10 pb-8">
          <h1 className="text-2xl font-extrabold tracking-wide text-white">ACADEME RAG</h1>
        </div>

        <div className="px-6">
          <button
            onClick={handleNewChat}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-white/10 py-4 text-base font-bold text-white transition-all hover:bg-white/20 border border-white/10 shadow-lg"
          >
            <Plus size={20} /> New Chat
          </button>
        </div>

        <div className="mt-8 flex-1 overflow-y-auto px-6 scrollbar-thin scrollbar-thumb-white/20">
          <p className="mb-4 px-2 text-xs font-bold uppercase tracking-wider text-white/50">
            Previous Chats
          </p>
          {chats.map((chat) => (
            <div
              key={chat.id}
              className={`group mb-3 flex cursor-pointer items-center gap-3 rounded-xl px-4 py-4 text-sm transition-all ${
                chat.id === activeChatId
                  ? "bg-white/20 text-white font-semibold shadow-inner"
                  : "text-white/80 hover:bg-white/10"
              }`}
              onClick={() => setActiveChatId(chat.id)}
            >
              <MessageSquare size={18} className="flex-shrink-0 opacity-70" />
              <span className="flex-1 truncate text-base">{chat.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleteChatId(chat.id);
                }}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-white/50 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>
          ))}
        </div>

        <div className="flex-shrink-0 p-6 border-t border-white/10">
          <button
            onClick={() => setShowLogoutDialog(true)}
            className="flex w-full items-center justify-center gap-2 rounded-xl py-4 text-sm font-bold uppercase tracking-wider text-white/90 transition-all hover:bg-red-500/20 hover:text-white"
          >
            <LogOut size={18} /> Logout
          </button>
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex flex-1 flex-col relative bg-gray-50 h-screen">
        {/* Top bar (Hidden or Minimal) */}
        {!sidebarOpen && (
           <div className="absolute top-4 left-4 z-50">
              <button onClick={() => setSidebarOpen(true)} className="p-2 bg-white rounded-full shadow-md text-gray-600 hover:text-blue-600">
                <Menu size={24} />
              </button>
           </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-8 pb-32">
          <div className="max-w-[1000px] mx-auto space-y-8">
            {activeChat?.messages.map((msg) => (
              <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                
                {msg.role === "assistant" && (
                  <div className="mr-4 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white shadow-lg mt-1">
                    <Bot size={24} />
                  </div>
                )}

                <div
                  className={`max-w-[80%] rounded-[24px] px-8 py-5 text-[16px] leading-relaxed shadow-md ${
                    msg.role === "user"
                      ? "bg-blue-600 text-white rounded-br-sm"
                      : "bg-white text-gray-800 border border-gray-100 rounded-bl-sm"
                  }`}
                >
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                </div>
              </div>
            ))}
            
            {isLoading && (
               <div className="flex justify-start">
                  <div className="mr-4 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white shadow-lg">
                    <Bot size={24} />
                  </div>
                  <div className="bg-white px-8 py-5 rounded-[24px] border border-gray-100 shadow-md flex items-center gap-2">
                     <div className="w-2.5 h-2.5 bg-blue-500 rounded-full animate-bounce"></div>
                     <div className="w-2.5 h-2.5 bg-blue-500 rounded-full animate-bounce delay-100"></div>
                     <div className="w-2.5 h-2.5 bg-blue-500 rounded-full animate-bounce delay-200"></div>
                  </div>
               </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Floating Input Area (UPDATED) */}
        <div className="absolute bottom-8 left-0 right-0 px-6">
          <div className="max-w-[1000px] mx-auto">
            <form
              onSubmit={handleSend}
              className="flex items-center gap-4 rounded-full border border-gray-200 bg-white p-2 shadow-2xl transition-all hover:shadow-xl focus-within:ring-2 focus-within:ring-blue-500/50"
            >
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about your documents..."
                disabled={isLoading}
                className="flex-1 bg-transparent px-6 py-4 text-base text-gray-800 placeholder:text-gray-400 outline-none"
              />
              <button 
                type="submit" 
                disabled={isLoading || !input.trim()}
                className={`p-4 rounded-full text-white transition-all transform hover:scale-105 ${
                  isLoading || !input.trim() 
                    ? "bg-gray-300 cursor-not-allowed" 
                    : "bg-gradient-to-r from-blue-600 to-indigo-600 shadow-lg"
                }`}
              >
                <Rocket size={24} className={isLoading ? "animate-pulse" : ""} />
              </button>
            </form>
            <p className="text-center text-xs font-medium text-gray-400 mt-3 tracking-wide">
              AcademeRAG AI can make mistakes. Please verify important information.
            </p>
          </div>
        </div>
      </main>

      {/* Confirmation Dialogs */}
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
            open={!!deleteChatId}
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