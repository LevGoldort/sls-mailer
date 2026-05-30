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
  return <div className="s-grain" aria-hidden="true" />;
}
function Halftone({ on = true, corner = false, style }) {
  if (!on) return null;
  return <div className={'s-halftone' + (corner ? ' s-halftone--corner' : '')} style={style} aria-hidden="true" />;
}
function Tape({ on = true, color = 'cyan', style }) {
  if (!on) return null;
  return <div className={'s-tape s-tape--' + color} style={style} aria-hidden="true" />;
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

/* ── Image slot (click / drop to fill; value is a data URL) ── */
function ImageSlot({ value, onChange, label = 'ФОТО', className, style, round = false }) {
  const inputRef = useRef(null);
  const read = (file) => {
    if (!file || !file.type.startsWith('image/')) return;
    const r = new FileReader();
    r.onload = () => onChange(r.result);
    r.readAsDataURL(file);
  };
  return (
    <div
      className={'s-img ' + (className || '')}
      style={{ borderRadius: round ? '50%' : 0, ...style }}
      onClick={() => inputRef.current && inputRef.current.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => { e.preventDefault(); read(e.dataTransfer.files[0]); }}
    >
      {value
        ? <img src={value} alt={label} />
        : (
          <div className="s-img__ph">
            <div className="s-img__ph-icon" aria-hidden="true">✦</div>
            <div className="s-img__ph-label">{label}</div>
            <div className="s-img__ph-hint">КЛИК / ПЕРЕТАЩИ ФОТО</div>
          </div>
        )}
      <input ref={inputRef} type="file" accept="image/*" hidden
        onChange={(e) => read(e.target.files[0])} />
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
