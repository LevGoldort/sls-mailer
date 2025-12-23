/**
 * Handler: POST /api/abort-upload
 * Отменить незавершенную загрузку
 */

import { abortMultipartUpload } from '../lib/r2-client.js';
import { jsonResponse, errorResponse } from '../lib/cors.js';

export async function handleAbortUpload(request, env) {
	try {
		const body = await request.json();
		const { fileId, uploadId } = body;

		// Валидация входных данных
		if (!fileId || !uploadId) {
			return errorResponse('Отсутствуют обязательные параметры', 400);
		}

		// Проверка существования upload в KV
		const metadataStr = await env.FILE_METADATA.get(fileId);
		if (!metadataStr) {
			return errorResponse('Загрузка не найдена', 404);
		}

		const metadata = JSON.parse(metadataStr);

		// Проверка uploadId
		if (metadata.uploadId !== uploadId) {
			return errorResponse('Некорректный ID загрузки', 400);
		}

		// Отмена multipart upload в R2 (использует нативный R2 API)
		const key = `uploads/${fileId}`;

		await abortMultipartUpload(env.FILE_STORAGE, key, uploadId);

		// Удаление метаданных из KV
		await env.FILE_METADATA.delete(fileId);

		return jsonResponse(
			{
				success: true,
				message: 'Загрузка отменена',
			},
			200
		);
	} catch (error) {
		console.error('Abort upload error:', error);
		return errorResponse(error.message, 500);
	}
}
