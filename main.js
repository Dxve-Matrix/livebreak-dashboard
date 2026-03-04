const { app, BrowserWindow } = require('electron')
const { spawn } = require('child_process')

let pyProcess = null

function createWindow() {

  pyProcess = spawn('python', ['app.py'])

  const win = new BrowserWindow({
    width: 1200,
    height: 800
  })

  win.loadURL('http://127.0.0.1:8000')
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (pyProcess) pyProcess.kill()
  app.quit()
})