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

		// ОПТИМИЗАЦИЯ: Не сохраняем список частей в KV!
		// Список частей хранится в R2 и получается через listUploadedParts() при resume.
		// Это экономит сотни операций put() в KV.

		// Продлеваем TTL только каждые 20 частей или на последней части
		// Это предотвращает истечение срока действия метаданных при длительной загрузке
		const shouldRefreshTTL =
			partNumber % 20 === 0 || // каждые 20 частей
			partNumber === metadata.totalParts; // последняя часть

		if (shouldRefreshTTL) {
			await env.FILE_METADATA.put(fileId, metadataStr, {
				expirationTtl: 172800, // 48 hours
			});
			console.log(`[TTL REFRESH] Part ${partNumber}/${metadata.totalParts} - fileId: ${fileId}`);
		}

		console.log(`[PART OK] Part ${partNumber}/${metadata.totalParts} uploaded - fileId: ${fileId}`);

		return jsonResponse(
			{
				success: true,
				partNumber,
				totalParts: metadata.totalParts,
			},
			200
		);
	} catch (error) {
		console.error('Part uploaded error:', error);
		return errorResponse(error.message, 500);
	}
}
