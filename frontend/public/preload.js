// frontend/public/preload.js
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {
    send: (channel, ...args) => {
        let validChannels = ['set-ignore-mouse-events'];
        if (validChannels.includes(channel)) {
            ipcRenderer.send(channel, ...args);
        }
    },
    // 🔥 [추가됨] Electron에서 보내는 신호를 받는 기능
    on: (channel, func) => {
        let validChannels = ['global-mouse-move']; // 좌표 신호 허용
        if (validChannels.includes(channel)) {
            // 이벤트 리스너 등록 (메모리 누수 방지용 래퍼)
            const subscription = (event, ...args) => func(...args);
            ipcRenderer.on(channel, subscription);
            
            // 나중에 끌 수 있게 클린업 함수 반환
            return () => ipcRenderer.removeListener(channel, subscription);
        }
    }
});