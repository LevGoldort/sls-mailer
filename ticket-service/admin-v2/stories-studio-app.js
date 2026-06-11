/* Yalla Balagan — STORIES STUDIO app shell */
const { useState, useEffect, useRef, useMemo, useCallback } = React;

const LAYER_LABELS = { grain: 'Зерно', halftone: 'Полутон', tape: 'Скотч', stamps: 'Штампы / лого' };
const STORE_KEY = 'yb-studio-edits-v2';

const DEFAULT_LAYERS = { grain: true, halftone: true, tape: true, stamps: true };
const DEFAULT_FLAGS = {
  show_footer_chrome: true, show_brand_lockup: true, show_swipe_hint: true,
  show_ticker: true, show_tags: true, show_date_stamp: true,
  show_price: true, show_venue: true, show_bottom_bar: true, show_city: true,
};

function loadEdits() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {}; } catch { return {}; }
}
function sanitize(s) {
  return (s || '').toString().toLowerCase().replace(/[^a-zа-я0-9]+/gi, '-').replace(/^-+|-+$/g, '').slice(0, 24);
}

/* ── Templates Panel ── */
function TemplatesPanel({ templates, activeId, onActivate, onDelete, onImport }) {
  const [showImport, setShowImport] = React.useState(false);
  const [name, setName] = React.useState('');
  const [html, setHtml] = React.useState('');
  const [err, setErr] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const handleImport = async () => {
    setErr('');
    if (!name.trim()) { setErr('Введите название'); return; }
    if (!html.trim()) { setErr('Вставьте HTML'); return; }
    if (html.length > 380000) { setErr('HTML слишком большой (макс. 380KB)'); return; }
    setBusy(true);
    try {
      await onImport({ name: name.trim(), html: html.trim() });
      setName(''); setHtml(''); setShowImport(false);
    } catch (e) {
      setErr(e.message || 'Ошибка сохранения');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="st-section">
      <div className="st-section__h">HTML Шаблоны</div>
      {templates.length === 0 && (
        <div style={{ fontSize: 10, color: 'var(--st-dim)', letterSpacing: '.1em', marginBottom: 8 }}>НЕТ ШАБЛОНОВ</div>
      )}
      {templates.map(t => (
        <div key={t.id} style={{ marginBottom: 8, borderLeft: '2px solid ' + (t.id === activeId ? 'var(--st-yellow)' : 'var(--st-line)'), paddingLeft: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ flex: 1, fontSize: 11, letterSpacing: '.08em', color: t.id === activeId ? 'var(--st-yellow)' : 'var(--st-text)', fontFamily: 'var(--f-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {t.id === activeId ? '✓ ' : ''}{t.name}
            </div>
            {t.id !== activeId && (
              <button className="st-chip" style={{ padding: '2px 8px', fontSize: 9 }} onClick={() => onActivate(t)}>ON</button>
            )}
            <button className="st-chip" style={{ padding: '2px 8px', fontSize: 9, opacity: .5 }} onClick={() => onDelete(t)}>✕</button>
          </div>
        </div>
      ))}
      {showImport ? (
        <div style={{ marginTop: 8 }}>
          <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="Название шаблона"
            style={{ width: '100%', marginBottom: 6, background: 'var(--st-panel2)', border: '1px solid var(--st-line)', color: 'var(--st-text)', fontFamily: 'var(--f-mono)', fontSize: 10, padding: '6px 8px', boxSizing: 'border-box' }} />
          <textarea value={html} onChange={e => setHtml(e.target.value)}
            placeholder={'<!DOCTYPE html>\n<html>...\n  {{event.name}}\n  <div data-yb-image="main">'}
            style={{ width: '100%', height: 160, background: 'var(--st-panel2)', border: '1px solid var(--st-line)', color: 'var(--st-text)', fontFamily: 'var(--f-mono)', fontSize: 10, padding: 8, boxSizing: 'border-box', resize: 'vertical' }} />
          {err && <div style={{ color: '#f87171', fontSize: 10, marginTop: 4 }}>{err}</div>}
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <button className="st-btn" style={{ flex: 1 }} onClick={handleImport} disabled={busy}>СОХРАНИТЬ</button>
            <button className="st-btn st-btn--ghost" onClick={() => { setShowImport(false); setErr(''); }}>ОТМЕНА</button>
          </div>
        </div>
      ) : (
        <button className="st-btn st-btn--ghost" style={{ width: '100%', marginTop: 4 }} onClick={() => setShowImport(true)}>+ ИМПОРТ HTML</button>
      )}
    </div>
  );
}

/* ── Template image slot (inspector crop control) ── */
function TplImageSlot({ slotName, value, fallbackUrl, cropW, cropH, onChange }) {
  const fileRef = useRef(null);
  const [showActions, setShowActions] = useState(false);

  const currentUrl = value || fallbackUrl || null;

  useEffect(() => {
    const handler = (e) => {
      if (e.detail.slotName !== slotName) return;
      if (currentUrl) {
        setShowActions(true);
      } else {
        fileRef.current?.click();
      }
    };
    document.addEventListener('yb-crop-slot', handler);
    return () => document.removeEventListener('yb-crop-slot', handler);
  }, [slotName, currentUrl]);

  const handleFile = (file) => {
    if (!file || !window.showCropModal) return;
    setShowActions(false);
    window.showCropModal(file, cropW, cropH, 0.9, blob => {
      const reader = new FileReader();
      reader.onload = e => onChange(e.target.result);
      reader.readAsDataURL(blob);
    });
  };

  const handleReplace = () => { setShowActions(false); fileRef.current?.click(); };

  const handleReCrop = async () => {
    if (!currentUrl) return;
    setShowActions(false);
    const blob = await fetch(currentUrl).then(r => r.blob());
    handleFile(new File([blob], 'image.jpg', { type: blob.type || 'image/jpeg' }));
  };

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 9, letterSpacing: '.12em', color: 'var(--st-dim)', marginBottom: 4, fontFamily: 'var(--f-mono)' }}>{slotName}</div>
      <div
        style={{ width: '100%', height: 60, background: currentUrl ? 'none' : 'var(--st-panel2)', backgroundImage: currentUrl ? `url(${currentUrl})` : 'none', backgroundSize: 'cover', backgroundPosition: 'center', border: '1px dashed ' + (showActions ? 'var(--st-yellow)' : 'var(--st-line)'), cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}
        onClick={() => currentUrl ? setShowActions(a => !a) : fileRef.current?.click()}
        onDragOver={e => e.preventDefault()}
        onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
      >
        {!currentUrl && <span style={{ fontSize: 9, letterSpacing: '.1em', color: 'var(--st-dim)', fontFamily: 'var(--f-mono)', pointerEvents: 'none' }}>НАЖМИ ИЛИ ПЕРЕТАЩИ</span>}
        <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
          onChange={e => { const f = e.target.files[0]; if (f) handleFile(f); e.target.value = ''; }} />
      </div>
      {showActions && (
        <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
          <button className="st-btn" style={{ flex: 1, fontSize: 10 }} onClick={handleReCrop}>✂ КРОП</button>
          <button className="st-btn st-btn--ghost" style={{ flex: 1, fontSize: 10 }} onClick={handleReplace}>↺ ЗАМЕНИТЬ</button>
        </div>
      )}
    </div>
  );
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
  const [ybData,       setYbData]       = useState(null);
  const [loadError,    setLoadError]    = useState(null);
  const [recipeId,     setRecipeId]     = useState('weekly');
  const [htmlTemplates,   setHtmlTemplates]   = useState([]);
  const [activeTemplateId, setActiveTemplateId] = useState(null);
  const [subjects,  setSubjects]  = useState({ performer: null, event: null, episode: null, product: null });
  const [format,    setFormat]    = useState('story');
  const [active,    setActive]    = useState(0);
  const [edits,     setEdits]     = useState(loadEdits);
  const [toast,     setToast]     = useState(null);
  const [busy,      setBusy]      = useState(null);
  const [scale,     setScale]     = useState(0.3);

  /* Instagram state */
  const [igAccounts,   setIgAccounts]   = useState(null);   // null=not loaded, []=loaded
  const [igModal,      setIgModal]      = useState(null);    // null | 'one' | 'all'
  const [igPosting,    setIgPosting]    = useState(null);    // null | {done,total,account}
  const [igResult,     setIgResult]     = useState(null);    // null | {ok, count, error}

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
      const today = new Date().toISOString().slice(0, 10);
      const firstUpcomingEvt = data.events
        .filter(e => e.date >= today)
        .sort((a, b) => a.date.localeCompare(b.date))[0];
      setSubjects({
        performer: data.performers[0]?.id || null,
        event:     firstUpcomingEvt?.id || data.events[0]?.id || null,
        episode:   data.episodes[0]?.id   || null,
        product:   data.merch[0]?.id      || null,
      });
    }).catch(e => setLoadError(e.message || String(e)));

    apiCall('/api/studio/templates').then(data => {
      const templates = data.templates || [];
      window.__htmlTemplates = templates;
      window.__htmlTemplateSlots = {};
      setHtmlTemplates(templates);
      templates.forEach(t => {
        window.injectTemplateStyles(t);
        window.__htmlTemplateSlots[t.id] = window.parseTemplateSlots(t.html);
      });
      if (templates.length > 0) setActiveTemplateId(templates[0].id);
    }).catch(() => {});
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
    window.__activeTemplateId = activeTemplateId;
    const result = recipe.build(subjectId);
    window.YB_DATA.events = saved;
    return result;
  }, [recipeId, subjectId, ybData, filteredEvents, activeTemplateId]);

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
  const resetSlide     = (key)       => setEdits(p => { const n = { ...p }; delete n[key]; return n; });
  const setStoryLink   = (key, url)  => patch(key, c => ({ ...c, link: url }));
  const setLinkEnabled = (key, on)   => patch(key, c => ({ ...c, linkEnabled: on }));

  const makeCtx = useCallback((slide) => {
    const st = edits[slide.key] || {};
    const safeBottom = format === 'story' ? 168 : 48;
    return {
      f: format, dims, accent: slide.accent,
      safeBottom,
      variant: st.variant ?? 0,
      layers: { ...DEFAULT_LAYERS, ...(st.layers || {}) },
      flags: DEFAULT_FLAGS,
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
    await new Promise(r => requestAnimationFrame(r));
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

  /* Instagram: load accounts, upload slide, post */
  const loadIgAccounts = async () => {
    try {
      const data = await apiCall('/api/instagram/accounts');
      setIgAccounts(data.accounts || []);
    } catch (e) { flash('Ошибка загрузки аккаунтов Instagram'); }
  };

  const openIgModal = async (target) => {
    if (!igAccounts) await loadIgAccounts();
    setIgModal(target);
    setIgResult(null);
  };

  const uploadSlide = async (i) => {
    const dataUri = await captureSlide(i);
    const base64 = dataUri.split(',')[1];
    const filename = `stories/${Date.now()}_${recipeId}_${String(i+1).padStart(2,'0')}.jpg`;
    const result = await apiCall('/api/upload-image', 'POST', { filename, contentType: 'image/jpeg', data: base64 });
    return result.url;
  };

  const postToInstagram = async (account, indices) => {
    setIgModal(null);
    setIgPosting({ done: 0, total: indices.length, account });
    setIgResult(null);
    let posted = 0;
    try {
      for (let i = 0; i < indices.length; i++) {
        const slideIdx = indices[i];
        const slideSt = edits[slides[slideIdx]?.key] || {};
        const imageUrl = await uploadSlide(slideIdx);
        const body = { ig_user_id: account.ig_user_id, image_url: imageUrl, caption: '', is_story: true };
        await apiCall('/api/instagram/post', 'POST', body);
        posted++;
        setIgPosting({ done: posted, total: indices.length, account });
        if (i < indices.length - 1) await new Promise(r => setTimeout(r, 1500));
      }
      setIgResult({ ok: true, count: posted });
    } catch (e) {
      setIgResult({ ok: false, error: e.message, count: posted });
    } finally {
      setIgPosting(null);
    }
  };

  /* event exclusion toggle */
  const toggleEvent = useCallback((id) => {
    setExcludedEventIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  /* template ops */
  const handleTemplateImport = async (payload) => {
    const data = await apiCall('/api/studio/templates', 'POST', payload);
    const tpl = data.template;
    window.__htmlTemplates = [...(window.__htmlTemplates || []), tpl];
    window.__htmlTemplateSlots = window.__htmlTemplateSlots || {};
    window.__htmlTemplateSlots[tpl.id] = window.parseTemplateSlots(tpl.html);
    window.injectTemplateStyles(tpl);
    setHtmlTemplates(prev => [...prev, tpl]);
    setActiveTemplateId(tpl.id);
  };

  const handleTemplateActivate = (tpl) => {
    setActiveTemplateId(tpl.id);
  };

  const handleTemplateDelete = async (tpl) => {
    if (!confirm(`Удалить шаблон «${tpl.name}»?`)) return;
    await apiCall(`/api/studio/templates/${tpl.id}`, 'DELETE');
    setHtmlTemplates(prev => prev.filter(t => t.id !== tpl.id));
    window.__htmlTemplates = (window.__htmlTemplates || []).filter(t => t.id !== tpl.id);
    const remaining = htmlTemplates.filter(t => t.id !== tpl.id);
    if (activeTemplateId === tpl.id) setActiveTemplateId(remaining[0]?.id || null);
    const styleEl = document.getElementById('yb-tpl-css-' + tpl.id);
    if (styleEl) styleEl.remove();
  };

  /* loading / error states */
  if (!ybData) return <LoadingScreen error={loadError} />;

  const activeSlide = slides[Math.min(active, Math.max(0, slides.length - 1))];
  if (!activeSlide) return <LoadingScreen error="Нет слайдов для этого рецепта" />;

  const activeComp   = window.SLIDE_TYPES[activeSlide.type].Comp;
  const activeSt     = edits[activeSlide.key] || {};
  const activeLayers = { ...DEFAULT_LAYERS, ...(activeSt.layers || {}) };

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
            <div className="st-section__h">Instagram</div>
            <div style={{ fontSize: 10, letterSpacing: '.12em', color: 'var(--st-dim)', marginBottom: 12, lineHeight: 1.5 }}>
              Ссылки в сторис через API не поддерживаются Meta.<br/>
              Текст «Подробности на Yallabalagan.org» уже добавлен на все слайды.
            </div>
            {igResult && (
              <div style={{ fontSize: 11, marginBottom: 8, color: igResult.ok ? '#16a34a' : '#dc2626', letterSpacing: '.05em' }}>
                {igResult.ok ? `✓ Опубликовано ${igResult.count} слайд(ов)` : `✗ Ошибка: ${igResult.error}`}
              </div>
            )}
            <div className="st-dl-row">
              <button className="st-btn" onClick={() => openIgModal('one')} disabled={!!busy || !!igPosting}>
                📸 ЭТОТ СЛАЙД
              </button>
              <button className="st-btn st-btn--ghost" onClick={() => openIgModal('all')} disabled={!!busy || !!igPosting}>
                📸 ВСЯ СЕРИЯ
              </button>
            </div>
            <div style={{ fontSize: 10, color: 'var(--st-dim)', marginTop: 6, letterSpacing: '.08em' }}>
              ПУБЛИКУЕТСЯ КАК STORIES · <a href="instagram-history.html" style={{ color: 'var(--st-dim)' }}>ИСТОРИЯ</a>
            </div>
          </div>

          {recipeId === 'html' && (() => {
            const slots = (window.__htmlTemplateSlots || {})[activeSlide.data?.templateId] || [];
            return (
              <>
                {slots.length > 0 && (
                  <div className="st-section">
                    <div className="st-section__h">Изображения</div>
                    {slots.map(slot => (
                      <TplImageSlot
                        key={slot.name}
                        slotName={slot.name}
                        value={(activeSt.images || {})[slot.name] || null}
                        fallbackUrl={slot.name === 'main' ? activeSlide.data?.event?.photo || null : null}
                        cropW={slot.cropW || dims.w}
                        cropH={slot.cropH || dims.h}
                        onChange={dataUrl => updateImage(activeSlide.key, slot.name, dataUrl)}
                      />
                    ))}
                  </div>
                )}
                <TemplatesPanel
                  templates={htmlTemplates}
                  activeId={activeTemplateId}
                  onActivate={handleTemplateActivate}
                  onDelete={handleTemplateDelete}
                  onImport={handleTemplateImport}
                />
              </>
            );
          })()}

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

      {/* Instagram posting progress overlay */}
      {igPosting && (
        <div className="st-modal-overlay">
          <div className="st-modal">
            <div className="st-modal__title">📸 Публикация в Instagram</div>
            <div className="st-modal__sub">@{igPosting.account.ig_username} — слайд {igPosting.done} / {igPosting.total}</div>
            <div className="st-busy__bar" style={{ width: '100%' }}>
              <div className="st-busy__fill" style={{ width: (igPosting.total ? igPosting.done / igPosting.total * 100 : 0) + '%' }} />
            </div>
          </div>
        </div>
      )}

      {/* Instagram account picker modal */}
      {igModal && (
        <div className="st-modal-overlay" onClick={() => setIgModal(null)}>
          <div className="st-modal" onClick={e => e.stopPropagation()}>
            <div className="st-modal__title">Опубликовать в Instagram</div>
            <div className="st-modal__sub">
              {igModal === 'one'
                ? `Слайд ${active + 1} — «${slides[active]?.label || ''}» будет опубликован как Story`
                : `${slides.length} слайдов будут опубликованы как Stories по очереди`}
            </div>
            {!igAccounts
              ? <div style={{ color: 'rgba(255,255,255,.5)', fontSize: 12 }}>Загрузка...</div>
              : igAccounts.length === 0
                ? <div style={{ color: 'rgba(255,255,255,.5)', fontSize: 12 }}>
                    Нет подключённых аккаунтов.{' '}
                    <a href="social-settings.html" style={{ color: 'var(--paper)' }}>Подключить →</a>
                  </div>
                : igAccounts.map(acc => (
                    <button key={acc.ig_user_id} className="st-ig-account-btn"
                      onClick={() => postToInstagram(acc, igModal === 'one' ? [active] : slides.map((_, i) => i))}>
                      <span style={{ fontSize: 20 }}>📷</span>
                      <span>
                        <b>@{acc.ig_username}</b>
                        <small style={{ display: 'block', opacity: .6 }}>{acc.ig_name}</small>
                      </span>
                    </button>
                  ))
            }
            <button style={{ marginTop: 12, background: 'transparent', border: 'none', color: 'rgba(255,255,255,.5)', cursor: 'pointer', fontSize: 12 }}
              onClick={() => setIgModal(null)}>ОТМЕНА</button>
          </div>
        </div>
      )}

      <CropModal />
    </div>
  );
}

/* ── Crop Modal ── */
function CropInner({ url, cropW, cropH, quality, cb, onClose }) {
  const ASPECT = cropW / cropH;
  const FW = Math.min(360, Math.round(560 * ASPECT));
  const FH = Math.round(FW / ASPECT);

  const [nat, setNat] = useState({ w: 0, h: 0 });
  const [tr, setTr]   = useState({ x: 0, y: 0, s: 1 });
  const drag = useRef(null);
  const viewRef = useRef(null);

  const minScale = nat.w > 0 ? Math.min(FW / nat.w, FH / nat.h) * 0.9 : 0.05;
  const maxScale = nat.w > 0 ? Math.max(FW / nat.w, FH / nat.h) * 3 : 20;

  const onLoad = (e) => {
    const nw = e.target.naturalWidth, nh = e.target.naturalHeight;
    const s = Math.max(FW / nw, FH / nh);
    setNat({ w: nw, h: nh });
    setTr({ x: (FW - nw * s) / 2, y: (FH - nh * s) / 2, s });
  };

  useEffect(() => {
    const el = viewRef.current;
    if (!el) return;
    const handler = (e) => {
      e.preventDefault();
      const f = e.deltaY > 0 ? 0.92 : 1.08;
      setTr(t => {
        const s = Math.max(minScale, Math.min(maxScale, t.s * f));
        const cx = FW / 2, cy = FH / 2;
        return { s, x: cx - (cx - t.x) * (s / t.s), y: cy - (cy - t.y) * (s / t.s) };
      });
    };
    el.addEventListener('wheel', handler, { passive: false });
    return () => el.removeEventListener('wheel', handler);
  }, [minScale, maxScale]);

  const onMouseDown = (e) => {
    drag.current = { lx: e.clientX, ly: e.clientY };
    e.preventDefault();
  };
  const onMouseMove = (e) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.lx, dy = e.clientY - drag.current.ly;
    drag.current = { lx: e.clientX, ly: e.clientY };
    setTr(t => ({ ...t, x: t.x + dx, y: t.y + dy }));
  };
  const onMouseUp = () => { drag.current = null; };

  const sliderVal = nat.w > 0
    ? Math.max(0, Math.min(100, Math.round((tr.s - minScale) / (maxScale - minScale) * 100)))
    : 50;
  const onSlider = (e) => {
    const newS = minScale + (Number(e.target.value) / 100) * (maxScale - minScale);
    setTr(t => {
      const s = Math.max(minScale, Math.min(maxScale, newS));
      const cx = FW / 2, cy = FH / 2;
      return { s, x: cx - (cx - t.x) * (s / t.s), y: cy - (cy - t.y) * (s / t.s) };
    });
  };

  const apply = () => {
    if (!nat.w) return;
    const ratio = cropW / FW;
    const canvas = document.createElement('canvas');
    canvas.width = cropW; canvas.height = cropH;
    const ctx = canvas.getContext('2d');
    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, tr.x * ratio, tr.y * ratio, nat.w * tr.s * ratio, nat.h * tr.s * ratio);
      canvas.toBlob(b => { cb(b); onClose(); }, 'image/jpeg', quality);
    };
    img.src = url;
  };

  const BTN = { fontFamily: 'var(--f-mono)', fontSize: 13, letterSpacing: '.12em', padding: '10px 24px', cursor: 'pointer', border: '2px solid rgba(255,255,255,.5)', borderRadius: 0 };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.9)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{ fontFamily: 'var(--f-mono)', color: 'rgba(255,255,255,.5)', fontSize: 11, letterSpacing: '.16em', marginBottom: 14 }}>
        КАДРИРОВАТЬ · {cropW}×{cropH}px · ПЕРЕТАЩИ / ПРОКРУТИ
      </div>
      <div ref={viewRef}
        style={{ position: 'relative', width: FW, height: FH, overflow: 'hidden', cursor: 'grab', border: '2px solid rgba(255,255,255,.45)', background: '#111', userSelect: 'none' }}
        onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp} onMouseLeave={onMouseUp}>
        <img src={url} alt="" style={{ display: 'none' }} onLoad={onLoad} />
        {nat.w > 0 && (
          <img src={url} alt="кроп"
            style={{ position: 'absolute', left: tr.x, top: tr.y, width: nat.w * tr.s, height: nat.h * tr.s, pointerEvents: 'none', userSelect: 'none', display: 'block' }} />
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12, width: FW }}>
        <span style={{ fontFamily: 'var(--f-mono)', fontSize: 12, color: 'rgba(255,255,255,.4)', userSelect: 'none' }}>−</span>
        <input type="range" min="0" max="100" value={sliderVal} onChange={onSlider}
          style={{ flex: 1, cursor: 'pointer', accentColor: 'var(--paper)' }} />
        <span style={{ fontFamily: 'var(--f-mono)', fontSize: 12, color: 'rgba(255,255,255,.4)', userSelect: 'none' }}>+</span>
      </div>
      <div style={{ display: 'flex', gap: 12, marginTop: 12 }}>
        <button style={{ ...BTN, background: 'transparent', color: 'rgba(255,255,255,.6)' }} onClick={onClose}>ОТМЕНА</button>
        <button style={{ ...BTN, background: 'var(--paper)', color: 'var(--ink)', border: '2px solid var(--paper)' }} onClick={apply}>✓ ПРИМЕНИТЬ</button>
      </div>
    </div>
  );
}

function CropModal() {
  const [sess, setSess] = useState(null);
  useEffect(() => {
    window.showCropModal = (file, w, h, q, cb) => {
      setSess({ url: URL.createObjectURL(file), cropW: w, cropH: h, quality: q, cb });
    };
    return () => { delete window.showCropModal; };
  }, []);
  const close = () => { if (sess) URL.revokeObjectURL(sess.url); setSess(null); };
  if (!sess) return null;
  return <CropInner key={sess.url} {...sess} onClose={close} />;
}
