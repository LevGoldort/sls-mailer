/**
 * Cookie Consent Manager
 * GDPR-compliant cookie consent handling
 */

(function() {
    'use strict';

    const COOKIE_NAME = 'yb_cookie_consent';
    const COOKIE_EXPIRY_DAYS = 365;

    // Get cookie value
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }

    // Set cookie
    function setCookie(name, value, days) {
        const date = new Date();
        date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
        const expires = `expires=${date.toUTCString()}`;
        document.cookie = `${name}=${value};${expires};path=/;SameSite=Lax`;
    }

    // Check if user has given consent
    function hasConsent() {
        return getCookie(COOKIE_NAME) === 'accepted';
    }

    // Check if user has declined
    function hasDeclined() {
        return getCookie(COOKIE_NAME) === 'declined';
    }

    // Load analytics scripts
    function loadAnalytics() {
        // Get analytics IDs from data attributes
        const consentBanner = document.getElementById('cookie-consent-banner');
        if (!consentBanner) return;

        const fbPixelId = consentBanner.dataset.fbPixel;
        const ga4Id = consentBanner.dataset.ga4;

        // Load Facebook Pixel
        if (fbPixelId) {
            !function(f,b,e,v,n,t,s)
            {if(f.fbq)return;n=f.fbq=function(){n.callMethod?
            n.callMethod.apply(n,arguments):n.queue.push(arguments)};
            if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
            n.queue=[];t=b.createElement(e);t.async=!0;
            t.src=v;s=b.getElementsByTagName(e)[0];
            s.parentNode.insertBefore(t,s)}(window, document,'script',
            'https://connect.facebook.net/en_US/fbevents.js');
            fbq('init', fbPixelId);
            fbq('track', 'PageView');
        }

        // Load Google Analytics 4
        if (ga4Id) {
            const gaScript = document.createElement('script');
            gaScript.async = true;
            gaScript.src = `https://www.googletagmanager.com/gtag/js?id=${ga4Id}`;
            document.head.appendChild(gaScript);

            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', ga4Id);
            window.gtag = gtag;
        }
    }

    // Accept cookies
    function acceptCookies() {
        setCookie(COOKIE_NAME, 'accepted', COOKIE_EXPIRY_DAYS);
        hideBanner();
        loadAnalytics();
    }

    // Decline cookies
    function declineCookies() {
        setCookie(COOKIE_NAME, 'declined', COOKIE_EXPIRY_DAYS);
        hideBanner();
    }

    // Show banner
    function showBanner() {
        const banner = document.getElementById('cookie-consent-banner');
        if (banner) {
            setTimeout(() => banner.classList.add('show'), 100);
        }
    }

    // Hide banner
    function hideBanner() {
        const banner = document.getElementById('cookie-consent-banner');
        if (banner) {
            banner.classList.remove('show');
            setTimeout(() => banner.remove(), 300);
        }
    }

    // Initialize
    function init() {
        // If user has already consented, load analytics
        if (hasConsent()) {
            loadAnalytics();
            return;
        }

        // If user hasn't made a choice, show banner
        if (!hasDeclined() && !hasConsent()) {
            showBanner();
        }

        // Set up event listeners
        const acceptBtn = document.getElementById('cookie-accept');
        const declineBtn = document.getElementById('cookie-decline');

        if (acceptBtn) {
            acceptBtn.addEventListener('click', acceptCookies);
        }

        if (declineBtn) {
            declineBtn.addEventListener('click', declineCookies);
        }
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Helper function to track events (only if consent given)
    function trackEvent(eventName, eventData, callback) {
        if (!hasConsent()) {
            console.log('[Cookie Consent] Event not tracked - no consent:', eventName);
            if (callback) callback();
            return;
        }

        // Event will be tracked by fbq/gtag if they are loaded
        if (callback) callback();
    }

    // Expose functions for use in analytics tracking
    window.YBCookieConsent = {
        hasConsent: hasConsent,
        acceptCookies: acceptCookies,
        declineCookies: declineCookies,
        trackEvent: trackEvent
    };
})();
