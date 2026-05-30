/* Yalla Balagan — STORIES STUDIO app shell */
const { useState, useEffect, useRef, useMemo, useCallback } = React;

const LAYER_LABELS = { grain: 'Зерно', halftone: 'Полутон', tape: 'Скотч', stamps: 'Штампы / лого' };
const STORE_KEY = 'yb-studio-edits-v2';

function loadEdits() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {}; } catch { return {}; }
}
function sanitize(s) {
  return (s || '').toString().toLowerCase().replace(/[^a-zа-я0-9]+/gi, '-').replace(/^-+|-+$/g, '').slice(0, 24);
}

/* ── Loading screen ── */
function LoadingScreen({ error }) {
  return (
    <div className="st-loading">
      <div className="st-logo">
        <div className="st-logo__box">ЯБ</div>
        <div className="st-logo__txt">STORIES STUDIO<small>ГЕНЕРАТОР · ИНСТАГРАМ</small></div>
      </div>
      {error
        ? <div className="st-loading__error">Ошибка загрузки данных:<br />{error}</div>
        : <div className="st-loading__sub">Загрузка данных...</div>}
    </div>
  );
}

/* ── Event filter bar (weekly recipe only) ── */
function EventFilterBar({ allEvents, dateFrom, dateTo, excludedIds, onDateFrom, onDateTo, onToggle }) {
  const visible = allEvents.filter(ev =>
    (!dateFrom || ev.date >= dateFrom) && (!dateTo || ev.date <= dateTo)
  );
  return (
    <div className="st-filter-bar">
      <span className="st-filter-bar__label">Период</span>
      <div className="st-filter-bar__dates">
        <input type="date" className="st-date-input" value={dateFrom} onChange={e => onDateFrom(e.target.value)} />
        <span className="st-filter-bar__sep">—</span>
        <input type="date" className="st-date-input" value={dateTo} onChange={e => onDateTo(e.target.value)} />
      </div>
      <span className="st-filter-bar__label">События</span>
      <div className="st-filter-bar__events">
        {visible.length === 0 && <span style={{ fontSize: 10, color: 'var(--st-dim)', letterSpacing: '.1em' }}>НЕТ СОБЫТИЙ В ЭТОМ ПЕРИОДЕ</span>}
        {visible.map(ev => {
          const isOn = !excludedIds.has(ev.id);
          const d = window.parseDate(ev.date);
          return (
            <button key={ev.id} className={'st-event-chip ' + (isOn ? 'is-on' : 'is-off')} onClick={() => onToggle(ev.id)}>
              <span className="st-event-chip__dot" />
              {d.num}.{d.monthAbbr} {ev.title.slice(0, 22)}{ev.title.length > 22 ? '…' : ''}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── Main Studio ── */
function Studio() {
  const [ybData,    setYbData]    = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [recipeId,  setRecipeId]  = useState('weekly');
  const [subjects,  setSubjects]  = useState({ performer: null, event: null, episode: null, product: null });
  const [format,    setFormat]    = useState('story');
  const [active,    setActive]    = useState(0);
  const [edits,     setEdits]     = useState(loadEdits);
  const [toast,     setToast]     = useState(null);
  const [busy,      setBusy]      = useState(null);
  const [scale,     setScale]     = useState(0.3);

  /* weekly recipe filters */
  const today     = new Date().toISOString().slice(0, 10);
  const twoWeeks  = new Date(Date.now() + 14 * 24 * 3600 * 1000).toISOString().slice(0, 10);
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo,   setDateTo]   = useState(twoWeeks);
  const [excludedEventIds, setExcludedEventIds] = useState(new Set());

  const stageRef    = useRef(null);
  const captureRefs = useRef({});

  /* load data from real API */
  useEffect(() => {
    window.loadYBData().then(data => {
      window.YB_DATA = data;
      setYbData(data);
      setSubjects({
        performer: data.performers[0]?.id || null,
        event:     data.events[0]?.id     || null,
        episode:   data.episodes[0]?.id   || null,
        product:   data.merch[0]?.id      || null,
      });
    }).catch(e => setLoadError(e.message || String(e)));
  }, []);

  useEffect(() => {
    if (edits) localStorage.setItem(STORE_KEY, JSON.stringify(edits));
  }, [edits]);

  /* filtered events for weekly recipe */
  const filteredEvents = useMemo(() => {
    if (!ybData) return [];
    return ybData.events.filter(ev => {
      if (excludedEventIds.has(ev.id)) return false;
      if (dateFrom && ev.date < dateFrom) return false;
      if (dateTo   && ev.date > dateTo)   return false;
      return true;
    });
  }, [ybData, dateFrom, dateTo, excludedEventIds]);

  const recipe    = useMemo(() => window.RECIPES?.find(r => r.id === recipeId), [recipeId]);
  const subjectId = recipe?.subjectKind === 'none' ? null : subjects[recipe?.subjectKind];
  const dims      = window.FORMATS?.[format];

  const slides = useMemo(() => {
    if (!ybData || !recipe || !window.YB_DATA) return [];
    const saved = window.YB_DATA.events;
    if (recipeId === 'weekly') window.YB_DATA.events = filteredEvents;
    const result = recipe.build(subjectId);
    window.YB_DATA.events = saved;
    return result;
  }, [recipeId, subjectId, ybData, filteredEvents]);

  /* fit-to-stage scaling */
  useEffect(() => {
    const el = stageRef.current;
    if (!el || !dims) return;
    let raf = 0;
    const compute = () => {
      const pad = 72;
      const w = el.clientWidth - pad, h = el.clientHeight - pad;
      if (w <= 0 || h <= 0) return;
      setScale(Math.max(0.12, Math.min(w / dims.w, h / dims.h)));
    };
    const schedule = () => { compute(); clearTimeout(raf); raf = setTimeout(compute, 60); };
    schedule();
    const t = setTimeout(schedule, 300);
    const ro = new ResizeObserver(schedule); ro.observe(el);
    window.addEventListener('resize', schedule);
    return () => { ro.disconnect(); window.removeEventListener('resize', schedule); clearTimeout(raf); clearTimeout(t); };
  }, [dims?.w, dims?.h]);

  /* keyboard nav */
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.isContentEditable || /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
      if (e.key === 'ArrowRight') setActive(a => Math.min(a + 1, slides.length - 1));
      if (e.key === 'ArrowLeft')  setActive(a => Math.max(a - 1, 0));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [slides.length]);

  useEffect(() => { if (active >= slides.length && slides.length > 0) setActive(0); }, [slides.length]);

  /* edit ops */
  const patch = useCallback((key, fn) => {
    setEdits(prev => { const cur = prev[key] || {}; return { ...prev, [key]: fn(cur) }; });
  }, []);
  const updateField = (key, f, v) => patch(key, c => ({ ...c, fields:  { ...(c.fields  || {}), [f]: v } }));
  const updateImage = (key, f, v) => patch(key, c => ({ ...c, images:  { ...(c.images  || {}), [f]: v } }));
  const setVariant  = (key, v)    => patch(key, c => ({ ...c, variant: v }));
  const setLayer    = (key, l, on)=> patch(key, c => ({ ...c, layers:  { ...(c.layers  || {}), [l]: on } }));
  const resetSlide  = (key)       => setEdits(p => { const n = { ...p }; delete n[key]; return n; });

  const makeCtx = useCallback((slide) => {
    const st = edits[slide.key] || {};
    return {
      f: format, dims, accent: slide.accent,
      variant: st.variant || 0,
      layers: { grain: true, halftone: true, tape: true, stamps: true, ...(st.layers || {}) },
      data: slide.data,
      rootStyle: { width: dims.w, height: dims.h },
      T:      (k, def)  => (st.fields && st.fields[k] != null) ? st.fields[k] : def,
      set:    (k, v)    => updateField(slide.key, k, v),
      img:    (k)       => st.images && st.images[k],
      setImg: (k, v)    => updateImage(slide.key, k, v),
    };
  }, [edits, format, dims]);

  /* capture / export: toSvg → canvas → PNG */
  const captureSlide = async (i) => {
    const node = captureRefs.current[i];
    if (!node) throw new Error('no capture node ' + i);
    await document.fonts.ready;
    const dataUri = await window.htmlToImage.toSvg(node, { width: dims.w, height: dims.h, backgroundColor: '#f3eee1' });
    const img = new Image();
    await new Promise((res, rej) => { img.onload = res; img.onerror = () => rej(new Error('svg load failed')); img.src = dataUri; });
    const c = document.createElement('canvas');
    c.width = dims.w; c.height = dims.h;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#f3eee1'; ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL('image/jpeg', 0.92);
  };

  const flash = (m) => { setToast(m); setTimeout(() => setToast(null), 2400); };

  const downloadOne = async (i) => {
    try {
      setBusy({ done: 0, total: 1 });
      const url = await captureSlide(i);
      const a = document.createElement('a');
      a.href = url;
      a.download = `yb-${recipeId}-${format}-${String(i + 1).padStart(2, '0')}-${sanitize(slides[i].label)}.jpg`;
      a.click();
      setBusy(null); flash('PNG скачан');
    } catch (e) { setBusy(null); flash('Ошибка экспорта'); console.error(e); }
  };

  const downloadAll = async () => {
    try {
      setBusy({ done: 0, total: slides.length });
      const zip = new JSZip();
      for (let i = 0; i < slides.length; i++) {
        const url = await captureSlide(i);
        zip.file(
          `yb-${recipeId}-${format}-${String(i + 1).padStart(2, '0')}-${sanitize(slides[i].label)}.jpg`,
          url.split(',')[1], { base64: true }
        );
        setBusy({ done: i + 1, total: slides.length });
      }
      const blob = await zip.generateAsync({ type: 'blob' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `yallabalagan-${recipeId}-${format}.zip`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      setBusy(null); flash(slides.length + ' слайдов в архиве');
    } catch (e) { setBusy(null); flash('Ошибка экспорта'); console.error(e); }
  };

  /* event exclusion toggle */
  const toggleEvent = useCallback((id) => {
    setExcludedEventIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  /* loading / error states */
  if (!ybData) return <LoadingScreen error={loadError} />;

  const activeSlide = slides[Math.min(active, Math.max(0, slides.length - 1))];
  if (!activeSlide) return <LoadingScreen error="Нет слайдов для этого рецепта" />;

  const activeComp   = window.SLIDE_TYPES[activeSlide.type].Comp;
  const activeSt     = edits[activeSlide.key] || {};
  const activeLayers = { grain: true, halftone: true, tape: true, stamps: true, ...(activeSt.layers || {}) };

  const renderSlide = (slide) => {
    const { Comp } = window.SLIDE_TYPES[slide.type];
    return <Comp ctx={makeCtx(slide)} />;
  };

  const subjOpts = window.subjectOptions(recipe.subjectKind);
  const showFilterBar = recipeId === 'weekly';

  return (
    <div className="st-app editing">

      {/* TOP BAR */}
      <div className="st-top">
        <div className="st-logo">
          <div className="st-logo__box">ЯБ</div>
          <div className="st-logo__txt">STORIES STUDIO<small>ГЕНЕРАТОР · ИНСТАГРАМ</small></div>
        </div>
        <div className="st-recipes">
          {window.RECIPES.map(r => (
            <button key={r.id} className={'st-recipe-tab' + (r.id === recipeId ? ' is-active' : '')}
              onClick={() => { setRecipeId(r.id); setActive(0); }}>
              <span className="ico">{r.ico}</span>{r.label}
            </button>
          ))}
        </div>
        <div className="st-top__spacer" />
        {recipe.subjectKind !== 'none' && (
          <select className="st-select" value={subjectId || ''}
            onChange={e => { setSubjects(s => ({ ...s, [recipe.subjectKind]: e.target.value })); setActive(0); }}>
            {subjOpts.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        )}
        <div className="st-seg">
          {Object.keys(window.FORMATS).map(fk => (
            <button key={fk} className={format === fk ? 'is-active' : ''} onClick={() => setFormat(fk)}>
              {window.FORMATS[fk].label}
            </button>
          ))}
        </div>
        <button className="st-btn" onClick={downloadAll} disabled={!!busy}>↓ ВСЁ ({slides.length})</button>
      </div>

      {/* WEEKLY FILTER BAR */}
      {showFilterBar && (
        <EventFilterBar
          allEvents={ybData.events}
          dateFrom={dateFrom} dateTo={dateTo}
          excludedIds={excludedEventIds}
          onDateFrom={setDateFrom} onDateTo={setDateTo}
          onToggle={toggleEvent}
        />
      )}

      {/* BODY */}
      <div className="st-body">

        {/* FILMSTRIP */}
        <div className="st-strip">
          <div className="st-strip__head"><span>СЛАЙДЫ</span><span>{slides.length}</span></div>
          {slides.map((slide, i) => {
            const thumbScale = 196 / dims.w;
            return (
              <button key={slide.key} className={'st-thumb' + (i === active ? ' is-active' : '')} onClick={() => setActive(i)}>
                <span className="st-thumb__n">{String(i + 1).padStart(2, '0')}</span>
                <div className="st-thumb__wrap" style={{ width: '100%', height: dims.h * thumbScale }}>
                  <div style={{ width: dims.w, height: dims.h, transform: `scale(${thumbScale})`, transformOrigin: 'top left' }}>
                    {renderSlide(slide)}
                  </div>
                </div>
                <div className="st-thumb__label">{window.SLIDE_TYPES[slide.type].label} · {slide.label}</div>
              </button>
            );
          })}
        </div>

        {/* STAGE */}
        <div className="st-stage" ref={stageRef}>
          <div className="st-stage__hint">КЛИК ПО ТЕКСТУ — РЕДАКТИРОВАТЬ · ПЕРЕТАЩИ ФОТО НА ПЛЕЙСХОЛДЕР</div>
          <button className="st-nav st-nav--prev" onClick={() => setActive(a => Math.max(a - 1, 0))} disabled={active === 0}>←</button>
          <div className="st-slide-mount" style={{ width: dims.w * scale, height: dims.h * scale }}>
            <div style={{ width: dims.w, height: dims.h, transform: `scale(${scale})`, transformOrigin: 'top left' }}>
              {renderSlide(activeSlide)}
            </div>
          </div>
          <button className="st-nav st-nav--next" onClick={() => setActive(a => Math.min(a + 1, slides.length - 1))} disabled={active === slides.length - 1}>→</button>
        </div>

        {/* INSPECTOR */}
        <div className="st-insp">
          <div className="st-insp__title">{window.SLIDE_TYPES[activeSlide.type].label}</div>
          <div className="st-insp__sub">Слайд {active + 1} / {slides.length} · {dims.label}</div>

          {activeComp.variants && activeComp.variants.length > 1 && (
            <div className="st-section">
              <div className="st-section__h">Раскладка</div>
              <div className="st-chips">
                {activeComp.variants.map((v, vi) => (
                  <button key={vi} className={'st-chip' + ((activeSt.variant || 0) === vi ? ' is-active' : '')}
                    onClick={() => setVariant(activeSlide.key, vi)}>{v}</button>
                ))}
              </div>
            </div>
          )}

          <div className="st-section">
            <div className="st-section__h">Слои</div>
            {(activeComp.layers || []).map(l => (
              <div key={l} className="st-toggle" onClick={() => setLayer(activeSlide.key, l, !activeLayers[l])}>
                <span>{LAYER_LABELS[l] || l}</span>
                <span className={'st-switch' + (activeLayers[l] ? ' on' : '')} />
              </div>
            ))}
          </div>

          <div className="st-section">
            <div className="st-section__h">Экспорт</div>
            <div className="st-dl-row">
              <button className="st-btn" onClick={() => downloadOne(active)} disabled={!!busy}>↓ ЭТОТ СЛАЙД</button>
              <button className="st-btn st-btn--ghost" onClick={downloadAll} disabled={!!busy}>↓ ВСЯ СЕРИЯ (.zip)</button>
              <button className="st-btn st-btn--ghost" onClick={() => resetSlide(activeSlide.key)}>⟲ СБРОСИТЬ СЛАЙД</button>
            </div>
          </div>

          <div className="st-section">
            <div className="st-section__h">Подсказка</div>
            <div className="st-note">
              <b>Текст</b> — кликни и печатай. <b>Фото</b> — перетащи на плейсхолдер. Раскладку и слои меняй выше. Экспорт — ровно <b>{dims.w}×{dims.h}</b>px.
            </div>
          </div>
        </div>
      </div>

      {/* HIDDEN FULL-SIZE CAPTURE COLUMN */}
      <div aria-hidden="true" inert="" style={{ position: 'fixed', left: -100000, top: 0, pointerEvents: 'none' }}>
        {slides.map((slide, i) => (
          <div key={slide.key + format} ref={el => { captureRefs.current[i] = el; }} style={{ width: dims.w, height: dims.h }}>
            {renderSlide(slide)}
          </div>
        ))}
      </div>

      {toast && <div className="st-toast">{toast}</div>}
      {busy && (
        <div className="st-busy">
          <div className="st-busy__txt">РЕНДЕРЮ {busy.done} / {busy.total}</div>
          <div className="st-busy__bar"><div className="st-busy__fill" style={{ width: (busy.total ? busy.done / busy.total * 100 : 0) + '%' }} /></div>
        </div>
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<Studio />);
