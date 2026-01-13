/**
 * UploadStorage - IndexedDB wrapper для сохранения состояния загрузок
 * Позволяет возобновлять загрузки после закрытия браузера
 */

class UploadStorage {
	constructor() {
		this.dbName = 'YallabaganUploads';
		this.dbVersion = 1;
		this.storeName = 'uploads';
		this.db = null;
	}

	/**
	 * Инициализировать IndexedDB
	 */
	async init() {
		return new Promise((resolve, reject) => {
			const request = indexedDB.open(this.dbName, this.dbVersion);

			request.onerror = () => {
				console.error('IndexedDB error:', request.error);
				reject(request.error);
			};

			request.onsuccess = () => {
				this.db = request.result;
				resolve();
			};

			request.onupgradeneeded = (event) => {
				const db = event.target.result;

				// Создать object store если не существует
				if (!db.objectStoreNames.contains(this.storeName)) {
					const objectStore = db.createObjectStore(this.storeName, {
						keyPath: 'fileId',
					});

					// Создать индексы
					objectStore.createIndex('status', 'status', { unique: false });
					objectStore.createIndex('timestamp', 'timestamp', { unique: false });
				}
			};
		});
	}

	/**
	 * Сохранить новую загрузку
	 */
	async saveUpload(uploadData) {
		if (!this.db) {
			throw new Error('IndexedDB not initialized');
		}

		const data = {
			...uploadData,
			timestamp: Date.now(),
			lastUpdated: new Date().toISOString(),
		};

		return new Promise((resolve, reject) => {
			const transaction = this.db.transaction([this.storeName], 'readwrite');
			const objectStore = transaction.objectStore(this.storeName);
			const request = objectStore.put(data);

			request.onsuccess = () => resolve();
			request.onerror = () => reject(request.error);
		});
	}

	/**
	 * Получить загрузку по fileId
	 */
	async getUpload(fileId) {
		if (!this.db) {
			throw new Error('IndexedDB not initialized');
		}

		return new Promise((resolve, reject) => {
			const transaction = this.db.transaction([this.storeName], 'readonly');
			const objectStore = transaction.objectStore(this.storeName);
			const request = objectStore.get(fileId);

			request.onsuccess = () => resolve(request.result);
			request.onerror = () => reject(request.error);
		});
	}

	/**
	 * Получить все незавершенные загрузки
	 */
	async getInProgressUploads() {
		if (!this.db) {
			throw new Error('IndexedDB not initialized');
		}

		return new Promise((resolve, reject) => {
			const transaction = this.db.transaction([this.storeName], 'readonly');
			const objectStore = transaction.objectStore(this.storeName);
			const index = objectStore.index('status');
			const request = index.getAll('in-progress');

			request.onsuccess = () => resolve(request.result || []);
			request.onerror = () => reject(request.error);
		});
	}

	/**
	 * Обновить прогресс загрузки (добавить загруженные части)
	 */
	async updateProgress(fileId, uploadedPartsData) {
		if (!this.db) {
			throw new Error('IndexedDB not initialized');
		}

		const upload = await this.getUpload(fileId);
		if (!upload) {
			throw new Error(`Upload ${fileId} not found`);
		}

		upload.uploadedPartsData = uploadedPartsData;
		upload.lastUpdated = new Date().toISOString();

		return this.saveUpload(upload);
	}

	/**
	 * Пометить загрузку как завершенную
	 */
	async markCompleted(fileId) {
		if (!this.db) {
			throw new Error('IndexedDB not initialized');
		}

		const upload = await this.getUpload(fileId);
		if (!upload) {
			return; // Already deleted or doesn't exist
		}

		upload.status = 'completed';
		upload.completedAt = new Date().toISOString();
		upload.lastUpdated = new Date().toISOString();

		return this.saveUpload(upload);
	}

	/**
	 * Удалить загрузку
	 */
	async deleteUpload(fileId) {
		if (!this.db) {
			throw new Error('IndexedDB not initialized');
		}

		return new Promise((resolve, reject) => {
			const transaction = this.db.transaction([this.storeName], 'readwrite');
			const objectStore = transaction.objectStore(this.storeName);
			const request = objectStore.delete(fileId);

			request.onsuccess = () => resolve();
			request.onerror = () => reject(request.error);
		});
	}

	/**
	 * Удалить старые записи (старше N дней)
	 */
	async clearOldUploads(days = 7) {
		if (!this.db) {
			throw new Error('IndexedDB not initialized');
		}

		const cutoffTime = Date.now() - days * 24 * 60 * 60 * 1000;

		return new Promise((resolve, reject) => {
			const transaction = this.db.transaction([this.storeName], 'readwrite');
			const objectStore = transaction.objectStore(this.storeName);
			const index = objectStore.index('timestamp');
			const request = index.openCursor();

			const toDelete = [];

			request.onsuccess = (event) => {
				const cursor = event.target.result;
				if (cursor) {
					const upload = cursor.value;

					// Удалить если:
					// 1. Завершенные загрузки старше cutoff
					// 2. Незавершенные загрузки старше cutoff (истекли)
					if (upload.timestamp < cutoffTime) {
						toDelete.push(upload.fileId);
					}

					cursor.continue();
				} else {
					// Удалить все найденные
					const deleteTransaction = this.db.transaction([this.storeName], 'readwrite');
					const deleteStore = deleteTransaction.objectStore(this.storeName);

					toDelete.forEach((fileId) => {
						deleteStore.delete(fileId);
					});

					deleteTransaction.oncomplete = () => {
						console.log(`Cleared ${toDelete.length} old uploads`);
						resolve(toDelete.length);
					};
					deleteTransaction.onerror = () => reject(deleteTransaction.error);
				}
			};

			request.onerror = () => reject(request.error);
		});
	}

	/**
	 * Получить все загрузки (для отладки)
	 */
	async getAllUploads() {
		if (!this.db) {
			throw new Error('IndexedDB not initialized');
		}

		return new Promise((resolve, reject) => {
			const transaction = this.db.transaction([this.storeName], 'readonly');
			const objectStore = transaction.objectStore(this.storeName);
			const request = objectStore.getAll();

			request.onsuccess = () => resolve(request.result || []);
			request.onerror = () => reject(request.error);
		});
	}
}
