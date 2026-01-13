/**
 * SeatPicker - Interactive seat selection component for ticketing
 *
 * Features:
 * - SVG-based seat map rendering
 * - Real-time availability updates
 * - Seat reservation with timer
 * - Touch support for mobile
 * - Zoom/pan controls
 * - Keyboard navigation (accessibility)
 */

class SeatPicker {
    constructor(containerId, eventId, ticketTypes, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Container element with id "${containerId}" not found`);
        }

        this.eventId = eventId;
        this.ticketTypes = ticketTypes; // [{ id, name, price }]
        this.selectedSeats = [];
        this.seatingData = null;
        this.reservationTimer = null;
        this.sessionId = this.generateSessionId();
        this.refreshInterval = null;
        this.seatAllocation = options.seatAllocation || {}; // Maps seat ID to ticket type ID

        // Seating map configuration (numbering settings)
        const seatingMapConfig = options.seatingMapConfig || {};
        this.numberingDirection = seatingMapConfig.numbering_direction || 'left-to-right';
        this.customNumbers = seatingMapConfig.custom_numbers || {};
        this.seatsPerRow = seatingMapConfig.seats_per_row || 20;

        // Generate colors for ticket types
        this.ticketTypeColors = this.generateTicketTypeColors();

        // Options
        this.options = {
            refreshRate: options.refreshRate || 5000, // 5 seconds
            reservationDuration: options.reservationDuration || 600, // 10 minutes
            seatWidth: options.seatWidth || 30,
            seatHeight: options.seatHeight || 30,
            seatSpacing: options.seatSpacing || 10,
            enableZoom: options.enableZoom !== false,
            enableTouch: options.enableTouch !== false,
            ...options
        };

        // Zoom/Pan state
        this.scale = 1.0;
        this.translateX = 0;
        this.translateY = 0;
        this.isPanning = false;
        this.panStartX = 0;
        this.panStartY = 0;

        // Touch state
        this.lastTouchDistance = 0;

        this.init();
    }

    generateTicketTypeColors() {
        // Generate distinct colors for each ticket type
        // Note: Purple (#9333ea) is reserved for selected seats
        const colors = [
            '#10b981', // green
            '#3b82f6', // blue
            '#f59e0b', // amber
            '#ec4899', // pink
            '#06b6d4', // cyan
            '#f97316', // orange
            '#14b8a6', // teal
            '#84cc16'  // lime
        ];

        const colorMap = {};
        this.ticketTypes.forEach((tt, index) => {
            colorMap[tt.id] = colors[index % colors.length];
        });

        return colorMap;
    }

    generateSessionId() {
        return 'sess-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    }

    async init() {
        try {
            this.showLoading();

            // Load seating map and availability
            const [seatingMapData, availabilityData] = await Promise.all([
                this.fetchSeatingMap(),
                this.fetchAvailability()
            ]);

            // Filter reserved seats to exclude current session's reservations
            const reservedSeatsDetails = availabilityData.reserved_seats_details || [];
            const reservedByOthers = reservedSeatsDetails
                .filter(r => r.session_id !== this.sessionId)
                .map(r => r.seat_id);

            this.seatingData = {
                map: this.normalizeSeatingMap(seatingMapData.seating_map),
                venueType: seatingMapData.venue_type,
                allocation: availabilityData.seat_allocation || {},
                purchased: availabilityData.purchased_seats || [],
                reserved: reservedByOthers  // Only seats reserved by OTHER sessions
            };

            this.render();
            this.attachEventListeners();

            // Start auto-refresh
            this.startAutoRefresh();

            this.hideLoading();
        } catch (error) {
            console.error('SeatPicker initialization error:', error);
            this.showError('Не удалось загрузить карту мест. Пожалуйста, обновите страницу.');
        }
    }

    async fetchSeatingMap() {
        const url = `${this.options.apiUrl}/api/events/${this.eventId}/seating-map`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.json();
    }

    async fetchAvailability() {
        const url = `${this.options.apiUrl}/api/events/${this.eventId}/seat-availability`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.json();
    }

    /**
     * Normalize seating map data from grid format to row array format
     * Handles both formats:
     * - Grid: { rows: 14, seats_per_row: 32, disabled_seats: ["0-0", ...] }
     * - Array: { rows: [{ id: "A", seats: [...] }, ...] }
     */
    normalizeSeatingMap(mapData) {
        // If rows is already an array, return as-is
        if (Array.isArray(mapData.rows)) {
            return mapData;
        }

        // Convert grid format to row array format
        const { rows, seats_per_row, disabled_seats = [] } = mapData;
        const disabledSet = new Set(disabled_seats);

        const rowArray = [];
        for (let rowIndex = 0; rowIndex < rows; rowIndex++) {
            const seats = [];
            for (let seatIndex = 0; seatIndex < seats_per_row; seatIndex++) {
                const seatId = `${rowIndex}-${seatIndex}`;
                seats.push({
                    id: seatIndex, // Keep 0-indexed to match API format
                    enabled: !disabledSet.has(seatId)
                });
            }

            rowArray.push({
                id: rowIndex, // Keep 0-indexed to match API format
                seats: seats
            });
        }

        return { rows: rowArray };
    }

    render() {
        if (!this.seatingData) {
            return;
        }

        // Clear container
        this.container.innerHTML = '';

        // Create main structure
        const wrapper = document.createElement('div');
        wrapper.className = 'seat-picker-wrapper';

        // Create sidebar (left side)
        const sidebar = document.createElement('div');
        sidebar.className = 'seat-picker-sidebar';

        // Add legend to sidebar
        sidebar.appendChild(this.createLegend());

        // Add summary to sidebar
        const summary = this.createSummary();
        sidebar.appendChild(summary);

        wrapper.appendChild(sidebar);

        // Create main area (right side)
        const main = document.createElement('div');
        main.className = 'seat-picker-main';

        // Add controls
        if (this.options.enableZoom) {
            main.appendChild(this.createControls());
        }

        // Add seat map
        const mapContainer = document.createElement('div');
        mapContainer.className = 'seat-map-container';
        mapContainer.id = `${this.container.id}-map`;

        const svg = this.renderSeatingMap();
        mapContainer.appendChild(svg);
        main.appendChild(mapContainer);

        // Add timer placeholder (inside map container, positioned absolutely)
        const timerDiv = document.createElement('div');
        timerDiv.id = 'reservation-timer';
        timerDiv.className = 'reservation-timer';
        timerDiv.style.display = 'none';  // Hidden by default
        mapContainer.appendChild(timerDiv);

        wrapper.appendChild(main);
        this.container.appendChild(wrapper);

        // Setup zoom/pan if enabled
        if (this.options.enableZoom) {
            this.setupZoomPan(mapContainer, svg);
        }
    }

    renderSeatingMap() {
        const { rows } = this.seatingData.map;
        const { seatWidth, seatHeight, seatSpacing } = this.options;

        // Calculate SVG dimensions
        const maxSeatsPerRow = Math.max(...rows.map(r => r.seats.length));
        const totalWidth = (seatWidth + seatSpacing) * maxSeatsPerRow + 100;
        const totalHeight = (seatHeight + seatSpacing) * rows.length + 150;

        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', `0 0 ${totalWidth} ${totalHeight}`);
        svg.setAttribute('width', '100%');
        svg.setAttribute('height', '100%');
        svg.classList.add('seat-map-svg');
        svg.setAttribute('role', 'application');
        svg.setAttribute('aria-label', 'Карта мест');

        // Create main group for zoom/pan
        const mainGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        mainGroup.setAttribute('id', 'seat-map-group');
        mainGroup.setAttribute('transform', `translate(${this.translateX}, ${this.translateY}) scale(${this.scale})`);

        // Draw stage
        this.drawStage(mainGroup, totalWidth);

        // Draw rows
        rows.forEach((row, rowIndex) => {
            this.drawRow(mainGroup, row, rowIndex);
        });

        svg.appendChild(mainGroup);
        return svg;
    }

    drawStage(parent, width) {
        const stageGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');

        const stage = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        stage.setAttribute('x', 50);
        stage.setAttribute('y', 20);
        stage.setAttribute('width', width - 100);
        stage.setAttribute('height', 40);
        stage.setAttribute('fill', '#333');
        stage.setAttribute('rx', 5);

        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', width / 2);
        text.setAttribute('y', 48);
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('fill', 'white');
        text.setAttribute('font-size', '18');
        text.setAttribute('font-weight', 'bold');
        text.textContent = 'СЦЕНА';

        stageGroup.appendChild(stage);
        stageGroup.appendChild(text);
        parent.appendChild(stageGroup);
    }

    drawRow(parent, row, rowIndex) {
        const { seatWidth, seatHeight, seatSpacing } = this.options;
        const rowGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        rowGroup.setAttribute('data-row-id', row.id);

        const y = 80 + rowIndex * (seatHeight + seatSpacing);

        // Row label (display as 1-indexed)
        const rowLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        rowLabel.setAttribute('x', 20);
        rowLabel.setAttribute('y', y + seatHeight / 2 + 5);
        rowLabel.setAttribute('text-anchor', 'end');
        rowLabel.setAttribute('font-size', '14');
        rowLabel.setAttribute('fill', '#666');
        rowLabel.textContent = `Ряд ${parseInt(row.id) + 1}`;
        rowGroup.appendChild(rowLabel);

        // Draw seats
        row.seats.forEach((seat, seatIndex) => {
            if (seat.enabled) {
                const seatId = `${row.id}-${seat.id}`;
                const x = 50 + seatIndex * (seatWidth + seatSpacing);

                const seatElement = this.createSeatElement(seatId, x, y, seat, seatIndex);
                rowGroup.appendChild(seatElement);
            }
        });

        parent.appendChild(rowGroup);
    }

    createSeatElement(seatId, x, y, seat, seatIndex) {
        const { seatWidth, seatHeight } = this.options;
        const status = this.getSeatStatus(seatId);
        const ticketTypeId = this.seatAllocation[seatId];
        const color = this.ticketTypeColors[ticketTypeId] || '#10b981';

        // Parse seatId to get row and seat indices
        const [rowId, seatCol] = seatId.split('-');

        // Calculate display number based on venue configuration
        const displayNumber = this.getSeatDisplayNumber(rowId, seatCol);

        const seatGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        seatGroup.setAttribute('data-seat-id', seatId);
        seatGroup.setAttribute('data-ticket-type', ticketTypeId || '');
        seatGroup.setAttribute('class', `seat seat-${status}`);
        seatGroup.setAttribute('role', 'button');
        seatGroup.setAttribute('aria-label', `Место ${displayNumber}, ${this.getSeatStatusLabel(status)}`);
        seatGroup.setAttribute('tabindex', status === 'available' ? '0' : '-1');

        // Seat rect
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', x);
        rect.setAttribute('y', y);
        rect.setAttribute('width', seatWidth);
        rect.setAttribute('height', seatHeight);
        rect.setAttribute('rx', 4);

        // Apply color based on ticket type and status
        if (status === 'available') {
            rect.setAttribute('fill', color);
            rect.setAttribute('stroke', this.darkenColor(color, 20));
            rect.setAttribute('stroke-width', '1');
        } else if (status === 'selected') {
            // Purple fill for selected seats (reserved color, never used for ticket types)
            rect.setAttribute('fill', '#9333ea');  // Purple
            rect.setAttribute('stroke', '#7c3aed');  // Darker purple
            rect.setAttribute('stroke-width', '2');
        } else if (status === 'sold') {
            rect.setAttribute('fill', '#6c757d');
            rect.setAttribute('stroke', '#5a6268');
            rect.setAttribute('stroke-width', '1');
        } else if (status === 'reserved') {
            rect.setAttribute('fill', '#ffc107');
            rect.setAttribute('stroke', '#e0a800');
            rect.setAttribute('stroke-width', '1');
        }

        // Seat label - use calculated display number from venue config
        // Only show label for selected seats to reduce visual clutter
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', x + seatWidth / 2);
        text.setAttribute('y', y + seatHeight / 2 + 4);
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('font-size', '12');
        text.setAttribute('class', 'seat-label');
        text.setAttribute('pointer-events', 'none');
        text.setAttribute('fill', 'white');  // White text for selected seats

        // Only show number if seat is selected
        if (status === 'selected') {
            text.textContent = displayNumber;
            text.style.display = 'block';
        } else {
            text.textContent = displayNumber;
            text.style.display = 'none';  // Hide for non-selected seats
        }

        seatGroup.appendChild(rect);
        seatGroup.appendChild(text);

        return seatGroup;
    }

    darkenColor(color, percent) {
        const num = parseInt(color.replace('#', ''), 16);
        const amt = Math.round(2.55 * percent);
        const R = (num >> 16) - amt;
        const G = (num >> 8 & 0x00FF) - amt;
        const B = (num & 0x0000FF) - amt;
        return '#' + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 +
            (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 +
            (B < 255 ? B < 1 ? 0 : B : 255))
            .toString(16).slice(1);
    }

    /**
     * Calculate seat display number based on venue configuration
     * Same logic as in seating-allocation-editor.js
     */
    getSeatDisplayNumber(rowId, seatId) {
        const fullSeatId = `${rowId}-${seatId}`;

        // Check custom numbers first
        if (this.customNumbers[fullSeatId]) {
            return this.customNumbers[fullSeatId].seat;
        }

        // Calculate based on numbering direction
        const seatIndex = parseInt(seatId);
        if (this.numberingDirection === 'right-to-left') {
            return this.seatsPerRow - seatIndex;
        } else {
            return seatIndex + 1;  // 1-indexed
        }
    }

    getSeatStatus(seatId) {
        if (this.seatingData.purchased.includes(seatId)) return 'sold';
        if (this.seatingData.reserved.includes(seatId)) return 'reserved';
        if (this.selectedSeats.includes(seatId)) return 'selected';
        return 'available';
    }

    getSeatStatusLabel(status) {
        const labels = {
            'available': 'доступно',
            'selected': 'выбрано',
            'sold': 'продано',
            'reserved': 'зарезервировано'
        };
        return labels[status] || status;
    }

    createControls() {
        const controls = document.createElement('div');
        controls.className = 'seat-picker-controls';

        const zoomIn = document.createElement('button');
        zoomIn.className = 'control-btn zoom-in';
        zoomIn.textContent = '+';
        zoomIn.setAttribute('aria-label', 'Увеличить');
        zoomIn.onclick = () => this.zoomIn();

        const zoomOut = document.createElement('button');
        zoomOut.className = 'control-btn zoom-out';
        zoomOut.textContent = '−';
        zoomOut.setAttribute('aria-label', 'Уменьшить');
        zoomOut.onclick = () => this.zoomOut();

        const reset = document.createElement('button');
        reset.className = 'control-btn zoom-reset';
        reset.textContent = '⟲';
        reset.setAttribute('aria-label', 'Сбросить масштаб');
        reset.onclick = () => this.resetZoom();

        controls.appendChild(zoomIn);
        controls.appendChild(zoomOut);
        controls.appendChild(reset);

        return controls;
    }

    createLegend() {
        const legend = document.createElement('div');
        legend.className = 'seat-legend';

        // Add ticket type legend items
        this.ticketTypes.forEach(ticketType => {
            const legendItem = document.createElement('div');
            legendItem.className = 'legend-item';

            const color = this.ticketTypeColors[ticketType.id];
            const colorBox = document.createElement('span');
            colorBox.className = 'legend-color';
            colorBox.style.cssText = `
                background: ${color};
                border-color: ${this.darkenColor(color, 20)};
            `;

            const label = document.createElement('span');
            label.innerHTML = `<strong>${ticketType.name}</strong> - ${ticketType.price}₪`;

            legendItem.appendChild(colorBox);
            legendItem.appendChild(label);
            legend.appendChild(legendItem);
        });

        // Add separator
        const separator = document.createElement('div');
        separator.style.cssText = 'width: 100%; border-top: 1px solid #dee2e6; margin: 0.5rem 0;';
        legend.appendChild(separator);

        // Add status legend items
        const statusItems = [
            { status: 'selected', label: 'Выбрано', color: '#9333ea' },
            { status: 'reserved', label: 'Зарезервировано', color: '#ffc107' },
            { status: 'sold', label: 'Продано', color: '#6c757d' }
        ];

        statusItems.forEach(item => {
            const legendItem = document.createElement('div');
            legendItem.className = 'legend-item';

            const colorBox = document.createElement('span');
            colorBox.className = 'legend-color';
            colorBox.style.cssText = `
                background: ${item.color};
                border-color: ${this.darkenColor(item.color, 20)};
            `;

            const label = document.createElement('span');
            label.textContent = item.label;

            legendItem.appendChild(colorBox);
            legendItem.appendChild(label);
            legend.appendChild(legendItem);
        });

        return legend;
    }

    createSummary() {
        const summary = document.createElement('div');
        summary.className = 'seat-summary';
        summary.id = 'seat-summary';

        const selectedCount = this.selectedSeats.length;
        let totalPrice = 0;

        // Calculate total price
        this.selectedSeats.forEach(seatId => {
            const ticketTypeId = this.seatAllocation[seatId];
            const ticketType = this.ticketTypes.find(tt => tt.id === ticketTypeId);
            if (ticketType) {
                totalPrice += ticketType.price;
            }
        });

        summary.innerHTML = `
            <div class="summary-header">Выбранные места</div>
            <div class="summary-content">
                <div class="summary-row">
                    <span>Выбрано мест:</span>
                    <span class="summary-value">${selectedCount}</span>
                </div>
                ${selectedCount > 0 ? `
                <div class="summary-row">
                    <span>Итого:</span>
                    <span class="summary-value summary-item-value highlight">${totalPrice}₪</span>
                </div>
                <div style="margin-top: 8px;">
                    <div style="font-size: 13px; margin-bottom: 6px; opacity: 0.9;">Места:</div>
                    <div class="selected-seats-details">
                        ${this.formatSeatListDetailed(this.selectedSeats)}
                    </div>
                </div>
                ` : ''}
            </div>
        `;

        return summary;
    }

    updateSummary() {
        const summary = document.getElementById('seat-summary');
        if (summary) {
            const selectedCount = this.selectedSeats.length;
            let totalPrice = 0;

            // Calculate total price
            this.selectedSeats.forEach(seatId => {
                const ticketTypeId = this.seatAllocation[seatId];
                const ticketType = this.ticketTypes.find(tt => tt.id === ticketTypeId);
                if (ticketType) {
                    totalPrice += ticketType.price;
                }
            });

            summary.innerHTML = `
                <div class="summary-header">Выбранные места</div>
                <div class="summary-content">
                    <div class="summary-row">
                        <span>Выбрано мест:</span>
                        <span class="summary-value">${selectedCount}</span>
                    </div>
                    ${selectedCount > 0 ? `
                    <div class="summary-row">
                        <span>Итого:</span>
                        <span class="summary-value summary-item-value highlight">${totalPrice}₪</span>
                    </div>
                    <div style="margin-top: 8px;">
                        <div style="font-size: 13px; margin-bottom: 6px; opacity: 0.9;">Места:</div>
                        <div class="selected-seats-details">
                            ${this.formatSeatListDetailed(this.selectedSeats)}
                        </div>
                    </div>
                    ` : ''}
                </div>
            `;
        }
    }

    formatSeatList(seats) {
        if (seats.length === 0) return '';

        // Convert internal seat IDs to display format
        const formattedSeats = seats.map(seatId => {
            const [rowId, seatIndex] = seatId.split('-');
            const displayRow = parseInt(rowId) + 1;  // Rows are 1-indexed for display
            const displaySeat = this.getSeatDisplayNumber(rowId, seatIndex);
            return `${displayRow}-${displaySeat}`;
        });

        if (formattedSeats.length <= 5) {
            return formattedSeats.join(', ');
        }
        return `${formattedSeats.slice(0, 5).join(', ')} и ещё ${formattedSeats.length - 5}`;
    }

    formatSeatListDetailed(seats) {
        if (seats.length === 0) return '';

        // Convert internal seat IDs to detailed format
        return seats.map(seatId => {
            const [rowId, seatIndex] = seatId.split('-');
            const displayRow = parseInt(rowId) + 1;  // Rows are 1-indexed for display
            const displaySeat = this.getSeatDisplayNumber(rowId, seatIndex);
            return `<div style="font-size: 13px; padding: 3px 0;">Ряд ${displayRow}, место ${displaySeat}</div>`;
        }).join('');
    }

    attachEventListeners() {
        // Click handlers for seats
        this.container.querySelectorAll('[data-seat-id]').forEach(seatElement => {
            seatElement.addEventListener('click', (e) => this.handleSeatClick(e));

            // Keyboard support
            seatElement.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.handleSeatClick(e);
                }
            });
        });

        // Touch support
        if (this.options.enableTouch) {
            this.setupTouchHandlers();
        }
    }

    async handleSeatClick(e) {
        const seatElement = e.target.closest('[data-seat-id]');
        if (!seatElement) return;

        const seatId = seatElement.getAttribute('data-seat-id');
        const status = this.getSeatStatus(seatId);

        // Check if seat is available
        if (status === 'sold') {
            this.showNotification('Это место уже продано', 'error');
            return;
        }

        if (status === 'reserved') {
            this.showNotification('Это место зарезервировано другим пользователем', 'warning');
            return;
        }

        // Toggle selection
        const rect = seatElement.querySelector('rect');
        const text = seatElement.querySelector('text');
        const ticketTypeId = seatElement.getAttribute('data-ticket-type');
        const color = this.ticketTypeColors[ticketTypeId] || '#10b981';

        if (this.selectedSeats.includes(seatId)) {
            // Deselect
            this.selectedSeats = this.selectedSeats.filter(s => s !== seatId);
            seatElement.classList.remove('seat-selected');
            seatElement.classList.add('seat-available');
            rect.setAttribute('fill', color);
            rect.setAttribute('stroke', this.darkenColor(color, 20));
            rect.setAttribute('stroke-width', '1');
            // Hide seat number when deselected
            if (text) text.style.display = 'none';
        } else {
            // Select
            this.selectedSeats.push(seatId);
            seatElement.classList.remove('seat-available');
            seatElement.classList.add('seat-selected');
            rect.setAttribute('fill', '#9333ea');  // Purple for selected
            rect.setAttribute('stroke', '#7c3aed');  // Darker purple
            rect.setAttribute('stroke-width', '2');
            // Show seat number when selected
            if (text) text.style.display = 'block';
        }

        this.updateSummary();

        // Trigger callback
        if (this.options.onSelectionChange) {
            this.options.onSelectionChange(this.selectedSeats);
        }
    }

    async reserveSeats() {
        try {
            const url = `${this.options.apiUrl}/api/orders/reserve-seats`;
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    event_id: this.eventId,
                    seat_ids: this.selectedSeats,
                    session_id: this.sessionId
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Не удалось зарезервировать места');
            }

            const data = await response.json();
            this.startReservationTimer(data.reserved_until || (Date.now() / 1000 + this.options.reservationDuration));
            this.showNotification('Места успешно зарезервированы!', 'success');

            // Trigger event for parent page
            this.dispatchEvent('seatsReserved', {
                seatIds: this.selectedSeats,
                reservedUntil: data.reserved_until
            });
        } catch (error) {
            console.error('Reservation error:', error);
            this.showNotification(error.message, 'error');

            // Reset selection
            this.selectedSeats = [];
            this.render();
        }
    }

    startReservationTimer(expiresAt) {
        // Clear existing timer
        if (this.reservationTimer) {
            clearInterval(this.reservationTimer);
        }

        const timerElement = document.getElementById('reservation-timer');
        if (!timerElement) return;

        const updateTimer = () => {
            const remaining = Math.floor(expiresAt - (Date.now() / 1000));

            if (remaining <= 0) {
                clearInterval(this.reservationTimer);
                this.showNotification('Время резервирования истекло. Пожалуйста, выберите места снова.', 'error');
                setTimeout(() => window.location.reload(), 2000);
                return;
            }

            const minutes = Math.floor(remaining / 60);
            const seconds = remaining % 60;

            timerElement.innerHTML = `
                <div class="timer-content ${remaining < 60 ? 'timer-warning' : ''}">
                    <span class="timer-icon">⏱</span>
                    <span>Места зарезервированы на ${minutes}:${seconds.toString().padStart(2, '0')}</span>
                </div>
            `;
            timerElement.style.display = 'block';
        };

        updateTimer();
        this.reservationTimer = setInterval(updateTimer, 1000);
    }

    // Zoom/Pan methods
    setupZoomPan(container, svg) {
        let isDragging = false;
        let startX, startY;

        container.addEventListener('mousedown', (e) => {
            // Don't start panning if clicking on a seat
            const clickedSeat = e.target.closest('[data-seat-id]');
            if (clickedSeat) {
                return;
            }

            // Only pan if clicking on background
            if (e.target === svg || e.target === container || e.target.id === 'seat-map-group' || e.target.tagName === 'svg') {
                isDragging = true;
                startX = e.clientX - this.translateX;
                startY = e.clientY - this.translateY;
                container.classList.add('grabbing');
                e.preventDefault();
            }
        });

        container.addEventListener('mousemove', (e) => {
            if (isDragging) {
                this.translateX = e.clientX - startX;
                this.translateY = e.clientY - startY;
                this.updateTransform();
            }
        });

        container.addEventListener('mouseup', () => {
            isDragging = false;
            container.classList.remove('grabbing');
        });

        container.addEventListener('mouseleave', () => {
            isDragging = false;
            container.classList.remove('grabbing');
        });

        // Wheel zoom
        container.addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.deltaY < 0) {
                this.zoomIn();
            } else {
                this.zoomOut();
            }
        }, { passive: false });
    }

    setupTouchHandlers() {
        const container = this.container.querySelector('.seat-map-container');
        if (!container) return;

        container.addEventListener('touchstart', (e) => {
            if (e.touches.length === 2) {
                // Pinch zoom
                this.lastTouchDistance = this.getTouchDistance(e.touches);
            } else if (e.touches.length === 1) {
                // Pan
                this.isPanning = true;
                this.panStartX = e.touches[0].clientX - this.translateX;
                this.panStartY = e.touches[0].clientY - this.translateY;
            }
        });

        container.addEventListener('touchmove', (e) => {
            if (e.touches.length === 2) {
                e.preventDefault();
                const distance = this.getTouchDistance(e.touches);
                const delta = distance - this.lastTouchDistance;

                if (Math.abs(delta) > 10) {
                    if (delta > 0) {
                        this.zoomIn();
                    } else {
                        this.zoomOut();
                    }
                    this.lastTouchDistance = distance;
                }
            } else if (e.touches.length === 1 && this.isPanning) {
                e.preventDefault();
                this.translateX = e.touches[0].clientX - this.panStartX;
                this.translateY = e.touches[0].clientY - this.panStartY;
                this.updateTransform();
            }
        }, { passive: false });

        container.addEventListener('touchend', () => {
            this.isPanning = false;
        });
    }

    getTouchDistance(touches) {
        const dx = touches[0].clientX - touches[1].clientX;
        const dy = touches[0].clientY - touches[1].clientY;
        return Math.sqrt(dx * dx + dy * dy);
    }

    zoomIn() {
        const newScale = Math.min(this.scale * 1.2, 3);
        this.zoomToCenter(newScale);
    }

    zoomOut() {
        const newScale = Math.max(this.scale / 1.2, 0.5);
        this.zoomToCenter(newScale);
    }

    zoomToCenter(newScale) {
        // Get container dimensions
        const container = this.container.querySelector('.seat-map-container');
        if (!container) {
            this.scale = newScale;
            this.updateTransform();
            return;
        }

        const rect = container.getBoundingClientRect();
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;

        // Calculate the point in the content space that's currently at the center
        const contentX = (centerX - this.translateX) / this.scale;
        const contentY = (centerY - this.translateY) / this.scale;

        // Calculate new translation to keep that point at the center
        this.translateX = centerX - contentX * newScale;
        this.translateY = centerY - contentY * newScale;
        this.scale = newScale;

        this.updateTransform();
    }

    resetZoom() {
        this.scale = 1;
        this.translateX = 0;
        this.translateY = 0;
        this.updateTransform();
    }

    updateTransform() {
        const group = document.getElementById('seat-map-group');
        if (group) {
            group.setAttribute('transform', `translate(${this.translateX}, ${this.translateY}) scale(${this.scale})`);
        }
    }

    // Auto-refresh
    startAutoRefresh() {
        this.refreshInterval = setInterval(() => {
            this.refreshAvailability();
        }, this.options.refreshRate);
    }

    async refreshAvailability() {
        try {
            const availabilityData = await this.fetchAvailability();

            // Filter reserved seats to exclude current session's reservations
            const reservedSeatsDetails = availabilityData.reserved_seats_details || [];
            const reservedByOthers = reservedSeatsDetails
                .filter(r => r.session_id !== this.sessionId)
                .map(r => r.seat_id);

            // Check if data actually changed
            const purchasedChanged = JSON.stringify(this.seatingData.purchased) !== JSON.stringify(availabilityData.purchased_seats || []);
            const reservedChanged = JSON.stringify(this.seatingData.reserved) !== JSON.stringify(reservedByOthers);

            if (!purchasedChanged && !reservedChanged) {
                return; // No changes, skip update
            }

            // Update data
            this.seatingData.purchased = availabilityData.purchased_seats || [];
            this.seatingData.reserved = reservedByOthers;  // Only seats reserved by OTHER sessions

            // Update only seats that changed status
            this.container.querySelectorAll('[data-seat-id]').forEach(seatElement => {
                const seatId = seatElement.getAttribute('data-seat-id');
                const newStatus = this.getSeatStatus(seatId);
                const currentClasses = seatElement.className.split(' ');
                const oldStatus = currentClasses.find(c => c.startsWith('seat-') && c !== 'seat')?.replace('seat-', '');

                if (newStatus !== oldStatus) {
                    // Status changed, update element
                    const rect = seatElement.querySelector('rect');
                    const text = seatElement.querySelector('text');
                    const ticketTypeId = seatElement.getAttribute('data-ticket-type');
                    const color = this.ticketTypeColors[ticketTypeId] || '#10b981';

                    // Update classes
                    seatElement.classList.remove('seat-available', 'seat-selected', 'seat-sold', 'seat-reserved');
                    seatElement.classList.add(`seat-${newStatus}`);

                    // Update colors directly on rect
                    if (newStatus === 'available') {
                        rect.setAttribute('fill', color);
                        rect.setAttribute('stroke', this.darkenColor(color, 20));
                        rect.setAttribute('stroke-width', '1');
                        // Hide number for available seats
                        if (text) text.style.display = 'none';
                    } else if (newStatus === 'selected') {
                        rect.setAttribute('fill', '#9333ea');  // Purple for selected
                        rect.setAttribute('stroke', '#7c3aed');  // Darker purple
                        rect.setAttribute('stroke-width', '2');
                        // Show number for selected seats
                        if (text) text.style.display = 'block';
                    } else if (newStatus === 'sold') {
                        rect.setAttribute('fill', '#6c757d');
                        rect.setAttribute('stroke', '#5a6268');
                        rect.setAttribute('stroke-width', '1');
                        // Hide number for sold seats
                        if (text) text.style.display = 'none';
                    } else if (newStatus === 'reserved') {
                        rect.setAttribute('fill', '#ffc107');
                        rect.setAttribute('stroke', '#e0a800');
                        rect.setAttribute('stroke-width', '1');
                        // Hide number for reserved seats
                        if (text) text.style.display = 'none';
                    }

                    // Update aria-label
                    seatElement.setAttribute('aria-label', `Место ${seatId}, ${this.getSeatStatusLabel(newStatus)}`);
                }
            });
        } catch (error) {
            console.error('Failed to refresh availability:', error);
        }
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }

    // Utility methods
    showLoading() {
        this.container.innerHTML = '<div class="seat-picker-loading">Загрузка карты мест...</div>';
    }

    hideLoading() {
        const loading = this.container.querySelector('.seat-picker-loading');
        if (loading) {
            loading.remove();
        }
    }

    showError(message) {
        this.container.innerHTML = `<div class="seat-picker-error">${message}</div>`;
    }

    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `seat-picker-notification notification-${type}`;
        notification.textContent = message;

        this.container.appendChild(notification);

        // Auto-remove after 3 seconds
        setTimeout(() => {
            notification.classList.add('notification-fade');
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    dispatchEvent(eventName, detail) {
        const event = new CustomEvent(`seatPicker:${eventName}`, { detail });
        this.container.dispatchEvent(event);
    }

    // Public API
    getSelectedSeats() {
        return [...this.selectedSeats];
    }

    clearSelection() {
        this.selectedSeats = [];
        this.render();
    }

    destroy() {
        this.stopAutoRefresh();
        if (this.reservationTimer) {
            clearInterval(this.reservationTimer);
        }
        this.container.innerHTML = '';
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SeatPicker;
}
