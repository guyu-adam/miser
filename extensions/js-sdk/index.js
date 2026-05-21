const http = require('http');

const BASE = process.env.MISER_URL || 'http://localhost:7860';

function post(path, data = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, BASE);
    const body = JSON.stringify(data);
    const opts = {
      hostname: url.hostname, port: url.port, path: url.pathname,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
    };
    const req = http.request(opts, (res) => {
      let raw = '';
      res.on('data', (c) => (raw += c));
      res.on('end', () => {
        try {
          const d = JSON.parse(raw);
          resolve(d.data || d.result || d.output || d);
        } catch { resolve(raw); }
      });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

function get(path) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, BASE);
    http.get({ hostname: url.hostname, port: url.port, path: url.pathname }, (res) => {
      let raw = '';
      res.on('data', (c) => (raw += c));
      res.on('end', () => { try { resolve(JSON.parse(raw)); } catch { resolve(raw); } });
    }).on('error', reject);
  });
}

// Zero-LLM ops (instant)
exports.outline = (path) => post('/outline', { path });
exports.grep = (path, pattern, ctx = 2) => post('/grep', { path, pattern, context: ctx });
exports.tree = (path, depth = 2) => post('/tree', { path, depth });
exports.exists = (path) => post('/exists', { path });
exports.read = (path, limit = 8000) => post('/read', { path, limit });
exports.write = (path, content) => post('/write', { path, content });
exports.run = (cmd) => post('/run', { cmd });

// Local-LLM ops (zero API cost)
exports.ask = (task, maxTokens = 600) => post('/ask', { task, max_tokens: maxTokens });
exports.codegen = (task, lang = 'python') => post('/codegen', { task, lang });
exports.explain = (pathOrCode) => {
  const key = pathOrCode.includes('/') || pathOrCode.includes('~') ? 'path' : 'code';
  return post('/explain', { [key]: pathOrCode });
};
exports.fix = (error, code = '') => post('/fix', { error, code });
exports.test = (path, func = '') => post('/test', { path, function: func });
exports.review = (pathOrCode) => {
  const key = pathOrCode.includes('/') || pathOrCode.includes('~') ? 'path' : 'code';
  return post('/review', { [key]: pathOrCode });
};
exports.condense = (pathOrText, category = 'code_file') => {
  const key = pathOrText.includes('/') || pathOrText.includes('~') ? 'path' : 'text';
  return post('/condense', { [key]: pathOrText, category });
};

// Admin
exports.status = () => get('/status');
exports.health = () => get('/health');
exports.metrics = () => get('/metrics');
