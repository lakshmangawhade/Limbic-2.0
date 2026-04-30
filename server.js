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

function normalizeEnvValue(value) {
    if (typeof value !== 'string') {
        return value;
    }

    const trimmed = value.trim();
    if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
        return trimmed.slice(1, -1);
    }
    return trimmed;
}

const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || '0.0.0.0';
const ROOT_DIR = __dirname;
const ANTHROPIC_API_KEY = normalizeEnvValue(process.env.ANTHROPIC_API_KEY);
const ANTHROPIC_MODEL = normalizeEnvValue(process.env.ANTHROPIC_MODEL);
const MAX_BODY_BYTES = 1024 * 1024;
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
const PUPILOMETRY_PARSE_URL = normalizeEnvValue(process.env.PUPILOMETRY_PARSE_URL)
    || 'http://127.0.0.1:8000/parse-pupilometry';

function sendJson(res, statusCode, payload) {
    res.writeHead(statusCode, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(payload));
}

function parseJsonSafe(value) {
    try {
        return JSON.parse(value);
    } catch {
        return null;
    }
}

function normalizeAnthropicError(statusCode, rawBody) {
    const parsed = parseJsonSafe(rawBody);
    const upstreamMessage = parsed?.error?.message || parsed?.message || `Anthropic API returned HTTP ${statusCode}.`;
    const normalized = {
        error: {
            code: 'anthropic_api_error',
            message: 'AI request failed.',
            details: upstreamMessage
        }
    };

    if (statusCode === 401 || /invalid x-api-key/i.test(upstreamMessage)) {
        normalized.error.code = 'anthropic_auth_error';
        normalized.error.message = 'Anthropic authentication failed.';
        normalized.error.details = 'The server-side ANTHROPIC_API_KEY is invalid, missing, revoked, or belongs to a different account/project. Update the key in your environment and restart or redeploy the app.';
        return normalized;
    }

    if (statusCode === 404 || /model/i.test(upstreamMessage)) {
        normalized.error.code = 'anthropic_model_error';
        normalized.error.message = 'Anthropic model configuration is invalid.';
        normalized.error.details = 'Check ANTHROPIC_MODEL in your environment and make sure it is a valid model name available to your Anthropic account.';
        return normalized;
    }

    if (statusCode === 429) {
        normalized.error.code = 'anthropic_rate_limit';
        normalized.error.message = 'Anthropic rate limit reached.';
        normalized.error.details = 'Too many requests were sent to Anthropic. Wait a moment and try again.';
        return normalized;
    }

    return normalized;
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
    if (!ANTHROPIC_MODEL) {
        sendJson(res, 500, { error: { message: 'Server is missing ANTHROPIC_MODEL.' } });
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

        const requestBody = JSON.stringify({
            model: ANTHROPIC_MODEL,
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
                const statusCode = proxyRes.statusCode || 502;
                if (statusCode >= 400) {
                    sendJson(res, statusCode, normalizeAnthropicError(statusCode, data));
                    return;
                }
                res.writeHead(statusCode, {
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

function proxyPupilometryParseRequest(req, res) {
    let parsedUrl;
    try {
        parsedUrl = new URL(PUPILOMETRY_PARSE_URL);
    } catch {
        sendJson(res, 500, { error: { message: 'Server PUPILOMETRY_PARSE_URL is invalid.' } });
        return;
    }

    const transport = parsedUrl.protocol === 'https:' ? https : http;
    const headers = {
        'content-type': req.headers['content-type'] || 'application/octet-stream'
    };
    if (req.headers['content-length']) {
        headers['content-length'] = req.headers['content-length'];
    }

    const upstreamReq = transport.request({
        protocol: parsedUrl.protocol,
        hostname: parsedUrl.hostname,
        port: parsedUrl.port || (parsedUrl.protocol === 'https:' ? 443 : 80),
        path: `${parsedUrl.pathname}${parsedUrl.search}`,
        method: 'POST',
        headers
    }, upstreamRes => {
        let body = '';
        upstreamRes.on('data', chunk => body += chunk);
        upstreamRes.on('end', () => {
            const statusCode = upstreamRes.statusCode || 502;
            if (statusCode >= 400) {
                const parsed = parseJsonSafe(body);
                sendJson(res, statusCode, { error: { message: parsed?.error?.message || parsed?.message || `Pupilometry parser returned HTTP ${statusCode}.` } });
                return;
            }
            let payload = parseJsonSafe(body);
            if (payload === null) payload = { sessions: [] };
            sendJson(res, 200, payload);
        });
    });

    upstreamReq.on('error', error => {
        sendJson(res, 502, { error: { message: `Pupilometry backend error: ${error.message}` } });
    });

    let size = 0;
    let rejected = false;
    req.on('data', chunk => {
        size += chunk.length;
        if (!rejected && size > MAX_UPLOAD_BYTES) {
            rejected = true;
            upstreamReq.destroy();
            req.destroy();
            sendJson(res, 413, { error: { message: 'Upload too large. Max 25MB.' } });
        }
    });
    req.on('error', error => {
        if (!rejected) sendJson(res, 400, { error: { message: error.message } });
    });
    if (!rejected) req.pipe(upstreamReq);
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

    if (req.method === 'POST' && req.url === '/api/pupilometry/parse') {
        proxyPupilometryParseRequest(req, res);
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
    console.log(`Posturography Analyzer listening on ${HOST}:${PORT}`);
    console.log(`Local URL: http://localhost:${PORT}`);
    console.log('Set ANTHROPIC_API_KEY and ANTHROPIC_MODEL in your environment before using AI interpretation.');
});
