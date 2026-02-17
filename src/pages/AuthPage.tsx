import { useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";

const AuthPage = () => {
  const [isSignUp, setIsSignUp] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [signInForm, setSignInForm] = useState({ email: "", password: "" });
  const [signUpForm, setSignUpForm] = useState({ name: "", email: "", password: "" });
  const navigate = useNavigate();

  const handleSignIn = (e: React.FormEvent) => {
    e.preventDefault();
    navigate("/chat");
  };

  const handleSignUp = (e: React.FormEvent) => {
    e.preventDefault();
    navigate("/chat");
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="relative flex h-[600px] w-full max-w-[900px] overflow-hidden rounded-2xl bg-card shadow-2xl">
        {/* Sign In Form */}
        <div className="flex w-1/2 flex-col items-center justify-center px-10">
          <h2 className="mb-2 text-3xl font-bold text-foreground">Sign in</h2>
          <p className="mb-8 text-muted-foreground">Welcome back! Please enter your details.</p>
          <form onSubmit={handleSignIn} className="w-full max-w-[320px] space-y-4">
            <div className="relative">
              <input
                type="email"
                placeholder="Email"
                value={signInForm.email}
                onChange={(e) => setSignInForm({ ...signInForm, email: e.target.value })}
                className="w-full rounded-full bg-muted px-5 py-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                placeholder="Password"
                value={signInForm.password}
                onChange={(e) => setSignInForm({ ...signInForm, password: e.target.value })}
                className="w-full rounded-full bg-muted px-5 py-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-ring"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            <div className="flex justify-center pt-2">
              <button
                type="submit"
                className="rounded-full bg-primary px-10 py-2.5 text-sm font-semibold uppercase tracking-wider text-primary-foreground transition-all hover:opacity-90"
              >
                Sign In
              </button>
            </div>
          </form>
        </div>

        {/* Sign Up Form */}
        <div className="flex w-1/2 flex-col items-center justify-center px-10">
          <h2 className="mb-6 text-3xl font-bold text-foreground">Create Account</h2>
          <form onSubmit={handleSignUp} className="w-full max-w-[320px] space-y-4">
            <input
              type="text"
              placeholder="Full Name"
              value={signUpForm.name}
              onChange={(e) => setSignUpForm({ ...signUpForm, name: e.target.value })}
              className="w-full rounded-lg bg-muted px-5 py-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-ring"
            />
            <input
              type="email"
              placeholder="Email"
              value={signUpForm.email}
              onChange={(e) => setSignUpForm({ ...signUpForm, email: e.target.value })}
              className="w-full rounded-lg bg-muted px-5 py-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-ring"
            />
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                placeholder="Password"
                value={signUpForm.password}
                onChange={(e) => setSignUpForm({ ...signUpForm, password: e.target.value })}
                className="w-full rounded-lg bg-muted px-5 py-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div className="flex justify-center pt-2">
              <button
                type="submit"
                className="rounded-full bg-primary px-10 py-2.5 text-sm font-semibold uppercase tracking-wider text-primary-foreground transition-all hover:opacity-90"
              >
                Sign Up
              </button>
            </div>
          </form>
        </div>

        {/* Sliding Blue Overlay */}
        <motion.div
          className="absolute top-0 h-full w-1/2 rounded-2xl flex flex-col items-center justify-center text-primary-foreground"
          style={{ background: "linear-gradient(135deg, hsl(234 72% 55%), hsl(224 80% 45%))" }}
          animate={{ x: isSignUp ? 0 : "100%" }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
        >
          {isSignUp ? (
            <>
              <h2 className="mb-4 text-3xl font-bold">Hello! Welcome!</h2>
              <button
                onClick={() => setIsSignUp(false)}
                className="rounded-full border-2 border-primary-foreground px-8 py-2 text-sm font-semibold uppercase tracking-wider transition-all hover:bg-primary-foreground/10"
              >
                Sign In
              </button>
            </>
          ) : (
            <>
              <h2 className="mb-4 text-3xl font-bold">Welcome Back!</h2>
              <button
                onClick={() => setIsSignUp(true)}
                className="rounded-full border-2 border-primary-foreground px-8 py-2 text-sm font-semibold uppercase tracking-wider transition-all hover:bg-primary-foreground/10"
              >
                Sign Up
              </button>
            </>
          )}
        </motion.div>
      </div>
    </div>
  );
};

export default AuthPage;
