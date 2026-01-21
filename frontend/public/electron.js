const { app, BrowserWindow, screen, Tray, Menu, Notification, powerSaveBlocker, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

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
      { label: 'LoL Overlay Pro 작동 중', enabled: false },
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
    body: '오버레이가 실행되었습니다! 트레이에서 종료 가능합니다.',
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
// 4. 메인 윈도우 생성 (GPS 기능 추가)
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

  // 🔥 [핵심 추가] GPS 추적 시스템 (0.1초마다 좌표 전송)
  // 마우스 이벤트를 OS가 씹어버리는 현상을 방지하기 위함
  setInterval(() => {
    try {
      if (mainWindow && !mainWindow.isDestroyed()) {
        const point = screen.getCursorScreenPoint(); // 현재 마우스 절대 좌표
        mainWindow.webContents.send('global-mouse-move', point); // React로 전송
      }
    } catch (e) {
      // 윈도우 종료 시 에러 무시
    }
  }, 100); // 0.1초 간격 (CPU 부하 거의 없음)
}

// ==============================
// 5. IPC 통신 핸들러
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