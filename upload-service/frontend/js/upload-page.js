/**
 * Upload Page Logic
 */

// Конфигурация
const API_BASE_URL = 'https://file-upload-api.yalla.workers.dev';

// DOM элементы
const uploadSection = document.getElementById('upload-section');
const progressSection = document.getElementById('progress-section');
const resultSection = document.getElementById('result-section');
const errorSection = document.getElementById('error-section');

const uploadForm = document.getElementById('upload-form');
const passwordInput = document.getElementById('password');
const fileInput = document.getElementById('file-input');
const fileInfo = document.getElementById('file-info');
const uploadBtn = document.getElementById('upload-btn');
const cancelBtn = document.getElementById('cancel-btn');

const progressFill = document.getElementById('progress-fill');
const progressPercentage = document.getElementById('progress-percentage');
const progressParts = document.getElementById('progress-parts');
const uploadSpeed = document.getElementById('upload-speed');
const timeRemaining = document.getElementById('time-remaining');
const uploadedSize = document.getElementById('uploaded-size');
const statusMessage = document.getElementById('status-message');

const downloadUrl = document.getElementById('download-url');
const copyBtn = document.getElementById('copy-btn');
const uploadAnotherBtn = document.getElementById('upload-another-btn');
const resultFilename = document.getElementById('result-filename');

const errorMessage = document.getElementById('error-message');
const retryBtn = document.getElementById('retry-btn');

// State
let uploader = null;
let currentFile = null;
let uploadStorage = null;
let pendingResumeData = null;

// Инициализация
document.addEventListener('DOMContentLoaded', async () => {
	// Инициализация storage
	uploadStorage = new UploadStorage();
	await uploadStorage.init();

	// Uploader с storage
	uploader = new MultipartUploader(API_BASE_URL, {
		concurrency: 3,
		maxRetries: 3,
		storage: uploadStorage,
	});

	// Проверка незавершенных загрузок
	await checkForResumeUploads();

	// Event listeners
	fileInput.addEventListener('change', handleFileSelect);
	uploadForm.addEventListener('submit', handleUploadSubmit);
	cancelBtn.addEventListener('click', handleCancel);
	copyBtn.addEventListener('click', handleCopy);
	uploadAnotherBtn.addEventListener('click', resetForm);
	retryBtn.addEventListener('click', resetForm);
});

/**
 * Проверка незавершенных загрузок при загрузке страницы
 */
async function checkForResumeUploads() {
	try {
		const inProgressUploads = await uploadStorage.getInProgressUploads();

		if (inProgressUploads.length > 0) {
			// Взять последнюю незавершенную загрузку
			const latest = inProgressUploads.sort((a, b) => b.timestamp - a.timestamp)[0];

			// Проверить с backend что загрузка еще активна
			const resumeInfo = await uploader.canResumeUpload(latest.fileId);

			if (resumeInfo && resumeInfo.success) {
				showResumeModal(resumeInfo);
				pendingResumeData = resumeInfo;
			} else {
				// Истекло - удалить из IndexedDB
				await uploadStorage.deleteUpload(latest.fileId);
			}
		}

		// Очистка старых записей (>7 дней)
		await uploadStorage.clearOldUploads(7);
	} catch (error) {
		console.error('Resume check error:', error);
	}
}

/**
 * Показать modal для возобновления загрузки
 */
function showResumeModal(resumeInfo) {
	const modal = document.getElementById('resume-modal');
	const percentDone = Math.round(
		(resumeInfo.completedParts / resumeInfo.totalParts) * 100
	);

	document.getElementById('resume-filename').textContent = resumeInfo.filename;
	document.getElementById('resume-filesize').textContent = formatBytes(resumeInfo.fileSize);
	document.getElementById('resume-progress').textContent =
		`${resumeInfo.completedParts} из ${resumeInfo.totalParts} частей (${percentDone}%)`;

	modal.style.display = 'flex';

	document.getElementById('resume-continue-btn').onclick = handleResumeContinue;
	document.getElementById('resume-cancel-btn').onclick = handleResumeCancel;
}

/**
 * Продолжить загрузку
 */
async function handleResumeContinue() {
	document.getElementById('resume-modal').style.display = 'none';
	// Попросить пользователя выбрать тот же файл
	fileInput.click();
}

/**
 * Отменить и начать новую загрузку
 */
async function handleResumeCancel() {
	document.getElementById('resume-modal').style.display = 'none';

	if (pendingResumeData) {
		try {
			// Отменить загрузку на бэкенде
			await uploader.abortUpload(pendingResumeData.fileId, pendingResumeData.uploadId);
		} catch (error) {
			console.error('Abort error:', error);
		}

		// Удалить из IndexedDB
		await uploadStorage.deleteUpload(pendingResumeData.fileId);
		pendingResumeData = null;
	}
}

/**
 * Обработка выбора файла
 */
function handleFileSelect(e) {
	const file = e.target.files[0];
	if (!file) {
		fileInfo.textContent = '';
		currentFile = null;
		return;
	}

	currentFile = file;

	// Если есть pending resume - проверить совпадение
	if (pendingResumeData) {
		if (
			file.size === pendingResumeData.fileSize &&
			file.name === pendingResumeData.filename
		) {
			fileInfo.innerHTML = `
				<strong>✅ ${file.name}</strong><br>
				<span style="color: #28a745;">Файл совпадает - загрузка будет продолжена</span><br>
				Прогресс: ${pendingResumeData.completedParts}/${pendingResumeData.totalParts} частей<br>
				Размер: ${formatBytes(file.size)}
			`;
			return;
		} else {
			// Не совпадает - отменить resume
			pendingResumeData = null;
			fileInfo.innerHTML = `
				<strong>${file.name}</strong><br>
				<span style="color: #dc3545;">Файл не совпадает с незавершенной загрузкой - начнется новая загрузка</span><br>
				Размер: ${formatBytes(file.size)}<br>
				Тип: ${file.type || 'неизвестен'}
			`;
			return;
		}
	}

	// Обычное отображение
	fileInfo.innerHTML = `
		<strong>${file.name}</strong><br>
		Размер: ${formatBytes(file.size)}<br>
		Тип: ${file.type || 'неизвестен'}
	`;
}

/**
 * Обработка отправки формы
 */
async function handleUploadSubmit(e) {
	e.preventDefault();

	const password = passwordInput.value;
	const file = currentFile || fileInput.files[0];

	if (!file) {
		showError('Выберите файл для загрузки');
		return;
	}

	// При resume пароль не нужен (уже есть fileId/uploadId)
	if (!password && !pendingResumeData) {
		showError('Введите пароль');
		return;
	}

	// Показать прогресс
	showProgress();

	try {
		const result = await uploader.uploadFile(
			file,
			password,
			{
				onProgress: updateProgress,
				onSpeedUpdate: updateSpeed,
				onError: (error) => {
					console.error('Upload error:', error);
				},
			},
			pendingResumeData // Передать resume data
		);

		// Сбросить pending resume
		pendingResumeData = null;

		// Показать результат
		showResult(result);
	} catch (error) {
		showError(error.message);
	}
}

/**
 * Обновление прогресса
 */
function updateProgress(progress) {
	const { percentage, currentPart, totalParts, uploadedBytes, totalBytes } = progress;

	progressFill.style.width = `${percentage}%`;
	progressPercentage.textContent = `${Math.round(percentage)}%`;
	progressParts.textContent = `Часть ${currentPart} из ${totalParts}`;
	uploadedSize.textContent = formatBytes(uploadedBytes);

	statusMessage.textContent = `Загружено ${formatBytes(uploadedBytes)} из ${formatBytes(totalBytes)}`;
}

/**
 * Обновление скорости
 */
function updateSpeed(speed, remaining) {
	uploadSpeed.textContent = formatSpeed(speed);
	timeRemaining.textContent = formatTime(remaining);
}

/**
 * Отмена загрузки
 */
async function handleCancel() {
	if (uploader) {
		uploader.cancel();

		if (uploader.uploadState) {
			try {
				await uploader.abortUpload(
					uploader.uploadState.fileId,
					uploader.uploadState.uploadId
				);
			} catch (error) {
				console.error('Abort error:', error);
			}
		}
	}

	showError('Загрузка отменена');
}

/**
 * Копирование ссылки
 */
async function handleCopy() {
	const url = downloadUrl.value;

	try {
		await navigator.clipboard.writeText(url);
		copyBtn.textContent = '✅ Скопировано!';
		setTimeout(() => {
			copyBtn.textContent = '📋 Копировать';
		}, 2000);
	} catch (error) {
		// Fallback для старых браузеров
		downloadUrl.select();
		document.execCommand('copy');
		copyBtn.textContent = '✅ Скопировано!';
		setTimeout(() => {
			copyBtn.textContent = '📋 Копировать';
		}, 2000);
	}
}

/**
 * Показать секцию прогресса
 */
function showProgress() {
	uploadSection.style.display = 'none';
	progressSection.style.display = 'block';
	resultSection.style.display = 'none';
	errorSection.style.display = 'none';

	uploadBtn.disabled = true;
	cancelBtn.style.display = 'inline-block';

	// Reset progress
	progressFill.style.width = '0%';
	progressPercentage.textContent = '0%';
	progressParts.textContent = 'Часть 0 из 0';
	uploadSpeed.textContent = '-';
	timeRemaining.textContent = 'Расчет...';
	uploadedSize.textContent = '0 MB';
	statusMessage.textContent = 'Начало загрузки...';
}

/**
 * Показать результат
 */
function showResult(result) {
	uploadSection.style.display = 'none';
	progressSection.style.display = 'none';
	resultSection.style.display = 'block';
	errorSection.style.display = 'none';

	downloadUrl.value = result.downloadUrl;
	resultFilename.textContent = result.filename;
}

/**
 * Показать ошибку
 */
function showError(message) {
	uploadSection.style.display = 'none';
	progressSection.style.display = 'none';
	resultSection.style.display = 'none';
	errorSection.style.display = 'block';

	errorMessage.textContent = message;
}

/**
 * Сброс формы
 */
function resetForm() {
	uploadSection.style.display = 'block';
	progressSection.style.display = 'none';
	resultSection.style.display = 'none';
	errorSection.style.display = 'none';

	uploadForm.reset();
	fileInfo.textContent = '';
	currentFile = null;
	uploadBtn.disabled = false;
	cancelBtn.style.display = 'none';

	// Reset uploader
	if (uploader) {
		uploader.aborted = false;
		uploader.uploadState = null;
	}
}
