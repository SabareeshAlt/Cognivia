import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

const AuthPage = () => {
  const [isSignUp, setIsSignUp] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [signInForm, setSignInForm] = useState({ email: "", password: "" });
  const [signUpForm, setSignUpForm] = useState({ name: "", email: "", password: "" });
  const navigate = useNavigate();

  useEffect(() => {
    if (localStorage.getItem("rag_user")) {
      navigate("/chat");
    }
  }, [navigate]);

  const handleSignIn = (e: React.FormEvent) => {
    e.preventDefault();
    if ((signInForm.email === "admin@mail.com" && signInForm.password === "12345") || signInForm.email.length > 0) {
      localStorage.setItem("rag_user", JSON.stringify({ email: signInForm.email }));
      toast.success("Welcome back!");
      navigate("/chat");
    } else {
      toast.error("Invalid credentials");
    }
  };

  const handleSignUp = (e: React.FormEvent) => {
    e.preventDefault();
    if (signUpForm.email && signUpForm.password) {
      localStorage.setItem("rag_user", JSON.stringify({ email: signUpForm.email, name: signUpForm.name }));
      toast.success("Account created successfully!");
      navigate("/chat");
    } else {
      toast.error("Please fill in all fields");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100 p-4 font-['Poppins']">
      {/* Container: Large and Rounded */}
      <div className="relative flex h-[750px] w-full max-w-[1200px] overflow-hidden rounded-[30px] bg-white shadow-2xl">
        
        {/* Sign In Form (Left Side) */}
        <div className="flex w-1/2 flex-col items-center justify-center px-16 z-10">
          <h2 className="mb-3 text-4xl font-bold text-gray-800">Sign in</h2>
          <p className="mb-10 text-lg text-gray-500">Welcome back! Please enter your details.</p>
          <form onSubmit={handleSignIn} className="w-full max-w-[400px] space-y-6">
            <div className="relative">
              <input
                type="email"
                placeholder="Email"
                value={signInForm.email}
                onChange={(e) => setSignInForm({ ...signInForm, email: e.target.value })}
                className="w-full rounded-xl bg-gray-50 px-6 py-4 text-base text-gray-800 placeholder:text-gray-400 outline-none focus:ring-2 focus:ring-blue-500 border border-gray-100"
              />
            </div>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                placeholder="Password"
                value={signInForm.password}
                onChange={(e) => setSignInForm({ ...signInForm, password: e.target.value })}
                className="w-full rounded-xl bg-gray-50 px-6 py-4 text-base text-gray-800 placeholder:text-gray-400 outline-none focus:ring-2 focus:ring-blue-500 border border-gray-100"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
            <div className="flex justify-center pt-4">
              <button
                type="submit"
                className="w-full rounded-xl bg-blue-600 px-10 py-4 text-base font-bold uppercase tracking-wider text-white transition-all hover:bg-blue-700 hover:shadow-lg hover:-translate-y-0.5"
              >
                Sign In
              </button>
            </div>
          </form>
        </div>

        {/* Sign Up Form (Right Side) */}
        <div className="absolute right-0 top-0 flex h-full w-1/2 flex-col items-center justify-center px-16 z-0">
          <h2 className="mb-8 text-4xl font-bold text-gray-800">Create Account</h2>
          <form onSubmit={handleSignUp} className="w-full max-w-[400px] space-y-5">
            <input
              type="text"
              placeholder="Full Name"
              value={signUpForm.name}
              onChange={(e) => setSignUpForm({ ...signUpForm, name: e.target.value })}
              className="w-full rounded-xl bg-gray-50 px-6 py-4 text-base text-gray-800 placeholder:text-gray-400 outline-none focus:ring-2 focus:ring-blue-500 border border-gray-100"
            />
            <input
              type="email"
              placeholder="Email"
              value={signUpForm.email}
              onChange={(e) => setSignUpForm({ ...signUpForm, email: e.target.value })}
              className="w-full rounded-xl bg-gray-50 px-6 py-4 text-base text-gray-800 placeholder:text-gray-400 outline-none focus:ring-2 focus:ring-blue-500 border border-gray-100"
            />
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                placeholder="Password"
                value={signUpForm.password}
                onChange={(e) => setSignUpForm({ ...signUpForm, password: e.target.value })}
                className="w-full rounded-xl bg-gray-50 px-6 py-4 text-base text-gray-800 placeholder:text-gray-400 outline-none focus:ring-2 focus:ring-blue-500 border border-gray-100"
              />
            </div>
            <div className="flex justify-center pt-4">
              <button
                type="submit"
                className="w-full rounded-xl bg-blue-600 px-10 py-4 text-base font-bold uppercase tracking-wider text-white transition-all hover:bg-blue-700 hover:shadow-lg hover:-translate-y-0.5"
              >
                Sign Up
              </button>
            </div>
          </form>
        </div>

        {/* Sliding Blue Overlay */}
        <motion.div
          className="absolute top-0 left-0 h-full w-1/2 flex flex-col items-center justify-center text-white z-20"
          style={{ background: "linear-gradient(135deg, #355CDE 0%, #1a2a6c 100%)" }}
          animate={{ x: isSignUp ? "100%" : 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
        >
          {isSignUp ? (
            <div className="flex flex-col items-center px-12 text-center">
              <h2 className="mb-6 text-5xl font-bold">Hello!</h2>
              <p className="mb-10 text-xl text-blue-100 leading-relaxed">Enter your personal details and start your journey with us.</p>
              <button
                onClick={() => setIsSignUp(false)}
                className="rounded-full border-2 border-white px-12 py-3 text-sm font-bold uppercase tracking-wider transition-all hover:bg-white hover:text-blue-700"
              >
                Sign In
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center px-12 text-center">
              <h2 className="mb-6 text-5xl font-bold">Welcome Back!</h2>
              <p className="mb-10 text-xl text-blue-100 leading-relaxed">To keep connected with us please login with your personal info.</p>
              <button
                onClick={() => setIsSignUp(true)}
                className="rounded-full border-2 border-white px-12 py-3 text-sm font-bold uppercase tracking-wider transition-all hover:bg-white hover:text-blue-700"
              >
                Sign Up
              </button>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
};

export default AuthPage;