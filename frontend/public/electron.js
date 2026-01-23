const { app, BrowserWindow, screen, Tray, Menu, Notification, powerSaveBlocker, ipcMain, dialog } = require('electron');
const { autoUpdater } = require('electron-updater');
const log = require('electron-log');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

// 🔥 [로그 설정] 업데이트 문제 발생 시 로그 파일 확인용
log.transports.file.level = 'info';
autoUpdater.logger = log;

// 🔥 [하드웨어 가속 끄기] 투명창 마우스 인식을 돕습니다 (필수 권장)
app.disableHardwareAcceleration();

let mainWindow;
let tray = null;
let backendProcess = null;
let isQuitting = false;

// ==============================
// 1. 트레이 아이콘 생성
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
    const contextMenu = Menu.buildFromTemplate([
      { label: `LoL Overlay Pro v${app.getVersion()}`, enabled: false }, // 버전 표시 추가
      { type: 'separator' },
      { 
        label: '종료 (Quit)', 
        click: () => {
          isQuitting = true;
          app.quit(); 
        } 
      }
    ]);
    tray.setToolTip('LoL Overlay Pro');
    tray.setContextMenu(contextMenu);
    tray.on('click', () => {
      if (mainWindow) mainWindow.show();
    });
  } catch (e) {
    console.log("트레이 생성 실패:", e);
  }
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

// ==============================
// 3. 백엔드 실행 함수
// ==============================
function launchBackend() {
  if (backendProcess) return;

  const backendPath = path.join(process.resourcesPath, 'lol_backend', 'lol_api.exe');
  console.log(`🚀 백엔드 실행: ${backendPath}`);

  const options = {
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' } 
  };

  try {
    backendProcess = spawn(backendPath, [], options);
    // backendProcess.stdout.on('data', (data) => console.log(`[Backend]: ${data}`)); // 디버깅용
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
// 4. 메인 윈도우 생성 (GPS 기능 + 업데이트 확인)
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
      devTools: false, // 배포 시 false 권장
      backgroundThrottling: false,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  mainWindow.setAlwaysOnTop(true, 'screen-saver');
  mainWindow.setFullScreen(true);

  // 클릭은 게임으로, 마우스 움직임 감지는 유지
  mainWindow.setIgnoreMouseEvents(true, { forward: true });

  const isDev = !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL('http://localhost:3000');
  } else {
    mainWindow.loadURL(`file://${path.join(__dirname, '../build/index.html')}`);
    launchBackend();
  }
  
  mainWindow.on('closed', () => (mainWindow = null));

  // 🔥 [업데이트 체크] 창이 뜰 준비가 되면 업데이트 확인 시작
  mainWindow.once('ready-to-show', () => {
    if (!isDev) { // 개발 모드에서는 업데이트 체크 안 함
        autoUpdater.checkForUpdatesAndNotify();
    }
  });

  // 🔥 [핵심 유지] GPS 추적 시스템 (0.1초마다 좌표 전송)
  setInterval(() => {
    try {
      if (mainWindow && !mainWindow.isDestroyed()) {
        const point = screen.getCursorScreenPoint(); // 현재 마우스 절대 좌표
        mainWindow.webContents.send('global-mouse-move', point); // React로 전송
      }
    } catch (e) {
      // 윈도우 종료 시 에러 무시
    }
  }, 100); // 0.1초 간격
}

// ==============================
// 5. 업데이트 이벤트 핸들러 (로그 & 알림)
// ==============================
autoUpdater.on('checking-for-update', () => {
    log.info('업데이트 확인 중...');
});

autoUpdater.on('update-available', () => {
    log.info('새로운 업데이트 발견! 다운로드 시작...');
    // 필요하다면 사용자에게 알림 (여기선 조용히 다운로드)
});

autoUpdater.on('update-not-available', () => {
    log.info('현재 최신 버전입니다.');
});

autoUpdater.on('error', (err) => {
    log.error('업데이트 에러:', err);
});

autoUpdater.on('update-downloaded', () => {
    log.info('다운로드 완료. 앱 종료 시 설치됩니다.');
    
    // 사용자에게 "지금 재시작하시겠습니까?" 물어보기
    dialog.showMessageBox({
        type: 'info',
        title: '업데이트 설치',
        message: '새로운 버전이 다운로드되었습니다. 지금 재시작하여 설치하시겠습니까?',
        buttons: ['지금 재시작', '나중에']
    }).then((result) => {
        if (result.response === 0) { // '지금 재시작' 클릭 시
            isQuitting = true;
            autoUpdater.quitAndInstall();
        }
    });
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