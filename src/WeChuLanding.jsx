import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowUpRight, Send } from "lucide-react";
import { motion } from "framer-motion";

// 질문 예시 배열
const questions = [
  "VT 전공 학생인데 수업 추천해줘",
  "대학원 진학이랑 취업 중 어떤걸 선택하면 좋을까?",
  "재수강 규정이 어떻게 돼?",
  "정보융합학부 졸업을 위해 필요한 이수 조건이 어떻게 돼?",
  "국가장학금을 받으려면 성적 기준이 어떻게 돼?",
  "정보융합학부인데, 졸업하려면 졸업 논문 필수야?",
  "요즘 건강이 안 좋아서 학점이 떨어지고 있어.ㅠㅠ ",
  "학교 공부가 너무 힘들어서 자퇴하고 싶어..."
];

function CardItem({ text, onClick }) {
  return (
    <motion.button
      whileHover={{ y: -2, scale: 1.01 }}
      whileTap={{ scale: 0.99 }}
      className="group relative w-80 h-28 rounded-[10px] bg-white outline outline-1 outline-neutral-200 
                 shadow-[0px_1.018px_2.29px_rgba(0,0,0,0.13),0px_0.191px_0.573px_rgba(0,0,0,0.11)]
                 overflow-hidden px-6 py-4 text-center"
      onClick={onClick}
    >
      <p className="text-black text-xl font-normal font-['Pretendard'] leading-snug break-keep">
        {text}
      </p>
      <span className="absolute right-3 top-3 inline-flex h-6 w-6 items-center justify-center rounded-full border border-neutral-200 bg-white text-neutral-700 transition group-hover:border-neutral-300">
        <ArrowUpRight className="h-4 w-4" />
      </span>
    </motion.button>
  );
}

export default function WeChuLanding() {
  const navigate = useNavigate();
  const [userMessage, setUserMessage] = useState("");

  const handleSend = () => {
    if (!userMessage.trim()) return;
    navigate("/chat", { state: { question: userMessage } }); // ✅ 질문 전달
    setUserMessage("");
  };

  return (
    <div
      className="relative min-h-screen w-full overflow-hidden"
      style={{
        background:
        "linear-gradient(245deg, #DED6FF -10.92%, #F3E2E8 38.7%, rgba(247, 236, 240, 0.95) 76.13%, #FFF 110.9%)",
      }}
    >
      <main className="mx-auto flex max-w-[1348px] flex-col items-center gap-14 px-6 pt-[180px] pb-36">
        {/* 타이틀 */}
        <div className="flex flex-col items-center gap-4 w-[434px] text-center">
          <motion.h2
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="text-zinc-900 text-[32px] leading-[40px] font-extrabold font-['Pretendard']"
          >
            나만의 길을 찾는 여정
          </motion.h2>
          <motion.h1
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.05 }}
            className="text-[#5F37FF] text-[39px] leading-[48px] font-extrabold font-['Pretendard'] text-center"
          >
            WEcHU
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="text-[#52575C] text-[16px] leading-[24px] font-normal font-['Pretendard'] text-center"
          >
            Hyper Clova X로 구현된 AI 진로상담 챗봇 WEcHU는 <br />
            여러분들의 꿈을 언제나 응원합니다.
          </motion.p>
        </div>

        {/* 카드 그리드 */}
        <section className="grid grid-cols-4 gap-5">
          {questions.map((q, i) => (
            <CardItem
              key={i}
              text={q}
              onClick={() => navigate("/chat", { state: { question: q } })} // ✅ 카드 클릭 시도 질문 전달
            />
          ))}
        </section>
      </main>

      {/* 하단 입력창 */}
      <div className="fixed inset-x-0 bottom-0 z-10 bg-white/40 backdrop-blur-[50px]">
        <div className="mx-auto flex max-w-4xl items-center gap-2 px-4 py-4">
          <div className="flex w-full items-center justify-between rounded-2xl bg-neutral-200 px-5 py-3">
            <input
              value={userMessage}
              onChange={(e) => setUserMessage(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              className="w-full bg-transparent text-[#737373] text-[14px] leading-[20px] font-normal font-['Pretendard'] outline-none placeholder:text-[#737373]"
              placeholder="KW_VIZER와 이야기 나눠보세요!"
            />
            <button
              onClick={handleSend}
              className="ml-3 inline-flex h-9 w-9 items-center justify-center rounded-full border border-neutral-200 bg-white text-neutral-700 transition hover:bg-neutral-50">
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}