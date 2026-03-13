const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');

const PORT = 3000;

http.createServer((req, res) => {
    // CORS preflight
    if (req.method === 'OPTIONS') {
        res.writeHead(204, {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, x-api-key, anthropic-version'
        });
        res.end();
        return;
    }

    // Proxy API calls to Anthropic
    if (req.method === 'POST' && req.url === '/api/messages') {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', () => {
            const options = {
                hostname: 'api.anthropic.com',
                path: '/v1/messages',
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-api-key': req.headers['x-api-key'],
                    'anthropic-version': '2023-06-01',
                    'Content-Length': Buffer.byteLength(body)
                }
            };
            const proxyReq = https.request(options, proxyRes => {
                let data = '';
                proxyRes.on('data', chunk => data += chunk);
                proxyRes.on('end', () => {
                    res.writeHead(proxyRes.statusCode, {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    });
                    res.end(data);
                });
            });
            proxyReq.on('error', e => {
                res.writeHead(502, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
                res.end(JSON.stringify({ error: { message: e.message } }));
            });
            proxyReq.write(body);
            proxyReq.end();
        });
        return;
    }

    // Serve static files
    const filePath = req.url === '/' ? '/pgr-2-0-1.html' : req.url;
    const fullPath = path.join(__dirname, filePath);
    fs.readFile(fullPath, (err, data) => {
        if (err) { res.writeHead(404); res.end('Not found'); return; }
        const mimeTypes = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css' };
        const ext = path.extname(fullPath);
        res.writeHead(200, { 'Content-Type': mimeTypes[ext] || 'text/plain' });
        res.end(data);
    });

}).listen(PORT, '127.0.0.1', () => {
    console.log(`Posturography Analyzer running at http://127.0.0.1:${PORT}`);
    console.log('Open that URL in your browser. Press Ctrl+C to stop.');
});
