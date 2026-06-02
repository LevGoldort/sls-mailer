/* HTML Template slide — renders arbitrary external HTML as a studio slide */

/* ── CSS scoping ── */
function scopeCSS(css, prefix) {
  css = css.replace(/@import\s+[^;]+;/g, '');

  // Preserve @keyframes blocks verbatim (don't scope from/to/etc.)
  const preserved = [];
  css = css.replace(/@keyframes\s+[^{]+\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/g, m => {
    const tok = `/*YBP${preserved.length}*/`;
    preserved.push(m);
    return tok;
  });

  // Scope all remaining selector { declarations } blocks
  // @-rule selectors start with @, so [^{}@] fails on them → left intact
  // Inner rules inside @media ARE matched and scoped correctly
  css = css.replace(/([^{}@][^{}]*)\{([^{}]*)\}/g, (_, selPart, decl) => {
    const sel = selPart.trim();
    if (!sel) return `{${decl}}`;
    const scoped = sel.split(',').map(s => {
      s = s.trim();
      if (!s) return '';
      if (/^(html|body|:root)$/.test(s)) return prefix;
      if (/^(html|body)\s/.test(s)) return prefix + ' ' + s.replace(/^(?:html|body)\s+/, '');
      return prefix + ' ' + s;
    }).filter(Boolean).join(', ');
    return `${scoped} {${decl}}`;
  });

  preserved.forEach((block, i) => { css = css.replace(`/*YBP${i}*/`, block); });
  return css;
}

/* Inject template CSS and Google Font links into document <head> once per template */
function injectTemplateStyles(tpl) {
  if (document.getElementById('yb-tpl-css-' + tpl.id)) return;

  const parser = new DOMParser();
  const doc = parser.parseFromString(tpl.html, 'text/html');
  const rawCSS = Array.from(doc.querySelectorAll('style')).map(s => s.textContent).join('\n');

  // Inject Google Fonts @import as <link crossorigin> (required for html-to-image)
  const urlImports = [...rawCSS.matchAll(/@import\s+url\(['"]?([^'")\s]+)['"]?\)[^;]*;/g)];
  const strImports = [...rawCSS.matchAll(/@import\s+['"]([^'"]+)['"]\s*;/g)];
  [...urlImports.map(m => m[1]), ...strImports.map(m => m[1])].forEach(url => {
    if (document.querySelector(`link[href="${url}"]`)) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet'; link.href = url; link.crossOrigin = 'anonymous';
    document.head.appendChild(link);
  });

  const style = document.createElement('style');
  style.id = 'yb-tpl-css-' + tpl.id;
  style.textContent = scopeCSS(rawCSS, '.yb-tpl-' + tpl.id);
  document.head.appendChild(style);
}

/* Parse image slot definitions from template HTML */
function parseTemplateSlots(html) {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  return Array.from(doc.querySelectorAll('[data-yb-image]')).map(el => ({
    name: el.getAttribute('data-yb-image'),
    cropW: parseInt(el.getAttribute('data-yb-crop-w')) || null,
    cropH: parseInt(el.getAttribute('data-yb-crop-h')) || null,
  }));
}

/* Build template variable map from event data */
function buildVars(event) {
  if (!event) return {};
  const d = window.parseDate ? window.parseDate(event.date) : { num: '', monthGen: '' };
  return {
    'event.name':  event.title || '',
    'event.date':  (d.num || '') + ' ' + (d.monthGen || ''),
    'event.time':  event.time || '',
    'event.venue': event.venue || '',
    'event.city':  event.city || '',
    'event.price': event.price ? event.price + '₪' : 'БИЛЕТЫ',
    'event.tags':  (event.tags || []).join(', '),
  };
}

/* Replace {{placeholders}} in HTML string */
function applyTextSubstitutions(html, vars) {
  return html.replace(/\{\{([^}]+)\}\}/g, (_, key) => {
    const val = vars[key.trim()];
    return val != null ? val : '';
  });
}

/* ── HtmlTemplateSlide component ── */
function HtmlTemplateSlide({ ctx }) {
  const { data, dims } = ctx;
  const containerRef = React.useRef(null);

  const tpl = React.useMemo(
    () => (window.__htmlTemplates || []).find(t => t.id === data.templateId),
    [data.templateId]
  );
  const slots = React.useMemo(
    () => tpl ? parseTemplateSlots(tpl.html) : [],
    [tpl?.html]
  );

  // Collect image values as a stable dep string
  const imageVals = slots.map(s => ctx.img(s.name) || '').join('|');

  React.useEffect(() => {
    const el = containerRef.current;
    if (!el || !tpl) return;

    const vars = buildVars(data.event);
    const substituted = applyTextSubstitutions(tpl.html, vars);
    const doc = new DOMParser().parseFromString(substituted, 'text/html');
    doc.querySelectorAll('script').forEach(s => s.remove());
    el.innerHTML = doc.body.innerHTML;

    slots.forEach(slot => {
      const dataUrl = ctx.img(slot.name)
        || (slot.name === 'main' ? data.event?.photo : null)
        || null;
      el.querySelectorAll(`[data-yb-image="${slot.name}"]`).forEach(node => {
        if (dataUrl) {
          node.style.backgroundImage = `url(${dataUrl})`;
          node.style.backgroundSize = 'cover';
          node.style.backgroundPosition = 'center';
        }
        node.style.cursor = 'pointer';
        node.addEventListener('click', (e) => {
          if (node.closest('.st-thumb')) return; // filmstrip — ignore
          e.stopPropagation();
          document.dispatchEvent(new CustomEvent('yb-crop-slot', { detail: { slotName: slot.name } }));
        });
      });
    });
  }, [tpl?.html, data.event?.id, imageVals]);

  if (!tpl) {
    return (
      <div style={{ width: dims.w, height: dims.h, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#1a1410', gap: 20 }}>
        <div style={{ fontFamily: 'var(--f-mono)', color: 'rgba(255,255,255,.3)', fontSize: 18, letterSpacing: '.2em' }}>НЕТ ШАБЛОНА</div>
        <div style={{ fontFamily: 'var(--f-mono)', color: 'rgba(255,255,255,.2)', fontSize: 13, letterSpacing: '.12em' }}>ИМПОРТИРУЙ HTML В ПАНЕЛИ</div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={'yb-tpl-' + tpl.id}
      style={{ width: dims.w, height: dims.h, overflow: 'hidden', position: 'relative' }}
    />
  );
}

Object.assign(window, {
  HtmlTemplateSlide,
  injectTemplateStyles,
  parseTemplateSlots,
  buildVars,
  applyTextSubstitutions,
});
