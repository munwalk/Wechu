import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import MainPage from "./MainPage";
import WeChuLanding from "./WeChuLanding";
import WeChuChat from "./WeChuChat";

function App() {
  return (
    <Router>
      <Routes>
        {/* ✅ 첫 화면은 MainPage */}
        <Route path="/" element={<MainPage />} />

        {/* 랜딩 → 카드 + 질문 입력 */}
        <Route path="/landing" element={<WeChuLanding />} />

        {/* 챗봇 화면 */}
        <Route path="/chat" element={<WeChuChat />} />
      </Routes>
    </Router>
  );
}

export default App;