import { useEffect, useState, useRef } from "react";
import ItemBuild from "./ItemBuild"; // 새로 만든 아이템 추천 컴포넌트
import { getBenchPosPick, getTeammatePos, getAugmentPosAug } from "./layout";
import "./overlay.css";

const API_URL = "http://127.0.0.1:5000";

export default function Overlay() {
  // 1. 상태 관리
  const [pickData, setPickData] = useState(null);
  const [augData, setAugData] = useState(null);
  const [buildData, setBuildData] = useState(null); // [추가] 빌드 데이터
  const [isShopOpen, setIsShopOpen] = useState(false); // [추가] 상점 상태
  
  const [windowRect, setWindowRect] = useState(null);

  // 타이머 참조 (메모리 누수 방지)
  const pickTimerRef = useRef(null);
  const augTimerRef = useRef(null);
  const buildTimerRef = useRef(null); // [추가]

  // 🔥 [핵심 솔루션] 오버레이가 켜지자마자 "마우스 감지 모드" 강제 활성화
  // 이것이 없으면 오버레이가 투명해서 마우스가 그냥 통과해버립니다.
  useEffect(() => {
    // 로딩 딜레이 등을 고려해 1초 뒤에 확실하게 신호를 보냅니다.
    const timer = setTimeout(() => {
      if (window['electron']) {
        console.log("🚀 [Overlay] 마우스 감지 모드(forward: true) 강제 활성화!");
        // ignore: true (클릭은 게임으로 통과)
        // forward: true (마우스 움직임은 오버레이로 전달 -> 툴팁 작동!)
        window['electron'].send('set-ignore-mouse-events', true, { forward: true });
      } else {
        console.warn("⚠️ window.electron이 없습니다. 브라우저 모드인가요?");
      }
    }, 1000);

    return () => clearTimeout(timer);
  }, []);

  // ------------------------------------------------
  // 1. 픽창 데이터 폴링 (Champ Select)
  // ------------------------------------------------
  useEffect(() => {
    const fetchPick = async () => {
      try {
        const res = await fetch(`${API_URL}/champ-select`);
        const json = await res.json();
        setPickData(json);
        if (json.window_rect) setWindowRect(json.window_rect);
      } catch (e) {
        // console.log("Pick Fetch Error:", e.message);
      } finally {
        pickTimerRef.current = setTimeout(fetchPick, 1000);
      }
    };
    fetchPick();
    return () => clearTimeout(pickTimerRef.current);
  }, []);

  // ------------------------------------------------
  // 2. 증강 데이터 폴링 (Augments)
  // ------------------------------------------------
  useEffect(() => {
    const fetchAug = async () => {
      try {
        const res = await fetch(`${API_URL}/augments/current`);
        const json = await res.json();
        setAugData(json.active ? json : null);
      } catch (e) {
        // console.log("Aug Fetch Error:", e.message);
      } finally {
        augTimerRef.current = setTimeout(fetchAug, 500);
      }
    };
    fetchAug();
    return () => clearTimeout(augTimerRef.current);
  }, []);

  // ------------------------------------------------
  // 3. [추가] 상점 및 빌드 데이터 폴링 (Shop & Build)
  // ------------------------------------------------
  useEffect(() => {
    const fetchBuild = async () => {
      try {
        const res = await fetch(`${API_URL}/champion/build`);
        const json = await res.json();
        
        if (json.ok) {
          setIsShopOpen(json.shop_open);
          setBuildData(json.data);
        }
      } catch (e) {
        // console.log("Build Fetch Error:", e.message);
      } finally {
        buildTimerRef.current = setTimeout(fetchBuild, 1000);
      }
    };
    fetchBuild();
    return () => clearTimeout(buildTimerRef.current);
  }, []);


  // ------------------------------------------------
  // 렌더링 로직
  // ------------------------------------------------

  // 표시 조건 확인
  const showPick = !!(pickData?.team && pickData.team.length > 0);
  const showAug = !!(augData && augData.augments && augData.augments.length > 0);
  const showBuild = isShopOpen && buildData; // [추가] 상점이 열리고 데이터가 있을 때

  // 아무것도 보여줄 게 없으면 렌더링 안 함
  if (!showPick && !showAug && !showBuild) return null;

  // 스타일 정의
  const screenW = window.innerWidth;
  const screenH = window.innerHeight;

  const pickContainerStyle = windowRect ? {
    position: "absolute",
    left: windowRect.x,
    top: windowRect.y,
    width: windowRect.w,
    height: windowRect.h,
    pointerEvents: "none",
  } : {
    position: "absolute", left: 0, top: 0, width: "100%", height: "100%", pointerEvents: "none"
  };

  const augContainerStyle = {
    position: "absolute", left: 0, top: 0, width: "100%", height: "100%", pointerEvents: "none"
  };

  // [추가] 상점 오버레이 스타일 (화면 중앙 상단)
  const buildContainerStyle = {
    position: "absolute",
    left: "1%",
    top: "1%", // 상점 헤더 높이에 맞춤
    zIndex: 9999,
    // 🔥 [중요] 컨테이너는 클릭 통과 (CSS 파일에 설정되어 있어도 안전장치로)
    pointerEvents: "none", 
    display: "flex",
    justifyContent: "flex-start"
  };

  return (
    <div className="root">
      
      {/* 🟢 1. 픽창 UI (기존 코드 유지) */}
      {/* 상점이 안 켜져있을 때만 표시 */}
      {showPick && !showAug && !showBuild && (
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

      {/* 🔵 2. 증강 UI (기존 코드 유지) */}
      {/* 상점이 안 켜져있을 때만 표시 */}
      {showAug && !showBuild && (
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

      {/* 🟠 3. [추가] 상점 아이템 추천 UI */}
      {showBuild && (
        <div style={buildContainerStyle}>
          <ItemBuild buildData={buildData} />
        </div>
      )}

    </div>
  );
}

// --------------------------------------
// 하위 컴포넌트 (TierBadge 등 기존 유지)
// --------------------------------------
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