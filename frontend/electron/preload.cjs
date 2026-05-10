const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  openFileDialog: () => ipcRenderer.invoke('open-file-dialog'),
  onFileSelected: (callback) =>
    ipcRenderer.on('file-selected', (_event, filePath) => callback(filePath)),
});
