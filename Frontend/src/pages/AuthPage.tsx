import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

import { apiClient, ApiError } from "@/lib/api-client";
import { authStorage } from "@/lib/auth";

const signInSchema = z.object({
  email: z.string().email("Provide a valid email"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

const signUpSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  email: z.string().email("Provide a valid email"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type SignInValues = z.infer<typeof signInSchema>;
type SignUpValues = z.infer<typeof signUpSchema>;

const AuthPage = () => {
  const [isSignUp, setIsSignUp] = useState(false);
  const [showSignInPassword, setShowSignInPassword] = useState(false);
  const [showSignUpPassword, setShowSignUpPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();
  const reduceMotion = useReducedMotion();

  const signInForm = useForm<SignInValues>({ resolver: zodResolver(signInSchema), mode: "onSubmit" });
  const signUpForm = useForm<SignUpValues>({ resolver: zodResolver(signUpSchema), mode: "onSubmit" });

  useEffect(() => {
    if (authStorage.getUser() && authStorage.getTokens()?.access) {
      navigate("/chat");
    }
  }, [navigate]);

  const overlayCopy = useMemo(
    () =>
      isSignUp
        ? {
            title: "Hello!",
            text: "Enter your personal details and start your journey with us.",
            action: "Sign Up",
            onClick: () => setIsSignUp(false),
          }
        : {
            title: "Welcome Back!",
            text: "To keep connected with us please login with your personal info.",
            action: "Sign In",
            onClick: () => setIsSignUp(true),
          },
    [isSignUp],
  );

  const handleSignIn = async (values: SignInValues) => {
    setIsSubmitting(true);
    try {
      await apiClient.login(values.email, values.password);
      toast.success("Welcome back!");
      navigate("/chat");
    } catch (error) {
      const message = error instanceof ApiError ? `${error.message}${error.traceId ? ` (trace: ${error.traceId})` : ""}` : "Login failed";
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSignUp = async (values: SignUpValues) => {
    setIsSubmitting(true);
    try {
      await apiClient.register(values.name, values.email, values.password);
      toast.success("Account created successfully!");
      navigate("/chat");
    } catch (error) {
      const message = error instanceof ApiError ? `${error.message}${error.traceId ? ` (trace: ${error.traceId})` : ""}` : "Registration failed";
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4 font-sans">
      <div className="relative flex h-[750px] w-full max-w-[1200px] overflow-hidden rounded-[var(--radius-2xl)] bg-card shadow-elevated">
        <section aria-label="Sign in" className="z-10 flex w-1/2 flex-col items-center justify-center px-16">
          <h1 className="mb-3 text-4xl font-bold text-foreground">Sign in</h1>
          <p className="mb-10 text-lg text-muted-foreground">Welcome back! Please enter your details.</p>
          <form onSubmit={signInForm.handleSubmit(handleSignIn)} className="w-full max-w-[400px] space-y-5" noValidate>
            <div>
              <label htmlFor="signin-email" className="mb-2 block text-sm font-medium text-foreground">
                Email
              </label>
              <input
                id="signin-email"
                type="email"
                {...signInForm.register("email")}
                className="w-full rounded-xl border border-border bg-background px-6 py-4 text-base text-foreground outline-none focus:ring-2 focus:ring-ring"
              />
              {signInForm.formState.errors.email && (
                <p role="alert" className="mt-2 text-sm text-destructive">
                  {signInForm.formState.errors.email.message}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="signin-password" className="mb-2 block text-sm font-medium text-foreground">
                Password
              </label>
              <div className="relative">
                <input
                  id="signin-password"
                  type={showSignInPassword ? "text" : "password"}
                  {...signInForm.register("password")}
                  className="w-full rounded-xl border border-border bg-background px-6 py-4 text-base text-foreground outline-none focus:ring-2 focus:ring-ring"
                />
                <button
                  type="button"
                  onClick={() => setShowSignInPassword((current) => !current)}
                  className="absolute right-5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label={showSignInPassword ? "Hide password" : "Show password"}
                >
                  {showSignInPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                </button>
              </div>
              {signInForm.formState.errors.password && (
                <p role="alert" className="mt-2 text-sm text-destructive">
                  {signInForm.formState.errors.password.message}
                </p>
              )}
            </div>
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-xl bg-primary px-10 py-4 text-base font-bold uppercase tracking-wider text-primary-foreground transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? "Signing In..." : "Sign In"}
            </button>
          </form>
        </section>

        <section aria-label="Sign up" className="absolute right-0 top-0 z-0 flex h-full w-1/2 flex-col items-center justify-center px-16">
          <h2 className="mb-8 text-4xl font-bold text-foreground">Create Account</h2>
          <form onSubmit={signUpForm.handleSubmit(handleSignUp)} className="w-full max-w-[400px] space-y-5" noValidate>
            <div>
              <label htmlFor="signup-name" className="mb-2 block text-sm font-medium text-foreground">
                Full Name
              </label>
              <input
                id="signup-name"
                type="text"
                {...signUpForm.register("name")}
                className="w-full rounded-xl border border-border bg-background px-6 py-4 text-base text-foreground outline-none focus:ring-2 focus:ring-ring"
              />
              {signUpForm.formState.errors.name && (
                <p role="alert" className="mt-2 text-sm text-destructive">
                  {signUpForm.formState.errors.name.message}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="signup-email" className="mb-2 block text-sm font-medium text-foreground">
                Email
              </label>
              <input
                id="signup-email"
                type="email"
                {...signUpForm.register("email")}
                className="w-full rounded-xl border border-border bg-background px-6 py-4 text-base text-foreground outline-none focus:ring-2 focus:ring-ring"
              />
              {signUpForm.formState.errors.email && (
                <p role="alert" className="mt-2 text-sm text-destructive">
                  {signUpForm.formState.errors.email.message}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="signup-password" className="mb-2 block text-sm font-medium text-foreground">
                Password
              </label>
              <div className="relative">
                <input
                  id="signup-password"
                  type={showSignUpPassword ? "text" : "password"}
                  {...signUpForm.register("password")}
                  className="w-full rounded-xl border border-border bg-background px-6 py-4 text-base text-foreground outline-none focus:ring-2 focus:ring-ring"
                />
                <button
                  type="button"
                  onClick={() => setShowSignUpPassword((current) => !current)}
                  className="absolute right-5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label={showSignUpPassword ? "Hide password" : "Show password"}
                >
                  {showSignUpPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                </button>
              </div>
              {signUpForm.formState.errors.password && (
                <p role="alert" className="mt-2 text-sm text-destructive">
                  {signUpForm.formState.errors.password.message}
                </p>
              )}
            </div>
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-xl bg-primary px-10 py-4 text-base font-bold uppercase tracking-wider text-primary-foreground transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? "Creating..." : "Sign Up"}
            </button>
          </form>
        </section>

        <motion.div
          className="absolute left-0 top-0 z-20 flex h-full w-1/2 flex-col items-center justify-center text-primary-foreground"
          style={{ background: "linear-gradient(135deg, hsl(var(--brand-start)) 0%, hsl(var(--brand-end)) 100%)" }}
          animate={reduceMotion ? { x: 0 } : { x: isSignUp ? "100%" : 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
        >
          <div className="flex flex-col items-center px-12 text-center">
            <h2 className="mb-6 text-5xl font-bold">{overlayCopy.title}</h2>
            <p className="mb-10 text-xl leading-relaxed text-primary-foreground/80">{overlayCopy.text}</p>
            <button
              onClick={overlayCopy.onClick}
              onMouseEnter={() => {
                import("./ChatPage");
              }}
              className="rounded-full border-2 border-primary-foreground px-12 py-3 text-sm font-bold uppercase tracking-wider transition-all hover:bg-primary-foreground hover:text-primary"
            >
              {overlayCopy.action}
            </button>
          </div>
        </motion.div>
      </div>
    </div>
  );
};

export default AuthPage;
