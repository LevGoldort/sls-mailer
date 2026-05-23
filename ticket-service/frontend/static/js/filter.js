/**
 * Tag filter for event/performer listings.
 * Expects:
 *   - Filter stamps: .yb-stamp[data-tag][data-clickable]
 *   - Cards container: #events-list (or .yb-events-list)
 *   - Each card: [data-tags] = comma-separated tag list
 *   - Container data attrs: data-empty-tag, data-empty-sub (empty state messages)
 */
(function () {
  'use strict';

  function init() {
    const stamps = document.querySelectorAll('.yb-stamp[data-tag][data-clickable]');
    if (!stamps.length) return;

    const list = document.getElementById('events-list') ||
                 document.querySelector('.yb-events-list');
    if (!list) return;

    const cards = Array.from(list.querySelectorAll('[data-tags]'));
    const emptyTagTpl = list.dataset.emptyTag || 'По тегу «{tag}» ничего нет.';
    const emptySub   = list.dataset.emptyTag ? list.dataset.emptyTag : '';

    let emptyEl = null;

    function showEmpty(tag) {
      if (!emptyEl) {
        emptyEl = document.createElement('div');
        emptyEl.className = 'yb-filter-empty';
        emptyEl.style.cssText = 'padding:80px 0;text-align:center;font-family:var(--yb-font-mono);font-size:14px;letter-spacing:.1em;opacity:.6;text-transform:uppercase';
        list.appendChild(emptyEl);
      }
      const msg = emptyTagTpl.replace('{tag}', tag);
      emptyEl.innerHTML = msg + (list.dataset.emptyTag ? '<br><span style="opacity:.7">' + (list.dataset.emptyTag || '') + '</span>' : '');
      emptyEl.hidden = false;
    }

    function hideEmpty() {
      if (emptyEl) emptyEl.hidden = true;
    }

    function filter(activeTag) {
      const isAll = activeTag === 'ВСЕ' || activeTag === 'ALL';
      let visible = 0;

      cards.forEach(function (card) {
        const tags = (card.dataset.tags || '').split(',').map(function (t) { return t.trim().toUpperCase(); });
        const show = isAll || tags.includes(activeTag.toUpperCase());
        card.style.display = show ? '' : 'none';
        if (show) visible++;
      });

      if (visible === 0 && !isAll) {
        showEmpty(activeTag);
      } else {
        hideEmpty();
      }
    }

    function setActive(clickedStamp) {
      stamps.forEach(function (s) {
        s.classList.remove('yb-stamp--active');
        s.setAttribute('aria-pressed', 'false');
      });
      clickedStamp.classList.add('yb-stamp--active');
      clickedStamp.setAttribute('aria-pressed', 'true');
    }

    stamps.forEach(function (stamp) {
      stamp.addEventListener('click', function () {
        var tag = stamp.dataset.tag;
        setActive(stamp);
        filter(tag);
      });

      stamp.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          stamp.click();
        }
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
