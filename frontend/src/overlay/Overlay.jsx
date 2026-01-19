import { useEffect, useState, useRef } from "react"; // useRef 추가
import { getBenchPosPick, getTeammatePos, getAugmentPosAug } from "./layout";
import "./overlay.css";

const API_URL = "http://127.0.0.1:5000";

export default function Overlay() {
  const [pickData, setPickData] = useState(null);
  const [augData, setAugData] = useState(null);
  const [windowRect, setWindowRect] = useState(null);

  // 타이머 참조 변수 (컴포넌트가 꺼질 때 정리하기 위함)
  const pickTimerRef = useRef(null);
  const augTimerRef = useRef(null);

  // 1. 픽창 데이터 폴링 (죽지 않는 좀비 모드)
  useEffect(() => {
    const fetchPick = async () => {
      try {
        const res = await fetch(`${API_URL}/champ-select`);
        const json = await res.json();
        setPickData(json);
        if (json.window_rect) setWindowRect(json.window_rect);
      } catch (e) {
        console.log("Pick Fetch Error (Retrying...):", e.message);
      } finally {
        // 성공하든 실패하든 무조건 0.5초 뒤에 다시 실행 (절대 안 멈춤)
        pickTimerRef.current = setTimeout(fetchPick, 500);
      }
    };

    fetchPick(); // 시작

    return () => clearTimeout(pickTimerRef.current); // 정리
  }, []);

  // 2. 증강 데이터 폴링 (죽지 않는 좀비 모드)
  useEffect(() => {
    const fetchAug = async () => {
      try {
        const res = await fetch(`${API_URL}/augments/current`);
        const json = await res.json();
        setAugData(json.active ? json : null);
      } catch (e) {
        console.log("Augment Fetch Error (Retrying...):", e.message);
      } finally {
        // 성공하든 실패하든 무조건 0.2초 뒤에 다시 실행
        augTimerRef.current = setTimeout(fetchAug, 200);
      }
    };

    fetchAug(); // 시작

    return () => clearTimeout(augTimerRef.current); // 정리
  }, []);

  // 표시 조건
  const showPick = !!(pickData?.team && pickData.team.length > 0);
  const showAug = !!augData;

  if (!showPick && !showAug) return null;

  // ... (이 아래 UI 렌더링 코드는 기존 작성하신 그대로 유지하시면 됩니다) ...
  
  const pickContainerStyle = windowRect ? {
    position: "absolute",
    left: windowRect.x,
    top: windowRect.y,
    width: windowRect.w,
    height: windowRect.h,
    pointerEvents: "none",
  } : {
    position: "absolute", left: 0, top: 0, width: "100%", height: "100%"
  };

  const augContainerStyle = {
    position: "absolute", left: 0, top: 0, width: "100%", height: "100%"
  };
  
  const screenW = window.innerWidth;
  const screenH = window.innerHeight;

  return (
    <div className="root">
      
      {/* 🟢 픽창 UI */}
      {showPick && !showAug && (
        <div style={pickContainerStyle}>
           {pickData.team.map((member, i) => {
              const pos = getTeammatePos(1280, 720, i);
              const scaleX = (windowRect?.w || 1280) / 1280;
              const scaleY = (windowRect?.h || 720) / 720;

              return (
                <div key={i} className={`floating teammate ${member.is_me ? "me" : ""}`}
                     style={{ left: pos.x * scaleX, top: pos.y * scaleY }}>
                  <TierBadge tier={member.tier} size={member.is_me ? "large" : "normal"} />
                  {(member.score || member.win_rate) && (
                    <div className="statsRow">
                        {member.score && <span className="score">{member.score}</span>}
                        {member.win_rate && <span className="winRate">{member.win_rate}</span>}
                    </div>
                  )}
                </div>
              );
           })}

           {pickData.bench.map((b, i) => {
              const p = getBenchPosPick(1280, 720, i);
              const scaleX = (windowRect?.w || 1280) / 1280;
              const scaleY = (windowRect?.h || 720) / 720;
              return (
                <div key={i} className="floating bench" 
                     style={{ left: p.x * scaleX, top: p.y * scaleY }}>
                  <TierBadge tier={b.tier} size="small" />
                </div>
              );
           })}
        </div>
      )}

      {/* 🔵 증강 UI */}
      {showAug && (
        <div style={augContainerStyle}>
          {augData.augments.map((aug, i) => {
              const p = getAugmentPosAug(screenW, screenH, i);
              return (
               <div key={i} className="augmentUnderCard" style={{ left: p.x, top: p.y }}>
                  <div className="augName">{aug.name_ko}</div>
                  <div className="augHeader">
                    <div className="tierGroup">
                      <span className="tierLabel">전용</span>
                      <TierBadge tier={aug.tier_champ} size="normal" />
                    </div>
                    <div className="tierDivider"></div>
                    <div className="tierGroup">
                      <span className="tierLabel">범용</span>
                      <TierBadge tier={aug.tier_global} size="normal" />
                    </div>
                  </div>
               </div>
              )
          })}
        </div>
      )}
    </div>
  );
}

function TierBadge({ tier, size = "normal" }) {
  const c = getTierColor(tier);
  return (
    <div className={`badge ${size}`} style={{ borderColor: c, color: c }}>
      {tier || "?"}
    </div>
  );
}

function getTierColor(tier) {
  if (tier === "S+" || tier === "S") return "#ffcc00"; 
  if (tier === "A") return "#00ccff"; 
  if (tier === "B") return "#cccccc"; 
  return "#ffffff"; 
}