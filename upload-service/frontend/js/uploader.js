/**
 * MultipartUploader - класс для загрузки больших файлов
 * Использует multipart upload с presigned URLs
 */

class MultipartUploader {
	constructor(apiBaseUrl, options = {}) {
		this.apiBaseUrl = apiBaseUrl;
		this.partSize = options.partSize || 100 * 1024 * 1024; // 100MB default
		this.concurrency = options.concurrency || 3; // Параллельность загрузки
		this.maxRetries = options.maxRetries || 3;

		// State
		this.uploadState = null;
		this.aborted = false;
		this.startTime = null;
		this.uploadedBytes = 0;
	}

	/**
	 * Загрузить файл
	 */
	async uploadFile(file, password, callbacks = {}) {
		this.aborted = false;
		this.startTime = Date.now();
		this.uploadedBytes = 0;

		const { onProgress, onSpeedUpdate, onError } = callbacks;

		try {
			// Шаг 1: Инициализация multipart upload
			const initData = await this.initiateUpload(file, password);
			this.uploadState = initData;

			if (onProgress) {
				onProgress({
					percentage: 0,
					currentPart: 0,
					totalParts: initData.totalParts,
					uploadedBytes: 0,
					totalBytes: file.size,
				});
			}

			// Шаг 2: Загрузка частей
			const uploadedParts = await this.uploadParts(file, initData, {
				onProgress: (progress) => {
					if (onProgress) onProgress(progress);
					if (onSpeedUpdate) {
						const elapsed = (Date.now() - this.startTime) / 1000;
						const speed = this.uploadedBytes / elapsed;
						const remaining = (file.size - this.uploadedBytes) / speed;
						onSpeedUpdate(speed, remaining);
					}
				},
			});

			// Проверка отмены
			if (this.aborted) {
				throw new Error('Загрузка отменена пользователем');
			}

			// Шаг 3: Финализация
			const result = await this.completeUpload(
				initData.fileId,
				initData.uploadId,
				uploadedParts
			);

			return result;
		} catch (error) {
			console.error('Upload error:', error);
			if (onError) onError(error);

			// Попытка отмены при ошибке
			if (this.uploadState && !this.aborted) {
				try {
					await this.abortUpload(this.uploadState.fileId, this.uploadState.uploadId);
				} catch (abortError) {
					console.error('Abort upload error:', abortError);
				}
			}

			throw error;
		}
	}

	/**
	 * Инициализация multipart upload
	 */
	async initiateUpload(file, password) {
		const response = await fetch(`${this.apiBaseUrl}/api/initiate-upload`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({
				password,
				filename: file.name,
				fileSize: file.size,
				contentType: file.type || 'application/octet-stream',
			}),
		});

		if (!response.ok) {
			const error = await response.json();
			throw new Error(error.error || 'Ошибка инициализации загрузки');
		}

		return await response.json();
	}

	/**
	 * Загрузка всех частей файла
	 */
	async uploadParts(file, initData, callbacks = {}) {
		const { fileId, uploadId, totalParts, partSize } = initData;
		const { onProgress } = callbacks;

		const uploadedParts = [];
		const queue = [];

		// Создаем очередь частей
		for (let partNumber = 1; partNumber <= totalParts; partNumber++) {
			queue.push(partNumber);
		}

		// Загрузка с ограниченной параллельностью
		const workers = [];
		for (let i = 0; i < this.concurrency; i++) {
			workers.push(this.uploadWorker(file, fileId, uploadId, partSize, queue, uploadedParts, onProgress, totalParts));
		}

		await Promise.all(workers);

		// Сортировка по PartNumber
		uploadedParts.sort((a, b) => a.PartNumber - b.PartNumber);

		return uploadedParts;
	}

	/**
	 * Worker для параллельной загрузки частей
	 */
	async uploadWorker(file, fileId, uploadId, partSize, queue, uploadedParts, onProgress, totalParts) {
		while (queue.length > 0) {
			if (this.aborted) break;

			const partNumber = queue.shift();
			if (!partNumber) break;

			// Извлечь chunk из файла
			const start = (partNumber - 1) * partSize;
			const end = Math.min(start + partSize, file.size);
			const chunk = file.slice(start, end);

			// Загрузить часть с retry
			const part = await this.uploadPartWithRetry(
				fileId,
				uploadId,
				partNumber,
				chunk
			);

			uploadedParts.push(part);
			this.uploadedBytes += chunk.size;

			// Обновить прогресс
			if (onProgress) {
				onProgress({
					percentage: (uploadedParts.length / totalParts) * 100,
					currentPart: uploadedParts.length,
					totalParts,
					uploadedBytes: this.uploadedBytes,
					totalBytes: file.size,
				});
			}
		}
	}

	/**
	 * Загрузить одну часть с retry
	 */
	async uploadPartWithRetry(fileId, uploadId, partNumber, chunk) {
		let lastError;

		for (let attempt = 1; attempt <= this.maxRetries; attempt++) {
			try {
				// Получить presigned URL
				const urlResponse = await fetch(`${this.apiBaseUrl}/api/get-presigned-url`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
					},
					body: JSON.stringify({ fileId, uploadId, partNumber }),
				});

				if (!urlResponse.ok) {
					const error = await urlResponse.json();
					throw new Error(error.error || 'Ошибка получения presigned URL');
				}

				const { presignedUrl } = await urlResponse.json();

				// Загрузить chunk напрямую в R2
				const uploadResponse = await fetch(presignedUrl, {
					method: 'PUT',
					body: chunk,
					headers: {
						'Content-Type': 'application/octet-stream',
					},
				});

				if (!uploadResponse.ok) {
					throw new Error(`Upload failed with status ${uploadResponse.status}`);
				}

				// Извлечь ETag
				const etag = uploadResponse.headers.get('ETag');
				if (!etag) {
					throw new Error('ETag not found in response');
				}

				return {
					PartNumber: partNumber,
					ETag: etag.replace(/"/g, ''), // Remove quotes
				};
			} catch (error) {
				lastError = error;
				console.error(`Upload part ${partNumber} attempt ${attempt} failed:`, error);

				if (attempt < this.maxRetries) {
					// Exponential backoff
					const delay = Math.min(1000 * Math.pow(2, attempt), 10000);
					await new Promise((resolve) => setTimeout(resolve, delay));
				}
			}
		}

		throw new Error(`Failed to upload part ${partNumber} after ${this.maxRetries} attempts: ${lastError.message}`);
	}

	/**
	 * Финализировать upload
	 */
	async completeUpload(fileId, uploadId, parts) {
		const response = await fetch(`${this.apiBaseUrl}/api/complete-upload`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({
				fileId,
				uploadId,
				parts,
			}),
		});

		if (!response.ok) {
			const error = await response.json();
			throw new Error(error.error || 'Ошибка финализации загрузки');
		}

		return await response.json();
	}

	/**
	 * Отменить upload
	 */
	async abortUpload(fileId, uploadId) {
		this.aborted = true;

		const response = await fetch(`${this.apiBaseUrl}/api/abort-upload`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify({ fileId, uploadId }),
		});

		if (!response.ok) {
			const error = await response.json();
			throw new Error(error.error || 'Ошибка отмены загрузки');
		}

		return await response.json();
	}

	/**
	 * Отменить текущую загрузку
	 */
	cancel() {
		this.aborted = true;
	}
}

// Утилиты для форматирования

function formatBytes(bytes) {
	if (bytes === 0) return '0 B';
	const k = 1024;
	const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
	const i = Math.floor(Math.log(bytes) / Math.log(k));
	return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

function formatSpeed(bytesPerSecond) {
	return formatBytes(bytesPerSecond) + '/s';
}

function formatTime(seconds) {
	if (!isFinite(seconds) || seconds < 0) return 'Расчет...';

	const hours = Math.floor(seconds / 3600);
	const minutes = Math.floor((seconds % 3600) / 60);
	const secs = Math.floor(seconds % 60);

	if (hours > 0) {
		return `${hours}ч ${minutes}м ${secs}с`;
	} else if (minutes > 0) {
		return `${minutes}м ${secs}с`;
	} else {
		return `${secs}с`;
	}
}
