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

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
	uploader = new MultipartUploader(API_BASE_URL, {
		concurrency: 3,
		maxRetries: 3,
	});

	// Event listeners
	fileInput.addEventListener('change', handleFileSelect);
	uploadForm.addEventListener('submit', handleUploadSubmit);
	cancelBtn.addEventListener('click', handleCancel);
	copyBtn.addEventListener('click', handleCopy);
	uploadAnotherBtn.addEventListener('click', resetForm);
	retryBtn.addEventListener('click', resetForm);
});

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

	if (!password) {
		showError('Введите пароль');
		return;
	}

	// Показать прогресс
	showProgress();

	try {
		const result = await uploader.uploadFile(file, password, {
			onProgress: updateProgress,
			onSpeedUpdate: updateSpeed,
			onError: (error) => {
				console.error('Upload error:', error);
			},
		});

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
