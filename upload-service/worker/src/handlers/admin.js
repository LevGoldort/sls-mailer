/**
 * Admin handlers: list files, delete files
 */

import { deleteObject, listObjects } from '../lib/r2-client.js';
import { validateAdminKey, extractAdminKey } from '../lib/auth.js';
import { generateToken } from '../lib/crypto.js';
import { jsonResponse, errorResponse } from '../lib/cors.js';

/**
 * Handler: GET /api/admin/list
 * Получить список всех файлов
 */
export async function handleAdminList(request, env) {
	try {
		// Проверка admin key
		const adminKey = extractAdminKey(request);
		if (!validateAdminKey(adminKey, env)) {
			return errorResponse('Неверный admin key', 401);
		}

		// Получить все ключи из KV
		const kvList = await env.FILE_METADATA.list();
		const files = [];

		for (const key of kvList.keys) {
			const metadataStr = await env.FILE_METADATA.get(key.name);
			if (!metadataStr) continue;

			const metadata = JSON.parse(metadataStr);

			// Пропустить незавершенные загрузки
			if (metadata.status !== 'completed') continue;

			// Генерация download URL
			const url = new URL(request.url);
			const downloadUrl = `${url.protocol}//${url.host}/api/download/${key.name}?token=${metadata.downloadToken}`;

			files.push({
				fileId: key.name,
				filename: metadata.filename,
				size: metadata.fileSize,
				status: metadata.status,
				uploadedAt: metadata.completedAt || metadata.createdAt,
				downloadUrl,
			});
		}

		// Сортировка по дате (новые первыми)
		files.sort((a, b) => new Date(b.uploadedAt) - new Date(a.uploadedAt));

		return jsonResponse(
			{
				success: true,
				files,
				total: files.length,
			},
			200
		);
	} catch (error) {
		console.error('Admin list error:', error);
		return errorResponse(error.message, 500);
	}
}

/**
 * Handler: DELETE /api/admin/:fileId
 * Удалить файл
 */
export async function handleAdminDelete(request, env, ctx) {
	try {
		// Проверка admin key
		const adminKey = extractAdminKey(request);
		if (!validateAdminKey(adminKey, env)) {
			return errorResponse('Неверный admin key', 401);
		}

		// Извлечение fileId из URL
		const url = new URL(request.url);
		const pathParts = url.pathname.split('/');
		const fileId = pathParts[pathParts.length - 1];

		if (!fileId) {
			return errorResponse('Не указан ID файла', 400);
		}

		// Проверка существования файла
		const metadataStr = await env.FILE_METADATA.get(fileId);
		if (!metadataStr) {
			return errorResponse('Файл не найден', 404);
		}

		// Удаление из R2 (использует нативный R2 API)
		const key = `uploads/${fileId}`;

		await deleteObject(env.FILE_STORAGE, key);

		// Удаление метаданных из KV
		await env.FILE_METADATA.delete(fileId);

		return jsonResponse(
			{
				success: true,
				fileId,
				message: 'Файл успешно удален',
			},
			200
		);
	} catch (error) {
		console.error('Admin delete error:', error);
		return errorResponse(error.message, 500);
	}
}
