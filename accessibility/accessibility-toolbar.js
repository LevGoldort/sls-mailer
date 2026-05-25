/**
 * YallaBalagan Accessibility Toolbar
 * Custom accessibility features for WCAG 2.1 AA / IS 5568 compliance
 * Version: 1.0
 */

(function() {
    'use strict';

    // Configuration
    const STORAGE_KEY = 'yb_a11y_preferences';
    const VERSION = '1.0';

    // State
    let preferences = getDefaultPreferences();
    let currentLanguage = 'en';
    let isOpen = false;
    let readingGuideElement = null;

    // Translations
    const translations = {
        he: {
            toolbarTitle: 'נגישות',
            languageToggle: 'EN',
            close: 'סגור',
            reset: 'איפוס',
            resetConfirm: 'האם לאפס את כל ההגדרות?',
            visualSection: 'התאמות חזותיות',
            navigationSection: 'עזרי ניווט',
            cognitiveSection: 'תמיכה קוגניטיבית',
            fontSize: 'גודל גופן',
            fontSizeDefault: 'רגיל',
            fontSizeMedium: 'בינוני',
            fontSizeLarge: 'גדול',
            fontSizeXLarge: 'גדול מאוד',
            contrast: 'ניגודיות',
            contrastNone: 'רגיל',
            contrastDark: 'כהה',
            contrastLight: 'בהיר',
            contrastInverted: 'הפוך',
            textSpacing: 'ריווח טקסט',
            hideImages: 'הסתרת תמונות',
            highlightLinks: 'הדגשת קישורים',
            keyboardNav: '+ ניגודיות',
            readingGuide: 'ריווח עקסט',
            dyslexicFont: 'תמיכה בדיסלקציה',
            lineHeight: 'גובה שורה',
            lineHeightNormal: 'רגיל',
            lineHeightRelaxed: 'רגוע',
            lineHeightLoose: 'רופף',
            reducedMotion: 'ביטול הנפשות',
            pauseAnimations: 'עצור הנפשות',
            saved: 'ההגדרות נשמרו',
            cursor: 'סמן',
            textSize: 'טקסט גדול'
        },
        en: {
            toolbarTitle: 'Accessibility',
            languageToggle: 'עב',
            close: 'Close',
            reset: 'Reset',
            resetConfirm: 'Reset all settings?',
            visualSection: 'Visual Adjustments',
            navigationSection: 'Navigation Aids',
            cognitiveSection: 'Cognitive Support',
            fontSize: 'Font Size',
            fontSizeDefault: 'Default',
            fontSizeMedium: 'Medium',
            fontSizeLarge: 'Large',
            fontSizeXLarge: 'Extra Large',
            contrast: 'Contrast',
            contrastNone: 'Normal',
            contrastDark: 'Dark',
            contrastLight: 'Light',
            contrastInverted: 'Inverted',
            textSpacing: 'Text Spacing',
            hideImages: 'Hide Images',
            highlightLinks: 'Highlight Links',
            keyboardNav: 'Keyboard Navigation',
            readingGuide: 'Reading Guide',
            dyslexicFont: 'Dyslexia Support',
            lineHeight: 'Line Height',
            lineHeightNormal: 'Normal',
            lineHeightRelaxed: 'Relaxed',
            lineHeightLoose: 'Loose',
            reducedMotion: 'Reduced Motion',
            pauseAnimations: 'Pause Animations',
            saved: 'Settings saved',
            cursor: 'Cursor',
            textSize: 'Text Size'
        }
    };

    // Get default preferences
    function getDefaultPreferences() {
        return {
            version: VERSION,
            language: 'en',
            fontSize: 'default',
            contrast: 'none',
            textSpacing: false,
            hideImages: false,
            highlightLinks: false,
            keyboardNav: true,
            readingGuide: false,
            dyslexicFont: false,
            lineHeight: 'normal',
            reducedMotion: false,
            pauseAnimations: false
        };
    }

    // Translate helper
    function t(key) {
        return translations[currentLanguage][key] || key;
    }

    // LocalStorage helpers
    function loadPreferences() {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stored) {
                const parsed = JSON.parse(stored);
                if (parsed.version === VERSION) {
                    preferences = { ...getDefaultPreferences(), ...parsed };
                    currentLanguage = preferences.language;
                }
            }
        } catch (e) {
            console.error('Error loading accessibility preferences:', e);
        }
    }

    function savePreferences() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
        } catch (e) {
            console.error('Error saving accessibility preferences:', e);
        }
    }

    function resetPreferences() {
        // Create custom confirmation dialog
        const message = t('resetConfirm');

        // Create modal overlay
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 10002;
            display: flex;
            align-items: center;
            justify-content: center;
        `;

        // Create dialog
        const dialog = document.createElement('div');
        dialog.style.cssText = `
            background: white;
            padding: 2rem;
            border-radius: 0.5rem;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            max-width: 400px;
            text-align: center;
        `;

        dialog.innerHTML = `
            <p style="margin: 0 0 1.5rem 0; font-size: 1.125rem; color: #374151;">${message}</p>
            <div style="display: flex; gap: 1rem; justify-content: center;">
                <button id="a11y-confirm-yes" style="
                    padding: 0.75rem 1.5rem;
                    background: #ef4444;
                    color: white;
                    border: none;
                    border-radius: 0.375rem;
                    font-weight: 600;
                    cursor: pointer;
                    font-size: 1rem;
                ">OK</button>
                <button id="a11y-confirm-no" style="
                    padding: 0.75rem 1.5rem;
                    background: #6b7280;
                    color: white;
                    border: none;
                    border-radius: 0.375rem;
                    font-weight: 600;
                    cursor: pointer;
                    font-size: 1rem;
                ">${currentLanguage === 'he' ? 'ביטול' : 'Cancel'}</button>
            </div>
        `;

        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        // Handle confirmation
        const handleConfirm = (confirmed) => {
            overlay.remove();

            if (confirmed) {
                preferences = getDefaultPreferences();
                currentLanguage = 'he';
                savePreferences();
                applyAllPreferences();
                renderToolbar();
                updateButtonStates();

                // Close the panel after reset
                if (isOpen) {
                    togglePanel();
                }
            }
        };

        document.getElementById('a11y-confirm-yes').addEventListener('click', () => handleConfirm(true));
        document.getElementById('a11y-confirm-no').addEventListener('click', () => handleConfirm(false));

        // Close on overlay click
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                handleConfirm(false);
            }
        });

        // Close on Escape key
        const escapeHandler = (e) => {
            if (e.key === 'Escape') {
                handleConfirm(false);
                document.removeEventListener('keydown', escapeHandler);
            }
        };
        document.addEventListener('keydown', escapeHandler);
    }

    // Apply all preferences
    function applyAllPreferences() {
        applyFontSize(preferences.fontSize);
        applyContrast(preferences.contrast);
        applyTextSpacing(preferences.textSpacing);
        applyHideImages(preferences.hideImages);
        applyHighlightLinks(preferences.highlightLinks);
        applyKeyboardNav(preferences.keyboardNav);
        applyReadingGuide(preferences.readingGuide);
        applyDyslexicFont(preferences.dyslexicFont);
        applyLineHeight(preferences.lineHeight);
        applyReducedMotion(preferences.reducedMotion);
        applyPauseAnimations(preferences.pauseAnimations);
        applyLanguage(preferences.language);
    }

    // Feature: Font Size
    function applyFontSize(level) {
        const scales = {
            'default': 1,
            'medium': 1.15,
            'large': 1.3,
            'xlarge': 1.5
        };
        const scale = scales[level] || 1;
        document.documentElement.style.setProperty('--a11y-font-scale', scale);
        // zoom scales px-based layouts; fallback to transform for unsupported browsers
        document.body.style.zoom = scale === 1 ? '' : scale;
        preferences.fontSize = level;
    }

    // Feature: Contrast
    function applyContrast(mode) {
        const html = document.documentElement;
        html.classList.remove('a11y-contrast-dark', 'a11y-contrast-light', 'a11y-contrast-inverted');

        if (mode !== 'none') {
            html.classList.add(`a11y-contrast-${mode}`);
        }
        preferences.contrast = mode;
    }

    // Feature: Text Spacing
    function applyTextSpacing(enabled) {
        document.documentElement.classList.toggle('a11y-text-spacing', enabled);
        preferences.textSpacing = enabled;
    }

    // Feature: Hide Images
    function applyHideImages(enabled) {
        document.documentElement.classList.toggle('a11y-hide-images', enabled);
        preferences.hideImages = enabled;
    }

    // Feature: Highlight Links
    function applyHighlightLinks(enabled) {
        document.documentElement.classList.toggle('a11y-highlight-links', enabled);
        preferences.highlightLinks = enabled;
    }

    // Feature: Keyboard Navigation
    function applyKeyboardNav(enabled) {
        document.documentElement.classList.toggle('a11y-keyboard-nav', enabled);
        preferences.keyboardNav = enabled;
    }

    // Feature: Reading Guide
    function applyReadingGuide(enabled) {
        if (enabled && !readingGuideElement) {
            readingGuideElement = document.createElement('div');
            readingGuideElement.className = 'a11y-reading-guide';
            document.body.appendChild(readingGuideElement);

            document.addEventListener('mousemove', handleReadingGuideMove);
            document.addEventListener('touchmove', handleReadingGuideMove);
        } else if (!enabled && readingGuideElement) {
            document.removeEventListener('mousemove', handleReadingGuideMove);
            document.removeEventListener('touchmove', handleReadingGuideMove);
            readingGuideElement.remove();
            readingGuideElement = null;
        }
        preferences.readingGuide = enabled;
    }

    function handleReadingGuideMove(event) {
        if (!readingGuideElement) return;

        const y = event.type === 'touchmove' ? event.touches[0].clientY : event.clientY;
        readingGuideElement.style.top = `${y}px`;
    }

    // Feature: Dyslexic Font
    function applyDyslexicFont(enabled) {
        document.documentElement.classList.toggle('a11y-dyslexic-font', enabled);
        preferences.dyslexicFont = enabled;
    }

    // Feature: Line Height
    function applyLineHeight(level) {
        const heights = {
            'normal': 1.6,
            'relaxed': 2.0,
            'loose': 2.5
        };
        document.documentElement.style.setProperty('--a11y-line-height', heights[level] || 1.6);
        preferences.lineHeight = level;
    }

    // Feature: Reduced Motion
    function applyReducedMotion(enabled) {
        document.documentElement.classList.toggle('a11y-reduced-motion', enabled);
        preferences.reducedMotion = enabled;
    }

    // Feature: Pause Animations
    function applyPauseAnimations(enabled) {
        document.documentElement.classList.toggle('a11y-pause-animations', enabled);
        preferences.pauseAnimations = enabled;
    }

    // Feature: Language
    function applyLanguage(lang) {
        currentLanguage = lang;
        preferences.language = lang;

        const html = document.documentElement;
        html.setAttribute('lang', lang);
        html.setAttribute('dir', lang === 'he' ? 'rtl' : 'ltr');

        renderToolbar();
    }

    // Create toolbar UI
    function createToolbarUI() {
        // Create button
        const button = document.createElement('button');
        button.id = 'a11y-button';
        button.className = 'a11y-button';
        button.setAttribute('aria-label', t('toolbarTitle'));
        button.setAttribute('aria-expanded', 'false');
        button.innerHTML = `
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2C13.1 2 14 2.9 14 4C14 5.1 13.1 6 12 6C10.9 6 10 5.1 10 4C10 2.9 10.9 2 12 2ZM21 9H15V22H13V16H11V22H9V9H3V7H21V9Z" fill="currentColor"/>
            </svg>
        `;
        document.body.appendChild(button);

        // Create panel
        const panel = document.createElement('div');
        panel.id = 'a11y-panel';
        panel.className = 'a11y-panel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-labelledby', 'a11y-title');
        panel.setAttribute('hidden', '');
        document.body.appendChild(panel);

        renderToolbar();

        // ONE-TIME listeners — must not be inside renderToolbar (would accumulate)
        button.addEventListener('click', togglePanel);

        // All panel interactions via a single delegated listener on the persistent panel element
        panel.addEventListener('click', (e) => {
            if (e.target.closest('.a11y-close')) {
                togglePanel();
                return;
            }
            if (e.target.closest('.a11y-lang-toggle')) {
                applyLanguage(currentLanguage === 'he' ? 'en' : 'he');
                savePreferences();
                return;
            }
            const target = e.target.closest('[data-action]');
            if (target) {
                handleFeatureToggle(target.dataset.action, target.dataset.value);
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && isOpen) togglePanel();
        });

        // composedPath captures the original DOM path before innerHTML replacement,
        // so panel.contains check works correctly even after renderToolbar() re-renders
        document.addEventListener('click', (e) => {
            if (isOpen && !e.composedPath().includes(panel) && !e.composedPath().includes(button)) {
                togglePanel();
            }
        });
    }

    // Render toolbar content
    function renderToolbar() {
        const panel = document.getElementById('a11y-panel');
        if (!panel) return;

        panel.innerHTML = `
            <div class="a11y-panel-header">
                <h2 id="a11y-title">${t('toolbarTitle')}</h2>
                <div class="a11y-header-controls">
                    <button class="a11y-lang-toggle" aria-label="${t('languageToggle')}">${t('languageToggle')}</button>
                    <button class="a11y-close" aria-label="${t('close')}">×</button>
                </div>
            </div>
            <div class="a11y-panel-body">
                <!-- Visual Adjustments Section -->
                <section class="a11y-section">
                    <h3>${t('visualSection')}</h3>

                    <div class="a11y-control">
                        <label>${t('fontSize')}</label>
                        <div class="a11y-button-group">
                            <button class="a11y-option ${preferences.fontSize === 'default' ? 'active' : ''}" data-action="fontSize" data-value="default">${t('fontSizeDefault')}</button>
                            <button class="a11y-option ${preferences.fontSize === 'medium' ? 'active' : ''}" data-action="fontSize" data-value="medium">${t('fontSizeMedium')}</button>
                            <button class="a11y-option ${preferences.fontSize === 'large' ? 'active' : ''}" data-action="fontSize" data-value="large">${t('fontSizeLarge')}</button>
                            <button class="a11y-option ${preferences.fontSize === 'xlarge' ? 'active' : ''}" data-action="fontSize" data-value="xlarge">${t('fontSizeXLarge')}</button>
                        </div>
                    </div>

                    <div class="a11y-control">
                        <label>${t('contrast')}</label>
                        <div class="a11y-button-group">
                            <button class="a11y-option ${preferences.contrast === 'none' ? 'active' : ''}" data-action="contrast" data-value="none">${t('contrastNone')}</button>
                            <button class="a11y-option ${preferences.contrast === 'dark' ? 'active' : ''}" data-action="contrast" data-value="dark">${t('contrastDark')}</button>
                            <button class="a11y-option ${preferences.contrast === 'light' ? 'active' : ''}" data-action="contrast" data-value="light">${t('contrastLight')}</button>
                            <button class="a11y-option ${preferences.contrast === 'inverted' ? 'active' : ''}" data-action="contrast" data-value="inverted">${t('contrastInverted')}</button>
                        </div>
                    </div>

                    <div class="a11y-control">
                        <button class="a11y-toggle ${preferences.textSpacing ? 'active' : ''}" data-action="textSpacing">
                            <span>${t('textSpacing')}</span>
                            <span class="a11y-toggle-indicator"></span>
                        </button>
                    </div>

                    <div class="a11y-control">
                        <button class="a11y-toggle ${preferences.hideImages ? 'active' : ''}" data-action="hideImages">
                            <span>${t('hideImages')}</span>
                            <span class="a11y-toggle-indicator"></span>
                        </button>
                    </div>

                    <div class="a11y-control">
                        <button class="a11y-toggle ${preferences.highlightLinks ? 'active' : ''}" data-action="highlightLinks">
                            <span>${t('highlightLinks')}</span>
                            <span class="a11y-toggle-indicator"></span>
                        </button>
                    </div>
                </section>

                <!-- Navigation Aids Section -->
                <section class="a11y-section">
                    <h3>${t('navigationSection')}</h3>

                    <div class="a11y-control">
                        <button class="a11y-toggle ${preferences.keyboardNav ? 'active' : ''}" data-action="keyboardNav">
                            <span>${t('keyboardNav')}</span>
                            <span class="a11y-toggle-indicator"></span>
                        </button>
                    </div>

                    <div class="a11y-control">
                        <button class="a11y-toggle ${preferences.readingGuide ? 'active' : ''}" data-action="readingGuide">
                            <span>${t('readingGuide')}</span>
                            <span class="a11y-toggle-indicator"></span>
                        </button>
                    </div>
                </section>

                <!-- Cognitive Support Section -->
                <section class="a11y-section">
                    <h3>${t('cognitiveSection')}</h3>

                    <div class="a11y-control">
                        <button class="a11y-toggle ${preferences.dyslexicFont ? 'active' : ''}" data-action="dyslexicFont">
                            <span>${t('dyslexicFont')}</span>
                            <span class="a11y-toggle-indicator"></span>
                        </button>
                    </div>

                    <div class="a11y-control">
                        <label>${t('lineHeight')}</label>
                        <div class="a11y-button-group">
                            <button class="a11y-option ${preferences.lineHeight === 'normal' ? 'active' : ''}" data-action="lineHeight" data-value="normal">${t('lineHeightNormal')}</button>
                            <button class="a11y-option ${preferences.lineHeight === 'relaxed' ? 'active' : ''}" data-action="lineHeight" data-value="relaxed">${t('lineHeightRelaxed')}</button>
                            <button class="a11y-option ${preferences.lineHeight === 'loose' ? 'active' : ''}" data-action="lineHeight" data-value="loose">${t('lineHeightLoose')}</button>
                        </div>
                    </div>

                    <div class="a11y-control">
                        <button class="a11y-toggle ${preferences.reducedMotion ? 'active' : ''}" data-action="reducedMotion">
                            <span>${t('reducedMotion')}</span>
                            <span class="a11y-toggle-indicator"></span>
                        </button>
                    </div>

                    <div class="a11y-control">
                        <button class="a11y-toggle ${preferences.pauseAnimations ? 'active' : ''}" data-action="pauseAnimations">
                            <span>${t('pauseAnimations')}</span>
                            <span class="a11y-toggle-indicator"></span>
                        </button>
                    </div>
                </section>

                <div class="a11y-panel-footer">
                    <button class="a11y-reset" data-action="reset">${t('reset')}</button>
                </div>
            </div>
        `;

    }

    // Toggle panel open/close
    function togglePanel() {
        const button = document.getElementById('a11y-button');
        const panel = document.getElementById('a11y-panel');

        if (!button || !panel) return;

        isOpen = !isOpen;

        if (isOpen) {
            panel.removeAttribute('hidden');
            button.setAttribute('aria-expanded', 'true');
            // Focus first interactive element
            setTimeout(() => {
                const firstButton = panel.querySelector('button');
                if (firstButton) firstButton.focus();
            }, 100);
        } else {
            panel.setAttribute('hidden', '');
            button.setAttribute('aria-expanded', 'false');
            button.focus();
        }
    }

    // Update button active states
    function updateButtonStates() {
        renderToolbar();
    }

    // Handle feature toggle
    function handleFeatureToggle(action, value) {
        switch (action) {
            case 'fontSize':
                applyFontSize(value);
                break;
            case 'contrast':
                applyContrast(value);
                break;
            case 'textSpacing':
                applyTextSpacing(!preferences.textSpacing);
                break;
            case 'hideImages':
                applyHideImages(!preferences.hideImages);
                break;
            case 'highlightLinks':
                applyHighlightLinks(!preferences.highlightLinks);
                break;
            case 'keyboardNav':
                applyKeyboardNav(!preferences.keyboardNav);
                break;
            case 'readingGuide':
                applyReadingGuide(!preferences.readingGuide);
                break;
            case 'dyslexicFont':
                applyDyslexicFont(!preferences.dyslexicFont);
                break;
            case 'lineHeight':
                applyLineHeight(value);
                break;
            case 'reducedMotion':
                applyReducedMotion(!preferences.reducedMotion);
                break;
            case 'pauseAnimations':
                applyPauseAnimations(!preferences.pauseAnimations);
                break;
            case 'reset':
                resetPreferences();
                return;
        }

        savePreferences();
        updateButtonStates();
    }


    // Check browser preferences
    function checkBrowserPreferences() {
        // Check for prefers-reduced-motion
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches && !preferences.reducedMotion) {
            // Don't override if user has saved preferences
            if (!localStorage.getItem(STORAGE_KEY)) {
                applyReducedMotion(true);
            }
        }
    }

    // Initialize
    function init() {
        loadPreferences();
        applyAllPreferences();
        createToolbarUI();
        checkBrowserPreferences();
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Export for debugging
    window.YBAccessibility = {
        preferences: () => preferences,
        reset: resetPreferences,
        applyAll: applyAllPreferences
    };
})();
