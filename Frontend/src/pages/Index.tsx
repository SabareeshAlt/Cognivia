import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Bot, MessageSquare, Sparkles, Zap } from "lucide-react";

const Index = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="text-center max-w-3xl">
        <div className="mb-8 inline-block">
          <div className="w-32 h-32 rounded-full bg-card border-2 border-primary flex items-center justify-center glow-primary animate-glow mx-auto">
            <Bot className="w-16 h-16 text-primary" />
          </div>
        </div>

        <h1 className="text-5xl md:text-6xl font-bold text-primary glow-text mb-4 animate-fade-in">
          ACADEMERAG
        </h1>
        <p className="text-xl text-secondary-foreground mb-2 tracking-wider">
          College Assistant
        </p>
        <p className="text-muted-foreground mb-12 max-w-2xl mx-auto">
          Your intelligent companion for navigating college life. Get instant answers about admissions, 
          courses, placements, facilities, and more.
        </p>

        <div className="grid md:grid-cols-3 gap-6 mb-12">
          <div className="bg-card border border-border rounded-xl p-6 hover:border-primary/50 transition-all">
            <MessageSquare className="w-8 h-8 text-primary mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2 text-foreground">24/7 Support</h3>
            <p className="text-sm text-muted-foreground">
              Get instant answers to your questions anytime, anywhere
            </p>
          </div>
          <div className="bg-card border border-border rounded-xl p-6 hover:border-primary/50 transition-all">
            <Sparkles className="w-8 h-8 text-primary mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2 text-foreground">AI-Powered</h3>
            <p className="text-sm text-muted-foreground">
              Advanced AI technology for accurate and helpful responses
            </p>
          </div>
          <div className="bg-card border border-border rounded-xl p-6 hover:border-primary/50 transition-all">
            <Zap className="w-8 h-8 text-primary mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2 text-foreground">Instant Answers</h3>
            <p className="text-sm text-muted-foreground">
              Lightning-fast responses to all your college-related queries
            </p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Button
            onClick={() => navigate("/login")}
            className="bg-primary text-primary-foreground hover:bg-primary/90 h-14 px-8 text-lg font-bold tracking-wider glow-primary transition-all duration-300"
          >
            GET STARTED
          </Button>
          <Button
            onClick={() => navigate("/chat")}
            variant="outline"
            className="border-primary text-primary hover:bg-primary/10 h-14 px-8 text-lg font-bold tracking-wider transition-all duration-300"
          >
            SKIP TO CHAT
          </Button>
        </div>
      </div>
    </div>
  );
};

export default Index;
