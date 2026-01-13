/**
 * Handler: POST /api/get-presigned-url
 * Получить presigned URL для загрузки части файла
 */

import { createR2Client, generatePresignedUploadUrl } from '../lib/r2-client.js';
import { jsonResponse, errorResponse } from '../lib/cors.js';

export async function handleGetPresignedUrl(request, env) {
	try {
		const body = await request.json();
		const { fileId, uploadId, partNumber } = body;

		// Валидация входных данных
		if (!fileId || !uploadId || !partNumber) {
			return errorResponse('Отсутствуют обязательные параметры', 400);
		}

		if (typeof partNumber !== 'number' || partNumber < 1) {
			return errorResponse('Некорректный номер части', 400);
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

		// Проверка что partNumber не превышает totalParts
		if (partNumber > metadata.totalParts) {
			return errorResponse(
				`Номер части ${partNumber} превышает общее количество частей ${metadata.totalParts}`,
				400
			);
		}

		// ОПТИМИЗАЦИЯ: Убрали put() здесь, чтобы сократить количество записей в KV.
		// TTL будет продлеваться при фактической загрузке части в part-uploaded handler.

		// Генерация presigned URL
		const r2Client = createR2Client(env);
		const bucketName = env.FILE_STORAGE.name || 'video-uploads';
		const key = `uploads/${fileId}`;
		const expiresIn = parseInt(env.PRESIGNED_URL_EXPIRY || '900'); // 15 мин

		const presignedUrl = await generatePresignedUploadUrl(
			r2Client,
			bucketName,
			key,
			uploadId,
			partNumber,
			expiresIn
		);

		return jsonResponse(
			{
				success: true,
				presignedUrl,
				partNumber,
				expiresIn,
			},
			200
		);
	} catch (error) {
		console.error('Get presigned URL error:', error);
		return errorResponse(error.message, 500);
	}
}
