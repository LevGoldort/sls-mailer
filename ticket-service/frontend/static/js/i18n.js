/**
 * YallaBalagan i18n — client-side UI translation overlay.
 * Default language is Russian (pre-rendered in HTML by Jinja2).
 * When EN is selected, translations from i18n.en.json are applied via data-i18n attributes.
 */
(function () {
    'use strict';

    var LANG_KEY = 'yb_lang';
    var translations = {};
    var currentLang = localStorage.getItem(LANG_KEY) || 'ru';

    // Load EN translations synchronously so they're ready before DOMContentLoaded.
    // File is small (~10KB) and same-origin — served from CloudFront cache on repeat visits.
    function loadTranslations() {
        if (currentLang === 'ru') return;
        try {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', '/static/js/i18n.en.json', false);
            xhr.send();
            if (xhr.status === 200) {
                translations = JSON.parse(xhr.responseText);
            }
        } catch (e) {
            console.warn('i18n: failed to load translations', e);
        }
    }

    // Resolve a dot-notation key to a translated string.
    // Falls back to the key itself so missing translations are visible during development.
    function t(key) {
        if (currentLang === 'ru') return null; // RU text already in HTML
        return translations[key] !== undefined ? translations[key] : null;
    }

    // Apply translations to all marked elements in the document.
    function applyTranslations() {
        if (currentLang === 'ru') return;

        // Text content
        document.querySelectorAll('[data-i18n]').forEach(function (el) {
            var val = t(el.getAttribute('data-i18n'));
            if (val !== null) el.textContent = val;
        });

        // innerHTML (for strings containing HTML like links)
        document.querySelectorAll('[data-i18n-html]').forEach(function (el) {
            var val = t(el.getAttribute('data-i18n-html'));
            if (val !== null) el.innerHTML = val;
        });

        // aria-label
        document.querySelectorAll('[data-i18n-aria]').forEach(function (el) {
            var val = t(el.getAttribute('data-i18n-aria'));
            if (val !== null) el.setAttribute('aria-label', val);
        });

        // placeholder
        document.querySelectorAll('[data-i18n-placeholder]').forEach(function (el) {
            var val = t(el.getAttribute('data-i18n-placeholder'));
            if (val !== null) el.setAttribute('placeholder', val);
        });

        // title attribute
        document.querySelectorAll('[data-i18n-title]').forEach(function (el) {
            var val = t(el.getAttribute('data-i18n-title'));
            if (val !== null) el.setAttribute('title', val);
        });

        // Month name localization: replace Cyrillic month names with English equivalents
        var RU_MONTHS = {
            'Январь': 'January', 'Февраль': 'February', 'Март': 'March',
            'Апрель': 'April', 'Май': 'May', 'Июнь': 'June',
            'Июль': 'July', 'Август': 'August', 'Сентябрь': 'September',
            'Октябрь': 'October', 'Ноябрь': 'November', 'Декабрь': 'December'
        };
        document.querySelectorAll('[data-i18n-month]').forEach(function (el) {
            var text = el.textContent.trim();
            var months = Object.keys(RU_MONTHS);
            for (var i = 0; i < months.length; i++) {
                if (text.indexOf(months[i]) !== -1) {
                    el.textContent = text.replace(months[i], RU_MONTHS[months[i]]);
                    break;
                }
            }
        });

        document.documentElement.setAttribute('lang', currentLang);
    }

    // Switch language and reload the page.
    function setLang(lang) {
        localStorage.setItem(LANG_KEY, lang);
        location.reload();
    }

    // English plural: n=1 → one form, otherwise many form.
    // Accepts the same 4-argument signature as ru_plural for compatibility.
    function enPlural(n, oneKey, fewKey, manyKey) {
        var key = n === 1 ? oneKey : manyKey;
        var val = t(key);
        return val !== null ? val : key;
    }

    // Initialise
    loadTranslations();

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', applyTranslations);
    } else {
        applyTranslations();
    }

    // Public API — available to checkout.html, ticket-widget.js, etc.
    window.i18n = {
        t: t,
        lang: currentLang,
        setLang: setLang,
        enPlural: enPlural,
        isEN: currentLang === 'en',
    };
})();
