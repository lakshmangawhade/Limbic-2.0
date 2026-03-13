const https = require('https');

const MAX_BODY_BYTES = 1024 * 1024;

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

function sendJson(res, statusCode, payload) {
    res.status(statusCode).json(payload);
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
                'x-api-key': normalizeEnvValue(process.env.ANTHROPIC_API_KEY),
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

    const anthropicApiKey = normalizeEnvValue(process.env.ANTHROPIC_API_KEY);
    const anthropicModel = normalizeEnvValue(process.env.ANTHROPIC_MODEL);

    if (!anthropicApiKey) {
        sendJson(res, 500, { error: { message: 'ANTHROPIC_API_KEY is not configured.' } });
        return;
    }
    if (!anthropicModel) {
        sendJson(res, 500, { error: { message: 'ANTHROPIC_MODEL is not configured.' } });
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
        model: anthropicModel,
        max_tokens: Math.min(Number(payload.max_tokens) || 1800, 1800),
        system: payload.system,
        messages: payload.messages
    });

    try {
        const upstream = await callAnthropic(requestBody);
        if (upstream.statusCode >= 400) {
            sendJson(res, upstream.statusCode, normalizeAnthropicError(upstream.statusCode, upstream.body));
            return;
        }
        res.status(upstream.statusCode);
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.send(upstream.body);
    } catch (error) {
        sendJson(res, 502, { error: { message: error.message } });
    }
};
