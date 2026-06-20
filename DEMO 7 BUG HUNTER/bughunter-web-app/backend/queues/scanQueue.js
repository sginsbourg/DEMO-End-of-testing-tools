const { Queue } = require('bullmq');
const IORedis = require('ioredis');

const connection = new IORedis({ host: process.env.REDIS_HOST || '127.0.0.1', port: 6379 });
const scanQueue = new Queue('bughunter-scan', { connection });

module.exports = scanQueue;
