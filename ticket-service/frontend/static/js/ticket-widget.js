/**
 * Ticket widget interactivity.
 * Wires up quantity controls, total calculation, and buy button state.
 *
 * Expects in the DOM:
 *   .yb-ticket-widget[data-event-id][data-api-url]
 *   .yb-ticket-widget__tier[data-tier-id][data-price]
 *   .yb-qty-dec[data-tier], .yb-qty-inc[data-tier]
 *   .yb-qty-num[data-tier]
 *   #widget-total, #widget-total-label, #widget-buy
 *   #promo-code, #promo-apply
 */
(function () {
  'use strict';

  var TICKETS_RU = ['билет', 'билета', 'билетов'];

  function ruPlural(n, forms) {
    var mod10 = n % 10, mod100 = n % 100;
    if (mod100 >= 11 && mod100 <= 19) return forms[2];
    if (mod10 === 1) return forms[0];
    if (mod10 >= 2 && mod10 <= 4) return forms[1];
    return forms[2];
  }

  function init() {
    var widget = document.querySelector('.yb-ticket-widget[data-event-id]');
    if (!widget) return;

    var tiers = Array.from(widget.querySelectorAll('.yb-ticket-widget__tier[data-tier-id]'));
    if (!tiers.length) return;

    var totalEl = document.getElementById('widget-total');
    var totalLabelEl = document.getElementById('widget-total-label');
    var buyBtn = document.getElementById('widget-buy');

    var qty = {};
    var prices = {};
    var discount = 0;

    tiers.forEach(function (tier) {
      var id = tier.dataset.tierId;
      qty[id] = 0;
      prices[id] = parseFloat(tier.dataset.price) || 0;
    });

    function calcTotal() {
      var totalCount = 0, totalPrice = 0;
      Object.keys(qty).forEach(function (id) {
        totalCount += qty[id];
        totalPrice += qty[id] * prices[id];
      });
      totalPrice = Math.max(0, totalPrice - discount);
      return { count: totalCount, price: totalPrice };
    }

    function update() {
      var t = calcTotal();
      if (totalEl) totalEl.textContent = t.price;
      if (totalLabelEl) {
        totalLabelEl.textContent = 'Итого · ' + t.count + ' ' + ruPlural(t.count, TICKETS_RU);
      }
      if (buyBtn) {
        if (t.count > 0) {
          buyBtn.style.opacity = '1';
          buyBtn.style.pointerEvents = 'auto';
          buyBtn.textContent = '► Купить за ' + t.price + '₪';
        } else {
          buyBtn.style.opacity = '0.5';
          buyBtn.style.pointerEvents = 'none';
          buyBtn.textContent = 'Выбери билет';
        }
      }
    }

    widget.addEventListener('click', function (e) {
      var btn = e.target.closest('.yb-qty-dec, .yb-qty-inc');
      if (!btn) return;

      var tierId = btn.dataset.tier;
      var numEl = widget.querySelector('.yb-qty-num[data-tier="' + tierId + '"]');
      if (!numEl) return;

      var current = qty[tierId] || 0;
      if (btn.classList.contains('yb-qty-inc')) {
        qty[tierId] = current + 1;
      } else {
        qty[tierId] = Math.max(0, current - 1);
      }
      numEl.textContent = qty[tierId];
      update();
    });

    var promoApply = document.getElementById('promo-apply');
    var promoInput = document.getElementById('promo-code');
    if (promoApply && promoInput) {
      promoApply.addEventListener('click', function () {
        var code = promoInput.value.trim().toUpperCase();
        if (!code) return;

        var eventId = widget.dataset.eventId;
        var apiUrl = widget.dataset.apiUrl || '';

        fetch(apiUrl + '/api/coupons/validate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code: code, event_id: eventId }),
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.valid) {
              discount = data.discount_amount || 0;
              promoInput.style.borderColor = 'var(--yb-cyan)';
              update();
            } else {
              promoInput.style.borderColor = 'var(--yb-red)';
            }
          })
          .catch(function () {
            promoInput.style.borderColor = 'var(--yb-red)';
          });
      });
    }

    update();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
