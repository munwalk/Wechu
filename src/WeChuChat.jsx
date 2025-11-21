import React, { useState, useEffect, useRef } from "react";
import { Send, ChevronDown, Home } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import axios from "axios";

const BACKEND_URL = "http://127.0.0.1:8000/chat_unified";

// Function to detect and parse a basic Markdown table block into a structured object
const parseTable = (tableBlock) => {
    const rawRows = tableBlock.split('\n').map(row => row.trim()).filter(row => row.startsWith('|'));
    if (rawRows.length < 2) return null; 

    const separatorIndex = rawRows.findIndex(row => /\|-+\|/g.test(row));
    if (separatorIndex === -1) return null;

    const headerRow = rawRows[0];
    const dataRows = rawRows.slice(separatorIndex + 1).filter(r => r.length > 0);

    const extractCells = (row) => row.replace(/^\||\|$/g, '').split('|').map(cell => cell.trim());

    const headers = extractCells(headerRow);
    const rows = dataRows.map(row => extractCells(row));

    // Basic structure validation
    if (headers.length === 0 || rows.some(row => row.length !== headers.length)) {
        return null;
    }

    return { headers, rows };
};

// Main content processing function to return blocks (paragraph or table) and citation
const processContent = (text) => {
    if (!text) return { blocks: [], citation: null };
    let content = String(text);
    let citationText = null;

    // --- 1. Citation Extraction and Cleanup ---
    // Handles server output like: (출처: \n* 출처1 \n* 출처2)
    const citationRegex = /(\(출처: [\s\S]*?\))(<br\s*\/?>)?$/i;
    const citationMatch = content.match(citationRegex);
    
    if (citationMatch) {
        // Extract content inside (출처: ...)
        citationText = citationMatch[1].replace(/^\(출처:\s*/, '').replace(/\)$/, '');
        content = content.replace(citationRegex, '').trim();
        
        // Clean up markdown list bullets (* ) and ensure line breaks are visible
        // citationText = citationText.replace(/\n\*\s*/g, ' | ').replace(/\|$/, '').trim();
        // citationText = citationText.replace(/^\s*\|\s*/, '').replace(/\n/g, ' | '); // Remove leading | if any
        citationText = citationText
            .replace(/\n\*\s*/g, ' | ')
            .replace(/^\*\s*/g, '')
            .replace(/\s*\|\s*$/g, '')
            .replace(/\n/g, ' | ')
            .trim();
      }

    // --- 2. Content Cleanup (Boilerplate removal) ---
    const boilerplateRegex = /^(.*?)(에 대해 (설명|안내|알려|정리)드리겠습니다\.?|입니다\.)\s*/i;
    content = content.replace(boilerplateRegex, '').trim();

    // --- 3. Block Splitting and Rendering ---
    const rawBlocks = content.split(/\n\s*\n/).filter(b => b.trim() !== '');

    const renderedBlocks = rawBlocks.map((block, index) => {
        block = block.trim();
        
        // A. Table Check (returns structured data)
        if (block.startsWith('|') && block.includes('|---|')) {
            const tableData = parseTable(block);
            if (tableData) {
                return { type: 'table', data: tableData, key: index }; // Store table data structure
            }
        }
        
        // B. Paragraph/Inline Content
        // Bold: Apply strong tag with font-weight 700 inline style (for inline HTML)
        let html = block.replace(/\*\*(.+?)\*\*/g, "<strong style='font-weight: 700;'>$1</strong>");
        // Replace single newlines with <br> inside the block for correct paragraph spacing
        html = html.replace(/\n/g, "<br />"); 

        return { type: 'paragraph', html: html, key: index };
    });

    return { blocks: renderedBlocks, citation: citationText };
};

// --- Response Renderer Component (Pure Component) ---
const ResponseRenderer = ({ content }) => {
    const { blocks, citation } = processContent(content);

    // Common style object for table components (using JSX object style)
    const tableStyle = {
        width: '100%',
        borderCollapse: 'collapse',
        margin: '15px 0',
        fontSize: '1em',
        borderRadius: '8px',
        overflow: 'hidden',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    };
    const headerRowStyle = {
        backgroundColor: '#4F46E5',
    };
    const headerCellStyle = {
        padding: '12px 15px',
        textAlign: 'left',
        fontWeight: '700',
        color: '#ffffff',
        border: '1px solid #4338CA',
    };
    const dataCellStyle = (bgColor) => ({
        padding: '12px 15px',
        textAlign: 'left',
        color: '#4b5563',
        border: '1px solid #f3f4f6',
        backgroundColor: bgColor,
        borderBottom: '1px solid #e5e7eb',
    });

    // Helper to safely render HTML content
    const renderContent = (htmlContent) => ({ __html: htmlContent });

    return (
        <div className="flex flex-col gap-4">
            {blocks.map(block => (
                <React.Fragment key={block.key}>
                    {block.type === 'paragraph' ? (
                        <p 
                            className="text-[20px] leading-[30px] font-normal font-['Pretendard'] text-[#292929CC]"
                            dangerouslySetInnerHTML={renderContent(block.html)}
                        />
                    ) : block.type === 'table' ? (
                        <div className="overflow-x-auto">
                            <table style={tableStyle}>
                                <thead>
                                    <tr style={headerRowStyle}>
                                        {block.data.headers.map((h, i) => (
                                            <th key={i} style={headerCellStyle}>
                                                {h}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {block.data.rows.map((row, rowIndex) => {
                                        const bgColor = rowIndex % 2 === 0 ? '#f9fafb' : '#ffffff';
                                        return (
                                            <tr key={rowIndex}>
                                                {row.map((c, cellIndex) => {
                                                    // Apply bolding to cell content if needed
                                                    const cellHtml = c.replace(/\*\*(.+?)\*\*/g, "<strong style='font-weight: 700;'>$1</strong>");
                                                    return (
                                                        <td 
                                                            key={cellIndex} 
                                                            style={dataCellStyle(bgColor)}
                                                            dangerouslySetInnerHTML={renderContent(cellHtml)}
                                                        />
                                                    );
                                                })}
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    ) : null}
                </React.Fragment>
            ))}

                    {citation && (
                      <div className="text-sm pt-4 mt-2 border-t border-neutral-100 font-['Pretendard']">
                          <span className="text-neutral-500">(출처: </span>
                          <span 
                              className="font-bold text-blue-600"
                              dangerouslySetInnerHTML={{ __html: citation }}
                          />
                          <span className="text-neutral-500">)</span>
                      </div>
                  )}
              </div>
          );
};


export default function WeChuChat() {
    const location = useLocation();
    const navigate = useNavigate();
    const initialQuestion = location.state?.question || "";

    const [userMessage, setUserMessage] = useState("");
    const [messages, setMessages] = useState([]);
    const [isThinking, setIsThinking] = useState(false);
    const [dots, setDots] = useState("");

    const [chatHistory, setChatHistory] = useState([]);
    const [chatState, setChatState] = useState({ phase: "explore" });

    const hasAskedInitial = useRef(false);
    const messagesEndRef = useRef(null);    

    const scrollToBottom = () => {          
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    };

    useEffect(() => {                       
        scrollToBottom();
    }, [messages]);


    useEffect(() => {
        scrollToBottom();
    }, [messages, isThinking]); 

    const handleSend = async (messageText = userMessage) => {
        if (!messageText.trim()) return;

        setMessages((prev) => [...prev, { role: "user", text: messageText }]);
        setUserMessage("");
        setIsThinking(true);

        try {
            const response = await axios.post(
                BACKEND_URL,
                {
                    query: messageText,
                    history: chatHistory,
                    state: chatState,
                },
                {
                    headers: {
                        "Content-Type": "application/json",
                    }
                }
            );

            const aiAnswer =
                response.data.answer ||
                "죄송합니다. 답변을 생성하지 못했습니다.";
            const newHistory = response.data.history || [];
            const newState = response.data.state || chatState;

            setChatHistory(newHistory);
            setChatState(newState);

            setMessages((prev) => [
                ...prev,
                { role: "ai", text: String(aiAnswer) }
            ]);
        } catch (error) {
            console.error("FastAPI 호출 오류:", error);
            setMessages((prev) => [
                ...prev,
                {
                    role: "ai",
                    text: "🚫 서버와 통신하는 중 오류가 발생했습니다. CORS 설정을 확인하거나, 백엔드 서버가 실행 중인지 확인해주세요.",
                },
            ]);
        } finally {
            setIsThinking(false);
        }
    };

    useEffect(() => {
        if (initialQuestion && !hasAskedInitial.current) {
            hasAskedInitial.current = true;
            handleSend(initialQuestion);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialQuestion]);

    useEffect(() => {
        if (!isThinking) {
            setDots("");
            return;
        }
        const interval = setInterval(() => {
            setDots((prev) => (prev.length < 3 ? prev + "." : ""));
        }, 500);
        return () => clearInterval(interval);
    }, [isThinking]);

    return (
        <div
            className="relative min-h-screen w-full overflow-hidden"
            style={{
                background:
                    "linear-gradient(245deg, #DED6FF -10.92%, #F3E2E8 38.7%, rgba(247, 236, 240, 0.95) 76.13%, #FFF 110.9%)",
            }}
        >
            {/* 홈 버튼 */}
            <button
                onClick={() => navigate("/landing")}
                className="fixed top-6 left-6 z-50 flex items-center gap-2 px-5 py-3 bg-white rounded-full shadow-lg hover:shadow-xl transition-all duration-200 group border border-neutral-200"
                style={{
                    backdropFilter: "blur(10px)",
                    backgroundColor: "rgba(255, 255, 255, 0.95)",
                }}
            >
                <Home className="w-5 h-5 text-[#292929CC] group-hover:text-[#4F46E5] transition-colors" />
                <span className="text-[16px] font-semibold font-['Pretendard'] text-[#292929CC] group-hover:text-[#4F46E5] transition-colors">
                    홈으로
                </span>
            </button>

            <main className="flex flex-col items-start px-6 pt-24 pb-40 gap-6 overflow-y-auto h-[calc(100vh-120px)]">
                {messages.map((msg, i) =>
                    msg.role === "user" ? (
                        <div key={i} className="flex justify-end w-full">
                            <div className="w-full max-w-[608px] min-h-[96px] mr-40 rounded-[10px] bg-white outline outline-1 outline-neutral-200 shadow">
                                <div className="px-6 pt-[24px] pb-4">
                                    <p className="w-[506px] text-[20px] leading-[28px] font-normal font-['Pretendard'] text-[#292929CC]">
                                        {msg.text}
                                    </p>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div key={i} className="w-full">
                            <div className="mt-6 ml-40 flex items-center gap-2">
                                <p className="text-[20px] font-bold font-['Pretendard'] text-[#292929CC]">
                                    WEcHU의 생각
                                </p>
                                <ChevronDown className="w-6 h-6 text-[#292929CC]" />
                            </div>
                            <div className="w-full max-w-[782px] mt-4 ml-40 rounded-[10px] bg-white outline outline-1 outline-neutral-200 shadow">
                                <div className="px-14 py-10">
                                    <div className="max-w-[602px]">
                                        {/* 텍스트를 처리하여 블록별로 렌더링 */}
                                        <ResponseRenderer content={msg.text} />
                                    </div>
                                </div>
                            </div>
                        </div>
                    )
                )}
                {isThinking && (
                    <div className="mt-6 ml-40 flex items-center gap-2">
                        <p className="text-[20px] font-normal font-['Pretendard'] text-[#292929CC]">
                            WEcHU가 생각하는 중{dots}
                        </p>
                        <ChevronDown className="w-6 h-6 text-[#292929CC]" />
                    </div>
                )}

                {/* ✅ 이게 맨 아래 “앵커” */}
                <div ref={messagesEndRef} />
            </main>

            {/* 입력창 */}
            <div className="fixed inset-x-0 bottom-0 z-10 border-t border-white/60 bg-white/40 backdrop-blur-[50px]">
                <div className="mx-auto flex max-w-4xl items-center gap-2 px-4 py-4">
                    <div className="flex w-full items-center justify-between rounded-2xl bg-neutral-200 px-5 py-3">
                        <input
                            value={userMessage}
                            onChange={(e) => setUserMessage(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && handleSend()}
                            className="w-full bg-transparent text-[#737373] text-[14px] leading-[20px] font-normal font-['Pretendard'] outline-none placeholder:text-[#737373]"
                            placeholder="KW-VIZER와 이야기 나눠보세요!"
                        />
                        <button
                            onClick={() => handleSend()}
                            className="ml-3 inline-flex h-9 w-9 items-center justify-center rounded-full border border-neutral-200 bg-white text-neutral-700 transition hover:bg-neutral-50"
                        >
                            <Send className="h-4 w-4" />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}