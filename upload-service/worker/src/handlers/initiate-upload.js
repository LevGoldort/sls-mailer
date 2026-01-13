/**
 * Handler: POST /api/initiate-upload
 * Начать multipart upload
 */

import { createMultipartUpload } from '../lib/r2-client.js';
import { validateUploadPassword } from '../lib/auth.js';
import { generateUUID } from '../lib/crypto.js';
import { jsonResponse, errorResponse } from '../lib/cors.js';

export async function handleInitiateUpload(request, env) {
	try {
		const body = await request.json();
		const { password, filename, fileSize, contentType } = body;

		// Валидация password
		if (!validateUploadPassword(password, env)) {
			return errorResponse('Неверный пароль загрузки', 401);
		}

		// Валидация file size
		const maxSize = parseInt(env.MAX_FILE_SIZE || '107374182400'); // 100GB
		if (!fileSize || fileSize <= 0) {
			return errorResponse('Не указан размер файла', 400);
		}
		if (fileSize > maxSize) {
			return errorResponse(
				`Файл слишком большой (максимум ${Math.round(maxSize / 1024 / 1024 / 1024)}GB)`,
				413
			);
		}

		// Валидация filename
		if (!filename || typeof filename !== 'string') {
			return errorResponse('Не указано имя файла', 400);
		}

		// Генерация fileId и расчет частей
		const fileId = generateUUID();
		const partSize = parseInt(env.PART_SIZE || '104857600'); // 100MB
		const totalParts = Math.ceil(fileSize / partSize);

		// Начало multipart upload (использует нативный R2 API)
		const key = `uploads/${fileId}`;

		const uploadId = await createMultipartUpload(env.FILE_STORAGE, key, {
			'original-filename': filename,
			'uploaded-at': new Date().toISOString(),
			'file-id': fileId,
			'content-type': contentType || 'application/octet-stream',
		});

		// Сохранение метаданных в KV (TTL 48 часов = 172800 сек)
		// ОПТИМИЗАЦИЯ: Не храним uploadedParts в KV, они хранятся в R2
		const metadata = {
			uploadId,
			filename,
			fileSize,
			contentType: contentType || 'application/octet-stream',
			partSize,
			totalParts,
			status: 'in-progress',
			createdAt: new Date().toISOString(),
		};

		await env.FILE_METADATA.put(fileId, JSON.stringify(metadata), {
			expirationTtl: 172800, // 48 hours
		});

		// Возврат ответа
		const expiresAt = new Date(Date.now() + 172800 * 1000).toISOString();

		return jsonResponse(
			{
				success: true,
				fileId,
				uploadId,
				partSize,
				totalParts,
				expiresAt,
			},
			200
		);
	} catch (error) {
		console.error('Initiate upload error:', error);
		return errorResponse(error.message, 500);
	}
}
