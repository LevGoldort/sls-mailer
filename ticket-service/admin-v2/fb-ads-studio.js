const CITIES = [
    { label: 'Тель-Авив',  lat: 32.0853, lng: 34.7818 },
    { label: 'Хайфа',      lat: 32.8192, lng: 34.9983 },
    { label: 'Иерусалим',  lat: 31.7683, lng: 35.2137 },
    { label: 'Беэр-Шева',  lat: 31.2518, lng: 34.7913 },
    { label: 'Нетания',    lat: 32.3215, lng: 34.8532 },
];

const SLOTS = [
    { key: 'story_image',      label: 'Story (9:16)',       type: 'image', cropW: 1080, cropH: 1920, icon: '🖼' },
    { key: 'square_image',     label: 'Квадрат (1:1)',      type: 'image', cropW: 1080, cropH: 1080, icon: '⬛' },
    { key: 'horizontal_image', label: 'Широкий (16:9)',     type: 'image', cropW: 1200, cropH: 675,  icon: '🖥' },
    { key: 'story_video',      label: 'Story видео (9:16)', type: 'video', icon: '🎬' },
];

// Slot state: { key → s3_url | null }
const slotUrls = {};
SLOTS.forEach(s => slotUrls[s.key] = null);

let allEvents = [];
let mainImageUrl = null;

// ── Init ───────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    await initAdmin();
    initCityDropdown();
    setDefaultDates();
    renderSlots();
    await loadEvents();
    checkUrlParam();
});

function initCityDropdown() {
    const sel = document.getElementById('city-select');
    sel.innerHTML = CITIES.map(c =>
        `<option value="${c.lat},${c.lng}">${c.label}</option>`
    ).join('');
}

function setDefaultDates() {
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('start-date').value = today;
}

async function loadEvents() {
    try {
        const data = await API.getEvents();
        allEvents = (data.events || data || []).filter(e => e.status === 'active');
        allEvents.sort((a, b) => (a.date || '').localeCompare(b.date || ''));

        const sel = document.getElementById('event-select');
        sel.innerHTML = '<option value="">— Выбери событие —</option>' +
            allEvents.map(e => `<option value="${e.event_id}">${e.title || e.event_id}</option>`).join('');
    } catch (err) {
        showToast('Не удалось загрузить события: ' + err.message, 'error');
    }
}

function checkUrlParam() {
    const params = new URLSearchParams(window.location.search);
    const eventId = params.get('event_id');
    if (eventId) {
        const sel = document.getElementById('event-select');
        sel.value = eventId;
        onEventSelected();
    }
}

// ── Event selection ────────────────────────────────────────────────────

function onEventSelected() {
    const eventId = document.getElementById('event-select').value;
    if (!eventId) return;
    const ev = allEvents.find(e => e.event_id === eventId);
    if (!ev) return;

    document.getElementById('campaign-name').value = `${ev.title || ''} — FB Ads`;
    document.getElementById('ad-text').value = ev.description || ev.short_description || '';

    if (ev.date) {
        const endDate = ev.date.split('T')[0];
        document.getElementById('end-date').value = endDate;
    }

    const images = ev.images || (ev.photo_url ? [ev.photo_url] : []);
    mainImageUrl = images[0] || null;

    // Offer prefill for image slots
    SLOTS.forEach(slot => {
        if (slot.type === 'image' && mainImageUrl) {
            const prefillBtn = document.getElementById(`prefill-${slot.key}`);
            if (prefillBtn) prefillBtn.style.display = '';
        }
    });
}

// ── Slot rendering ─────────────────────────────────────────────────────

function renderSlots() {
    const grid = document.getElementById('slots-grid');
    grid.innerHTML = SLOTS.map(slot => `
        <div class="creative-slot" id="slot-${slot.key}">
            <div class="creative-slot-label">${slot.icon} ${slot.label}</div>
            <div class="creative-slot-preview" id="preview-${slot.key}"></div>
            <div class="creative-slot-actions">
                ${slot.type === 'image' ? `
                    <button class="btn btn-ghost" id="prefill-${slot.key}"
                        style="display:none" onclick="prefillSlot('${slot.key}')">
                        ↓ Из события
                    </button>
                    <label class="btn btn-ghost" style="cursor:pointer;">
                        Загрузить фото
                        <input type="file" accept="image/*" style="display:none"
                            onchange="handleImageFile('${slot.key}', this.files[0])">
                    </label>
                ` : `
                    <label class="btn btn-ghost" style="cursor:pointer;">
                        Загрузить видео
                        <input type="file" accept="video/mp4" style="display:none"
                            onchange="handleVideoFile(this.files[0])">
                    </label>
                `}
                <button class="btn btn-ghost" id="clear-${slot.key}"
                    style="display:none; color:var(--red, #ef4444);"
                    onclick="clearSlot('${slot.key}')">Очистить</button>
            </div>
        </div>
    `).join('');
}

function markSlotFilled(key, previewHtml) {
    slotUrls[key] = slotUrls[key]; // url already set before calling this
    const slotEl = document.getElementById(`slot-${key}`);
    slotEl.classList.add('filled');
    document.getElementById(`preview-${key}`).innerHTML = previewHtml;
    const clearBtn = document.getElementById(`clear-${key}`);
    if (clearBtn) clearBtn.style.display = '';
}

function clearSlot(key) {
    slotUrls[key] = null;
    const slotEl = document.getElementById(`slot-${key}`);
    slotEl.classList.remove('filled');
    document.getElementById(`preview-${key}`).innerHTML = '';
    const clearBtn = document.getElementById(`clear-${key}`);
    if (clearBtn) clearBtn.style.display = 'none';
}

// ── Image handling ─────────────────────────────────────────────────────

async function prefillSlot(key) {
    if (!mainImageUrl) return;
    try {
        const slot = SLOTS.find(s => s.key === key);
        const resp = await fetch(mainImageUrl);
        const blob = await resp.blob();
        const file = new File([blob], 'event-image.jpg', { type: blob.type || 'image/jpeg' });
        await cropAndUploadImage(key, file, slot.cropW, slot.cropH);
    } catch (err) {
        showToast('Не удалось загрузить изображение: ' + err.message, 'error');
    }
}

async function handleImageFile(key, file) {
    if (!file) return;
    const slot = SLOTS.find(s => s.key === key);
    await cropAndUploadImage(key, file, slot.cropW, slot.cropH);
}

async function cropAndUploadImage(key, file, cropW, cropH) {
    return new Promise(resolve => {
        showCropModal(file, cropW, cropH, 0.88, async blob => {
            try {
                const croppedFile = new File([blob], file.name, { type: 'image/jpeg' });
                const url = await uploadToS3(croppedFile, `fb-ads/${key}-${Date.now()}.jpg`);
                slotUrls[key] = url;
                markSlotFilled(key, `<img src="${url}" alt="${key}">`);
                resolve(url);
            } catch (err) {
                showToast('Ошибка загрузки: ' + err.message, 'error');
                resolve(null);
            }
        });
    });
}

// ── Video handling ─────────────────────────────────────────────────────

async function handleVideoFile(file) {
    if (!file) return;
    const key = 'story_video';

    const uploadingEl = document.getElementById(`preview-${key}`);
    uploadingEl.innerHTML = '<span style="opacity:.5; font-size:13px;">Загрузка...</span>';

    try {
        const filename = `fb-ads-video-${Date.now()}.mp4`;
        const { upload_url, s3_url } = await apiCall(
            `/api/facebook/upload-url?filename=${encodeURIComponent(filename)}&contentType=video/mp4`
        );
        await fetch(upload_url, {
            method: 'PUT',
            body: file,
            headers: { 'Content-Type': 'video/mp4' },
        });
        slotUrls[key] = s3_url;
        markSlotFilled(key, `<video src="${s3_url}" controls style="max-height:110px;"></video>`);
    } catch (err) {
        uploadingEl.innerHTML = '';
        showToast('Ошибка загрузки видео: ' + err.message, 'error');
    }
}

// ── Submit ─────────────────────────────────────────────────────────────

async function handleSubmit() {
    const eventId      = document.getElementById('event-select').value;
    const campaignName = document.getElementById('campaign-name').value.trim();
    const adText       = document.getElementById('ad-text').value.trim();
    const dailyBudget  = document.getElementById('daily-budget').value;
    const startDate    = document.getElementById('start-date').value;
    const endDate      = document.getElementById('end-date').value;
    const cityVal      = document.getElementById('city-select').value;

    if (!eventId)      return showToast('Выбери событие', 'error');
    if (!campaignName) return showToast('Введи название кампании', 'error');
    if (!adText)       return showToast('Введи текст объявления', 'error');
    if (!dailyBudget)  return showToast('Введи бюджет', 'error');
    if (!startDate || !endDate) return showToast('Укажи даты кампании', 'error');

    const filledCreatives = {};
    SLOTS.forEach(s => { if (slotUrls[s.key]) filledCreatives[s.key] = slotUrls[s.key]; });
    if (Object.keys(filledCreatives).length === 0) {
        return showToast('Добавь хотя бы один креатив', 'error');
    }

    const [cityLat, cityLng] = cityVal.split(',').map(Number);

    const btn = document.getElementById('submit-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner spinner-white"></span> Создаём...';

    try {
        const result = await apiCall('/api/facebook/create-ad', 'POST', {
            event_id:       eventId,
            campaign_name:  campaignName,
            ad_text:        adText,
            daily_budget_ils: Number(dailyBudget),
            start_date:     startDate,
            end_date:       endDate,
            city_lat:       cityLat,
            city_lng:       cityLng,
            creatives:      filledCreatives,
        });

        document.getElementById('result-campaign-id').textContent = result.campaign_id;
        document.getElementById('ads-manager-link').href = result.manager_url;

        if (result.partial && result.ads_failed?.length) {
            const warn = document.getElementById('partial-warning');
            warn.style.display = '';
            document.getElementById('failed-ads-list').innerHTML =
                result.ads_failed.map(f => `<li>${f.slot}: ${f.error}</li>`).join('');
        }

        document.getElementById('form-section').style.display = 'none';
        document.getElementById('success-section').style.display = '';

    } catch (err) {
        showToast(err.message || 'Ошибка создания кампании', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Создать кампанию (PAUSED)';
    }
}

function resetForm() {
    SLOTS.forEach(s => clearSlot(s.key));
    document.getElementById('event-select').value = '';
    document.getElementById('campaign-name').value = '';
    document.getElementById('ad-text').value = '';
    document.getElementById('daily-budget').value = '';
    setDefaultDates();
    document.getElementById('partial-warning').style.display = 'none';
    document.getElementById('success-section').style.display = 'none';
    mainImageUrl = null;
    switchTab('create');
}

// ── Tabs ───────────────────────────────────────────────────────────────────

function switchTab(tab) {
    document.querySelectorAll('.fb-tab').forEach(el =>
        el.classList.toggle('active', el.textContent.includes(tab === 'create' ? 'Создать' : 'Кампании'))
    );
    document.getElementById('form-section').style.display      = tab === 'create'    ? '' : 'none';
    document.getElementById('campaigns-section').style.display = tab === 'campaigns' ? '' : 'none';
    document.getElementById('success-section').style.display   = 'none';
    if (tab === 'campaigns') loadCampaigns();
}

// ── Campaign stats ─────────────────────────────────────────────────────────

async function loadCampaigns() {
    const list = document.getElementById('campaigns-list');
    list.innerHTML = '<span style="opacity:.5;font-size:13px;">Загрузка...</span>';
    try {
        const { campaigns } = await apiCall('/api/facebook/campaigns');
        renderCampaigns(campaigns);
    } catch (err) {
        list.innerHTML = `<span style="color:var(--red, #ef4444)">Ошибка: ${err.message}</span>`;
    }
}

function renderCampaigns(campaigns) {
    const list = document.getElementById('campaigns-list');
    if (!campaigns || campaigns.length === 0) {
        list.innerHTML = '<p style="text-align:center;opacity:.5;padding:24px 0;">Нет кампаний</p>';
        return;
    }

    const fmtNum  = n => Number(n).toLocaleString('ru');
    const fmtDate = s => {
        if (!s) return '—';
        const d = new Date(s);
        return `${String(d.getDate()).padStart(2,'0')}.${String(d.getMonth()+1).padStart(2,'0')}`;
    };

    const rows = campaigns.map(c => {
        const statusBadge = c.status === 'ACTIVE'
            ? `<span class="fb-status-active">ACTIVE</span>`
            : `<span class="fb-status-paused">${c.status}</span>`;
        const period = `${fmtDate(c.start_time)} — ${fmtDate(c.end_time)}`;
        const spend  = `${c.spend_ils} ₪ / ${c.daily_budget_ils} ₪`;
        return `<tr>
            <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${c.name}">${c.name}</td>
            <td>${statusBadge}</td>
            <td style="white-space:nowrap;">${period}</td>
            <td style="text-align:right;">${fmtNum(c.impressions)}</td>
            <td style="text-align:right;">${fmtNum(c.clicks)}</td>
            <td style="text-align:right;">${fmtNum(c.conversions)}</td>
            <td style="white-space:nowrap;">${spend}</td>
            <td><a href="${c.manager_url}" target="_blank" style="text-decoration:none;font-size:16px;">↗</a></td>
        </tr>`;
    }).join('');

    list.innerHTML = `<div style="overflow-x:auto;">
        <table class="fb-campaigns-table">
            <thead><tr>
                <th>Название</th>
                <th>Статус</th>
                <th>Период</th>
                <th style="text-align:right;">Показы</th>
                <th style="text-align:right;">Клики</th>
                <th style="text-align:right;">Конв.</th>
                <th>Потрачено / день</th>
                <th></th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;
}
