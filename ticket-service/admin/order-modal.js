// order-modal.js - Order detail modal with cancel tickets & resend email

(function () {
    // ===== Inject Modal HTML + CSS =====
    const style = document.createElement('style');
    style.textContent = `
        .order-modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7);
            z-index: 10000;
            justify-content: center;
            align-items: flex-start;
            padding: 40px 20px;
            overflow-y: auto;
        }
        .order-modal-overlay.active {
            display: flex;
        }
        .order-modal-content {
            background: white;
            border-radius: 12px;
            max-width: 800px;
            width: 100%;
            padding: 30px;
            position: relative;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .order-modal-close {
            position: absolute;
            top: 15px; right: 20px;
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: #666;
            padding: 5px;
            line-height: 1;
        }
        .order-modal-close:hover { color: #333; }
        .order-modal-section {
            margin-bottom: 24px;
        }
        .order-modal-section h3 {
            margin: 0 0 12px 0;
            color: #667eea;
            font-size: 16px;
        }
        .order-modal-info {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px 20px;
        }
        .order-modal-info p {
            margin: 0;
            font-size: 14px;
        }
        .order-modal-info .label {
            color: #888;
            font-size: 12px;
        }
        .order-modal-tickets-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }
        .order-modal-tickets-table th {
            background: #f5f5f5;
            padding: 8px 10px;
            text-align: left;
            font-weight: 600;
            font-size: 12px;
            color: #666;
        }
        .order-modal-tickets-table td {
            padding: 8px 10px;
            border-bottom: 1px solid #eee;
        }
        .ticket-cancelled td {
            opacity: 0.5;
            text-decoration: line-through;
        }
        .qr-status {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }
        .qr-status.active { background: #e8f5e9; color: #2e7d32; }
        .qr-status.scanned { background: #e3f2fd; color: #1565c0; }
        .qr-status.cancelled { background: #fce4ec; color: #c62828; }
        .order-modal-actions {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            align-items: flex-start;
        }
        .order-modal-btn {
            padding: 8px 16px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: opacity 0.2s;
        }
        .order-modal-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .order-modal-btn:hover:not(:disabled) { opacity: 0.85; }
        .btn-cancel-tickets {
            background: #ef4444;
            color: white;
        }
        .btn-resend-email {
            background: #667eea;
            color: white;
        }
        .resend-section {
            margin-top: 16px;
            padding: 16px;
            background: #f9f9f9;
            border-radius: 8px;
        }
        .resend-section textarea {
            width: 100%;
            min-height: 60px;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
            resize: vertical;
            margin-bottom: 8px;
            box-sizing: border-box;
        }
        .order-modal-loading {
            text-align: center;
            padding: 60px 20px;
            color: #888;
        }
        .whatsapp-link {
            color: #25D366;
            text-decoration: none;
            font-weight: 500;
        }
        .whatsapp-link:hover { text-decoration: underline; }
        .coupon-badge {
            display: inline-block;
            background: #fff3cd;
            color: #856404;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }
    `;
    document.head.appendChild(style);

    const overlay = document.createElement('div');
    overlay.className = 'order-modal-overlay';
    overlay.id = 'order-modal-overlay';
    overlay.innerHTML = '<div class="order-modal-content" id="order-modal-body"></div>';
    document.body.appendChild(overlay);

    // Close on overlay click
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeOrderModal();
    });

    // Close on Escape
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && overlay.classList.contains('active')) {
            closeOrderModal();
        }
    });

    // ===== Helpers =====
    function formatWhatsAppLink(phone) {
        if (!phone) return null;
        let cleaned = phone.replace(/[^\d]/g, '');
        if (cleaned.startsWith('0')) cleaned = '972' + cleaned.substring(1);
        return `https://wa.me/${cleaned}`;
    }

    function getQRStatus(qr) {
        if (qr.cancelled) return { text: 'Cancelled', cls: 'cancelled' };
        if (qr.scanned) return { text: 'Scanned', cls: 'scanned' };
        return { text: 'Active', cls: 'active' };
    }

    function formatSeat(seatId) {
        if (!seatId) return '-';
        const parts = seatId.split('-');
        if (parts.length === 2) return `Row ${parseInt(parts[0]) + 1}, Seat ${parseInt(parts[1]) + 1}`;
        return seatId;
    }

    // ===== Open Modal =====
    window.openOrderModal = async function (orderId) {
        const body = document.getElementById('order-modal-body');
        overlay.classList.add('active');
        body.innerHTML = '<div class="order-modal-loading">Loading order...</div>';

        try {
            const data = await API.getOrder(orderId);
            const order = data.order;
            renderOrder(order);
        } catch (err) {
            body.innerHTML = `
                <button class="order-modal-close" onclick="closeOrderModal()">&times;</button>
                <p style="color: #ef4444; padding: 40px; text-align: center;">Failed to load order: ${err.message}</p>
            `;
        }
    };

    window.closeOrderModal = function () {
        overlay.classList.remove('active');
    };

    // ===== Render =====
    function renderOrder(order) {
        const body = document.getElementById('order-modal-body');
        const customer = order.customer || {};
        const payment = order.payment || {};
        const qrCodes = order.qr_codes || [];
        const tickets = order.tickets || [];
        const isSeated = qrCodes.some(qr => qr.seat_id);

        // Build ticket type name map
        const typeNameMap = {};
        tickets.forEach(t => { typeNameMap[t.type_id] = t.type_name; });

        // WhatsApp link
        const waLink = formatWhatsAppLink(customer.phone);
        const phoneHtml = waLink
            ? `<a href="${waLink}" target="_blank" class="whatsapp-link">${customer.phone}</a>`
            : (customer.phone || '-');

        // Coupon info
        let couponHtml = '';
        if (order.coupon_code) {
            const discountAmt = order.discount_amount || 0;
            couponHtml = `
                <div>
                    <span class="label">Coupon</span>
                    <p><span class="coupon-badge">${order.coupon_code}</span> -${formatCurrency(discountAmt)}</p>
                </div>
            `;
        }

        // Status badge (account for cancellations)
        const displayStatus = (function() {
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

        // Tickets table rows
        const ticketRows = qrCodes.map(qr => {
            const status = getQRStatus(qr);
            const canSelect = !qr.cancelled && !qr.scanned && payment.status === 'completed';
            const rowClass = qr.cancelled ? 'ticket-cancelled' : '';
            const typeName = typeNameMap[qr.ticket_type] || qr.ticket_type;

            let cols = `<td>${typeName}</td>`;
            if (isSeated) {
                cols += `<td>${formatSeat(qr.seat_id)}</td>`;
            }
            cols += `
                <td style="font-family: monospace; font-size: 12px;">${qr.code}</td>
                <td><span class="qr-status ${status.cls}">${status.text}</span></td>
                <td><input type="checkbox" class="cancel-ticket-cb" data-code="${qr.code}" ${canSelect ? '' : 'disabled'}></td>
            `;

            return `<tr class="${rowClass}">${cols}</tr>`;
        }).join('');

        // Table header
        let thCols = '<th>Ticket Type</th>';
        if (isSeated) thCols += '<th>Seat</th>';
        thCols += '<th>QR Code</th><th>Status</th><th>Select</th>';

        body.innerHTML = `
            <button class="order-modal-close" onclick="closeOrderModal()">&times;</button>

            <h2 style="margin: 0 0 20px 0; font-size: 20px;">Order Details</h2>

            <div class="order-modal-section">
                <h3>Customer</h3>
                <div class="order-modal-info">
                    <div>
                        <span class="label">Name</span>
                        <p>${customer.name || '-'}</p>
                    </div>
                    <div>
                        <span class="label">Email</span>
                        <p>${customer.email || '-'}</p>
                    </div>
                    <div>
                        <span class="label">Phone</span>
                        <p>${phoneHtml}</p>
                    </div>
                </div>
            </div>

            <div class="order-modal-section">
                <h3>Order Summary</h3>
                <div class="order-modal-info">
                    <div>
                        <span class="label">Order ID</span>
                        <p style="font-family: monospace; font-size: 12px;">${order.order_id}</p>
                    </div>
                    <div>
                        <span class="label">Payment Status</span>
                        <p><span class="status-badge ${displayStatus.cls}">${displayStatus.label}</span></p>
                    </div>
                    <div>
                        <span class="label">Total Amount</span>
                        <p><strong>${formatCurrency(order.total_amount)}</strong></p>
                    </div>
                    <div>
                        <span class="label">Date</span>
                        <p>${formatDate(order.created_at)}</p>
                    </div>
                    ${couponHtml}
                </div>
            </div>

            <div class="order-modal-section">
                <h3>Tickets</h3>
                <table class="order-modal-tickets-table">
                    <thead><tr>${thCols}</tr></thead>
                    <tbody>${ticketRows}</tbody>
                </table>
            </div>

            <div class="order-modal-section">
                <div class="order-modal-actions">
                    <button class="order-modal-btn btn-cancel-tickets" id="btn-cancel-selected" disabled onclick="handleCancelTickets('${order.order_id}')">
                        Cancel Selected Tickets
                    </button>
                </div>
            </div>

            <div class="order-modal-section">
                <h3>Resend Tickets Email</h3>
                <div class="resend-section">
                    <textarea id="resend-custom-message" placeholder="Optional custom message to include in the email..."></textarea>
                    <button class="order-modal-btn btn-resend-email" onclick="handleResendEmail('${order.order_id}')">
                        Send Email
                    </button>
                </div>
            </div>
        `;

        // Wire up checkbox change to enable/disable cancel button
        body.querySelectorAll('.cancel-ticket-cb').forEach(cb => {
            cb.addEventListener('change', updateCancelButton);
        });
    }

    function updateCancelButton() {
        const btn = document.getElementById('btn-cancel-selected');
        const checked = document.querySelectorAll('.cancel-ticket-cb:checked');
        btn.disabled = checked.length === 0;
    }

    // ===== Cancel Tickets =====
    window.handleCancelTickets = async function (orderId) {
        const checked = document.querySelectorAll('.cancel-ticket-cb:checked');
        if (checked.length === 0) return;

        const codes = Array.from(checked).map(cb => cb.dataset.code);

        if (!confirm(`Cancel ${codes.length} ticket(s)?\n\n${codes.join('\n')}\n\nThis cannot be undone.`)) {
            return;
        }

        const btn = document.getElementById('btn-cancel-selected');
        btn.disabled = true;
        btn.textContent = 'Cancelling...';

        try {
            await API.cancelTickets(orderId, { qr_codes: codes });
            showToast(`${codes.length} ticket(s) cancelled successfully`);
            // Reload modal
            await openOrderModal(orderId);
        } catch (err) {
            showToast('Failed to cancel tickets: ' + err.message, 'error');
            btn.disabled = false;
            btn.textContent = 'Cancel Selected Tickets';
        }
    };

    // ===== Resend Email =====
    window.handleResendEmail = async function (orderId) {
        const textarea = document.getElementById('resend-custom-message');
        const customMessage = textarea ? textarea.value.trim() : '';

        const btn = document.querySelector('.btn-resend-email');
        btn.disabled = true;
        btn.textContent = 'Sending...';

        try {
            await API.resendEmail(orderId, { custom_message: customMessage });
            showToast('Email sent successfully');
            btn.textContent = 'Sent!';
            setTimeout(() => {
                btn.disabled = false;
                btn.textContent = 'Send Email';
            }, 2000);
        } catch (err) {
            showToast('Failed to send email: ' + err.message, 'error');
            btn.disabled = false;
            btn.textContent = 'Send Email';
        }
    };
})();
