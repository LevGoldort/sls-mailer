/**
 * Admin Page Logic
 */

// Конфигурация
const API_BASE_URL = 'https://file-upload-api.yalla.workers.dev';

// DOM элементы
const authSection = document.getElementById('auth-section');
const filesSection = document.getElementById('files-section');
const errorSection = document.getElementById('error-section');

const adminAuthForm = document.getElementById('admin-auth-form');
const adminKeyInput = document.getElementById('admin-key');
const refreshBtn = document.getElementById('refresh-btn');
const logoutLink = document.getElementById('logout-link');
const backBtn = document.getElementById('back-btn');

const loadingDiv = document.getElementById('loading');
const emptyState = document.getElementById('empty-state');
const filesTableWrapper = document.getElementById('files-table-wrapper');
const filesTbody = document.getElementById('files-tbody');

const totalFilesSpan = document.getElementById('total-files');
const totalSizeSpan = document.getElementById('total-size');

const deleteModal = document.getElementById('delete-modal');
const deleteFilename = document.getElementById('delete-filename');
const confirmDeleteBtn = document.getElementById('confirm-delete-btn');
const cancelDeleteBtn = document.getElementById('cancel-delete-btn');

const errorMessage = document.getElementById('error-message');

// State
let adminKey = null;
let files = [];
let deleteFileId = null;

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
	// Проверить сохраненный ключ
	const savedKey = localStorage.getItem('adminKey');
	if (savedKey) {
		adminKey = savedKey;
		adminKeyInput.value = savedKey;
		loadFiles();
	}

	// Event listeners
	adminAuthForm.addEventListener('submit', handleAuth);
	refreshBtn.addEventListener('click', loadFiles);
	logoutLink.addEventListener('click', handleLogout);
	backBtn.addEventListener('click', () => {
		authSection.style.display = 'block';
		errorSection.style.display = 'none';
	});

	confirmDeleteBtn.addEventListener('click', confirmDelete);
	cancelDeleteBtn.addEventListener('click', closeDeleteModal);
});

/**
 * Аутентификация
 */
async function handleAuth(e) {
	e.preventDefault();

	adminKey = adminKeyInput.value;
	if (!adminKey) {
		showError('Введите admin key');
		return;
	}

	// Сохранить ключ
	localStorage.setItem('adminKey', adminKey);

	// Загрузить файлы
	await loadFiles();
}

/**
 * Загрузить список файлов
 */
async function loadFiles() {
	if (!adminKey) {
		showError('Admin key не установлен');
		return;
	}

	authSection.style.display = 'none';
	filesSection.style.display = 'block';
	errorSection.style.display = 'none';
	loadingDiv.style.display = 'block';

	try {
		const response = await fetch(`${API_BASE_URL}/api/admin/list?key=${encodeURIComponent(adminKey)}`);

		if (!response.ok) {
			if (response.status === 401) {
				throw new Error('Неверный admin key');
			}
			const error = await response.json();
			throw new Error(error.error || 'Ошибка загрузки файлов');
		}

		const data = await response.json();
		files = data.files || [];

		renderFiles();
	} catch (error) {
		console.error('Load files error:', error);
		showError(error.message);
	} finally {
		loadingDiv.style.display = 'none';
	}
}

/**
 * Отобразить файлы
 */
function renderFiles() {
	// Обновить статистику
	totalFilesSpan.textContent = files.length;
	const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
	totalSizeSpan.textContent = formatBytes(totalBytes);

	// Показать/скрыть пустое состояние
	if (files.length === 0) {
		emptyState.style.display = 'block';
		filesTableWrapper.style.display = 'none';
		return;
	}

	emptyState.style.display = 'none';
	filesTableWrapper.style.display = 'block';

	// Заполнить таблицу
	filesTbody.innerHTML = '';

	files.forEach((file) => {
		const row = document.createElement('tr');

		// Имя файла
		const nameCell = document.createElement('td');
		nameCell.textContent = file.filename;
		nameCell.className = 'filename-cell';
		row.appendChild(nameCell);

		// Размер
		const sizeCell = document.createElement('td');
		sizeCell.textContent = formatBytes(file.size);
		row.appendChild(sizeCell);

		// Дата
		const dateCell = document.createElement('td');
		const date = new Date(file.uploadedAt);
		dateCell.textContent = date.toLocaleString('ru-RU');
		row.appendChild(dateCell);

		// Ссылка
		const linkCell = document.createElement('td');
		const copyLinkBtn = document.createElement('button');
		copyLinkBtn.className = 'btn btn-small';
		copyLinkBtn.textContent = '📋 Копировать';
		copyLinkBtn.onclick = () => copyLink(file.downloadUrl, copyLinkBtn);
		linkCell.appendChild(copyLinkBtn);
		row.appendChild(linkCell);

		// Действия
		const actionsCell = document.createElement('td');
		const deleteBtn = document.createElement('button');
		deleteBtn.className = 'btn btn-danger btn-small';
		deleteBtn.textContent = '🗑️ Удалить';
		deleteBtn.onclick = () => openDeleteModal(file.fileId, file.filename);
		actionsCell.appendChild(deleteBtn);
		row.appendChild(actionsCell);

		filesTbody.appendChild(row);
	});
}

/**
 * Копировать ссылку
 */
async function copyLink(url, button) {
	try {
		await navigator.clipboard.writeText(url);
		const originalText = button.textContent;
		button.textContent = '✅ Скопировано';
		setTimeout(() => {
			button.textContent = originalText;
		}, 2000);
	} catch (error) {
		alert('Ошибка копирования: ' + error.message);
	}
}

/**
 * Открыть модал удаления
 */
function openDeleteModal(fileId, filename) {
	deleteFileId = fileId;
	deleteFilename.textContent = filename;
	deleteModal.style.display = 'flex';
}

/**
 * Закрыть модал удаления
 */
function closeDeleteModal() {
	deleteModal.style.display = 'none';
	deleteFileId = null;
}

/**
 * Подтвердить удаление
 */
async function confirmDelete() {
	if (!deleteFileId) return;

	try {
		const response = await fetch(
			`${API_BASE_URL}/api/admin/${deleteFileId}?key=${encodeURIComponent(adminKey)}`,
			{
				method: 'DELETE',
			}
		);

		if (!response.ok) {
			const error = await response.json();
			throw new Error(error.error || 'Ошибка удаления файла');
		}

		// Обновить список
		await loadFiles();
		closeDeleteModal();
	} catch (error) {
		console.error('Delete error:', error);
		alert('Ошибка удаления: ' + error.message);
	}
}

/**
 * Выход
 */
function handleLogout(e) {
	e.preventDefault();

	if (confirm('Выйти из админ-панели?')) {
		localStorage.removeItem('adminKey');
		adminKey = null;
		adminKeyInput.value = '';

		authSection.style.display = 'block';
		filesSection.style.display = 'none';
		errorSection.style.display = 'none';
	}
}

/**
 * Показать ошибку
 */
function showError(message) {
	authSection.style.display = 'none';
	filesSection.style.display = 'none';
	errorSection.style.display = 'block';

	errorMessage.textContent = message;
}

/**
 * Форматирование размера
 */
function formatBytes(bytes) {
	if (bytes === 0) return '0 B';
	const k = 1024;
	const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
	const i = Math.floor(Math.log(bytes) / Math.log(k));
	return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}
