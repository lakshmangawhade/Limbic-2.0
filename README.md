# Posturography Analyzer

A lightweight browser-based dashboard for comparing CAPS EQ posturography PDF reports. The app parses uploaded PDFs in the browser, visualizes key balance metrics, exports results, and can generate AI-assisted clinical interpretation through a local proxy or a Vercel serverless API route.

## Features

- Upload one or more CAPS EQ PDF reports
- Parse test conditions and posturography metrics directly in the browser
- Compare sessions with bar charts, radar charts, birds-eye heatmaps, and COP scatter plots
- Export visualization data to CSV and charts to PNG
- Generate AI-assisted view interpretations and full summary reports
- Run locally with a minimal Node.js server
- Deploy to Vercel with environment-variable based secret handling

## Tech Stack

- Frontend: plain HTML, JavaScript, Tailwind via CDN
- Charts: Chart.js
- PDF parsing: PDF.js
- Backend: Node.js local proxy and Vercel serverless function

## Project Structure

- `pgr-2-0-1.html`: main single-page dashboard
- `server.js`: local HTTP server for development
- `api/messages.js`: Vercel serverless API route for Anthropic requests
- `vercel.json`: Vercel routing configuration
- `.env.example`: required environment variable example

## Requirements

- Node.js 18+ recommended
- Modern desktop browser
- CAPS EQ PDF reports for analysis

## Run Locally

1. Create a `.env` file from `.env.example` and add your Anthropic API key.
1. Open a terminal in the project folder.
2. Start the local server:

```bash
node server.js
```

3. Open [http://127.0.0.1:3000](http://127.0.0.1:3000) in your browser.

Example `.env`:

```bash
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

## Deploy To Vercel

1. Push this project to GitHub, GitLab, or Bitbucket.
2. In Vercel, import the repository.
3. When Vercel asks for the framework preset, choose `Other`.
4. Add the environment variable `ANTHROPIC_API_KEY` in the Vercel project settings.
5. Deploy.

Notes:

- `vercel.json` rewrites `/` to `pgr-2-0-1.html`
- `api/messages.js` handles `POST /api/messages`
- The frontend no longer stores the Anthropic API key

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

## API

Both local development and Vercel deployment expose the same endpoint:

- `POST /api/messages`: forwards AI interpretation requests to Anthropic using the server-side `ANTHROPIC_API_KEY`

Locally, `server.js` serves the dashboard and proxies API requests.
On Vercel, `api/messages.js` handles the API route and `vercel.json` serves the dashboard at `/`.

## Security Notes

This project is safer for deployment than the original prototype, but you should still treat it as a controlled app rather than a public open API.

- The Anthropic API key is now expected only in server-side environment variables.
- The frontend no longer sends secrets to the backend.
- The API route validates request structure and caps request size.
- The local static server now sanitizes file paths before reading from disk.
- If you deploy publicly, consider adding authentication and rate limiting to the API route to prevent abuse.

## Limitations

- Designed around CAPS EQ PDF formatting and may fail on differently structured reports
- PDF parsing depends on text extraction quality from the source report
- AI output is supportive only and should not be treated as a diagnosis
- No automated tests or build pipeline are included

## Notes

- The local server binds to `127.0.0.1`, so it is only reachable from the local machine by default.
- The project relies on built-in Node.js modules and CDN-delivered frontend libraries, so no extra npm dependencies are required for the current setup.
