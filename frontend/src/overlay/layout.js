// ==========================
// BASE 해상도 설정
// ==========================
const BASE_PICK_W = 1280;
const BASE_PICK_H = 720;
const BASE_AUG_W = 1920;
const BASE_AUG_H = 1080;

// ==========================
// PICK: BENCH (벤치) 위치 설정 (1280x720 기준)
// ==========================
const BENCH_X1_BASE = 353;
const BENCH_Y1_BASE = 11;
const BENCH_X2_BASE = 401;
const BENCH_Y2_BASE = 60;

// [수정 2] 벤치 간격 보정 (58 -> 68)
// 뒤로 갈수록 왼쪽으로 치우친다면, 간격을 더 넓혀야 합니다.
const BENCH_STEP_BASE = 60; 
const BENCH_BELOW_PADDING_BASE = 10;

// ==========================
// AUG: 증강 카드 3장 위치 설정 (1920x1080 기준)
// ==========================
const AUG_BOXES_BASE = [
  { x1: 449, y1: 188, x2: 760, y2: 702 },
  { x1: 806, y1: 187, x2: 1108, y2: 701 },
  { x1: 1160, y1: 187, x2: 1462, y2: 704 },
];

const AUG_TOP_GAP_BASE = 20;

// ==========================
// [함수] 내 픽(단일) 위치 계산
// ==========================
export function getMyPickPosPick(w, h) {
  return {
    x: Math.round(w * 0.50),
    y: Math.round(h * 0.72),
  };
}

// ==========================
// [함수] 벤치 챔피언 위치 계산
// ==========================
export function getBenchPosPick(w, h, i) {
  const sx = w / BASE_PICK_W;
  const sy = h / BASE_PICK_H;

  const x1 = (BENCH_X1_BASE + i * BENCH_STEP_BASE) * sx;
  const x2 = (BENCH_X2_BASE + i * BENCH_STEP_BASE) * sx;

  const x = Math.round((x1 + x2) / 2);
  const y = Math.round((BENCH_Y2_BASE + BENCH_BELOW_PADDING_BASE) * sy);

  return { x, y };
}

// ==========================
// [함수] 아군 5명 슬롯 위치 계산
// ==========================
export function getTeammatePos(w, h, index) {
  // [수정 1] 오버레이 위치를 오른쪽으로 이동
  // 기존 중앙(160) -> 오른쪽(260)으로 변경 (박스 끝이 304이므로 여유 있게 배치)
  const X_RIGHT_ANCHOR = 260; 
  
  const Y_START = 137;
  const Y_STEP = 80; 

  const baseX = X_RIGHT_ANCHOR;
  const baseY = Y_START + (index * Y_STEP);

  return {
    x: Math.round(baseX * (w / BASE_PICK_W)),
    y: Math.round(baseY * (h / BASE_PICK_H)),
  };
}

// ==========================
// [함수] 증강 카드 위치 계산
// ==========================
export function getAugmentPosAug(w, h, i) {
  const sx = w / BASE_AUG_W;
  const sy = h / BASE_AUG_H;

  const b = AUG_BOXES_BASE[i] ?? AUG_BOXES_BASE[1];

  const x = Math.round(((b.x1 + b.x2) / 2) * sx);
  const y = Math.round((b.y1 - AUG_TOP_GAP_BASE) * sy);

  return { x, y };
}