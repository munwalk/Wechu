// src/main.jsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";   // ✅ App.jsx에서 라우팅 관리
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />   {/* ✅ App.jsx 불러오기 */}
  </React.StrictMode>
);