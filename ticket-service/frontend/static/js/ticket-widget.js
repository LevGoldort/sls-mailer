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
    var couponType = null;   // 'percentage' or 'fixed_amount', null when no coupon
    var couponValue = 0;
    var autoDiscounts = widget.dataset.autoDiscounts === 'true';

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

      // Recalculate coupon discount dynamically — mirrors server-side logic
      var couponDiscount = 0;
      if (couponType === 'percentage') {
        couponDiscount = Math.round(totalPrice * (couponValue / 100) * 100) / 100;
      } else if (couponType === 'fixed_amount') {
        couponDiscount = Math.min(couponValue * totalCount, totalPrice);
      }
      totalPrice = Math.max(0, totalPrice - couponDiscount);

      var autoDiscountPct = 0;
      if (autoDiscounts && couponType === null) {
        if (totalCount >= 5) autoDiscountPct = 0.15;
        else if (totalCount >= 3) autoDiscountPct = 0.10;
      }
      var autoDiscountAmt = Math.round(totalPrice * autoDiscountPct * 100) / 100;

      return { count: totalCount, price: Math.round((totalPrice - autoDiscountAmt) * 100) / 100, autoDiscountPct: autoDiscountPct };
    }

    var discountInfoEl = widget.querySelector('.yb-ticket-widget__discount-info');

    function update() {
      var t = calcTotal();
      if (totalEl) totalEl.textContent = t.price;
      if (totalLabelEl) {
        var label = 'Итого · ' + t.count + ' ' + ruPlural(t.count, TICKETS_RU);
        if (t.autoDiscountPct > 0) label += ' (−' + (t.autoDiscountPct * 100) + '%)';
        totalLabelEl.textContent = label;
      }
      if (discountInfoEl) discountInfoEl.style.display = couponType !== null ? 'none' : '';
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

    if (buyBtn) {
      buyBtn.addEventListener('click', function (e) {
        var t = calcTotal();
        if (t.count === 0) { e.preventDefault(); return; }

        var tickets = [];
        Object.keys(qty).forEach(function (id) {
          if (qty[id] > 0) tickets.push({ type_id: id, quantity: qty[id] });
        });

        var orderData = {
          event_id: widget.dataset.eventId,
          tickets: tickets,
        };
        if (promoInput && promoInput.value.trim()) {
          orderData.coupon_code = promoInput.value.trim().toUpperCase();
        }

        try { sessionStorage.setItem('orderData', JSON.stringify(orderData)); } catch (_) {}

        e.preventDefault();
        window.location.href = '/checkout.html?event_id=' + widget.dataset.eventId + '&seated=true';
      });
    }

    var promoApply = document.getElementById('promo-apply');
    var promoInput = document.getElementById('promo-code');
    var promoMsg = document.getElementById('promo-message');

    function showPromoMsg(text, isError) {
      if (!promoMsg) return;
      promoMsg.textContent = text;
      promoMsg.style.color = isError ? 'var(--yb-red)' : 'var(--yb-cyan)';
      promoMsg.style.display = 'block';
    }

    if (promoApply && promoInput) {
      promoApply.addEventListener('click', function () {
        var code = promoInput.value.trim().toUpperCase();
        if (!code) return;

        var eventId = widget.dataset.eventId;
        var apiUrl = widget.dataset.apiUrl || '';
        var t = calcTotal();

        fetch(apiUrl + '/api/coupons/validate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            coupon_code: code,
            event_id: eventId,
            amount: t.price,
            ticket_quantity: t.count || 1,
          }),
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.valid) {
              couponType  = data.coupon.discount_type;
              couponValue = data.coupon.discount_value;
              promoInput.style.borderColor = 'var(--yb-cyan)';
              showPromoMsg('✓ ' + (data.discount_description || 'Промокод применён'), false);
              update();
            } else {
              promoInput.style.borderColor = 'var(--yb-red)';
              showPromoMsg(data.message || 'Промокод не найден', true);
            }
          })
          .catch(function () {
            promoInput.style.borderColor = 'var(--yb-red)';
            showPromoMsg('Ошибка при проверке промокода', true);
          });
      });
    }

    // Pre-fill and auto-apply promo code from URL ?c=CODE (influencer deep links)
    var urlCode = new URLSearchParams(window.location.search).get('c');
    if (urlCode && promoInput) {
      promoInput.value = urlCode.toUpperCase();
      if (promoApply) {
        promoApply.click();
      } else if (promoMsg) {
        promoMsg.textContent = 'Промокод из ссылки — нажми «Применить» для расчёта скидки';
        promoMsg.style.color = 'var(--yb-ink, #333)';
        promoMsg.style.display = 'block';
      }
    }

    update();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
