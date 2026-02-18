import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";
import { initializeClientTelemetry } from "@/lib/telemetry";

initializeClientTelemetry();

createRoot(document.getElementById("root")!).render(<App />);
