import React, { useState, useEffect } from 'react';
import './ItemBuild.css';

const DDRAGON_VER = "16.1.1"; 
const IMG_BASE_URL = `https://ddragon.leagueoflegends.com/cdn/${DDRAGON_VER}/img/item/`;
const DATA_URL = `https://ddragon.leagueoflegends.com/cdn/${DDRAGON_VER}/data/ko_KR/item.json`;

const ItemBuild = ({ buildData }) => {
  const [itemMeta, setItemMeta] = useState({});
  const [tooltip, setTooltip] = useState(null);

  // 1. 아이템 데이터 로드
  useEffect(() => {
    fetch(DATA_URL)
      .then(res => res.json())
      .then(json => setItemMeta(json.data))
      .catch(err => console.error("아이템 데이터 로드 실패:", err));
  }, []);

  // 🔥 [핵심 추가] GPS 좌표 수신 및 충돌 감지
  useEffect(() => {
    if (!window['electron']) return;

    const handleGlobalMouseMove = (pos) => {
      // 현재 마우스 좌표에 있는 HTML 요소 찾기
      const elem = document.elementFromPoint(pos.x, pos.y);
      
      if (elem) {
        // 요소가 'item-card-wrapper' 안에 있는지 확인
        const card = elem.closest('.item-card-wrapper');
        
        if (card) {
          const itemId = card.dataset.id; // data-id 속성 읽기
          if (itemId && itemMeta[itemId]) {
             // 이미 같은 툴팁이 떠있으면 리렌더링 방지
             setTooltip(prev => (prev && prev.id === itemId) ? prev : { id: itemId, data: itemMeta[itemId] });
             return;
          }
        }
      }
      // 아이템 위가 아니면 툴팁 끄기
      setTooltip(null);
    };

    // Electron 신호 구독
    const cleanup = window['electron'].on('global-mouse-move', handleGlobalMouseMove);
    return cleanup;
  }, [itemMeta]); // itemMeta가 로드된 후 작동

  if (!buildData) return null;

  // 세트 승률
  const startingWin = buildData.starting?.[0]?.win || "";
  const coreWin = buildData.core?.[1]?.win || "";

  return (
    <div className="build-container-horizontal">
      
      {/* 🟢 시작 아이템 */}
      <div className="build-section">
        <div className="section-header">
          <span className="section-title">STARTING</span>
          {startingWin && <span className="set-win-rate">{startingWin}%</span>}
        </div>
        <div className="item-row">
          {buildData.starting.map((item, idx) => (
            <React.Fragment key={idx}>
              <ItemCard item={item} hideWin={true} />
              {idx < buildData.starting.length - 1 && <span className="plus">+</span>}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="vertical-divider"></div>

      {/* 🟡 코어 아이템 */}
      <div className="build-section">
        <div className="section-header">
          <span className="section-title">CORE BUILD</span>
          {coreWin && <span className="set-win-rate core-highlight">{coreWin}%</span>}
        </div>
        <div className="item-row">
          {buildData.core.map((item, idx) => (
            <React.Fragment key={idx}>
              <ItemCard item={item} hideWin={true} />
              {idx < buildData.core.length - 1 && <span className="arrow">▶</span>}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="vertical-divider"></div>

      {/* ⚪ 옵션 아이템 */}
      <div className="build-section options-section">
        <div className="section-header">
            <span className="section-title">OPTIONS</span>
        </div>
        <div className="options-grid-horizontal">
            <HorizontalOptionRow label="4" items={buildData.item4} />
            <div className="option-divider"></div>
            <HorizontalOptionRow label="5" items={buildData.item5} />
            <div className="option-divider"></div>
            <HorizontalOptionRow label="6" items={buildData.item6} />
        </div>
      </div>

      {/* ✨ 툴팁 컴포넌트 */}
      {tooltip && <ItemTooltip info={tooltip.data} />}

    </div>
  );
};

// ---------------------------------------------------------
// 내부 컴포넌트
// ---------------------------------------------------------

const HorizontalOptionRow = ({ label, items }) => {
    if (!items || items.length === 0) return null;
    const displayItems = items.slice(0, 3);
    
    return (
        <div className="horizontal-option-group">
            <span className="option-label">{label}</span>
            <div className="option-items-row">
                {displayItems.map((item, i) => (
                    <ItemCard key={i} item={item} size="small" hideWin={false} />
                ))}
            </div>
        </div>
    )
}

// 🔥 [중요] 기존 onMouseEnter 제거하고 data-id 추가
const ItemCard = ({ item, size = "normal", hideWin = false }) => {
  if (!item || !item.id) return null;

  return (
    <div 
      className={`item-card-wrapper ${size}`}
      data-id={item.id}  /* 👈 GPS 추적을 위한 ID 태그 */
    >
      <div className="item-img-box">
        <img 
          src={`${IMG_BASE_URL}${item.id}.png`} 
          alt=""
          onError={(e) => e.target.style.display = 'none'} 
        />
      </div>
      {!hideWin && item.win && (
        <div className="item-stats-small">{item.win}%</div>
      )}
    </div>
  );
};

const ItemTooltip = ({ info }) => {
  if (!info) return null;

  const cleanDesc = (info.description || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, "");

  return (
    <div className="item-tooltip">
      <div className="tooltip-header">
        <span className="tooltip-name">{info.name}</span>
        <span className="tooltip-gold">🟡 {info.gold?.total || 0}</span>
      </div>
      <div className="tooltip-desc">{cleanDesc}</div>
    </div>
  );
};

export default ItemBuild;