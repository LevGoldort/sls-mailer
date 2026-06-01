/* Weekly lineup slides: cover · per-event · outro */
const { Grain, Halftone, Tape, EditableText, RisoText, ImageSlot,
        BrandBox, BrandLockup, FooterChrome, SwipeHint, StubMeta } = window;

/* shared: ink ticker strip */
function TickerStrip() {
  const S = window.YB_DATA.site;
  return (
    <div className="s-ticker">
      <span>★ {S.cities} ★</span>
      <span className="s-ticker__c">{S.zine}</span>
      <span className="s-ticker__r">{S.hebrew}</span>
    </div>
  );
}

/* shared: big date stamp */
function DateStamp({ iso, accentVar }) {
  const d = window.parseDate(iso);
  return (
    <div className="s-datestamp" style={accentVar ? { boxShadow: `9px 9px 0 ${accentVar}` } : null}>
      <div className="s-datestamp__num">{d.num}</div>
      <div className="s-datestamp__month">{d.monthAbbr}</div>
      <div className="s-datestamp__dow">{d.dow} · {d.year}</div>
    </div>
  );
}

/* ── COVER (image hero + title) ── */
function WeeklyCover({ ctx }) {
  const { T, set, img, setImg, layers, data } = ctx;
  const isos = data.events.map((e) => e.date);
  const range = window.dateRangeLabel(isos);
  const count = data.events.length;
  return (
    <div className={'slide s-weekly-cover acc-magenta'} style={ctx.rootStyle}>
      <Grain on={layers.grain} />
      <TickerStrip />

      {/* hero image */}
      <div style={{ position: 'relative', height: '42%', minHeight: 0 }}>
        <ImageSlot value={img('hero')} onChange={(v) => setImg('hero', v)} label="ГЛАВНОЕ ФОТО НЕДЕЛИ"
          style={{ width: '100%', height: '100%', border: 'none', borderBottom: '5px solid var(--ink)' }} />
        <Halftone on={layers.halftone} style={{ inset: 0, zIndex: 2 }} />
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(26,20,16,.35) 0%, rgba(26,20,16,0) 38%, rgba(26,20,16,.5) 100%)', pointerEvents: 'none' }} aria-hidden="true" />
        {layers.stamps && (
          <div style={{ position: 'absolute', top: 28, left: 32, zIndex: 4 }}><BrandLockup on={layers.stamps} /></div>
        )}
        <span className="s-stamp s-stamp--lg s-stamp--yellow-bg" style={{ position: 'absolute', top: 32, right: 34, zIndex: 4, transform: 'rotate(4deg)', boxShadow: '4px 4px 0 var(--ink)' }}>
          <EditableText value={T('badge', '★ АФИША ★')} onCommit={(v) => set('badge', v)} single />
        </span>
        <Tape on={layers.tape} color="cyan" style={{ bottom: -16, left: 60, width: 240, height: 42, transform: 'rotate(-4deg)', zIndex: 5 }} />
      </div>

      <Halftone on={layers.halftone} corner />
      <Tape on={layers.tape} color="yellow" style={{ top: '52%', right: -50, width: 240, height: 44, transform: 'rotate(6deg)' }} />

      <div className="s-weekly-cover__body" style={{ padding: '48px 64px 64px', flex: 1, gap: 24 }}>
        <EditableText className="s-eyebrow" value={T('eyebrow', 'ПРОГРАММА НЕДЕЛИ')} onCommit={(v) => set('eyebrow', v)} single
          style={{ fontSize: 26 }} />
        <h1 className="s-display" style={{ fontSize: 150 }}>
          <EditableText value={T('line1', 'СОБЫТИЯ')} onCommit={(v) => set('line1', v)} single style={{ display: 'block' }} />
          <RisoText value={T('line2', 'НА НЕДЕЛЕ')} onCommit={(v) => set('line2', v)} shadowColor="var(--magenta)"
            style={{ color: 'var(--ink)' }} />
        </h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap', marginTop: 4 }}>
          <span className="s-stamp s-stamp--lg s-stamp--yellow-bg" style={{ fontSize: 34, padding: '14px 22px', transform: 'rotate(-2deg)', boxShadow: '6px 6px 0 var(--ink)' }}>
            <EditableText value={T('range', range)} onCommit={(v) => set('range', v)} single />
          </span>
          <span className="s-counter" style={{ fontSize: 56 }}>
            <EditableText value={T('count', String(count))} onCommit={(v) => set('count', v)} single />
            <span style={{ fontFamily: 'var(--f-mono)', fontSize: 22, letterSpacing: '.1em', marginLeft: 10, opacity: .6 }}>СОБЫТИЙ</span>
          </span>
        </div>
        <div style={{ marginTop: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 18, flexWrap: 'wrap' }}>
          <SwipeHint label={T('swipe', 'СВАЙПНИ ↑ ВСЮ НЕДЕЛЮ')} />
          <FooterChrome layers={layers.stamps} />
        </div>
      </div>
    </div>
  );
}
WeeklyCover.variants = ['Классика'];
WeeklyCover.layers = ['grain', 'halftone', 'tape', 'stamps'];

/* ── BOARD (all events on one screen — «Ближайшее» style, mobile-scale) ── */
function WeeklyBoard({ ctx }) {
  const { T, set, layers, data } = ctx;
  const evs = data.events;
  const range = window.dateRangeLabel(evs.map((e) => e.date));
  const accents = ['var(--cyan)', 'var(--magenta)', 'var(--yellow)'];
  const tapes = ['cyan', 'magenta', 'yellow'];
  const big = evs.length <= 3;
  return (
    <div className="slide acc-magenta" style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
      <Grain on={layers.grain} />
      <Halftone on={layers.halftone} corner />
      <TickerStrip />
      <div style={{ position: 'relative', zIndex: 4, padding: '56px 56px 60px', flex: 1, display: 'flex', flexDirection: 'column', gap: 30 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 20 }}>
          <div>
            <EditableText className="s-eyebrow" value={T('eyebrow', 'ВСЯ НЕДЕЛЯ НА ОДНОМ ЭКРАНЕ')} onCommit={(v) => set('eyebrow', v)} single style={{ fontSize: 24 }} />
            <h2 className="s-display" style={{ fontSize: 110, marginTop: 12 }}>
              <RisoText value={T('heading', 'БЛИЖАЙШЕЕ')} onCommit={(v) => set('heading', v)} shadowColor="var(--magenta)" style={{ color: 'var(--ink)' }} />
            </h2>
          </div>
          <span className="s-stamp s-stamp--lg s-stamp--yellow-bg" style={{ fontSize: 28, transform: 'rotate(3deg)', boxShadow: '5px 5px 0 var(--ink)', whiteSpace: 'nowrap' }}>
            <EditableText value={T('range', range)} onCommit={(v) => set('range', v)} single />
          </span>
        </div>

        <div className="s-board" style={{ flex: 1, justifyContent: 'center', gap: big ? 24 : 16 }}>
          {evs.map((ev, i) => {
            const d = window.parseDate(ev.date);
            return (
              <div key={ev.id} className="s-board-row" style={{ boxShadow: `9px 9px 0 ${accents[i % 3]}`, transform: `rotate(${i % 2 ? 0.4 : -0.4}deg)` }}>
                <Tape on={layers.tape} color={tapes[i % 3]} style={{ top: -14, left: 28, width: 116, height: 28, transform: 'rotate(-4deg)' }} />
                <div className="s-board-row__date">
                  <span className="s-board-row__num">{d.num}</span>
                  <span className="s-board-row__mon">{d.monthAbbr}</span>
                  <div className="s-board-row__dow">{d.dow}</div>
                </div>
                <div style={{ minWidth: 0 }}>
                  <div className="s-board-row__title">{ev.title.toUpperCase()}</div>
                  <div className="s-board-row__meta">
                    <span>► {ev.venue}</span>
                    <span style={{ opacity: .4 }}>·</span>
                    <span>{ev.time}</span>
                    {ev.price
                      ? (<><span style={{ opacity: .4 }}>·</span><span>{ev.price}₪</span></>)
                      : (<><span style={{ opacity: .4 }}>·</span><span>БИЛЕТЫ</span></>)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <SwipeHint label={T('swipe', 'ПОДРОБНОСТИ →')} />
          <FooterChrome layers={layers.stamps} />
        </div>
      </div>
    </div>
  );
}
WeeklyBoard.variants = ['Доска'];
WeeklyBoard.layers = ['grain', 'halftone', 'tape', 'stamps'];

/* ── EVENT (3 variants) ── */
function WeeklyEvent({ ctx }) {
  const { T, set, img, setImg, layers, data, variant, safeBottom } = ctx;
  const ev = data.event;
  const d = window.parseDate(ev.date);
  const isExternal = ev.type === 'external';
  const accentVar = { magenta: 'var(--magenta)', cyan: 'var(--cyan)', yellow: 'var(--yellow)' }[ctx.accent] || 'var(--magenta)';
  const stubClass = ctx.accent === 'cyan' ? 's-stub--cyan' : ctx.accent === 'yellow' ? 's-stub--yellow' : '';

  const city = ev.city || '';
  const CityBlock = ({ size = 92, light = false }) => (
    <div>
      <div style={{ fontFamily: 'var(--f-mono)', fontSize: 19, letterSpacing: '.2em', opacity: light ? .8 : .55, color: light ? 'var(--paper)' : 'inherit' }}>★ ГОРОД</div>
      <div className="s-city" style={{ fontSize: size, marginTop: 6, color: light ? 'var(--paper)' : 'var(--ink)', textShadow: light ? '4px 4px 0 var(--ink)' : 'none' }}>
        <EditableText value={T('city', city)} onCommit={(v) => set('city', v)} single />
      </div>
    </div>
  );

  const Tags = () => (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
      {(ev.tags || []).map((tg, i) => (
        <span key={i} className={'s-stamp ' + (i === 0 ? 's-stamp--magenta' : 's-stamp--cyan')} style={{ transform: `rotate(${i ? 1.5 : -2}deg)` }}>{tg}</span>
      ))}
      {isExternal && <span className="s-stamp s-stamp--red" style={{ transform: 'rotate(3deg)' }}>EXTERNAL</span>}
    </div>
  );

  const Stub = () => (
    <div className={'s-stub ' + stubClass} style={{ boxShadow: '8px 8px 0 var(--ink)' }}>
      <Halftone on={layers.halftone} style={{ opacity: .35 }} />
      <div className="s-stub__perf"><span className="s-stub__dot s-stub__dot--t" /><span className="s-stub__dot s-stub__dot--b" /></div>
      <div style={{ position: 'relative' }}>
        <StubMeta index={data.index} dateStr={d.num + d.monthAbbr} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginTop: 16, gap: 16 }}>
          <div>
            <div className="s-stub__label">{ev.price ? T('priceLabel', 'ВХОД ОТ') : T('extLabel', 'БИЛЕТЫ')}</div>
            {ev.price
              ? <div className="s-stub__price"><EditableText value={T('price', String(ev.price))} onCommit={(v) => set('price', v)} single /><sup>₪</sup></div>
              : <div className="s-stub__price" style={{ fontSize: 46, lineHeight: 1.05 }}><EditableText value={T('extSub', 'У ПАРТНЁРА')} onCommit={(v) => set('extSub', v)} single /></div>}
          </div>
          <span className="s-btn s-btn--primary" style={{ fontSize: 24, boxShadow: '6px 6px 0 var(--ink)' }}>
            <EditableText value={T('cta', ev.ctaLabel || 'ПЕРЕЙТИ')} onCommit={(v) => set('cta', v)} single /> →
          </span>
        </div>
      </div>
    </div>
  );

  /* VARIANT 0 — POSTER (full image bg, default) */
  if (variant === 0) {
    return (
      <div className={'slide acc-' + ctx.accent} style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
        <div style={{ position: 'absolute', inset: 0 }}>
          <ImageSlot value={img('photo') || ev.photo} onChange={(v) => setImg('photo', v)} label={'АФИША · ' + ev.venue}
            cropW={1080} cropH={1920} style={{ width: '100%', height: '100%', border: 'none' }} />
        </div>
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(26,20,16,.15) 0%, rgba(26,20,16,.05) 45%, rgba(26,20,16,.85) 100%)', pointerEvents: 'none' }} aria-hidden="true" />
        <Halftone on={layers.halftone} corner />
        <div style={{ position: 'relative', zIndex: 4, padding: '64px 64px ' + safeBottom + 'px', display: 'flex', flexDirection: 'column', height: '100%', pointerEvents: 'none' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ transform: 'rotate(-4deg)' }}><DateStamp iso={ev.date} accentVar={accentVar} /></div>
            <span className="s-counter" style={{ fontSize: 86, color: 'var(--paper)', textShadow: '4px 4px 0 var(--ink)' }}>
              <sup>№</sup>{String(data.index).padStart(2, '0')}
            </span>
          </div>
          <div style={{ flex: 1 }} />
          <Tape on={layers.tape} color="yellow" style={{ position: 'static', alignSelf: 'flex-start', width: 220, height: 40, transform: 'rotate(-3deg)', marginBottom: -14, marginLeft: 30 }} />
          <div style={{ background: 'var(--paper)', border: '5px solid var(--ink)', boxShadow: '10px 10px 0 ' + accentVar, padding: '32px 36px', transform: 'rotate(-0.6deg)', pointerEvents: 'all' }}>
            {layers.stamps && <div style={{ marginBottom: 16 }}><Tags /></div>}
            <h1 className="s-event__title" style={{ fontSize: 60 }}>
              <EditableText value={T('title', ev.title.toUpperCase())} onCommit={(v) => set('title', v)} />
            </h1>
            <div style={{ marginTop: 24 }}><CityBlock size={104} /></div>
            <div className="s-meta-row" style={{ fontSize: 24, marginTop: 16 }}>
              <span>► <b>{ev.venue}</b></span><span style={{ opacity: .4 }}>·</span>
              <span>{d.day} {d.monthGen} · {ev.time}</span>
            </div>
            <div style={{ marginTop: 20 }}><Stub /></div>
          </div>
        </div>
      </div>
    );
  }

  /* VARIANT 2 — INDEX (type-forward, huge number) */
  if (variant === 2) {
    return (
      <div className={'slide acc-' + ctx.accent} style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
        <Grain on={layers.grain} />
        <Halftone on={layers.halftone} corner />
        <div style={{ position: 'absolute', top: -60, right: -30, fontFamily: 'var(--f-display)', fontSize: 560, lineHeight: .8, color: accentVar, opacity: .16, letterSpacing: '-.05em' }} aria-hidden="true">{String(data.index).padStart(2, '0')}</div>
        <Tape on={layers.tape} color="magenta" style={{ top: 180, left: -30, width: 240, height: 44, transform: 'rotate(-6deg)' }} />
        <div style={{ position: 'relative', zIndex: 4, padding: '72px 72px ' + safeBottom + 'px', display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="s-eyebrow" style={{ fontSize: 24 }}>{d.dow} · {d.num} {d.monthFull}</span>
            <BrandBox />
          </div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 30 }}>
            {layers.stamps && <Tags />}
            <h1 className="s-event__title" style={{ fontSize: 92 }}>
              <RisoText value={T('title', ev.title.toUpperCase())} onCommit={(v) => set('title', v)} shadowColor={accentVar} style={{ color: 'var(--ink)' }} />
            </h1>
            <p className="s-event__desc" style={{ fontSize: 30, maxWidth: 820, margin: 0 }}>
              <EditableText value={T('short', ev.short || ev.description)} onCommit={(v) => set('short', v)} />
            </p>
            <CityBlock size={116} />
            <div className="s-meta-row" style={{ fontSize: 24, marginTop: 2 }}>
              <span className="s-stamp s-stamp--ink" style={{ fontSize: 22 }}>► {ev.venue}</span>
              <span style={{ opacity: .7 }}>СТАРТ {ev.time}</span>
            </div>
          </div>
          <Stub />
        </div>
      </div>
    );
  }

  /* VARIANT 1 — TICKET */
  return (
    <div className={'slide acc-' + ctx.accent} style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
      <Grain on={layers.grain} />
      <Halftone on={layers.halftone} corner />
      <Tape on={layers.tape} color={ctx.accent === 'cyan' ? 'magenta' : 'cyan'} style={{ top: 40, left: '40%', width: 240, height: 44, transform: 'rotate(-4deg)' }} />

      <div style={{ position: 'relative', zIndex: 4, padding: '72px 72px ' + safeBottom + 'px', display: 'flex', flexDirection: 'column', height: '100%', gap: 28 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div style={{ transform: 'rotate(-3deg)' }}><DateStamp iso={ev.date} accentVar={accentVar} /></div>
          <div style={{ textAlign: 'right' }}>
            <BrandBox />
            <div className="s-counter" style={{ fontSize: 64, marginTop: 14 }}><sup>№</sup>{String(data.index).padStart(2, '0')}<span style={{ fontFamily: 'var(--f-mono)', fontSize: 18, opacity: .5, marginLeft: 8 }}>/ {data.total}</span></div>
          </div>
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 24 }}>
          {layers.stamps && <Tags />}
          <h1 className="s-event__title" style={{ fontSize: 76 }}>
            <EditableText value={T('title', ev.title.toUpperCase())} onCommit={(v) => set('title', v)} />
          </h1>
          <p className="s-event__desc" style={{ fontSize: 30, margin: 0, maxWidth: 880 }}>
            <EditableText value={T('short', ev.short || ev.description)} onCommit={(v) => set('short', v)} />
          </p>
          <CityBlock size={120} />
          <div className="s-meta-row" style={{ fontSize: 24, marginTop: 2, gap: 12 }}>
            <span className="s-stamp s-stamp--ink" style={{ fontSize: 22 }}>► {ev.venue}</span>
            <span style={{ opacity: .7 }}>СТАРТ {ev.time}</span>
          </div>
        </div>

        <Stub />
      </div>
    </div>
  );
}
WeeklyEvent.variants = ['Афиша', 'Билет', 'Индекс'];
WeeklyEvent.layers = ['grain', 'halftone', 'tape', 'stamps'];

/* ── OUTRO ── */
function WeeklyOutro({ ctx }) {
  const { T, set, layers } = ctx;
  const S = window.YB_DATA.site;
  return (
    <div className="slide acc-cyan" style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
      <Grain on={layers.grain} />
      <Halftone on={layers.halftone} corner />
      <TickerStrip />
      <Tape on={layers.tape} color="magenta" style={{ top: 360, right: -40, width: 280, height: 46, transform: 'rotate(7deg)' }} />
      <div style={{ position: 'relative', zIndex: 4, padding: 72, flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 40 }}>
        <EditableText className="s-eyebrow" value={T('eyebrow', 'ЭТО ВСЁ. НА ЭТОЙ НЕДЕЛЕ.')} onCommit={(v) => set('eyebrow', v)} single style={{ fontSize: 26 }} />
        <h1 className="s-display" style={{ fontSize: 130 }}>
          <EditableText value={T('line1', 'БИЛЕТЫ')} onCommit={(v) => set('line1', v)} single style={{ display: 'block' }} />
          <RisoText value={T('line2', 'И ПОДРОБНОСТИ')} onCommit={(v) => set('line2', v)} shadowColor="var(--magenta)" style={{ color: 'var(--cyan-deep)' }} />
        </h1>
        <div className="s-stamp s-stamp--lg s-stamp--yellow-bg" style={{ alignSelf: 'flex-start', fontSize: 34, padding: '16px 26px', transform: 'rotate(-1.5deg)', boxShadow: '6px 6px 0 var(--ink)' }}>
          <EditableText value={T('link', '★ ССЫЛКА В ШАПКЕ ПРОФИЛЯ ★')} onCommit={(v) => set('link', v)} single />
        </div>
      </div>
      <div style={{ position: 'relative', zIndex: 4, padding: '0 72px 72px', display: 'flex', flexDirection: 'column', gap: 24 }}>
        <BrandLockup on={layers.stamps} />
        <FooterChrome layers={layers.stamps} />
      </div>
    </div>
  );
}
WeeklyOutro.variants = ['Классика'];
WeeklyOutro.layers = ['grain', 'halftone', 'tape', 'stamps'];

Object.assign(window, { WeeklyCover, WeeklyBoard, WeeklyEvent, WeeklyOutro, TickerStrip, DateStamp });
