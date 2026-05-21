const vscode = require('vscode');
const http = require('http');
const { exec } = require('child_process');

const BASE = 'http://localhost:';

function getPort() {
  return vscode.workspace.getConfiguration('miser').get('port', 7860);
}

function api(path, method = 'GET', body = null) {
  return new Promise((resolve, reject) => {
    const url = `${BASE}${getPort()}${path}`;
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    const req = http.request(url, opts, (res) => {
      let data = '';
      res.on('data', (c) => (data += c));
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch { resolve(data); }
      });
    });
    req.on('error', reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

let statusBarItem;

async function activate(context) {
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.command = 'miser.showStatus';
  context.subscriptions.push(statusBarItem);
  updateStatusBar();

  context.subscriptions.push(
    vscode.commands.registerCommand('miser.start', async () => {
      const model = vscode.workspace.getConfiguration('miser').get('model');
      exec(`MISER_MODEL=${model} python3 -m miser &`, (err) => {
        if (err) vscode.window.showErrorMessage(`Miser: ${err.message}`);
        else vscode.window.showInformationMessage('Miser started');
        updateStatusBar();
      });
    }),
    vscode.commands.registerCommand('miser.stop', async () => {
      exec("pkill -f 'python.*miser'", () => {
        vscode.window.showInformationMessage('Miser stopped');
        updateStatusBar();
      });
    }),
    vscode.commands.registerCommand('miser.showStatus', async () => {
      try {
        const s = await api('/status');
        const saved = (s?.tokens_saved_est || 0).toLocaleString();
        vscode.window.showInformationMessage(
          `Miser: ${s?.model || '?'} | ${saved} tokens saved | Queue: ${s?.queue?.queue_size || 0}`
        );
      } catch {
        vscode.window.showWarningMessage('Miser is not running');
      }
    }),
    vscode.commands.registerCommand('miser.clearCache', async () => {
      try {
        await api('/memory/clear', 'POST');
        vscode.window.showInformationMessage('Miser cache cleared');
      } catch {
        vscode.window.showWarningMessage('Miser is not running');
      }
    })
  );

  // Auto-start
  if (vscode.workspace.getConfiguration('miser').get('autoStart')) {
    vscode.commands.executeCommand('miser.start');
  }

  // Periodic status update
  setInterval(updateStatusBar, 30000);
}

async function updateStatusBar() {
  try {
    const s = await api('/health');
    if (s?.status === 'ok') {
      statusBarItem.text = `$(check) Miser ${s.version || ''}`;
      statusBarItem.tooltip = `Model: ${s.model}\nQueue: ${s.queue_size} tasks`;
      statusBarItem.color = undefined;
    } else {
      statusBarItem.text = '$(warning) Miser';
      statusBarItem.color = '#ffcc00';
    }
  } catch {
    statusBarItem.text = '$(circle-slash) Miser offline';
    statusBarItem.color = '#ff4444';
  }
  statusBarItem.show();
}

function deactivate() {}

module.exports = { activate, deactivate };
