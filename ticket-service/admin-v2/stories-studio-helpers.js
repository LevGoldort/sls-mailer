/* Yalla Balagan Stories Studio — shared primitives & helpers */

const { useState, useEffect, useRef, useCallback } = React;

/* ── Date helpers (Russian) ── */
const RU_DOW   = ['ВС','ПН','ВТ','СР','ЧТ','ПТ','СБ'];
const RU_MON_ABBR = ['ЯНВ','ФЕВ','МАР','АПР','МАЙ','ИЮН','ИЮЛ','АВГ','СЕН','ОКТ','НОЯ','ДЕК'];
const RU_MON_FULL = ['ЯНВАРЬ','ФЕВРАЛЬ','МАРТ','АПРЕЛЬ','МАЙ','ИЮНЬ','ИЮЛЬ','АВГУСТ','СЕНТЯБРЬ','ОКТЯБРЬ','НОЯБРЬ','ДЕКАБРЬ'];
const RU_MON_GEN  = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];

function parseDate(iso) {
  const d = new Date(iso + 'T00:00:00');
  return {
    d,
    num: String(d.getDate()).padStart(2, '0'),
    day: d.getDate(),
    monthIdx: d.getMonth(),
    monthAbbr: RU_MON_ABBR[d.getMonth()],
    monthFull: RU_MON_FULL[d.getMonth()],
    monthGen: RU_MON_GEN[d.getMonth()],
    dow: RU_DOW[d.getDay()],
    year: String(d.getFullYear()),
  };
}

function dateRangeLabel(isoList) {
  if (!isoList || !isoList.length) return '';
  const ds = isoList.map(parseDate).sort((a, b) => a.d - b.d);
  const a = ds[0], b = ds[ds.length - 1];
  if (a.monthIdx === b.monthIdx) return `${a.day} — ${b.day} ${a.monthGen}`;
  return `${a.day} ${a.monthGen} — ${b.day} ${b.monthGen}`;
}

/* ── Layer helpers ── */
function Grain({ on = true }) {
  if (!on) return null;
  return <div className="s-grain" style={{ pointerEvents: 'none' }} aria-hidden="true" />;
}
function Halftone({ on = true, corner = false, style }) {
  if (!on) return null;
  return <div className={'s-halftone' + (corner ? ' s-halftone--corner' : '')} style={{ pointerEvents: 'none', ...style }} aria-hidden="true" />;
}
function Tape({ on = true, color = 'cyan', style }) {
  if (!on) return null;
  return <div className={'s-tape s-tape--' + color} style={{ pointerEvents: 'none', ...style }} aria-hidden="true" />;
}

/* ── Editable text ── */
function EditableText({ value, onCommit, as = 'span', className, style, single = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (el && document.activeElement !== el && el.textContent !== value) {
      el.textContent = value;
    }
  }, [value]);
  const Tag = as;
  return (
    <Tag
      ref={ref}
      className={className}
      style={style}
      data-edit
      contentEditable
      suppressContentEditableWarning
      spellCheck={false}
      onKeyDown={(e) => {
        if (single && e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur(); }
      }}
      onBlur={(e) => {
        const txt = e.currentTarget.textContent;
        if (txt !== value) onCommit(txt);
      }}
    >
      {value}
    </Tag>
  );
}

/* ── Riso offset display text ── */
function RisoText({ value, onCommit, shadowColor = 'var(--magenta)', className, style }) {
  return (
    <span className={'s-riso ' + (className || '')} style={style}>
      <span className="s-riso__shadow" style={{ color: shadowColor }} aria-hidden="true">{value}</span>
      <EditableText value={value} onCommit={onCommit} />
    </span>
  );
}

/* ── Image slot (click / drop to fill; supports crop modal) ── */
function ImageSlot({ value, onChange, label = 'ФОТО', className, style, round = false, cropW, cropH }) {
  const inputRef = useRef(null);
  const [hovered, setHovered] = useState(false);
  const originalRef = useRef(null); // исходный файл/URL до кропа, не перезаписывается после кропа

  useEffect(() => {
    if (value && value.startsWith('http')) {
      originalRef.current = { type: 'url', src: value };
    }
  }, [value]);

  const _openCropModal = (file) => {
    new Promise(resolve => window.showCropModal(file, cropW, cropH, 0.9, resolve))
      .then(blob => {
        const r = new FileReader();
        r.onload = () => onChange(r.result);
        r.readAsDataURL(blob);
      });
  };

  const applyFile = (file) => {
    if (!file || !file.type.startsWith('image/')) return;
    originalRef.current = { type: 'file', file }; // новая загрузка = новый оригинал
    if (cropW && cropH && window.showCropModal) {
      _openCropModal(file);
    } else {
      const r = new FileReader();
      r.onload = () => onChange(r.result);
      r.readAsDataURL(file);
    }
  };

  const doCrop = () => {
    if (!cropW || !cropH || !window.showCropModal) return;
    const orig = originalRef.current;
    if (orig?.type === 'file' && orig.file) {
      _openCropModal(orig.file);
      return;
    }
    const src = orig?.src || value;
    if (!src) return;
    const opts = src.startsWith('http') ? { mode: 'cors' } : {};
    fetch(src, opts)
      .then(r => r.blob())
      .then(blob => _openCropModal(new File([blob], 'image.jpg', { type: blob.type || 'image/jpeg' })))
      .catch(() => inputRef.current && inputRef.current.click());
  };

  const BTN = { fontFamily: 'var(--f-mono)', color: 'var(--paper)', fontSize: 15, letterSpacing: '.1em',
    background: 'rgba(255,255,255,.18)', border: '2px solid rgba(255,255,255,.6)',
    padding: '8px 16px', cursor: 'pointer', pointerEvents: 'all' };

  return (
    <div
      className={'s-img ' + (className || '')}
      style={{ position: 'relative', overflow: 'hidden', borderRadius: round ? '50%' : 0, cursor: 'pointer', ...style }}
      onClick={() => inputRef.current && inputRef.current.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => { e.preventDefault(); applyFile(e.dataTransfer.files[0]); }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {value ? (
        <>
          <img src={value} alt={label}
            crossOrigin={value && value.includes('amazonaws.com') ? 'anonymous' : undefined}
            onError={() => { if (value && value.startsWith('data:')) onChange(null); }}
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', pointerEvents: 'none' }} />
          {hovered && (
            <div style={{ position: 'absolute', inset: 0, background: 'rgba(26,20,16,.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, zIndex: 10 }}>
              {cropW && cropH && (
                <button style={BTN} onClick={(e) => { e.stopPropagation(); doCrop(); }}>✂ КРОП</button>
              )}
              <button style={BTN} onClick={(e) => { e.stopPropagation(); inputRef.current && inputRef.current.click(); }}>✏ ЗАМЕНИТЬ</button>
            </div>
          )}
        </>
      ) : (
        <div className="s-img__ph">
          <div className="s-img__ph-icon" aria-hidden="true">✦</div>
          <div className="s-img__ph-label">{label}</div>
          <div className="s-img__ph-hint">КЛИК / ПЕРЕТАЩИ ФОТО</div>
        </div>
      )}
      <input ref={inputRef} type="file" accept="image/*" hidden
        onChange={(e) => applyFile(e.target.files[0])} />
    </div>
  );
}

/* ── Brand chrome ── */
function BrandBox({ short }) {
  const S = window.YB_DATA.site;
  return <div className="s-brand__box">{short || S.short}</div>;
}
function BrandLockup({ on = true }) {
  const S = window.YB_DATA.site;
  if (!on) return null;
  return (
    <div className="s-brand">
      <BrandBox />
      <div>
        <div className="s-brand__name">{S.name}</div>
        <div className="s-brand__cities">{S.cities}</div>
      </div>
    </div>
  );
}
function FooterChrome({ layers }) {
  const S = window.YB_DATA.site;
  if (!layers) return null;
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 18 }}>
      <span className="s-handle">{S.handle}</span>
      <span className="s-handle" style={{ opacity: .6 }}>{S.url}</span>
    </div>
  );
}
function SwipeHint({ label = 'СВАЙПНИ ↑' }) {
  return <span className="s-swipe">{label}</span>;
}
function StubMeta({ index, dateStr }) {
  return (
    <div className="s-stub__meta">
      <span>№{String(index).padStart(3, '0')} · {dateStr}</span>
      <span>STUB</span>
    </div>
  );
}

Object.assign(window, {
  parseDate, dateRangeLabel,
  Grain, Halftone, Tape, EditableText, RisoText, ImageSlot,
  BrandBox, BrandLockup, FooterChrome, SwipeHint, StubMeta,
});
