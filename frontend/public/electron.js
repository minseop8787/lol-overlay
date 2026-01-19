const { app, BrowserWindow, screen, Tray, Menu, Notification, powerSaveBlocker, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let mainWindow;
let tray = null;
let backendProcess = null;
let isQuitting = false; // 앱이 종료 중인지 확인하는 플래그

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

  // 아이콘 없으면 경고 (배포 시 중요)
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
          isQuitting = true; // 종료 플래그 ON
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
  
  // 아이콘 파일이 있을 때만 설정 (에러 방지)
  if (fs.existsSync(iconPath)) {
    notif.icon = iconPath;
  }
  notif.show();
}

// ==============================
// 3. 백엔드 실행 함수 (오뚜기 기능 추가)
// ==============================
function launchBackend() {
  // 이미 실행 중이면 무시
  if (backendProcess) return;

  const backendPath = path.join(process.resourcesPath, 'lol_backend', 'lol_api.exe');
  
  console.log(`🚀 백엔드 실행: ${backendPath}`);

  // 1) 인코딩 설정 추가 (한글 로그 에러 방지)
  const options = {
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' } 
  };

  backendProcess = spawn(backendPath, [], options);

  // 2) 파이프 막힘 방지 (로그를 읽어줘야 안 멈춤!)
  backendProcess.stdout.on('data', (data) => {
    // 개발 모드에서만 로그 보기 (배포 시 주석 처리 가능)
    // console.log(`[Backend]: ${data}`); 
  });

  backendProcess.stderr.on('data', (data) => {
    console.error(`[Backend Error]: ${data}`);
  });

  // 3) 오뚜기 기능: 백엔드가 죽으면 1초 뒤 부활
  backendProcess.on('close', (code) => {
    console.log(`백엔드 종료됨 (코드: ${code})`);
    backendProcess = null;

    // 사용자가 끈 게 아니라면(isQuitting == false), 다시 켭니다.
    if (!isQuitting) {
      console.log("⚠️ 백엔드가 비정상 종료됨. 1초 후 재시작...");
      setTimeout(launchBackend, 1000);
    }
  });
}

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
    focusable: false,
    skipTaskbar: true, 
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      devTools: false,
      backgroundThrottling: false // 백그라운드에서도 멈추지 않게
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
    // 배포 모드일 때만 백엔드 실행
    launchBackend();
  }
  
  mainWindow.on('closed', () => (mainWindow = null));
}

// ==============================
// 앱 생명주기
// ==============================

app.on('ready', () => {
  // 절전 모드 방지 (가장 강력한 설정)
  powerSaveBlocker.start('prevent-app-suspension');

  createTray();
  showStartedNotification();
  
  // 창 생성 딜레이
  setTimeout(createWindow, 500);
});

app.on('will-quit', () => {
  isQuitting = true; // 종료 플래그 설정
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});