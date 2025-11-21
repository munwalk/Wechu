import React from "react";
import { useNavigate } from "react-router-dom";

export default function MainPage() {
  const navigate = useNavigate();

  return (
    <div
      className="relative min-h-screen w-full flex flex-col items-center justify-center bg-cover bg-center"
      style={{
        backgroundImage: `
          url('/main-bg2.png'),
          linear-gradient(
            245deg,
            #DED6FF -10.92%,
            #F3E2E8 38.7%,
            rgba(247, 236, 240, 0.95) 76.13%,
            #FFF 110.9%
          )
        `,
        backgroundSize: "cover",
        backgroundRepeat: "no-repeat",
        backgroundPosition: "center",
      }}
    >
      {/* 글자 영역 */}
      <div className="w-[482px] inline-flex flex-col justify-center items-start gap-6 -ml-[500px]">
        <div className="self-stretch text-[#1D1C24] text-[57px] font-extrabold font-['Pretendard']">
          나만의 길을 찾는 여정
        </div>

        <div className="self-stretch text-[#5F37FF] text-[57px] font-extrabold font-['Pretendard']">
          WEcHU
        </div>

        <div className="self-stretch text-[#52575C] text-[20px] font-normal font-['Pretendard']">
          Hyper Clova X로 구현된 AI 진로상담 챗봇 WEcHU는 <br />
          여러분들의 꿈을 언제나 응원합니다.
        </div>

        {/* 버튼 */}
        <div
          className="w-[326.48px] h-[68.25px] relative cursor-pointer"
          onClick={() => navigate("/landing")}
        >
          {/* ✅ 새로운 그라데이션 색상 적용 */}
          <div className="absolute inset-0 bg-gradient-to-br from-[#EC74E7] to-[#8468F5] rounded-[30px]" />

          {/* ✅ 글씨 중앙 정렬 */}
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-white text-[28px] font-bold font-['Pretendard']">
              WEcHU와 대화하기
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}