import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Bot, User, Lock, Eye, EyeOff, Mail } from "lucide-react";
import { toast } from "sonner";

const Login = () => {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [recoveryEmail, setRecoveryEmail] = useState("");
  const [signupData, setSignupData] = useState({
    username: "",
    email: "",
    password: "",
    confirmPassword: ""
  });
  const [showSignupPassword, setShowSignupPassword] = useState(false);
  const [forgotDialogOpen, setForgotDialogOpen] = useState(false);
  const [createAccountDialogOpen, setCreateAccountDialogOpen] = useState(false);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (username && password) {
      toast.success("Login successful!");
      navigate("/chat");
    } else {
      toast.error("Please enter username and password");
    }
  };

  const handleForgotPassword = (e: React.FormEvent) => {
    e.preventDefault();
    if (recoveryEmail) {
      toast.success("Recovery email sent! Please check your inbox.");
      setRecoveryEmail("");
      setForgotDialogOpen(false);
    } else {
      toast.error("Please enter your email address");
    }
  };

  const handleCreateAccount = (e: React.FormEvent) => {
    e.preventDefault();
    if (!signupData.username || !signupData.email || !signupData.password || !signupData.confirmPassword) {
      toast.error("Please fill in all fields");
      return;
    }
    if (signupData.password !== signupData.confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }
    toast.success("Account created successfully!");
    setSignupData({ username: "", email: "", password: "", confirmPassword: "" });
    setCreateAccountDialogOpen(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-md">
        <div className="border-glow bg-card rounded-2xl p-8 animate-fade-in">
          {/* Logo Section */}
          <div className="flex flex-col items-center mb-8">
            <div className="relative mb-6">
              <div className="w-24 h-24 rounded-full bg-card border-2 border-primary flex items-center justify-center glow-primary animate-glow">
                <Bot className="w-12 h-12 text-primary" />
              </div>
              <div className="absolute -top-1 -right-1 bg-primary text-primary-foreground text-xs px-2 py-1 rounded-full font-semibold">
                ChatBot
              </div>
            </div>
            <h1 className="text-4xl font-bold text-primary glow-text mb-2">
              ACADEMERAG
            </h1>
            <p className="text-secondary-foreground text-sm tracking-wider">
              College Assistant
            </p>
          </div>

          {/* Login Form */}
          <form onSubmit={handleLogin} className="space-y-4">
            <div className="relative">
              <Input
                type="text"
                placeholder="USERNAME"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="bg-input border-border text-foreground placeholder:text-muted-foreground pl-4 pr-20 h-12 rounded-lg"
              />
              <div className="absolute right-3 top-1/2 -translate-y-1/2 flex gap-2">
                <User className="w-4 h-4 text-muted-foreground" />
              </div>
            </div>

            <div className="relative">
              <Input
                type={showPassword ? "text" : "password"}
                placeholder="PASSWORD"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="bg-input border-border text-foreground placeholder:text-muted-foreground pl-4 pr-20 h-12 rounded-lg"
              />
              <div className="absolute right-3 top-1/2 -translate-y-1/2 flex gap-2">
                <Lock className="w-4 h-4 text-muted-foreground" />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="focus:outline-none"
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4 text-muted-foreground" />
                  ) : (
                    <Eye className="w-4 h-4 text-muted-foreground" />
                  )}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              className="w-full bg-primary text-primary-foreground hover:bg-primary/90 h-12 text-lg font-bold tracking-wider glow-primary transition-all duration-300"
            >
              LOGIN
            </Button>
          </form>

          {/* Footer Links */}
          <div className="flex items-center justify-center gap-4 mt-6 text-sm">
            <Dialog open={forgotDialogOpen} onOpenChange={setForgotDialogOpen}>
              <DialogTrigger asChild>
                <button className="text-primary hover:text-primary/80 transition-colors">
                  FORGOT CREDENTIALS
                </button>
              </DialogTrigger>
              <DialogContent className="bg-card border-primary/20">
                <DialogHeader>
                  <DialogTitle className="text-primary text-xl">Reset Password</DialogTitle>
                  <DialogDescription className="text-muted-foreground">
                    Enter your email address and we'll send you a recovery link.
                  </DialogDescription>
                </DialogHeader>
                <form onSubmit={handleForgotPassword} className="space-y-4 mt-4">
                  <div className="relative">
                    <Input
                      type="email"
                      placeholder="EMAIL ADDRESS"
                      value={recoveryEmail}
                      onChange={(e) => setRecoveryEmail(e.target.value)}
                      className="bg-input border-border text-foreground placeholder:text-muted-foreground pl-4 pr-12 h-12 rounded-lg"
                    />
                    <Mail className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  </div>
                  <Button
                    type="submit"
                    className="w-full bg-primary text-primary-foreground hover:bg-primary/90 h-12 font-bold tracking-wider"
                  >
                    SEND RECOVERY EMAIL
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
            
            <span className="text-muted-foreground">|</span>
            
            <Dialog open={createAccountDialogOpen} onOpenChange={setCreateAccountDialogOpen}>
              <DialogTrigger asChild>
                <button className="text-primary hover:text-primary/80 transition-colors">
                  CREATE ACCOUNT
                </button>
              </DialogTrigger>
              <DialogContent className="bg-card border-primary/20">
                <DialogHeader>
                  <DialogTitle className="text-primary text-xl">Create Account</DialogTitle>
                  <DialogDescription className="text-muted-foreground">
                    Fill in your details to create a new account.
                  </DialogDescription>
                </DialogHeader>
                <form onSubmit={handleCreateAccount} className="space-y-4 mt-4">
                  <div className="relative">
                    <Input
                      type="text"
                      placeholder="USERNAME"
                      value={signupData.username}
                      onChange={(e) => setSignupData({...signupData, username: e.target.value})}
                      className="bg-input border-border text-foreground placeholder:text-muted-foreground pl-4 pr-12 h-12 rounded-lg"
                    />
                    <User className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  </div>
                  <div className="relative">
                    <Input
                      type="email"
                      placeholder="EMAIL ADDRESS"
                      value={signupData.email}
                      onChange={(e) => setSignupData({...signupData, email: e.target.value})}
                      className="bg-input border-border text-foreground placeholder:text-muted-foreground pl-4 pr-12 h-12 rounded-lg"
                    />
                    <Mail className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  </div>
                  <div className="relative">
                    <Input
                      type={showSignupPassword ? "text" : "password"}
                      placeholder="PASSWORD"
                      value={signupData.password}
                      onChange={(e) => setSignupData({...signupData, password: e.target.value})}
                      className="bg-input border-border text-foreground placeholder:text-muted-foreground pl-4 pr-20 h-12 rounded-lg"
                    />
                    <div className="absolute right-3 top-1/2 -translate-y-1/2 flex gap-2">
                      <Lock className="w-4 h-4 text-muted-foreground" />
                      <button
                        type="button"
                        onClick={() => setShowSignupPassword(!showSignupPassword)}
                        className="focus:outline-none"
                      >
                        {showSignupPassword ? (
                          <EyeOff className="w-4 h-4 text-muted-foreground" />
                        ) : (
                          <Eye className="w-4 h-4 text-muted-foreground" />
                        )}
                      </button>
                    </div>
                  </div>
                  <div className="relative">
                    <Input
                      type={showSignupPassword ? "text" : "password"}
                      placeholder="CONFIRM PASSWORD"
                      value={signupData.confirmPassword}
                      onChange={(e) => setSignupData({...signupData, confirmPassword: e.target.value})}
                      className="bg-input border-border text-foreground placeholder:text-muted-foreground pl-4 pr-12 h-12 rounded-lg"
                    />
                    <Lock className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  </div>
                  <Button
                    type="submit"
                    className="w-full bg-primary text-primary-foreground hover:bg-primary/90 h-12 font-bold tracking-wider"
                  >
                    CREATE ACCOUNT
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
