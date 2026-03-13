# Posturography Analyzer

A lightweight browser-based dashboard for comparing CAPS EQ posturography PDF reports. The app parses uploaded PDFs in the browser, visualizes key balance metrics, exports results, and can generate AI-assisted clinical interpretation through a local Node.js proxy.

## Features

- Upload one or more CAPS EQ PDF reports
- Parse test conditions and posturography metrics directly in the browser
- Compare sessions with bar charts, radar charts, birds-eye heatmaps, and COP scatter plots
- Export visualization data to CSV and charts to PNG
- Generate AI-assisted view interpretations and full summary reports
- Run locally with a minimal Node.js server and no build step

## Tech Stack

- Frontend: plain HTML, JavaScript, Tailwind via CDN
- Charts: Chart.js
- PDF parsing: PDF.js
- Backend: Node.js `http`/`https` local proxy

## Project Structure

- `pgr-2-0-1.html`: main single-page dashboard
- `server.js`: local HTTP server and Anthropic proxy endpoint

## Requirements

- Node.js 18+ recommended
- Modern desktop browser
- CAPS EQ PDF reports for analysis

## Run Locally

1. Open a terminal in the project folder.
2. Start the local server:

```bash
node server.js
```

3. Open [http://127.0.0.1:3000](http://127.0.0.1:3000) in your browser.

## How To Use

1. Upload one or more CAPS EQ PDF reports.
2. Choose an analysis mode:
   - `Metric Comparison`
   - `Comprehensive View`
   - `Birds Eye View`
   - `COP Scatter Plot`
3. Review the generated chart and summary table.
4. Export data as CSV or chart output as PNG if needed.
5. Use `Interpret View` or `Full Report` to request AI-generated clinical commentary.

## Data Extracted

The parser attempts to identify test conditions and metrics such as:

- Stability Score
- Stability Class
- Sway Path Length
- Area 95% Confidence Ellipse
- Sway Velocity
- Sway Acceleration
- Actual Sway
- ML/AP sway values
- Sway Center Xo/Yo
- Fatigue Ratio
- Adaptation Ratio
- Directionality
- Predicted Direction of Sway

## Local API

The local server exposes one proxy endpoint:

- `POST /api/messages`: forwards AI interpretation requests to Anthropic

The server also serves the dashboard HTML from the project root.

## Security Notes

This project works as a local prototype, but the current API setup is **not production-ready**.

- The frontend currently contains an Anthropic API key in client-side code. This is a secret exposure risk and should be removed immediately before sharing or deploying.
- The proxy accepts `x-api-key` from the browser and forwards it upstream. In production, secrets should stay server-side only.
- CORS is set to `*`, which is too permissive for anything beyond local development.
- Static file serving uses request paths directly and should be hardened against path traversal before any broader use.
- There is no authentication, rate limiting, request validation, or audit logging on the proxy endpoint.

For a production deployment, move all secret handling to the server, validate request payloads, restrict origins, sanitize file paths, add authentication and rate limiting, and store configuration in environment variables.

## Limitations

- Designed around CAPS EQ PDF formatting and may fail on differently structured reports
- PDF parsing depends on text extraction quality from the source report
- AI output is supportive only and should not be treated as a diagnosis
- No automated tests or build pipeline are included

## Notes

- The server binds to `127.0.0.1`, so it is only reachable from the local machine by default.
- This project has no package manager setup because it relies on built-in Node.js modules and CDN-delivered frontend libraries.
