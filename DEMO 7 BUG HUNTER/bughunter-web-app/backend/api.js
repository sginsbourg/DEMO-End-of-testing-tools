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
