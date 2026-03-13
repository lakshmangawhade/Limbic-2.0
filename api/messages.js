const https = require('https');

const MAX_BODY_BYTES = 1024 * 1024;
const ALLOWED_MODELS = new Set([
    'claude-sonnet-4-5',
    'claude-sonnet-4-6',
    'claude-3-5-sonnet-latest',
    'claude-3-7-sonnet-latest'
]);

function sendJson(res, statusCode, payload) {
    res.status(statusCode).json(payload);
}

function readRequestBody(req) {
    return new Promise((resolve, reject) => {
        let body = '';
        let bodySize = 0;

        req.on('data', chunk => {
            bodySize += chunk.length;
            if (bodySize > MAX_BODY_BYTES) {
                reject(new Error('Request body too large.'));
                req.destroy();
                return;
            }
            body += chunk;
        });

        req.on('end', () => resolve(body));
        req.on('error', reject);
    });
}

function callAnthropic(requestBody) {
    return new Promise((resolve, reject) => {
        const proxyReq = https.request({
            hostname: 'api.anthropic.com',
            path: '/v1/messages',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': process.env.ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01',
                'Content-Length': Buffer.byteLength(requestBody)
            }
        }, proxyRes => {
            let data = '';
            proxyRes.on('data', chunk => data += chunk);
            proxyRes.on('end', () => {
                resolve({
                    statusCode: proxyRes.statusCode || 502,
                    body: data
                });
            });
        });

        proxyReq.on('error', reject);
        proxyReq.write(requestBody);
        proxyReq.end();
    });
}

module.exports = async function handler(req, res) {
    if (req.method === 'OPTIONS') {
        res.status(204).end();
        return;
    }

    if (req.method !== 'POST') {
        sendJson(res, 405, { error: { message: 'Method not allowed.' } });
        return;
    }

    if (!process.env.ANTHROPIC_API_KEY) {
        sendJson(res, 500, { error: { message: 'ANTHROPIC_API_KEY is not configured.' } });
        return;
    }

    let rawBody;
    try {
        rawBody = await readRequestBody(req);
    } catch (error) {
        const statusCode = error.message === 'Request body too large.' ? 413 : 400;
        sendJson(res, statusCode, { error: { message: error.message } });
        return;
    }

    let payload;
    try {
        payload = JSON.parse(rawBody || '{}');
    } catch {
        sendJson(res, 400, { error: { message: 'Invalid JSON payload.' } });
        return;
    }

    if (!Array.isArray(payload.messages) || typeof payload.system !== 'string') {
        sendJson(res, 400, { error: { message: 'Request must include system and messages.' } });
        return;
    }

    const requestBody = JSON.stringify({
        model: ALLOWED_MODELS.has(payload.model) ? payload.model : 'claude-sonnet-4-6',
        max_tokens: Math.min(Number(payload.max_tokens) || 1800, 1800),
        system: payload.system,
        messages: payload.messages
    });

    try {
        const upstream = await callAnthropic(requestBody);
        res.status(upstream.statusCode);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.send(upstream.body);
    } catch (error) {
        sendJson(res, 502, { error: { message: error.message } });
    }
};
