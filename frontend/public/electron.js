const { app, BrowserWindow, screen, Tray, Menu, Notification, powerSaveBlocker, ipcMain, dialog } = require('electron');
const { autoUpdater } = require('electron-updater');
const log = require('electron-log');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

// 🔥 [로그 설정] 업데이트 문제 발생 시 로그 파일 확인용
log.transports.file.level = 'info';
autoUpdater.logger = log;

// 🔥 자동 다운로드 비활성화 (수동 확인 방식으로 변경)
autoUpdater.autoDownload = false;

// 🔥 [하드웨어 가속 끄기] 투명창 마우스 인식을 돕습니다 (필수 권장)
app.disableHardwareAcceleration();

let mainWindow;
let tray = null;
let backendProcess = null;
let isQuitting = false;
let isCheckingUpdate = false; // 업데이트 확인 중인지 플래그
let isManualCheck = false;    // 🔥 수동 확인인지 구분 (수동일 때만 "최신 버전" 알림)

// ==============================
// 1. 트레이 아이콘 생성 (업데이트 확인 버튼 추가)
// ==============================
function createTray() {
  let iconPath;
  if (app.isPackaged) {
    iconPath = path.join(process.resourcesPath, 'tray_icon.ico');
  } else {
    iconPath = path.join(__dirname, 'favicon.ico');
  }

  if (!fs.existsSync(iconPath) && app.isPackaged) {
    console.error("트레이 아이콘 없음!");
  }

  try {
    tray = new Tray(iconPath);
    updateTrayMenu(); // 메뉴 생성을 별도 함수로 분리
    tray.setToolTip('LoL Overlay Pro');
    tray.on('click', () => {
      if (mainWindow) mainWindow.show();
    });
  } catch (e) {
    console.log("트레이 생성 실패:", e);
  }
}

// 🔥 [신규] 트레이 메뉴 업데이트 함수
function updateTrayMenu(updateStatus = null) {
  if (!tray) return;

  let updateLabel = '🔄 업데이트 확인';
  if (updateStatus === 'checking') {
    updateLabel = '⏳ 확인 중...';
  } else if (updateStatus === 'available') {
    updateLabel = '🆕 새 버전 다운로드';
  } else if (updateStatus === 'downloading') {
    updateLabel = '⬇️ 다운로드 중...';
  } else if (updateStatus === 'ready') {
    updateLabel = '✅ 재시작하여 설치';
  }

  const contextMenu = Menu.buildFromTemplate([
    { label: `LoL Overlay Pro v${app.getVersion()}`, enabled: false },
    { type: 'separator' },
    {
      label: updateLabel,
      click: () => handleUpdateClick(updateStatus)
    },
    { type: 'separator' },
    {
      label: '종료 (Quit)',
      click: () => {
        isQuitting = true;
        app.quit();
      }
    }
  ]);
  tray.setContextMenu(contextMenu);
}

// 🔥 [신규] 업데이트 버튼 클릭 핸들러
function handleUpdateClick(currentStatus) {
  if (currentStatus === 'ready') {
    // 다운로드 완료 상태면 재시작
    isQuitting = true;
    autoUpdater.quitAndInstall();
  } else if (currentStatus === 'available') {
    // 새 버전이 있으면 다운로드 시작
    updateTrayMenu('downloading');
    autoUpdater.downloadUpdate();
  } else if (!isCheckingUpdate) {
    // 그 외에는 업데이트 확인
    checkForUpdatesManual();
  }
}

// 🔥 [신규] 수동 업데이트 확인 함수
function checkForUpdatesManual() {
  if (isCheckingUpdate) return;

  isCheckingUpdate = true;
  isManualCheck = true; // 🔥 수동 확인 플래그 설정
  updateTrayMenu('checking');
  log.info('수동 업데이트 확인 시작...');

  autoUpdater.checkForUpdates().catch((err) => {
    log.error('업데이트 확인 실패:', err);
    showUpdateNotification('업데이트 확인 실패', '네트워크 연결을 확인해주세요.');
    isCheckingUpdate = false;
    isManualCheck = false;
    updateTrayMenu(null);
  });
}

// ==============================
// 2. 알림 함수
// ==============================
function showStartedNotification() {
  let iconPath;
  if (app.isPackaged) {
    iconPath = path.join(process.resourcesPath, 'tray_icon.ico');
  } else {
    iconPath = path.join(__dirname, 'favicon.ico');
  }

  const notif = new Notification({
    title: 'LoL Overlay Pro',
    body: `v${app.getVersion()} 실행됨! 트레이에서 종료 가능합니다.`,
    silent: false,
  });

  if (fs.existsSync(iconPath)) {
    notif.icon = iconPath;
  }
  notif.show();
}

// 🔥 [신규] 업데이트 관련 알림 함수
function showUpdateNotification(title, body) {
  let iconPath;
  if (app.isPackaged) {
    iconPath = path.join(process.resourcesPath, 'tray_icon.ico');
  } else {
    iconPath = path.join(__dirname, 'favicon.ico');
  }

  const notif = new Notification({
    title: title,
    body: body,
    silent: false,
  });

  if (fs.existsSync(iconPath)) {
    notif.icon = iconPath;
  }
  notif.show();
}

// ==============================
// 3. 백엔드 실행 함수
// ==============================
function launchBackend() {
  if (backendProcess) return;

  const backendPath = path.join(process.resourcesPath, 'lol_backend', 'lol_overlay.exe');
  console.log(`🚀 백엔드 실행: ${backendPath}`);

  const options = {
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
  };

  try {
    backendProcess = spawn(backendPath, [], options);
    backendProcess.stderr.on('data', (data) => console.error(`[Backend Error]: ${data}`));

    backendProcess.on('close', (code) => {
      console.log(`백엔드 종료됨 (코드: ${code})`);
      backendProcess = null;
      if (!isQuitting) {
        console.log("⚠️ 백엔드가 비정상 종료됨. 1초 후 재시작...");
        setTimeout(launchBackend, 1000);
      }
    });
  } catch (err) {
    console.error("백엔드 실행 실패:", err);
  }
}

// ==============================
// 4. 메인 윈도우 생성
// ==============================
function createWindow() {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.bounds;

  mainWindow = new BrowserWindow({
    width: width,
    height: height,
    x: 0,
    y: 0,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    hasShadow: false,
    resizable: false,
    skipTaskbar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      devTools: false,
      backgroundThrottling: false,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  mainWindow.setAlwaysOnTop(true, 'screen-saver');
  mainWindow.setFullScreen(true);
  mainWindow.setIgnoreMouseEvents(true, { forward: true });

  const isDev = !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL('http://localhost:3000');
  } else {
    mainWindow.loadURL(`file://${path.join(__dirname, '../build/index.html')}`);
    launchBackend();
  }

  mainWindow.on('closed', () => (mainWindow = null));

  // 🔥 [수정] 창이 뜰 준비가 되면 조용히 업데이트 확인 (알림만)
  mainWindow.once('ready-to-show', () => {
    if (!isDev) {
      // 조용히 확인만 하고 알림으로 알려줌
      autoUpdater.checkForUpdates();
    }
  });

  // GPS 추적 시스템 (0.1초마다 좌표 전송)
  setInterval(() => {
    try {
      if (mainWindow && !mainWindow.isDestroyed()) {
        const point = screen.getCursorScreenPoint();
        mainWindow.webContents.send('global-mouse-move', point);
      }
    } catch (e) {
      // 윈도우 종료 시 에러 무시
    }
  }, 100);
}

// ==============================
// 5. 업데이트 이벤트 핸들러
// ==============================
autoUpdater.on('checking-for-update', () => {
  log.info('업데이트 확인 중...');
});

autoUpdater.on('update-available', (info) => {
  log.info('새로운 업데이트 발견:', info.version);
  isCheckingUpdate = false;
  isManualCheck = false; // 업데이트가 있으면 수동 확인 플래그 초기화
  updateTrayMenu('available');

  // 알림으로 새 버전 알려주기
  showUpdateNotification(
    '🆕 새로운 버전 발견!',
    `v${info.version} 업데이트가 있습니다. 트레이 메뉴에서 다운로드하세요.`
  );
});

autoUpdater.on('update-not-available', () => {
  log.info('현재 최신 버전입니다.');
  isCheckingUpdate = false;
  updateTrayMenu(null);

  // 🔥 수동 확인일 때만 "최신 버전" 알림 표시
  if (isManualCheck) {
    showUpdateNotification('✅ 최신 버전', '현재 최신 버전을 사용 중입니다.');
  }
  isManualCheck = false;
});

autoUpdater.on('error', (err) => {
  log.error('업데이트 에러:', err);
  isCheckingUpdate = false;
  isManualCheck = false; // 에러 발생 시 수동 확인 플래그 초기화
  updateTrayMenu(null);
});

autoUpdater.on('download-progress', (progressObj) => {
  log.info(`다운로드 중: ${progressObj.percent.toFixed(1)}%`);
});

autoUpdater.on('update-downloaded', (info) => {
  log.info('다운로드 완료. 재시작하면 설치됩니다.');
  updateTrayMenu('ready');

  showUpdateNotification(
    '✅ 다운로드 완료!',
    `v${info.version} 설치 준비 완료. 트레이 메뉴에서 '재시작하여 설치'를 클릭하세요.`
  );
});

// ==============================
// 6. IPC 통신 핸들러
// ==============================
ipcMain.on('set-ignore-mouse-events', (event, ignore, options) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win) {
    win.setIgnoreMouseEvents(ignore, { forward: true });
  }
});

// ==============================
// 앱 생명주기
// ==============================
app.on('ready', () => {
  powerSaveBlocker.start('prevent-app-suspension');
  createTray();
  showStartedNotification();
  setTimeout(createWindow, 500);
});

app.on('will-quit', () => {
  isQuitting = true;
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});