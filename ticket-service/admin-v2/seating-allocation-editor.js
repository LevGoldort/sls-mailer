/**
 * Seating Allocation Editor - Interactive editor for assigning ticket types to venue seats
 * Based on SeatingMapEditor but focused on allocation, not venue editing
 */

class SeatingAllocationEditor {
    constructor() {
        // Venue map configuration (read-only from location)
        this.rows = 10;
        this.seatsPerRow = 20;
        this.disabledSeats = new Set();  // Seats disabled in venue config
        this.customNumbers = {};
        this.numberingDirection = 'left-to-right';

        // Allocation data (editable)
        this.seatAllocation = {};  // {"0-5": "tt-xxx", ...}
        this.ticketTypes = [];  // Array of ticket type objects
        this.ticketTypeColors = {};  // {"tt-xxx": "#4CAF50", ...}
        this.activeTicketTypeId = null;  // Currently selected ticket type for painting

        // Locked seats (sold tickets)
        this.lockedSeats = new Set();  // Seats that are sold (cannot be changed)
        this.lockedSeatDetails = {};   // {seat_id: {ticket_type_id, order_id, status}}
        this.eventId = null;

        // UI state
        this.selectedSeats = new Set();  // For multi-select (shift+click)
        this.rowSelectionMode = false;  // Row selection mode active

        // Zoom/Pan state (reused from SeatingMapEditor pattern)
        this.scale = 1.0;
        this.translateX = 0;
        this.translateY = 0;
        this.isPanning = false;
        this.panStartX = 0;
        this.panStartY = 0;

        // Undo/Redo history
        this.history = [];
        this.historyIndex = -1;
        this.maxHistorySize = 50;

        // SVG constants (same as SeatingMapEditor)
        this.seatRadius = 15;
        this.seatSpacing = 40;
        this.marginTop = 80;
        this.marginLeft = 80;
    }

    /**
     * Load configuration: venue map + ticket types + existing allocation
     */
    loadConfig(venueConfig, ticketTypes, existingAllocation = null, existingColors = null, eventId = null) {
        // Load venue configuration (read-only)
        this.rows = venueConfig.rows;
        this.seatsPerRow = venueConfig.seats_per_row;
        this.numberingDirection = venueConfig.numbering_direction || 'left-to-right';

        // Parse disabled seats
        this.disabledSeats.clear();
        if (venueConfig.disabled_seats) {
            venueConfig.disabled_seats.forEach(seatId => {
                this.disabledSeats.add(seatId);
            });
        }

        // Parse custom numbers
        this.customNumbers = venueConfig.custom_numbers || {};

        // Load ticket types
        this.ticketTypes = ticketTypes;
        this.eventId = eventId;

        // Generate default colors if not provided
        if (existingColors) {
            this.ticketTypeColors = existingColors;
        } else {
            this.ticketTypeColors = this.generateDefaultColors(ticketTypes);
        }

        // Load existing allocation
        if (existingAllocation) {
            this.seatAllocation = { ...existingAllocation };
        } else {
            this.seatAllocation = {};
        }

        // Select first ticket type by default
        if (this.ticketTypes.length > 0) {
            this.activeTicketTypeId = this.ticketTypes[0].id;
        }

        // Reset zoom/pan
        this.scale = 1.0;
        this.translateX = 0;
        this.translateY = 0;

        // Clear history and save initial state
        this.history = [];
        this.historyIndex = -1;
        this.saveState();

        // Fetch purchased seats if editing existing event
        if (eventId) {
            this.fetchPurchasedSeats(eventId).then(() => {
                this.renderMap();
                this.updateUndoRedoButtons();
            });
        } else {
            this.renderMap();
            this.updateUndoRedoButtons();
        }
    }

    /**
     * Fetch purchased seats from API
     */
    async fetchPurchasedSeats(eventId) {
        const token = Auth.getAccessToken();
        // Auto-detect environment
        const isDev = window.location.hostname.includes('-dev');
        const API_URL = isDev
            ? 'https://d4xhvmdzbg.execute-api.eu-north-1.amazonaws.com/dev'
            : 'https://ovajavet67.execute-api.eu-north-1.amazonaws.com';

        if (!token) {
            console.warn('Not authenticated - cannot fetch purchased seats');
            return;
        }

        try {
            const response = await fetch(
                `${API_URL}/api/events/${eventId}/purchased-seats`,
                {
                    headers: {'Authorization': `Bearer ${token}`}
                }
            );

            if (response.ok) {
                const data = await response.json();
                this.lockedSeats.clear();
                this.lockedSeatDetails = {};

                for (const [seatId, details] of Object.entries(data.purchased_seats || {})) {
                    this.lockedSeats.add(seatId);
                    this.lockedSeatDetails[seatId] = details;
                }

                console.log(`Loaded ${this.lockedSeats.size} locked seats`);

                if (this.lockedSeats.size > 0) {
                    // Show info message
                    this.showLockedSeatsInfo();
                }
            } else {
                console.error('Failed to fetch purchased seats:', await response.text());
            }
        } catch (error) {
            console.error('Error fetching purchased seats:', error);
            alert('⚠️ Не удалось загрузить информацию о проданных местах.\n\nРедактирование может быть небезопасным. Продолжайте с осторожностью.');
        }
    }

    /**
     * Show info message about locked seats
     */
    showLockedSeatsInfo() {
        const info = document.createElement('div');
        info.style.cssText = 'background: #fef3c7; border: 1px solid #f59e0b; padding: 12px; border-radius: 6px; margin-bottom: 15px;';
        info.innerHTML = `
            <strong>🔒 Проданные места</strong><br>
            <span style="font-size: 0.9rem;">
                ${this.lockedSeats.size} мест уже продано и заблокировано для редактирования.
                Вы можете перераспределять только непроданные места.
            </span>
        `;

        // Insert before map container
        const mapContainer = document.getElementById('seat-map-container');
        if (mapContainer && mapContainer.parentElement) {
            mapContainer.parentElement.insertBefore(info, mapContainer);
        }
    }

    /**
     * Generate default colors for ticket types
     */
    generateDefaultColors(ticketTypes) {
        const DEFAULT_COLORS = [
            '#4CAF50',  // Green
            '#2196F3',  // Blue
            '#FF9800',  // Orange
            '#9C27B0',  // Purple
            '#F44336',  // Red
            '#00BCD4',  // Cyan
            '#FFEB3B',  // Yellow
            '#795548',  // Brown
        ];

        const colors = {};
        ticketTypes.forEach((tt, index) => {
            colors[tt.id] = DEFAULT_COLORS[index % DEFAULT_COLORS.length];
        });
        return colors;
    }

    /**
     * Render the complete SVG seating map with allocations
     */
    renderMap() {
        const svg = document.getElementById('allocation-canvas');
        if (!svg) return;

        // Clear existing content
        svg.innerHTML = '';

        // Calculate SVG dimensions
        const width = this.seatsPerRow * this.seatSpacing + this.marginLeft * 2;
        const height = this.rows * this.seatSpacing + this.marginTop * 2;
        svg.setAttribute('width', width);
        svg.setAttribute('height', height);
        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

        // Create main group for zoom/pan transformation
        const mainGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        mainGroup.setAttribute('id', 'main-group');
        mainGroup.setAttribute('transform', `translate(${this.translateX}, ${this.translateY}) scale(${this.scale})`);
        svg.appendChild(mainGroup);

        // Draw stage indicator
        this.drawStage(mainGroup, width);

        // Draw row numbers
        this.drawRowNumbers(mainGroup);

        // Draw seats
        for (let row = 0; row < this.rows; row++) {
            for (let seat = 0; seat < this.seatsPerRow; seat++) {
                this.drawSeat(mainGroup, row, seat);
            }
        }

        // Remove old event listeners to prevent memory leaks
        const oldSvg = svg.cloneNode(false);
        svg.parentNode.replaceChild(oldSvg, svg);
        // Re-append the content
        oldSvg.appendChild(mainGroup);

        // Add event delegation for seat clicks (much more efficient!)
        oldSvg.addEventListener('click', (e) => {
            const seatGroup = e.target.closest('g[data-seat-id]');
            if (seatGroup) {
                const seatId = seatGroup.getAttribute('data-seat-id');
                const isDisabled = this.disabledSeats.has(seatId);
                if (!isDisabled) {
                    this.handleSeatClick(seatId, e);
                }
            }
        });

        // Add pan event listeners
        this.addPanListeners(oldSvg);

        // Add wheel zoom listener
        oldSvg.addEventListener('wheel', (e) => this.handleWheel(e));
    }

    /**
     * Draw stage indicator at the top
     */
    drawStage(svg, width) {
        const stageGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');

        // Stage rectangle
        const stageRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        stageRect.setAttribute('x', this.marginLeft);
        stageRect.setAttribute('y', 20);
        stageRect.setAttribute('width', width - this.marginLeft * 2);
        stageRect.setAttribute('height', 40);
        stageRect.setAttribute('fill', '#333');
        stageRect.setAttribute('rx', '5');
        stageGroup.appendChild(stageRect);

        // Stage text
        const stageText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        stageText.setAttribute('x', width / 2);
        stageText.setAttribute('y', 45);
        stageText.setAttribute('fill', 'white');
        stageText.setAttribute('font-size', '16');
        stageText.setAttribute('font-weight', 'bold');
        stageText.setAttribute('text-anchor', 'middle');
        stageText.textContent = 'СЦЕНА';
        stageGroup.appendChild(stageText);

        svg.appendChild(stageGroup);
    }

    /**
     * Draw row numbers on the left
     */
    drawRowNumbers(svg) {
        for (let row = 0; row < this.rows; row++) {
            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', this.marginLeft - 30);
            text.setAttribute('y', this.marginTop + row * this.seatSpacing + 5);
            text.setAttribute('fill', '#666');
            text.setAttribute('font-size', '14');
            text.setAttribute('text-anchor', 'middle');
            text.textContent = row + 1;  // 1-indexed for display
            svg.appendChild(text);
        }
    }

    /**
     * Draw a single seat
     */
    drawSeat(svg, row, seat) {
        const seatId = `${row}-${seat}`;
        const x = this.marginLeft + seat * this.seatSpacing;
        const y = this.marginTop + row * this.seatSpacing;

        const seatGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        seatGroup.setAttribute('data-seat-id', seatId);
        seatGroup.setAttribute('data-row', row);
        seatGroup.setAttribute('data-seat', seat);

        // Determine seat color and state
        const isDisabled = this.disabledSeats.has(seatId);
        const isLocked = this.lockedSeats.has(seatId);  // NEW
        const ticketTypeId = this.seatAllocation[seatId];
        const isAllocated = !!ticketTypeId;

        let fillColor, strokeColor, strokeWidth, cursor, opacity;

        if (isLocked) {
            // LOCKED SEAT (sold) - highest priority
            fillColor = this.ticketTypeColors[ticketTypeId] || '#999';
            strokeColor = '#dc2626';  // Red border
            strokeWidth = 3;
            cursor = 'not-allowed';
            opacity = 0.7;
        } else if (isDisabled) {
            // Disabled seat (from venue config)
            fillColor = '#999';
            strokeColor = '#666';
            strokeWidth = 1;
            cursor = 'not-allowed';
            opacity = 0.5;
        } else if (isAllocated) {
            // Allocated seat (painted with ticket type color)
            fillColor = this.ticketTypeColors[ticketTypeId] || '#667eea';
            strokeColor = '#333';
            strokeWidth = 2;
            cursor = 'pointer';
            opacity = 1;
        } else {
            // Unallocated seat
            fillColor = '#e0e0e0';
            strokeColor = '#999';
            strokeWidth = 1;
            cursor = 'pointer';
            opacity = 1;
        }

        if (opacity !== undefined) {
            seatGroup.style.opacity = opacity;
        }

        // Draw circle
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', x);
        circle.setAttribute('cy', y);
        circle.setAttribute('r', this.seatRadius);
        circle.setAttribute('fill', fillColor);
        circle.setAttribute('stroke', strokeColor);
        circle.setAttribute('stroke-width', strokeWidth);
        circle.style.cursor = cursor;
        seatGroup.appendChild(circle);

        // Add lock icon for locked seats
        if (isLocked) {
            const lockIcon = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            lockIcon.setAttribute('x', x);
            lockIcon.setAttribute('y', y + 4);
            lockIcon.setAttribute('text-anchor', 'middle');
            lockIcon.setAttribute('font-size', '12');
            lockIcon.setAttribute('pointer-events', 'none');
            lockIcon.setAttribute('fill', '#fff');
            lockIcon.textContent = '🔒';
            seatGroup.appendChild(lockIcon);
        }

        // Add hover effect (if not disabled and not locked)
        if (!isDisabled && !isLocked) {
            circle.addEventListener('mouseenter', () => {
                circle.style.opacity = '0.8';
                circle.setAttribute('stroke-width', strokeWidth + 1);
            });
            circle.addEventListener('mouseleave', () => {
                circle.style.opacity = '1';
                circle.setAttribute('stroke-width', strokeWidth);
            });
        }

        // Get seat number
        const seatNumber = this.getSeatNumber(row, seat);

        // Draw seat number
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', x);
        text.setAttribute('y', y + 4);
        text.setAttribute('fill', isDisabled ? '#ccc' : '#333');
        text.setAttribute('font-size', '10');
        text.setAttribute('font-weight', 'bold');
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('pointer-events', 'none');
        text.textContent = seatNumber;
        seatGroup.appendChild(text);

        // Don't add individual click handlers - use event delegation instead
        // Click handler is set up on the SVG element in renderMap()

        svg.appendChild(seatGroup);
    }

    /**
     * Get seat number (considering custom numbering)
     */
    getSeatNumber(row, seat) {
        const seatId = `${row}-${seat}`;

        // Check custom numbers first
        if (this.customNumbers[seatId]) {
            const custom = this.customNumbers[seatId];
            return custom.seat;
        }

        // Calculate based on numbering direction
        if (this.numberingDirection === 'right-to-left') {
            return this.seatsPerRow - seat;
        } else {
            return seat + 1;  // 1-indexed
        }
    }

    /**
     * Handle seat click
     */
    handleSeatClick(seatId, event) {
        // Check if seat is locked
        if (this.lockedSeats.has(seatId)) {
            const details = this.lockedSeatDetails[seatId];
            const ticketTypeName = this.getTicketTypeName(details.ticket_type_id);
            const statusText = details.status === 'completed' ? 'продано' : 'зарезервировано';

            alert(
                `🔒 Это место ${statusText} (${ticketTypeName}).\n\n` +
                `Невозможно изменить распределение проданных мест.`
            );
            return;
        }

        // Check if seat is disabled
        if (this.disabledSeats.has(seatId)) {
            return;
        }

        if (this.rowSelectionMode) {
            // Row selection mode
            const [row] = seatId.split('-').map(Number);
            this.selectAndPaintRow(row);
        } else {
            // Normal click: smart paint/unpaint/repaint
            const currentTicketTypeId = this.seatAllocation[seatId];

            if (!this.activeTicketTypeId) {
                // No ticket type selected - do nothing
                return;
            }

            if (currentTicketTypeId === this.activeTicketTypeId) {
                // Same color selected - unpaint (remove allocation)
                this.unpaintSeat(seatId);
            } else if (currentTicketTypeId) {
                // Different color selected - repaint directly
                this.seatAllocation[seatId] = this.activeTicketTypeId;
                this.saveState();
                this.updateSeatVisual(seatId);
                this.updateCounters();
                this.updateUndoRedoButtons();
            } else {
                // Not allocated - paint with active ticket type
                this.paintSeat(seatId, this.activeTicketTypeId);
            }
        }
    }

    /**
     * Paint a seat with a ticket type
     */
    paintSeat(seatId, ticketTypeId) {
        // For seated venues, quantity is determined by seat allocation on the map
        // No quota check needed

        this.seatAllocation[seatId] = ticketTypeId;
        this.saveState();
        this.updateSeatVisual(seatId); // Only update this one seat
        this.updateCounters();
        this.updateUndoRedoButtons();
        return true;
    }

    /**
     * Unpaint a seat (remove allocation)
     */
    unpaintSeat(seatId) {
        delete this.seatAllocation[seatId];
        this.saveState();
        this.updateSeatVisual(seatId); // Only update this one seat
        this.updateCounters();
        this.updateUndoRedoButtons();
    }

    /**
     * Update visual of a single seat (optimization - don't re-render entire map)
     */
    updateSeatVisual(seatId) {
        const seatGroup = document.querySelector(`g[data-seat-id="${seatId}"]`);
        if (!seatGroup) return;

        const ticketTypeId = this.seatAllocation[seatId];
        const isAllocated = !!ticketTypeId;
        const circle = seatGroup.querySelector('circle');

        if (!circle) return;

        if (isAllocated) {
            // Update to allocated color
            const fillColor = this.ticketTypeColors[ticketTypeId] || '#667eea';
            circle.setAttribute('fill', fillColor);
            circle.setAttribute('stroke', '#333');
            circle.setAttribute('stroke-width', '2');
        } else {
            // Update to unallocated
            circle.setAttribute('fill', '#e0e0e0');
            circle.setAttribute('stroke', '#999');
            circle.setAttribute('stroke-width', '1');
        }
    }

    /**
     * Toggle seat selection (for multi-select)
     */
    toggleSeatSelection(seatId) {
        if (this.selectedSeats.has(seatId)) {
            this.selectedSeats.delete(seatId);
        } else {
            this.selectedSeats.add(seatId);
        }
        this.renderMap();
    }

    /**
     * Paint all selected seats
     */
    paintSelectedSeats() {
        if (!this.activeTicketTypeId) {
            alert('Выберите тип билета для распределения');
            return;
        }

        const seatsToAllocate = Array.from(this.selectedSeats);

        // For seated venues, quantity is determined by seat allocation on the map
        // No need to check ticket.total - that's just for display

        // Allocate all selected seats
        seatsToAllocate.forEach(seatId => {
            this.seatAllocation[seatId] = this.activeTicketTypeId;
        });

        this.selectedSeats.clear();
        this.saveState();
        this.renderMap();
        this.updateCounters();
        this.updateUndoRedoButtons();
    }

    /**
     * Select and paint entire row
     */
    selectAndPaintRow(rowNumber) {
        if (!this.activeTicketTypeId) {
            alert('Выберите тип билета для распределения');
            return;
        }

        // Get all available seats in the row (not disabled, not locked)
        const rowSeats = [];
        for (let seat = 0; seat < this.seatsPerRow; seat++) {
            const seatId = `${rowNumber}-${seat}`;
            if (!this.disabledSeats.has(seatId) && !this.lockedSeats.has(seatId)) {
                rowSeats.push(seatId);
            }
        }

        if (rowSeats.length === 0) {
            alert('Все места в этом ряду отключены или проданы');
            return;
        }

        // For seated venues, quantity is determined by seat allocation on the map
        // No need to check ticket.total

        // Allocate all row seats
        rowSeats.forEach(seatId => {
            this.seatAllocation[seatId] = this.activeTicketTypeId;
            this.updateSeatVisual(seatId); // Update each seat individually
        });

        this.saveState();
        this.updateCounters();
        this.updateUndoRedoButtons();
    }

    /**
     * Check if a seat can be allocated to a ticket type (quota check)
     */
    canAllocateSeat(ticketTypeId) {
        const currentCount = this.getAllocationCount(ticketTypeId);
        const ticketType = this.ticketTypes.find(tt => tt.id === ticketTypeId);

        // For seated venues with placeholder (999999) or zero total, allow allocation
        // The total will be set based on actual allocated seats
        if (ticketType.total >= 999999 || ticketType.total === 0) {
            return true;
        }

        // Normal quota check for non-seated venues
        return currentCount < ticketType.total;
    }

    /**
     * Get allocation count for a ticket type
     */
    getAllocationCount(ticketTypeId) {
        let count = 0;
        for (const [seatId, ttId] of Object.entries(this.seatAllocation)) {
            if (ttId === ticketTypeId) {
                count++;
            }
        }
        return count;
    }

    /**
     * Get ticket type name by ID
     */
    getTicketTypeName(ticketTypeId) {
        const tt = this.ticketTypes.find(t => t.id === ticketTypeId);
        return tt ? tt.name : '';
    }

    /**
     * Update counters in the UI (called from external code)
     */
    updateCounters() {
        // This is called by event-edit.html to update the palette counters
        // Implementation is in event-edit.html
        if (typeof updateAllocationCounters === 'function') {
            updateAllocationCounters();
        }
    }

    /**
     * Set active ticket type for painting
     */
    setActiveTicketType(ticketTypeId) {
        this.activeTicketTypeId = ticketTypeId;
    }

    /**
     * Set ticket type color
     */
    setTicketTypeColor(ticketTypeId, color) {
        this.ticketTypeColors[ticketTypeId] = color;
        this.renderMap();
    }

    /**
     * Export allocation data
     */
    exportAllocation() {
        return {
            seatAllocation: { ...this.seatAllocation },
            ticketTypeColors: { ...this.ticketTypeColors }
        };
    }

    /**
     * Clear all selections
     */
    clearSelection() {
        this.selectedSeats.clear();
        this.renderMap();
    }

    /**
     * Zoom in
     */
    zoomIn() {
        this.scale = Math.min(this.scale * 1.2, 3.0);
        this.renderMap();
    }

    /**
     * Zoom out
     */
    zoomOut() {
        this.scale = Math.max(this.scale / 1.2, 0.5);
        this.renderMap();
    }

    /**
     * Reset zoom
     */
    resetZoom() {
        this.scale = 1.0;
        this.translateX = 0;
        this.translateY = 0;
        this.renderMap();
    }

    /**
     * Handle mouse wheel for zoom
     */
    handleWheel(event) {
        event.preventDefault();

        if (event.deltaY < 0) {
            this.zoomIn();
        } else {
            this.zoomOut();
        }
    }

    /**
     * Add pan listeners
     */
    addPanListeners(svg) {
        let startX = 0, startY = 0;

        svg.addEventListener('mousedown', (e) => {
            if (e.target === svg || e.target.id === 'main-group') {
                this.isPanning = true;
                startX = e.clientX - this.translateX;
                startY = e.clientY - this.translateY;
                svg.style.cursor = 'grabbing';
            }
        });

        svg.addEventListener('mousemove', (e) => {
            if (this.isPanning) {
                this.translateX = e.clientX - startX;
                this.translateY = e.clientY - startY;

                const mainGroup = svg.querySelector('#main-group');
                if (mainGroup) {
                    mainGroup.setAttribute('transform',
                        `translate(${this.translateX}, ${this.translateY}) scale(${this.scale})`);
                }
            }
        });

        const stopPan = () => {
            this.isPanning = false;
            svg.style.cursor = 'default';
        };

        svg.addEventListener('mouseup', stopPan);
        svg.addEventListener('mouseleave', stopPan);
    }

    /**
     * Save current state to history
     */
    saveState() {
        // Remove any states after current index
        this.history = this.history.slice(0, this.historyIndex + 1);

        // Save current state
        const state = {
            seatAllocation: { ...this.seatAllocation },
            ticketTypeColors: { ...this.ticketTypeColors }
        };

        this.history.push(state);
        this.historyIndex++;

        // Limit history size
        if (this.history.length > this.maxHistorySize) {
            this.history.shift();
            this.historyIndex--;
        }
    }

    /**
     * Undo last action
     */
    undo() {
        if (this.historyIndex > 0) {
            this.historyIndex--;
            const state = this.history[this.historyIndex];
            this.seatAllocation = { ...state.seatAllocation };
            this.ticketTypeColors = { ...state.ticketTypeColors };
            this.renderMap();
            this.updateCounters();
            this.updateUndoRedoButtons();
        }
    }

    /**
     * Redo last undone action
     */
    redo() {
        if (this.historyIndex < this.history.length - 1) {
            this.historyIndex++;
            const state = this.history[this.historyIndex];
            this.seatAllocation = { ...state.seatAllocation };
            this.ticketTypeColors = { ...state.ticketTypeColors };
            this.renderMap();
            this.updateCounters();
            this.updateUndoRedoButtons();
        }
    }

    /**
     * Update undo/redo button states
     */
    updateUndoRedoButtons() {
        const undoBtn = document.getElementById('undo-alloc-btn');
        const redoBtn = document.getElementById('redo-alloc-btn');

        if (undoBtn) {
            undoBtn.disabled = this.historyIndex <= 0;
        }

        if (redoBtn) {
            redoBtn.disabled = this.historyIndex >= this.history.length - 1;
        }
    }
}
