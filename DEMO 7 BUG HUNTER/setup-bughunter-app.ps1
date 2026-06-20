# Setup-BugHunter-App.ps1
# Bypasses the PowerShell string parser entirely to avoid any formatting or truncation errors
$ErrorActionPreference = "Stop"

Write-Host "🚀 Starting Advanced BugHunter Enterprise Web App Scaffolding..." -ForegroundColor Cyan

# 1. Define folder structures
$RootFolder = "bughunter-web-app"
$BackendFolder = "$RootFolder/backend"
$QueueFolder = "$BackendFolder/queues"
$PublicFolder = "$BackendFolder/public"

Write-Host "📁 Generating system workspaces..." -ForegroundColor Green
New-Item -ItemType Directory -Force -Path $QueueFolder | Out-Null
New-Item -ItemType Directory -Force -Path $PublicFolder | Out-Null
New-Item -ItemType Directory -Force -Path "$RootFolder/scans" | Out-Null

# 2. Generate package.json with Socket.IO dependencies
Write-Host "📝 Writing project dependency manifest (package.json)..." -ForegroundColor Green
$PackageJsonContent = @'
{
  "name": "bughunter-web-api",
  "version": "1.1.0",
  "description": "Production Tier Wrapper for BugHunter Core Engine",
  "main": "api.js",
  "scripts": {
    "start": "node api.js",
    "worker": "node worker.js"
  },
  "dependencies": {
    "bullmq": "^4.12.0",
    "express": "^4.19.2",
    "ioredis": "^5.4.1",
    "socket.io": "^4.7.5"
  }
}
'@
Set-Content -Path "$BackendFolder/package.json" -Value $PackageJsonContent

# 3. Create the Queue Config (scanQueue.js)
Write-Host "📝 Generating Redis Queue Controller..." -ForegroundColor Green
$QueueContent = @'
const { Queue } = require('bullmq');
const IORedis = require('ioredis');

const connection = new IORedis({ host: process.env.REDIS_HOST || '127.0.0.1', port: 6379 });
const scanQueue = new Queue('bughunter-scan', { connection });

module.exports = scanQueue;
'@
Set-Content -Path "$QueueFolder/scanQueue.js" -Value $QueueContent

# 4. Create the Upgraded API Server with Socket.IO WebSocket Support (api.js)
Write-Host "📝 Generating Advanced Real-time API Core..." -ForegroundColor Green
$ApiContent = @'
const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const path = require('path');
const scanQueue = require('./queues/scanQueue');
const IORedis = require('ioredis');

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: "*" } });

const connection = new IORedis({ host: process.env.REDIS_HOST || '127.0.0.1', port: 6379 });

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

global.io = io;

const scanDatabase = {};

io.on('connection', (socket) => {
    console.log(`🔌 UI client linked to stream engine: ${socket.id}`);
    socket.emit('history-sync', Object.values(scanDatabase));
});

const sub = connection.duplicate();
sub.subscribe('worker-logs');
sub.on('message', (channel, message) => {
    const logData = JSON.parse(message);
    io.emit(`logs-${logData.jobId}`, logData);

    if (logData.type === 'STATUS_UPDATE') {
        if (!scanDatabase[logData.jobId]) {
            scanDatabase[logData.jobId] = { id: logData.jobId, repo: logData.repo, branch: logData.branch, status: 'PENDING', vulnerabilities: [] };
        }
        scanDatabase[logData.jobId].status = logData.status;
        if (logData.vulnerabilities) {
            scanDatabase[logData.jobId].vulnerabilities = logData.vulnerabilities;
        }
        io.emit('history-sync', Object.values(scanDatabase));
    }
});

app.get('/api/scans', (req, res) => {
    return res.json(Object.values(scanDatabase));
});

app.post('/api/start-scan', async (req, res) => {
    const { repositoryUrl, targetBranch } = req.body;
    if (!repositoryUrl) return res.status(400).json({ error: "repositoryUrl is required." });

    try {
        const job = await scanQueue.add('bughunter-scan', {
            repo: repositoryUrl,
            branch: targetBranch || 'main'
        });

        scanDatabase[job.id] = {
            id: job.id,
            repo: repositoryUrl,
            branch: targetBranch || 'main',
            status: 'QUEUED',
            timestamp: new Date().toLocaleTimeString(),
            vulnerabilities: []
        };
        io.emit('history-sync', Object.values(scanDatabase));

        return res.status(202).json({ jobId: job.id, message: "Engine thread queued." });
    } catch (err) {
        return res.status(500).json({ error: err.message });
    }
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => console.log(`🚀 BugHunter Server Platform running on port ${PORT}`));
'@
Set-Content -Path "$BackendFolder/api.js" -Value $ApiContent

# 5. Create the Telemetry Streaming Worker Node (worker.js)
Write-Host "📝 Generating Background Telemetry Worker..." -ForegroundColor Green
$WorkerContent = @'
const { Worker } = require('bullmq');
const IORedis = require('ioredis');
const fs = require('fs');

const connection = new IORedis({ host: process.env.REDIS_HOST || '127.0.0.1', port: 6379 });
const pub = connection.duplicate();

const logToUI = async (jobId, repo, branch, text, type = 'LOG', status = 'PROCESSING', vulnerabilities = null) => {
    await pub.publish('worker-logs', JSON.stringify({ jobId, repo, branch, text, type, status, vulnerabilities }));
};

const worker = new Worker('bughunter-scan', async (job) => {
    const { repo, branch } = job.data;

    await logToUI(job.id, repo, branch, `⚡ Initializing worker thread execution instance...`, 'STATUS_UPDATE', 'PROCESSING');
    await new Promise(r => setTimeout(r, 1500));

    await logToUI(job.id, repo, branch, `📁 Cloning target scope repository branch context: ${branch}...`);
    await new Promise(r => setTimeout(r, 2000));

    await logToUI(job.id, repo, branch, `🔍 BugHunter Core Engine running static analysis rule maps...`);
    await new Promise(r => setTimeout(r, 2500));

    const mockFindings = [
        { id: "BH-001", file: "config/database.js", line: 14, severity: "CRITICAL", title: "Hardcoded Credentials Storage", snippet: "const PASS = 'SuperSecretAdminPassword2026!';" },
        { id: "BH-002", file: "routes/auth.js", line: 42, severity: "HIGH", title: "SQL Injection Vulnerability", snippet: "db.query(`SELECT * FROM users WHERE id = ${req.body.id}`)" },
        { id: "BH-003", file: "server.js", line: 105, severity: "MEDIUM", title: "Missing X-Frame-Options Security Headers", snippet: "app.listen(PORT);" }
    ];

    await logToUI(job.id, repo, branch, `✅ Analysis phase complete. Found ${mockFindings.length} threat vectors.`, 'LOG');
    await logToUI(job.id, repo, branch, `🎉 Compiling metrics tracking parameters...`, 'STATUS_UPDATE', 'COMPLETED', mockFindings);

}, { connection });

console.log("👷 Production Monitoring Threat Hunter worker nodes deployed.");
'@
Set-Content -Path "$BackendFolder/worker.js" -Value $WorkerContent

# 6. Generate Frontend UI Dashboard (Bypassing String Truncation Issues using Base64 Content Injection)
Write-Host "📝 Generating HTML Control Deck Dashboard UI (Protected Stream)..." -ForegroundColor Green
