/**
 * Handler: GET /api/resume-upload?fileId={fileId}
 * Получить информацию о незавершенной загрузке для возобновления
 * ОПТИМИЗАЦИЯ: Получаем список частей из R2, а не из KV
 */

import { jsonResponse, errorResponse } from '../lib/cors.js';
import { createR2Client, listUploadedParts } from '../lib/r2-client.js';

export async function handleResumeUpload(request, env) {
	try {
		const url = new URL(request.url);
		const fileId = url.searchParams.get('fileId');

		// Валидация fileId
		if (!fileId) {
			return errorResponse('Не указан fileId', 400);
		}

		console.log('[Resume] Request for fileId:', fileId);

		// Получить metadata из KV
		const metadataStr = await env.FILE_METADATA.get(fileId);
		if (!metadataStr) {
			console.log('[Resume] Metadata not found for fileId:', fileId);
			return errorResponse('Загрузка не найдена или истекла', 404);
		}

		const metadata = JSON.parse(metadataStr);

		console.log('[Resume] Metadata found:', {
			fileId,
			uploadId: metadata.uploadId,
			status: metadata.status,
			filename: metadata.filename,
			totalParts: metadata.totalParts,
		});

		// Проверка что загрузка еще не завершена
		if (metadata.status === 'completed') {
			return errorResponse('Загрузка уже завершена', 400);
		}

		// ОПТИМИЗАЦИЯ: Получить список загруженных частей напрямую из R2
		// Это позволяет не хранить части в KV, экономя операции put()
		const r2Client = createR2Client(env);
		const bucketName = env.FILE_STORAGE.name || 'video-uploads';
		const key = `uploads/${fileId}`;

		const uploadedPartsData = await listUploadedParts(
			r2Client,
			bucketName,
			key,
			metadata.uploadId
		);

		console.log('[Resume] Uploaded parts from R2:', {
			fileId,
			partsCount: uploadedPartsData.length,
			totalParts: metadata.totalParts,
			firstParts: uploadedPartsData.slice(0, 3),
		});

		// Рассчитать оставшиеся части
		const uploadedNumbers = uploadedPartsData.map((p) => p.PartNumber);
		const remainingParts = [];
		for (let i = 1; i <= metadata.totalParts; i++) {
			if (!uploadedNumbers.includes(i)) {
				remainingParts.push(i);
			}
		}

		console.log('[Resume] Summary:', {
			totalParts: metadata.totalParts,
			uploadedCount: uploadedPartsData.length,
			remainingCount: remainingParts.length,
		});

		// Продлить TTL метаданных только при resume (не при каждой части)
		// Это одна операция put() вместо сотен
		await env.FILE_METADATA.put(fileId, metadataStr, {
			expirationTtl: 172800, // 48 hours
		});

		// Вернуть информацию для resume
		return jsonResponse(
			{
				success: true,
				fileId,
				uploadId: metadata.uploadId,
				filename: metadata.filename,
				fileSize: metadata.fileSize,
				contentType: metadata.contentType,
				partSize: metadata.partSize,
				totalParts: metadata.totalParts,
				uploadedPartsData, // Массив {PartNumber, ETag}
				completedParts: uploadedPartsData.length,
				remainingParts,
				status: metadata.status,
				createdAt: metadata.createdAt,
			},
			200
		);
	} catch (error) {
		console.error('[Resume] Handler error:', error);
		return errorResponse(error.message, 500);
	}
}
