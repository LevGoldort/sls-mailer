/**
 * YallaBalagan - Main JavaScript
 */

// Utility: Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    const options = { day: 'numeric', month: 'long', year: 'numeric' };
    return date.toLocaleDateString('ru-RU', options);
}

// Utility: Format time
function formatTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

// Lazy loading images
document.addEventListener('DOMContentLoaded', function() {
    // Add smooth scroll behavior
    document.documentElement.style.scrollBehavior = 'smooth';

    // Image lazy loading (if browser doesn't support native lazy loading)
    if ('loading' in HTMLImageElement.prototype) {
        const images = document.querySelectorAll('img[loading="lazy"]');
        images.forEach(img => {
            img.src = img.dataset.src || img.src;
        });
    } else {
        // Fallback for browsers that don't support lazy loading
        const script = document.createElement('script');
        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/lazysizes/5.3.2/lazysizes.min.js';
        document.body.appendChild(script);
    }

    // Handle image errors (show placeholder)
    const images = document.querySelectorAll('img');
    images.forEach(img => {
        img.addEventListener('error', function() {
            this.style.display = 'none';
            const placeholder = this.nextElementSibling;
            if (placeholder && placeholder.classList.contains('image-placeholder')) {
                placeholder.style.display = 'flex';
            }
        });
    });

    // Mobile menu toggle (if needed in future)
    const mobileMenuButton = document.getElementById('mobile-menu-button');
    if (mobileMenuButton) {
        mobileMenuButton.addEventListener('click', function() {
            const nav = document.querySelector('nav');
            nav.classList.toggle('active');
        });
    }
});

// Phone number formatting
function formatPhoneNumber(input) {
    let phone = input.value.replace(/\D/g, '');

    // Format as +972-XX-XXX-XXXX
    if (phone.startsWith('972')) {
        phone = phone.substring(3);
    } else if (phone.startsWith('0')) {
        phone = phone.substring(1);
    }

    if (phone.length >= 2) {
        phone = '+972-' + phone.substring(0, 2) +
                (phone.length > 2 ? '-' + phone.substring(2, 5) : '') +
                (phone.length > 5 ? '-' + phone.substring(5, 9) : '');
    } else if (phone.length > 0) {
        phone = '+972-' + phone;
    }

    input.value = phone;
}

// Auto-format phone inputs
document.addEventListener('DOMContentLoaded', function() {
    const phoneInputs = document.querySelectorAll('input[type="tel"]');
    phoneInputs.forEach(input => {
        input.addEventListener('input', function() {
            formatPhoneNumber(this);
        });
    });
});

// Form validation helper
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

function validatePhone(phone) {
    const cleaned = phone.replace(/\D/g, '');
    return cleaned.length >= 9 && cleaned.length <= 13;
}

// Show notification (toast)
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'error' ? 'var(--danger)' : type === 'success' ? 'var(--success)' : 'var(--primary)'};
        color: white;
        border-radius: 0.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 9999;
        animation: slideIn 0.3s ease;
    `;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add animations CSS
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }

    .loading-spinner {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 3px solid rgba(255,255,255,.3);
        border-radius: 50%;
        border-top-color: #fff;
        animation: spin 1s ease-in-out infinite;
    }

    @keyframes spin {
        to { transform: rotate(360deg); }
    }
`;
document.head.appendChild(style);

// Image gallery/lightbox (simple version)
function initImageGallery() {
    const images = document.querySelectorAll('[data-gallery]');

    images.forEach(img => {
        img.style.cursor = 'pointer';
        img.addEventListener('click', function() {
            const overlay = document.createElement('div');
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.9);
                z-index: 10000;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
            `;

            const largeImg = document.createElement('img');
            largeImg.src = this.src;
            largeImg.style.cssText = `
                max-width: 90%;
                max-height: 90%;
                object-fit: contain;
            `;

            overlay.appendChild(largeImg);
            document.body.appendChild(overlay);

            overlay.addEventListener('click', () => overlay.remove());
        });
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initImageGallery);

// Countdown timer for events (if needed)
function updateCountdown(eventDate, elementId) {
    const countdownElement = document.getElementById(elementId);
    if (!countdownElement) return;

    const eventTime = new Date(eventDate).getTime();

    const updateTimer = () => {
        const now = new Date().getTime();
        const distance = eventTime - now;

        if (distance < 0) {
            countdownElement.textContent = 'Событие началось!';
            return;
        }

        const days = Math.floor(distance / (1000 * 60 * 60 * 24));
        const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));

        countdownElement.textContent = `${days}д ${hours}ч ${minutes}м`;
    };

    updateTimer();
    setInterval(updateTimer, 60000); // Update every minute
}

// Add to calendar functionality
function addToCalendar(event) {
    const startDate = new Date(event.date);
    const endDate = new Date(startDate.getTime() + 3 * 60 * 60 * 1000); // +3 hours default

    const formatDateForCalendar = (date) => {
        return date.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
    };

    const calendarUrl = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(event.title)}&dates=${formatDateForCalendar(startDate)}/${formatDateForCalendar(endDate)}&details=${encodeURIComponent(event.description)}&location=${encodeURIComponent(event.location_name || '')}`;

    window.open(calendarUrl, '_blank');
}

// Share functionality
async function shareEvent(event) {
    const shareData = {
        title: event.title,
        text: event.description,
        url: window.location.href
    };

    try {
        if (navigator.share) {
            await navigator.share(shareData);
        } else {
            // Fallback: copy to clipboard
            await navigator.clipboard.writeText(window.location.href);
            showNotification('Ссылка скопирована в буфер обмена', 'success');
        }
    } catch (err) {
        console.error('Error sharing:', err);
    }
}

// Export for use in templates
window.YallaBalagan = {
    formatDate,
    formatTime,
    validateEmail,
    validatePhone,
    showNotification,
    updateCountdown,
    addToCalendar,
    shareEvent
};
