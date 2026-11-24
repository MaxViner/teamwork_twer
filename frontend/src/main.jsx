import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/findings.css";
import "./styles/dossier.css";
import "./styles/landmarks.css";
import "./styles/keyframes.css";
import "./styles/insights.css";
import "./styles/responsive.css";

createRoot(document.getElementById("root")).render(<App />);
