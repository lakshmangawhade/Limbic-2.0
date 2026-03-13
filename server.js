const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');

function loadDotEnv() {
    const envPath = path.join(__dirname, '.env');
    if (!fs.existsSync(envPath)) {
        return;
    }

    const envFile = fs.readFileSync(envPath, 'utf8');
    envFile.split(/\r?\n/).forEach(line => {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) {
            return;
        }

        const separatorIndex = trimmed.indexOf('=');
        if (separatorIndex === -1) {
            return;
        }

        const key = trimmed.slice(0, separatorIndex).trim();
        let value = trimmed.slice(separatorIndex + 1).trim();

        if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
            value = value.slice(1, -1);
        }

        if (!(key in process.env)) {
            process.env[key] = value;
        }
    });
}

loadDotEnv();

const PORT = process.env.PORT || 3000;
const HOST = '127.0.0.1';
const ROOT_DIR = __dirname;
const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;
const MAX_BODY_BYTES = 1024 * 1024;
const ALLOWED_MODELS = new Set([
    'claude-sonnet-4-5',
    'claude-sonnet-4-6',
    'claude-3-5-sonnet-latest',
    'claude-3-7-sonnet-latest'
]);

function sendJson(res, statusCode, payload) {
    res.writeHead(statusCode, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(payload));
}

function sanitizePath(urlPath) {
    const pathname = new URL(urlPath, `http://${HOST}:${PORT}`).pathname;
    const requestedPath = pathname === '/' ? '/index.html' : pathname;
    const normalizedPath = path.normalize(requestedPath).replace(/^(\.\.[/\\])+/, '');
    const fullPath = path.join(ROOT_DIR, normalizedPath);
    if (!fullPath.startsWith(ROOT_DIR)) {
        return null;
    }
    return fullPath;
}

function proxyAnthropicRequest(req, res) {
    if (!ANTHROPIC_API_KEY) {
        sendJson(res, 500, { error: { message: 'Server is missing ANTHROPIC_API_KEY.' } });
        return;
    }

    let body = '';
    let bodySize = 0;

    req.on('data', chunk => {
        bodySize += chunk.length;
        if (bodySize > MAX_BODY_BYTES) {
            req.destroy(new Error('Request body too large.'));
            return;
        }
        body += chunk;
    });

    req.on('end', () => {
        let payload;
        try {
            payload = JSON.parse(body || '{}');
        } catch {
            sendJson(res, 400, { error: { message: 'Invalid JSON payload.' } });
            return;
        }

        if (!Array.isArray(payload.messages) || typeof payload.system !== 'string') {
            sendJson(res, 400, { error: { message: 'Request must include system and messages.' } });
            return;
        }

        const model = ALLOWED_MODELS.has(payload.model) ? payload.model : 'claude-sonnet-4-6';
        const requestBody = JSON.stringify({
            model,
            max_tokens: Math.min(Number(payload.max_tokens) || 1800, 1800),
            system: payload.system,
            messages: payload.messages
        });

        const proxyReq = https.request({
            hostname: 'api.anthropic.com',
            path: '/v1/messages',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01',
                'Content-Length': Buffer.byteLength(requestBody)
            }
        }, proxyRes => {
            let data = '';
            proxyRes.on('data', chunk => data += chunk);
            proxyRes.on('end', () => {
                res.writeHead(proxyRes.statusCode || 502, {
                    'Content-Type': 'application/json; charset=utf-8'
                });
                res.end(data);
            });
        });

        proxyReq.on('error', error => {
            sendJson(res, 502, { error: { message: error.message } });
        });

        proxyReq.write(requestBody);
        proxyReq.end();
    });

    req.on('error', error => {
        const statusCode = error.message === 'Request body too large.' ? 413 : 400;
        sendJson(res, statusCode, { error: { message: error.message } });
    });
}

http.createServer((req, res) => {
    if (req.method === 'OPTIONS' && req.url === '/api/messages') {
        res.writeHead(204);
        res.end();
        return;
    }

    if (req.method === 'POST' && req.url === '/api/messages') {
        proxyAnthropicRequest(req, res);
        return;
    }

    if (req.method !== 'GET' && req.method !== 'HEAD') {
        sendJson(res, 405, { error: { message: 'Method not allowed.' } });
        return;
    }

    const fullPath = sanitizePath(req.url || '/');
    if (!fullPath) {
        sendJson(res, 403, { error: { message: 'Forbidden path.' } });
        return;
    }

    fs.readFile(fullPath, (err, data) => {
        if (err) {
            res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
            res.end('Not found');
            return;
        }

        const mimeTypes = {
            '.html': 'text/html; charset=utf-8',
            '.js': 'application/javascript; charset=utf-8',
            '.css': 'text/css; charset=utf-8',
            '.json': 'application/json; charset=utf-8'
        };
        const ext = path.extname(fullPath);
        res.writeHead(200, { 'Content-Type': mimeTypes[ext] || 'text/plain; charset=utf-8' });
        res.end(data);
    });
}).listen(PORT, HOST, () => {
    console.log(`Posturography Analyzer running at http://${HOST}:${PORT}`);
    console.log('Set ANTHROPIC_API_KEY in your environment before using AI interpretation.');
});
