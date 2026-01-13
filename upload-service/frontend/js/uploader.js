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
		this.storage = options.storage || null; // UploadStorage instance

		// State
		this.uploadState = null;
		this.aborted = false;
		this.startTime = null;
		this.uploadedBytes = 0;
	}

	/**
	 * Проверить возможность возобновления загрузки
	 */
	async canResumeUpload(fileId) {
		try {
			const response = await fetch(`${this.apiBaseUrl}/api/resume-upload?fileId=${fileId}`);
			if (!response.ok) return null;
			const data = await response.json();
			return data.success ? data : null;
		} catch (error) {
			console.error('Resume check error:', error);
			return null;
		}
	}

	/**
	 * Загрузить файл
	 */
	async uploadFile(file, password, callbacks = {}, resumeData = null) {
		this.aborted = false;
		this.startTime = Date.now();
		this.uploadedBytes = 0;

		const { onProgress, onSpeedUpdate, onError } = callbacks;

		try {
			let initData;
			let alreadyUploadedParts = [];

			// Проверка - resume или новая загрузка
			if (resumeData && resumeData.fileId) {
				// RESUME LOGIC
				console.log('Resuming upload:', resumeData.fileId);
				console.log('Resume data received:', resumeData);
				console.log('uploadedPartsData:', resumeData.uploadedPartsData);

				// Проверить что файл совпадает
				if (file.size !== resumeData.fileSize || file.name !== resumeData.filename) {
					throw new Error('Файл не совпадает с сохраненной загрузкой');
				}

				// Использовать существующий upload session
				initData = {
					fileId: resumeData.fileId,
					uploadId: resumeData.uploadId,
					totalParts: resumeData.totalParts,
					partSize: resumeData.partSize,
				};

				alreadyUploadedParts = resumeData.uploadedPartsData || [];
				console.log('Already uploaded parts:', alreadyUploadedParts);

				// Рассчитать уже загруженные байты
				this.uploadedBytes = alreadyUploadedParts.reduce((sum, part) => {
					const partNumber = part.PartNumber;
					const start = (partNumber - 1) * resumeData.partSize;
					const end = Math.min(start + resumeData.partSize, file.size);
					return sum + (end - start);
				}, 0);

				console.log(
					`Resuming: ${alreadyUploadedParts.length}/${resumeData.totalParts} parts already uploaded (${formatBytes(this.uploadedBytes)})`
				);
			} else {
				// NEW UPLOAD
				initData = await this.initiateUpload(file, password);

				// Сохранить в IndexedDB
				if (this.storage) {
					await this.storage.saveUpload({
						fileId: initData.fileId,
						uploadId: initData.uploadId,
						filename: file.name,
						fileSize: file.size,
						contentType: file.type || 'application/octet-stream',
						partSize: initData.partSize,
						totalParts: initData.totalParts,
						uploadedPartsData: [],
						status: 'in-progress',
					});
				}
			}

			this.uploadState = initData;

			if (onProgress) {
				const completedParts = alreadyUploadedParts.length;
				onProgress({
					percentage: (completedParts / initData.totalParts) * 100,
					currentPart: completedParts,
					totalParts: initData.totalParts,
					uploadedBytes: this.uploadedBytes,
					totalBytes: file.size,
				});
			}

			// Шаг 2: Загрузка оставшихся частей
			const newUploadedParts = await this.uploadParts(file, initData, {
				onProgress: (progress) => {
					if (onProgress) onProgress(progress);
					if (onSpeedUpdate) {
						const elapsed = (Date.now() - this.startTime) / 1000;
						const speed = this.uploadedBytes / elapsed;
						const remaining = (file.size - this.uploadedBytes) / speed;
						onSpeedUpdate(speed, remaining);
					}
				},
			}, alreadyUploadedParts);

			// Проверка отмены
			if (this.aborted) {
				throw new Error('Загрузка отменена пользователем');
			}

			// Объединить старые и новые части
			const allParts = [...alreadyUploadedParts, ...newUploadedParts].sort(
				(a, b) => a.PartNumber - b.PartNumber
			);

			// Шаг 3: Финализация
			const result = await this.completeUpload(
				initData.fileId,
				initData.uploadId,
				allParts
			);

			// Пометить как завершенную в IndexedDB
			if (this.storage) {
				await this.storage.markCompleted(initData.fileId);
			}

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
	async uploadParts(file, initData, callbacks = {}, alreadyUploadedParts = []) {
		const { fileId, uploadId, totalParts, partSize } = initData;
		const { onProgress } = callbacks;

		const uploadedParts = [];
		const queue = [];

		// Получить номера уже загруженных частей
		const alreadyUploadedNumbers = alreadyUploadedParts.map((p) => p.PartNumber);

		// Создаем очередь частей, исключая уже загруженные
		for (let partNumber = 1; partNumber <= totalParts; partNumber++) {
			if (!alreadyUploadedNumbers.includes(partNumber)) {
				queue.push(partNumber);
			}
		}

		console.log(
			`Uploading ${queue.length} remaining parts (${alreadyUploadedParts.length} already done)`
		);

		// Загрузка с ограниченной параллельностью
		const workers = [];
		for (let i = 0; i < this.concurrency; i++) {
			workers.push(this.uploadWorker(file, fileId, uploadId, partSize, queue, uploadedParts, onProgress, totalParts, alreadyUploadedParts));
		}

		await Promise.all(workers);

		// Сортировка по PartNumber
		uploadedParts.sort((a, b) => a.PartNumber - b.PartNumber);

		return uploadedParts;
	}

	/**
	 * Worker для параллельной загрузки частей
	 */
	async uploadWorker(file, fileId, uploadId, partSize, queue, uploadedParts, onProgress, totalParts, alreadyUploadedParts = []) {
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

			// Сообщить backend о загруженной части
			try {
				await fetch(`${this.apiBaseUrl}/api/part-uploaded`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
					},
					body: JSON.stringify({
						fileId,
						uploadId,
						partNumber: part.PartNumber,
						etag: part.ETag,
					}),
				});
			} catch (error) {
				console.error('Failed to notify backend about uploaded part:', error);
				// Не прерываем загрузку из-за ошибки уведомления
			}

			// Сохранить прогресс в IndexedDB
			if (this.storage) {
				try {
					const existingData = await this.storage.getUpload(fileId);
					if (existingData) {
						const updatedPartsData = [...existingData.uploadedPartsData, part];
						await this.storage.updateProgress(fileId, updatedPartsData);
					}
				} catch (error) {
					console.error('Failed to save progress to IndexedDB:', error);
					// Не прерываем загрузку из-за ошибки IndexedDB
				}
			}

			// Обновить прогресс
			if (onProgress) {
				const totalUploadedParts = alreadyUploadedParts.length + uploadedParts.length;
				onProgress({
					percentage: (totalUploadedParts / totalParts) * 100,
					currentPart: totalUploadedParts,
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
