/**
 * Handler: POST /api/complete-upload
 * Финализировать multipart upload
 */

import { completeMultipartUpload } from '../lib/r2-client.js';
import { generateToken } from '../lib/crypto.js';
import { jsonResponse, errorResponse } from '../lib/cors.js';

export async function handleCompleteUpload(request, env) {
	try {
		const body = await request.json();
		const { fileId, uploadId, parts } = body;

		// Валидация входных данных
		if (!fileId || !uploadId || !parts || !Array.isArray(parts)) {
			return errorResponse('Отсутствуют обязательные параметры', 400);
		}

		// Проверка существования upload в KV
		const metadataStr = await env.FILE_METADATA.get(fileId);
		if (!metadataStr) {
			return errorResponse('Загрузка не найдена или истекла', 404);
		}

		const metadata = JSON.parse(metadataStr);

		// Проверка uploadId
		if (metadata.uploadId !== uploadId) {
			return errorResponse('Некорректный ID загрузки', 400);
		}

		// Проверка что все части загружены
		if (parts.length !== metadata.totalParts) {
			return errorResponse(
				`Загружено ${parts.length} частей из ${metadata.totalParts} ожидаемых`,
				400
			);
		}

		// Проверка формата parts
		for (const part of parts) {
			if (!part.PartNumber || !part.ETag) {
				return errorResponse('Некорректный формат данных о частях', 400);
			}
		}

		// Финализация multipart upload в R2 (использует нативный R2 API)
		const key = `uploads/${fileId}`;

		await completeMultipartUpload(env.FILE_STORAGE, key, uploadId, parts);

		// Генерация download token
		const downloadToken = await generateToken(fileId, env.TOKEN_SECRET);

		// Обновление метаданных в KV (без TTL - файл завершен)
		metadata.status = 'completed';
		metadata.completedAt = new Date().toISOString();
		metadata.downloadToken = downloadToken;

		await env.FILE_METADATA.put(fileId, JSON.stringify(metadata));

		// Формирование download URL
		const url = new URL(request.url);
		const downloadUrl = `${url.protocol}//${url.host}/api/download/${fileId}?token=${downloadToken}`;

		return jsonResponse(
			{
				success: true,
				fileId,
				downloadUrl,
				filename: metadata.filename,
				size: metadata.fileSize,
			},
			200
		);
	} catch (error) {
		console.error('Complete upload error:', error);
		return errorResponse(error.message, 500);
	}
}
