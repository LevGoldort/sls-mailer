/**
 * Handler: POST /api/part-uploaded
 * Уведомление о успешно загруженной части (для обновления metadata)
 */

import { jsonResponse, errorResponse } from '../lib/cors.js';

export async function handlePartUploaded(request, env) {
	try {
		const body = await request.json();
		const { fileId, uploadId, partNumber, etag } = body;

		// Валидация
		if (!fileId || !uploadId || !partNumber || !etag) {
			return errorResponse('Отсутствуют обязательные параметры', 400);
		}

		// Получить metadata из KV
		const metadataStr = await env.FILE_METADATA.get(fileId);
		if (!metadataStr) {
			return errorResponse('Загрузка не найдена или истекла', 404);
		}

		const metadata = JSON.parse(metadataStr);

		// Проверка uploadId
		if (metadata.uploadId !== uploadId) {
			return errorResponse('Некорректный ID загрузки', 400);
		}

		// Добавить часть в uploadedParts если еще нет
		if (!metadata.uploadedParts) {
			metadata.uploadedParts = [];
		}

		// Проверить что эта часть еще не добавлена
		const exists = metadata.uploadedParts.some((p) => p.PartNumber === partNumber);
		if (!exists) {
			metadata.uploadedParts.push({
				PartNumber: partNumber,
				ETag: etag,
			});

			// Сортировать по номеру части
			metadata.uploadedParts.sort((a, b) => a.PartNumber - b.PartNumber);

			// Обновить metadata в KV с продлением TTL
			await env.FILE_METADATA.put(fileId, JSON.stringify(metadata), {
				expirationTtl: 172800, // 48 hours
			});

			console.log(`Part ${partNumber} uploaded for ${fileId} (${metadata.uploadedParts.length}/${metadata.totalParts})`);
		}

		return jsonResponse(
			{
				success: true,
				uploadedParts: metadata.uploadedParts.length,
				totalParts: metadata.totalParts,
			},
			200
		);
	} catch (error) {
		console.error('Part uploaded error:', error);
		return errorResponse(error.message, 500);
	}
}
