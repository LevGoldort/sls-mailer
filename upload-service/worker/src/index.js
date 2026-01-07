/**
 * Cloudflare Worker - Main Entry Point
 * Сервис загрузки больших файлов в R2
 */

import { Router } from 'itty-router';
import { handleInitiateUpload } from './handlers/initiate-upload.js';
import { handleGetPresignedUrl } from './handlers/get-presigned-url.js';
import { handleCompleteUpload } from './handlers/complete-upload.js';
import { handleDownload } from './handlers/download.js';
import { handleAbortUpload } from './handlers/abort-upload.js';
import { handleResumeUpload } from './handlers/resume-upload.js';
import { handlePartUploaded } from './handlers/part-uploaded.js';
import { handleAdminList, handleAdminDelete } from './handlers/admin.js';
import { handleOptions, errorResponse } from './lib/cors.js';

// Создание router
const router = Router();

// CORS preflight requests
router.options('*', handleOptions);

// Upload endpoints
router.post('/api/initiate-upload', handleInitiateUpload);
router.post('/api/get-presigned-url', handleGetPresignedUrl);
router.post('/api/part-uploaded', handlePartUploaded);
router.post('/api/complete-upload', handleCompleteUpload);
router.post('/api/abort-upload', handleAbortUpload);
router.get('/api/resume-upload', handleResumeUpload);

// Download endpoint
router.get('/api/download/:fileId', handleDownload);

// Admin endpoints
router.get('/api/admin/list', handleAdminList);
router.delete('/api/admin/:fileId', handleAdminDelete);

// Health check endpoint
router.get('/health', () => {
	return new Response(
		JSON.stringify({
			status: 'healthy',
			service: 'file-upload-api',
			version: '2.0.0-kv-optimized', // Оптимизация KV: ~97% меньше операций put()
			timestamp: new Date().toISOString(),
		}),
		{
			headers: { 'Content-Type': 'application/json' },
		}
	);
});

// 404 handler
router.all('*', () => {
	return errorResponse('Endpoint не найден', 404);
});

// Main export - Worker entry point
export default {
	async fetch(request, env, ctx) {
		try {
			// Validate required environment variables
			if (!env.FILE_STORAGE) {
				throw new Error('FILE_STORAGE (R2 bucket) не настроен');
			}
			if (!env.FILE_METADATA) {
				throw new Error('FILE_METADATA (KV namespace) не настроен');
			}
			if (!env.UPLOAD_PASSWORD || !env.DOWNLOAD_PASSWORD || !env.ADMIN_KEY || !env.TOKEN_SECRET) {
				throw new Error('Не все secrets настроены (UPLOAD_PASSWORD, DOWNLOAD_PASSWORD, ADMIN_KEY, TOKEN_SECRET)');
			}
			if (!env.R2_ACCESS_KEY_ID || !env.R2_SECRET_ACCESS_KEY || !env.R2_ENDPOINT) {
				throw new Error('R2 credentials не настроены (R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT)');
			}

			return await router.handle(request, env, ctx);
		} catch (error) {
			console.error('Worker error:', error);
			return errorResponse(error.message, 500);
		}
	},
};
