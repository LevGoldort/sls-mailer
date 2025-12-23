/**
 * Handler: GET /api/download/:fileId
 * Скачать файл (с проверкой token или password)
 */

import { createR2Client, generatePresignedDownloadUrl } from '../lib/r2-client.js';
import { validateDownloadPassword, extractDownloadPassword } from '../lib/auth.js';
import { verifyToken } from '../lib/crypto.js';
import { errorResponse } from '../lib/cors.js';

export async function handleDownload(request, env, ctx) {
	try {
		const url = new URL(request.url);
		const pathParts = url.pathname.split('/');
		const fileId = pathParts[pathParts.length - 1];

		if (!fileId) {
			return errorResponse('Не указан ID файла', 400);
		}

		// Получить метаданные из KV
		const metadataStr = await env.FILE_METADATA.get(fileId);
		if (!metadataStr) {
			return errorResponse('Файл не найден', 404);
		}

		const metadata = JSON.parse(metadataStr);

		// Проверка что файл завершен
		if (metadata.status !== 'completed') {
			return errorResponse('Файл еще не загружен полностью', 400);
		}

		// Проверка аутентификации: token ИЛИ password
		const token = url.searchParams.get('token');
		const password = extractDownloadPassword(request);

		let authorized = false;

		// Вариант 1: Проверка token
		if (token) {
			const isValidToken = await verifyToken(fileId, token, env.TOKEN_SECRET);
			if (isValidToken) {
				authorized = true;
			}
		}

		// Вариант 2: Проверка password
		if (!authorized && password) {
			if (validateDownloadPassword(password, env)) {
				authorized = true;
			}
		}

		if (!authorized) {
			return errorResponse('Неверный token или пароль', 401);
		}

		// Генерация presigned download URL
		const r2Client = createR2Client(env);
		const bucketName = env.FILE_STORAGE.name || 'video-uploads';
		const key = `uploads/${fileId}`;
		const expiresIn = parseInt(env.DOWNLOAD_URL_EXPIRY || '3600'); // 1 час

		const presignedUrl = await generatePresignedDownloadUrl(
			r2Client,
			bucketName,
			key,
			metadata.filename,
			expiresIn
		);

		// Redirect на presigned URL
		return Response.redirect(presignedUrl, 302);
	} catch (error) {
		console.error('Download error:', error);
		return errorResponse(error.message, 500);
	}
}
