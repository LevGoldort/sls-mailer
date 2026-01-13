/**
 * Seating Map Editor - Interactive visual editor for creating venue seating maps
 */

class SeatingMapEditor {
    constructor() {
        // Map configuration
        this.rows = 10;
        this.seatsPerRow = 20;
        this.disabledSeats = new Set();
        this.customNumbers = {};
        this.selectedSeats = new Set();
        this.numberingDirection = 'left-to-right';
        this.editMode = 'select';

        // Zoom/Pan state
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

        // SVG constants
        this.seatRadius = 15;
        this.seatSpacing = 40;
        this.marginTop = 80;
        this.marginLeft = 80;
    }

    /**
     * Generate initial seating map
     */
    generateMap(rows, seatsPerRow) {
        this.rows = rows;
        this.seatsPerRow = seatsPerRow;
        this.disabledSeats.clear();
        this.customNumbers = {};
        this.selectedSeats.clear();
        this.scale = 1.0;
        this.translateX = 0;
        this.translateY = 0;

        // Clear history and save initial state
        this.history = [];
        this.historyIndex = -1;
        this.saveState();

        this.renderSeatingChart();
        this.updateUndoRedoButtons();
    }

    /**
     * Render the complete SVG seating chart
     */
    renderSeatingChart() {
        const svg = document.getElementById('seating-canvas');
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
    }

    /**
     * Draw stage indicator at the top
     */
    drawStage(svg, width) {
        const stageGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');

        const stage = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        stage.setAttribute('x', this.marginLeft);
        stage.setAttribute('y', 20);
        stage.setAttribute('width', width - this.marginLeft * 2);
        stage.setAttribute('height', 30);
        stage.setAttribute('fill', '#333');
        stage.setAttribute('rx', 4);

        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.setAttribute('x', width / 2);
        text.setAttribute('y', 40);
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('fill', 'white');
        text.setAttribute('font-size', '16');
        text.setAttribute('font-weight', 'bold');
        text.textContent = 'СЦЕНА';

        stageGroup.appendChild(stage);
        stageGroup.appendChild(text);
        svg.appendChild(stageGroup);
    }

    /**
     * Draw row numbers on the left
     */
    drawRowNumbers(svg) {
        for (let row = 0; row < this.rows; row++) {
            const y = this.marginTop + row * this.seatSpacing;
            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', this.marginLeft - 35);
            text.setAttribute('y', y + 5);
            text.setAttribute('text-anchor', 'middle');
            text.setAttribute('fill', '#666');
            text.setAttribute('font-size', '14');
            text.setAttribute('font-weight', 'bold');
            text.textContent = `Ряд ${row + 1}`;
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

        const isDisabled = this.disabledSeats.has(seatId);
        const isSelected = this.selectedSeats.has(seatId);

        // Create group for seat
        const seatGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        seatGroup.setAttribute('data-seat-id', seatId);

        // Draw circle
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', x);
        circle.setAttribute('cy', y);
        circle.setAttribute('r', this.seatRadius);
        circle.setAttribute('class', 'seat');
        circle.classList.add(
            isDisabled ? 'seat-disabled' :
            isSelected ? 'seat-selected' :
            'seat-available'
        );

        // Event listeners
        circle.addEventListener('click', (e) => this.handleSeatClick(seatId, e));

        seatGroup.appendChild(circle);

        // Draw seat number (if not disabled)
        if (!isDisabled) {
            const seatNumber = this.getSeatNumber(row, seat);
            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', x);
            text.setAttribute('y', y + 4);
            text.setAttribute('class', 'seat-text');
            text.textContent = `${seatNumber.row}-${seatNumber.seat}`;
            seatGroup.appendChild(text);
        }

        svg.appendChild(seatGroup);
    }

    /**
     * Get seat number based on numbering direction and custom numbers
     */
    getSeatNumber(row, seat) {
        const seatId = `${row}-${seat}`;

        // Check for custom number
        if (this.customNumbers[seatId]) {
            return this.customNumbers[seatId];
        }

        // Count only enabled seats in this row before current seat
        let enabledSeatsCount = 0;

        if (this.numberingDirection === 'right-to-left') {
            // Count from right to left
            for (let s = this.seatsPerRow - 1; s >= 0; s--) {
                const checkId = `${row}-${s}`;
                if (!this.disabledSeats.has(checkId)) {
                    enabledSeatsCount++;
                    if (s === seat) {
                        break;
                    }
                }
            }
        } else {
            // Count from left to right
            for (let s = 0; s <= seat; s++) {
                const checkId = `${row}-${s}`;
                if (!this.disabledSeats.has(checkId)) {
                    enabledSeatsCount++;
                }
            }
        }

        return { row: row + 1, seat: enabledSeatsCount };
    }

    /**
     * Handle seat click - always selects seats
     */
    handleSeatClick(seatId, event) {
        event.stopPropagation();

        // Select mode - toggle selection
        if (event.shiftKey) {
            // Multi-select with Shift
            if (this.selectedSeats.has(seatId)) {
                this.selectedSeats.delete(seatId);
            } else {
                this.selectedSeats.add(seatId);
            }
        } else {
            // Single select
            this.selectedSeats.clear();
            this.selectedSeats.add(seatId);
        }

        this.renderSeatingChart();
        this.updateSelectionButtons();
    }

    /**
     * Prompt user for custom seat number
     */
    promptCustomNumber(seatId) {
        const newRow = prompt('Введите номер ряда:', '1');
        const newSeat = prompt('Введите номер места:', '1');

        if (newRow && newSeat) {
            this.saveState(); // Save state before modification
            this.customNumbers[seatId] = {
                row: parseInt(newRow),
                seat: parseInt(newSeat)
            };
            this.renderSeatingChart();
        }
    }

    /**
     * Delete all selected seats
     */
    deleteSelected() {
        if (this.selectedSeats.size === 0) return;

        this.saveState(); // Save state before modification

        // Add all selected seats to disabled seats
        this.selectedSeats.forEach(seatId => {
            this.disabledSeats.add(seatId);
        });

        // Clear selection
        this.selectedSeats.clear();

        this.renderSeatingChart();
        this.updateSelectionButtons();
    }

    /**
     * Enable (restore) selected disabled seats
     */
    enableSelected() {
        if (this.selectedSeats.size === 0) return;

        this.saveState(); // Save state before modification

        // Remove selected seats from disabled set (restore them)
        this.selectedSeats.forEach(seatId => {
            this.disabledSeats.delete(seatId);
        });

        // Clear selection
        this.selectedSeats.clear();

        this.renderSeatingChart();
        this.updateSelectionButtons();
    }

    /**
     * Clear all selected seats
     */
    clearSelection() {
        this.selectedSeats.clear();
        this.renderSeatingChart();
        this.updateSelectionButtons();
    }

    /**
     * Center all rows by distributing edge padding evenly
     */
    centerRows() {
        this.saveState(); // For undo

        const newDisabledSeats = new Set();
        const newCustomNumbers = {};

        for (let row = 0; row < this.rows; row++) {
            // Build pattern for this row (true = enabled, false = disabled)
            const pattern = [];
            for (let seat = 0; seat < this.seatsPerRow; seat++) {
                const seatId = `${row}-${seat}`;
                pattern.push(!this.disabledSeats.has(seatId));
            }

            // Find first and last enabled seat
            let firstEnabled = pattern.indexOf(true);
            let lastEnabled = pattern.lastIndexOf(true);

            if (firstEnabled === -1) {
                // Row is completely disabled, keep it as is
                for (let seat = 0; seat < this.seatsPerRow; seat++) {
                    newDisabledSeats.add(`${row}-${seat}`);
                }
                continue;
            }

            // Extract the "core" pattern (from first to last enabled, inclusive)
            const corePattern = pattern.slice(firstEnabled, lastEnabled + 1);
            const coreLength = corePattern.length;

            // Calculate total edge padding
            const totalPadding = this.seatsPerRow - coreLength;
            const leftPad = Math.floor(totalPadding / 2);

            // Rebuild row with centered pattern
            for (let seat = 0; seat < this.seatsPerRow; seat++) {
                const seatId = `${row}-${seat}`;

                if (seat < leftPad || seat >= leftPad + coreLength) {
                    // This seat is in the padding zone
                    newDisabledSeats.add(seatId);
                } else {
                    // This seat is in the core zone
                    const coreIndex = seat - leftPad;
                    if (!corePattern[coreIndex]) {
                        // Core pattern says this should be disabled (internal gap)
                        newDisabledSeats.add(seatId);
                    }
                    // else: enabled seat, don't add to disabled set
                }

                // Handle custom numbers - map from old position to new
                // Old position: firstEnabled + coreIndex
                // New position: leftPad + coreIndex
                if (seat >= leftPad && seat < leftPad + coreLength) {
                    const coreIndex = seat - leftPad;
                    const oldSeat = firstEnabled + coreIndex;
                    const oldSeatId = `${row}-${oldSeat}`;
                    if (this.customNumbers[oldSeatId]) {
                        newCustomNumbers[seatId] = this.customNumbers[oldSeatId];
                    }
                }
            }
        }

        this.disabledSeats = newDisabledSeats;
        this.customNumbers = newCustomNumbers;
        this.renderSeatingChart();
    }

    /**
     * Select entire row
     */
    selectEntireRow() {
        if (this.selectedSeats.size === 0) {
            alert('Сначала выберите хотя бы одно место в ряду');
            return;
        }

        // Get row number from first selected seat
        const firstSeat = Array.from(this.selectedSeats)[0];
        const row = parseInt(firstSeat.split('-')[0]);

        // Select all enabled seats in this row
        this.selectedSeats.clear();
        for (let seat = 0; seat < this.seatsPerRow; seat++) {
            const seatId = `${row}-${seat}`;
            if (!this.disabledSeats.has(seatId)) {
                this.selectedSeats.add(seatId);
            }
        }

        this.renderSeatingChart();
        this.updateSelectionButtons();
    }

    /**
     * Select entire column
     */
    selectEntireColumn() {
        if (this.selectedSeats.size === 0) {
            alert('Сначала выберите хотя бы одно место в колонке');
            return;
        }

        // Get column number from first selected seat
        const firstSeat = Array.from(this.selectedSeats)[0];
        const col = parseInt(firstSeat.split('-')[1]);

        // Select all enabled seats in this column
        this.selectedSeats.clear();
        for (let row = 0; row < this.rows; row++) {
            const seatId = `${row}-${col}`;
            if (!this.disabledSeats.has(seatId)) {
                this.selectedSeats.add(seatId);
            }
        }

        this.renderSeatingChart();
        this.updateSelectionButtons();
    }

    /**
     * Recalculate seat numbers (removes all custom numbers except those explicitly set)
     */
    recalculateNumbers() {
        if (!confirm('Пересчитать номера мест? Все кастомные номера будут удалены.')) {
            return;
        }

        this.saveState(); // Save state before modification

        // Clear all custom numbers
        this.customNumbers = {};

        this.renderSeatingChart();
        alert('Номера мест пересчитаны');
    }

    /**
     * Open modal to set custom number for selected seat
     */
    openCustomNumberModal() {
        if (this.selectedSeats.size !== 1) {
            alert('Выберите ровно одно место для изменения номера');
            return;
        }

        const seatId = Array.from(this.selectedSeats)[0];
        const [row, seat] = seatId.split('-').map(n => parseInt(n));

        // Get current number
        const currentNum = this.getSeatNumber(row, seat);

        // Prompt for new number
        const newRow = prompt(`Введите номер ряда (текущий: ${currentNum.row}):`, currentNum.row);
        if (newRow === null) return; // Cancelled

        const newSeat = prompt(`Введите номер места (текущий: ${currentNum.seat}):`, currentNum.seat);
        if (newSeat === null) return; // Cancelled

        if (newRow && newSeat) {
            this.saveState(); // Save state before modification
            this.customNumbers[seatId] = {
                row: parseInt(newRow),
                seat: parseInt(newSeat)
            };
            this.renderSeatingChart();
        }
    }

    /**
     * Update selection button states
     */
    updateSelectionButtons() {
        const deleteBtn = document.getElementById('delete-selected-btn');
        const enableBtn = document.getElementById('enable-selected-btn');
        const clearBtn = document.getElementById('clear-selection-btn');
        const customNumberBtn = document.getElementById('custom-number-btn');
        const selectRowBtn = document.getElementById('select-row-btn');
        const selectColBtn = document.getElementById('select-col-btn');

        const hasSelection = this.selectedSeats.size > 0;
        const hasOneSelection = this.selectedSeats.size === 1;

        if (deleteBtn) {
            deleteBtn.disabled = !hasSelection;
        }
        if (enableBtn) {
            enableBtn.disabled = !hasSelection;
        }
        if (clearBtn) {
            clearBtn.disabled = !hasSelection;
        }
        if (customNumberBtn) {
            customNumberBtn.disabled = !hasOneSelection;
        }
        if (selectRowBtn) {
            selectRowBtn.disabled = !hasSelection;
        }
        if (selectColBtn) {
            selectColBtn.disabled = !hasSelection;
        }
    }

    // ===== Zoom/Pan Functions =====

    /**
     * Zoom in
     */
    zoomIn() {
        this.scale *= 1.2;
        this.scale = Math.min(this.scale, 5); // Max zoom 5x
        this.renderSeatingChart();
    }

    /**
     * Zoom out
     */
    zoomOut() {
        this.scale /= 1.2;
        this.scale = Math.max(this.scale, 0.3); // Min zoom 0.3x
        this.renderSeatingChart();
    }

    /**
     * Reset zoom and pan to default
     */
    resetZoom() {
        this.scale = 1.0;
        this.translateX = 0;
        this.translateY = 0;
        this.renderSeatingChart();
    }

    /**
     * Setup pan and zoom event handlers
     */
    setupPanHandlers() {
        const container = document.getElementById('seating-canvas-container');
        const svg = document.getElementById('seating-canvas');

        if (!container || !svg) return;

        // Mouse down - start panning
        container.addEventListener('mousedown', (e) => {
            if (e.target === svg || e.target.closest('#main-group')) {
                this.isPanning = true;
                this.panStartX = e.clientX - this.translateX;
                this.panStartY = e.clientY - this.translateY;
                container.style.cursor = 'grabbing';
            }
        });

        // Mouse move - pan
        container.addEventListener('mousemove', (e) => {
            if (this.isPanning) {
                this.translateX = e.clientX - this.panStartX;
                this.translateY = e.clientY - this.panStartY;
                this.renderSeatingChart();
            }
        });

        // Mouse up - stop panning
        const stopPanning = () => {
            if (this.isPanning) {
                this.isPanning = false;
                container.style.cursor = 'grab';
            }
        };

        container.addEventListener('mouseup', stopPanning);
        container.addEventListener('mouseleave', stopPanning);

        // Mouse wheel - zoom
        container.addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.deltaY < 0) {
                this.zoomIn();
            } else {
                this.zoomOut();
            }
        }, { passive: false });
    }

    // ===== Undo/Redo Functions =====

    /**
     * Save current state to history
     */
    saveState() {
        // Create state snapshot
        const state = {
            disabledSeats: new Set(this.disabledSeats),
            customNumbers: JSON.parse(JSON.stringify(this.customNumbers)),
            selectedSeats: new Set(this.selectedSeats),
            numberingDirection: this.numberingDirection
        };

        // Remove any states after current index (if we're not at the end)
        this.history = this.history.slice(0, this.historyIndex + 1);

        // Add new state
        this.history.push(state);
        this.historyIndex++;

        // Limit history size
        if (this.history.length > this.maxHistorySize) {
            this.history.shift();
            this.historyIndex--;
        }

        this.updateUndoRedoButtons();
    }

    /**
     * Undo last action
     */
    undo() {
        if (this.historyIndex > 0) {
            this.historyIndex--;
            this.restoreState(this.history[this.historyIndex]);
            this.updateUndoRedoButtons();
        }
    }

    /**
     * Redo last undone action
     */
    redo() {
        if (this.historyIndex < this.history.length - 1) {
            this.historyIndex++;
            this.restoreState(this.history[this.historyIndex]);
            this.updateUndoRedoButtons();
        }
    }

    /**
     * Restore state from history
     */
    restoreState(state) {
        this.disabledSeats = new Set(state.disabledSeats);
        this.customNumbers = JSON.parse(JSON.stringify(state.customNumbers));
        this.selectedSeats = new Set(state.selectedSeats);
        this.numberingDirection = state.numberingDirection;

        // Update numbering direction select
        const select = document.getElementById('numbering-direction');
        if (select) {
            select.value = this.numberingDirection;
        }

        this.renderSeatingChart();
    }

    /**
     * Update undo/redo button states
     */
    updateUndoRedoButtons() {
        const undoBtn = document.getElementById('undo-btn');
        const redoBtn = document.getElementById('redo-btn');

        if (undoBtn) {
            undoBtn.disabled = this.historyIndex <= 0;
        }
        if (redoBtn) {
            redoBtn.disabled = this.historyIndex >= this.history.length - 1;
        }
    }

    // ===== Export/Import Functions =====

    /**
     * Export configuration for saving
     */
    exportConfig() {
        return {
            rows: this.rows,
            seats_per_row: this.seatsPerRow,
            disabled_seats: Array.from(this.disabledSeats),
            custom_numbers: this.customNumbers,
            numbering_direction: this.numberingDirection
        };
    }

    /**
     * Load existing configuration
     */
    loadConfig(config) {
        this.rows = config.rows;
        this.seatsPerRow = config.seats_per_row;
        this.disabledSeats = new Set(config.disabled_seats || []);
        this.customNumbers = config.custom_numbers || {};
        this.numberingDirection = config.numbering_direction || 'left-to-right';
        this.selectedSeats.clear();

        // Update form inputs
        const rowsInput = document.getElementById('map-rows');
        const seatsInput = document.getElementById('map-seats-per-row');
        const directionSelect = document.getElementById('numbering-direction');

        if (rowsInput) rowsInput.value = this.rows;
        if (seatsInput) seatsInput.value = this.seatsPerRow;
        if (directionSelect) directionSelect.value = this.numberingDirection;

        // Clear and reset history
        this.history = [];
        this.historyIndex = -1;
        this.saveState();

        this.renderSeatingChart();
        this.updateUndoRedoButtons();
    }

    /**
     * Setup event listeners (called when modal opens)
     */
    setupEventListeners() {
        // Numbering direction select
        const directionSelect = document.getElementById('numbering-direction');
        if (directionSelect) {
            // Remove old listener if exists
            directionSelect.removeEventListener('change', this._directionChangeHandler);

            // Create new handler and save reference
            this._directionChangeHandler = (e) => {
                this.saveState(); // Save state before modification
                this.numberingDirection = e.target.value;
                this.renderSeatingChart();
            };

            directionSelect.addEventListener('change', this._directionChangeHandler);
        }

        // Setup pan handlers
        this.setupPanHandlers();
    }
}

// Initialize global instance
let seatingEditor = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    seatingEditor = new SeatingMapEditor();
});
