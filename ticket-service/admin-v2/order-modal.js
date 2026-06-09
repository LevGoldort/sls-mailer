// order-modal.js — Order detail modal (styles live in style.css)

(function () {
    const overlay = document.createElement('div');
    overlay.className = 'order-modal-overlay';
    overlay.id = 'order-modal-overlay';
    overlay.innerHTML = '<div class="order-modal-content" id="order-modal-body"></div>';
    document.body.appendChild(overlay);

    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeOrderModal();
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && overlay.classList.contains('active')) closeOrderModal();
    });

    // === Helpers ===
    function formatWhatsAppLink(phone) {
        if (!phone) return null;
        let cleaned = phone.replace(/[^\d]/g, '');
        if (cleaned.startsWith('0')) cleaned = '972' + cleaned.substring(1);
        return `https://wa.me/${cleaned}`;
    }

    function getQRStatus(qr) {
        if (qr.cancelled) return { text: 'Cancelled', cls: 'cancelled' };
        if (qr.scanned)   return { text: 'Scanned',   cls: 'scanned' };
        return { text: 'Active', cls: 'active' };
    }

    let seatingMapCache = {};

    function formatSeat(seatId) {
        if (!seatId) return '-';
        const parts = seatId.split('-');
        if (parts.length !== 2) return seatId;
        const rowIndex  = parseInt(parts[0]);
        const seatIndex = parseInt(parts[1]);
        let rowDisplay  = rowIndex + 1;
        let seatDisplay = seatIndex + 1;

        if (window._currentSeatingMap) {
            const cfg    = window._currentSeatingMap;
            const custom = cfg.custom_numbers && cfg.custom_numbers[seatId];
            if (custom) {
                seatDisplay = custom.seat;
                if (custom.row !== undefined) rowDisplay = custom.row;
            } else {
                const disabledSeats = new Set(cfg.disabled_seats || []);
                const seatsPerRow   = parseInt(cfg.seats_per_row);
                let enabledCount = 0;
                if (cfg.numbering_direction === 'right-to-left') {
                    for (let s = seatsPerRow - 1; s >= 0; s--) {
                        if (!disabledSeats.has(`${rowIndex}-${s}`)) {
                            enabledCount++;
                            if (s === seatIndex) break;
                        }
                    }
                } else {
                    for (let s = 0; s <= seatIndex; s++) {
                        if (!disabledSeats.has(`${rowIndex}-${s}`)) enabledCount++;
                    }
                }
                seatDisplay = enabledCount;
            }
        }
        return `Ряд ${rowDisplay}, Место ${seatDisplay}`;
    }

    // === Open ===
    window.openOrderModal = async function (orderId) {
        const body = document.getElementById('order-modal-body');
        overlay.classList.add('active');
        body.innerHTML = '<div class="order-modal-loading"><span class="spinner"></span> Загрузка...</div>';

        try {
            const data  = await API.getOrder(orderId);
            const order = data.order;

            window._currentSeatingMap = null;
            if (!seatingMapCache[order.event_id]) {
                try {
                    const smData = await API.getSeatingMap(order.event_id);
                    seatingMapCache[order.event_id] = smData.seating_map || null;
                } catch {
                    seatingMapCache[order.event_id] = null;
                }
            }
            window._currentSeatingMap = seatingMapCache[order.event_id];

            renderOrder(order);
        } catch (err) {
            body.innerHTML = `
                <button class="order-modal-close" onclick="closeOrderModal()">&times;</button>
                <p style="color:var(--red);padding:40px;text-align:center;">
                    Ошибка загрузки заказа: ${escapeHtml(err.message)}
                </p>`;
        }
    };

    window.closeOrderModal = function () {
        overlay.classList.remove('active');
    };

    // === Render ===
    function renderOrder(order) {
        const body     = document.getElementById('order-modal-body');
        const customer = order.customer || {};
        const payment  = order.payment  || {};
        const qrCodes  = order.qr_codes || [];
        const tickets  = order.tickets  || [];
        const isSeated = qrCodes.some(qr => qr.seat_id);

        const typeNameMap = {};
        tickets.forEach(t => { typeNameMap[t.type_id] = t.type_name; });

        const waLink    = formatWhatsAppLink(customer.phone);
        const phoneHtml = waLink
            ? `<a href="${waLink}" target="_blank" class="whatsapp-link">${escapeHtml(customer.phone)}</a>`
            : escapeHtml(customer.phone || '-');

        let couponHtml = '';
        if (order.coupon_code) {
            couponHtml = `
                <div>
                    <span class="label">Купон</span>
                    <p><span class="coupon-badge">${escapeHtml(order.coupon_code)}</span> -${formatCurrency(order.discount_amount || 0)}</p>
                </div>`;
        }

        const displayStatus = (function () {
            if (payment.status !== 'completed') {
                return { label: payment.status || 'pending', cls: 'status-pending' };
            }
            const cancelledCount = qrCodes.filter(qr => qr.cancelled).length;
            if (qrCodes.length > 0 && cancelledCount === qrCodes.length) {
                return { label: 'cancelled', cls: 'status-cancelled' };
            }
            if (cancelledCount > 0) {
                return { label: 'partially cancelled', cls: 'status-partially_cancelled' };
            }
            return { label: 'completed', cls: 'status-completed' };
        })();

        const ticketRows = qrCodes.map(qr => {
            const status   = getQRStatus(qr);
            const canSelect = !qr.cancelled && !qr.scanned && payment.status === 'completed';
            const rowClass  = qr.cancelled ? 'ticket-cancelled' : '';
            const typeName  = typeNameMap[qr.ticket_type] || qr.ticket_type;

            let cols = `<td>${typeName}</td>`;
            if (isSeated) cols += `<td>${formatSeat(qr.seat_id)}</td>`;
            cols += `
                <td class="mono">${qr.code}</td>
                <td><span class="qr-status ${status.cls}">${status.text}</span></td>
                <td><input type="checkbox" class="cancel-ticket-cb" data-code="${qr.code}" ${canSelect ? '' : 'disabled'}></td>
            `;
            return `<tr class="${rowClass}">${cols}</tr>`;
        }).join('');

        let thCols = '<th>Тип</th>';
        if (isSeated) thCols += '<th>Место</th>';
        thCols += '<th>QR Code</th><th>Статус</th><th>Отмена</th>';

        body.innerHTML = `
            <button class="order-modal-close" onclick="closeOrderModal()">&times;</button>

            <h2 style="margin:0 0 20px;font-size:18px;font-weight:700;">Детали заказа</h2>

            <div class="order-modal-section">
                <h3>Покупатель</h3>
                <div class="order-modal-info">
                    <div>
                        <span class="label">Имя</span>
                        <div class="customer-field" id="field-name">
                            <span class="customer-field-value">${escapeHtml(customer.name || '-')}</span>
                            <button class="btn-edit-field" onclick="startEditField('${order.order_id}','name','${escapeHtml(customer.name || '')}')">✏️</button>
                        </div>
                    </div>
                    <div>
                        <span class="label">Email</span>
                        <div class="customer-field" id="field-email">
                            <span class="customer-field-value">${escapeHtml(customer.email || '-')}</span>
                            <button class="btn-edit-field" onclick="startEditField('${order.order_id}','email','${escapeHtml(customer.email || '')}')">✏️</button>
                        </div>
                    </div>
                    <div>
                        <span class="label">Телефон</span>
                        <div class="customer-field" id="field-phone">
                            <span class="customer-field-value">${phoneHtml}</span>
                            <button class="btn-edit-field" onclick="startEditField('${order.order_id}','phone','${escapeHtml(customer.phone || '')}')">✏️</button>
                        </div>
                    </div>
                </div>
            </div>

            <div class="order-modal-section">
                <h3>Заказ</h3>
                <div class="order-modal-info">
                    <div>
                        <span class="label">ID заказа</span>
                        <p class="mono">${order.order_id}</p>
                    </div>
                    <div>
                        <span class="label">Статус</span>
                        <p><span class="status-badge ${displayStatus.cls}">${displayStatus.label}</span></p>
                    </div>
                    <div>
                        <span class="label">Сумма</span>
                        <p><strong>${formatCurrency(order.total_amount)}</strong></p>
                    </div>
                    <div>
                        <span class="label">Дата</span>
                        <p>${formatDate(order.created_at)}</p>
                    </div>
                    ${couponHtml}
                </div>
            </div>

            <div class="order-modal-section">
                <h3>Билеты</h3>
                <table class="order-modal-tickets-table">
                    <thead><tr>${thCols}</tr></thead>
                    <tbody>${ticketRows}</tbody>
                </table>
            </div>

            <div class="order-modal-section">
                <div class="order-modal-actions">
                    <button class="order-modal-btn btn-cancel-tickets" id="btn-cancel-selected" disabled
                            onclick="handleCancelTickets('${order.order_id}')">
                        Отменить выбранные
                    </button>
                </div>
            </div>

            <div class="order-modal-section">
                <h3>Отправить письмо</h3>
                <div class="resend-section">
                    <textarea id="resend-custom-message" placeholder="Дополнительное сообщение (необязательно)..."></textarea>
                    <button class="order-modal-btn btn-resend-email" onclick="handleResendEmail('${order.order_id}')">
                        Отправить письмо
                    </button>
                </div>
            </div>

            <div class="order-modal-section">
                <h3>Отправить SMS</h3>
                <div class="resend-section">
                    <textarea id="resend-sms-message" placeholder="Текст SMS (необязательно)..."></textarea>
                    <button class="order-modal-btn btn-resend-sms" onclick="handleResendSms('${order.order_id}')">
                        Отправить SMS
                    </button>
                </div>
            </div>
        `;

        body.querySelectorAll('.cancel-ticket-cb').forEach(cb => {
            cb.addEventListener('change', updateCancelButton);
        });
    }

    function updateCancelButton() {
        const btn     = document.getElementById('btn-cancel-selected');
        const checked = document.querySelectorAll('.cancel-ticket-cb:checked');
        btn.disabled = checked.length === 0;
    }

    // === Cancel tickets ===
    window.handleCancelTickets = async function (orderId) {
        const checked = document.querySelectorAll('.cancel-ticket-cb:checked');
        if (checked.length === 0) return;

        const codes = Array.from(checked).map(cb => cb.dataset.code);
        if (!confirm(`Отменить ${codes.length} билет(а)?\n\n${codes.join('\n')}\n\nДействие необратимо.`)) return;

        const btn = document.getElementById('btn-cancel-selected');
        btn.disabled = true;
        btn.textContent = 'Отмена...';

        try {
            await API.cancelTickets(orderId, { qr_codes: codes });
            showToast(`${codes.length} билет(а) отменено`);
            await openOrderModal(orderId);
            window.dispatchEvent(new CustomEvent('yb:orderUpdated', { detail: { orderId } }));
        } catch (err) {
            showToast('Ошибка отмены: ' + err.message, 'error');
            btn.disabled = false;
            btn.textContent = 'Отменить выбранные';
        }
    };

    // === Edit customer field ===
    window.startEditField = function (orderId, field, currentValue) {
        const container = document.getElementById(`field-${field}`);
        const inputType = field === 'email' ? 'email' : 'text';
        container.innerHTML = `
            <input type="${inputType}" class="customer-field-input" id="input-${field}" value="${escapeHtml(currentValue)}">
            <button class="btn-save-field" onclick="saveField('${orderId}','${field}')">Сохранить</button>
            <button class="btn-cancel-field" onclick="openOrderModal('${orderId}')">✕</button>
        `;
        document.getElementById(`input-${field}`).focus();
    };

    window.saveField = async function (orderId, field) {
        const input    = document.getElementById(`input-${field}`);
        const newValue = input.value.trim();
        if (!newValue) { showToast(`${field} не может быть пустым`, 'error'); return; }

        const saveBtn = document.getElementById(`field-${field}`).querySelector('.btn-save-field');
        saveBtn.disabled = true;
        saveBtn.textContent = '...';

        try {
            const data = {};
            data[field] = newValue;
            await API.updateOrderCustomer(orderId, data);
            showToast(`${field} обновлено`);
            await openOrderModal(orderId);
        } catch (err) {
            showToast(`Ошибка: ${err.message}`, 'error');
            saveBtn.disabled = false;
            saveBtn.textContent = 'Сохранить';
        }
    };

    // === Resend Email ===
    window.handleResendEmail = async function (orderId) {
        const textarea = document.getElementById('resend-custom-message');
        const customMessage = textarea ? textarea.value.trim() : '';
        const btn = document.querySelector('.btn-resend-email');
        btn.disabled = true;
        btn.textContent = 'Отправка...';
        try {
            await API.resendEmail(orderId, { custom_message: customMessage });
            showToast('Письмо отправлено');
            btn.textContent = 'Отправлено ✓';
            setTimeout(() => { btn.disabled = false; btn.textContent = 'Отправить письмо'; }, 2000);
        } catch (err) {
            showToast('Ошибка: ' + err.message, 'error');
            btn.disabled = false;
            btn.textContent = 'Отправить письмо';
        }
    };

    // === Resend SMS ===
    window.handleResendSms = async function (orderId) {
        const textarea = document.getElementById('resend-sms-message');
        const customMessage = textarea ? textarea.value.trim() : '';
        const btn = document.querySelector('.btn-resend-sms');
        btn.disabled = true;
        btn.textContent = 'Отправка...';
        try {
            await API.resendSms(orderId, { custom_message: customMessage });
            showToast('SMS отправлено');
            btn.textContent = 'Отправлено ✓';
            setTimeout(() => { btn.disabled = false; btn.textContent = 'Отправить SMS'; }, 2000);
        } catch (err) {
            showToast('Ошибка: ' + err.message, 'error');
            btn.disabled = false;
            btn.textContent = 'Отправить SMS';
        }
    };
})();
