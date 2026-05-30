/* Standalone recipes: single event · content drop · merch drop */
const { Grain, Halftone, Tape, EditableText, RisoText, ImageSlot,
        BrandBox, BrandLockup, FooterChrome, SwipeHint, StubMeta,
        TickerStrip, DateStamp } = window;

/* ── SINGLE EVENT ANNOUNCEMENT ── */
function EventSolo({ ctx }) {
  const { T, set, img, setImg, layers, data, variant } = ctx;
  const ev = data.event;
  const d = window.parseDate(ev.date);
  const isExternal = ev.type === 'external';
  const accentVar = { magenta: 'var(--magenta)', cyan: 'var(--cyan)', yellow: 'var(--yellow)' }[ctx.accent] || 'var(--magenta)';

  const MetaGrid = () => (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0, border: '4px solid var(--ink)', boxShadow: '8px 8px 0 var(--ink)' }}>
      {[['ДАТА', `${d.day} ${d.monthGen}`], ['ВРЕМЯ', `СТАРТ ${ev.time}`], ['ПЛОЩАДКА', ev.venue], ['АДРЕС', ev.address]].map(([l, v], i) => (
        <div key={i} style={{ padding: '20px 22px', borderRight: i % 2 === 0 ? '4px solid var(--ink)' : 'none', borderBottom: i < 2 ? '4px solid var(--ink)' : 'none' }}>
          <div style={{ fontFamily: 'var(--f-mono)', fontSize: 16, letterSpacing: '.14em', opacity: .6, textTransform: 'uppercase' }}>{l}</div>
          <div style={{ fontFamily: 'var(--f-body)', fontWeight: 900, fontSize: 26, marginTop: 6 }}>{v}</div>
        </div>
      ))}
    </div>
  );

  /* variant 1 — type-forward (no image) */
  if (variant === 1) {
    return (
      <div className={'slide acc-' + ctx.accent} style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
        <Grain on={layers.grain} />
        <Halftone on={layers.halftone} corner />
        <TickerStrip />
        <Tape on={layers.tape} color="yellow" style={{ top: 150, left: -30, width: 250, height: 44, transform: 'rotate(-6deg)' }} />
        <div style={{ position: 'relative', zIndex: 4, padding: 72, flex: 1, display: 'flex', flexDirection: 'column', gap: 30 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ transform: 'rotate(-3deg)' }}><DateStamp iso={ev.date} accentVar={accentVar} /></div>
            {layers.stamps && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
                {(ev.tags || []).map((tg, i) => <span key={i} className={'s-stamp ' + (i ? 's-stamp--cyan' : 's-stamp--magenta')} style={{ transform: `rotate(${i ? 2 : -2}deg)` }}>{tg}</span>)}
                {isExternal && <span className="s-stamp s-stamp--red" style={{ transform: 'rotate(3deg)' }}>EXTERNAL</span>}
              </div>
            )}
          </div>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 26 }}>
            <h1 className="s-event__title" style={{ fontSize: 116 }}>
              <RisoText value={T('title', ev.title.toUpperCase())} onCommit={(v) => set('title', v)} shadowColor={accentVar} style={{ color: 'var(--ink)' }} />
            </h1>
            <p className="s-event__desc" style={{ fontSize: 32, margin: 0 }}><EditableText value={T('short', ev.short || ev.description)} onCommit={(v) => set('short', v)} /></p>
          </div>
          <MetaGrid />
          <span className="s-btn s-btn--yellow s-btn--full" style={{ fontSize: 32 }}><EditableText value={T('cta', ev.ctaLabel || 'БИЛЕТЫ НА САЙТЕ')} onCommit={(v) => set('cta', v)} single /> →</span>
          <FooterChrome layers={layers.stamps} />
        </div>
      </div>
    );
  }

  /* overlaid pill (paper text on translucent ink) */
  const Pill = ({ children, accent }) => (
    <span className="s-stamp s-stamp--lg" style={{ background: accent ? accentVar : 'rgba(26,20,16,.55)', color: 'var(--paper)', borderColor: 'var(--paper)' }}>{children}</span>
  );

  /* variant 0 — FULL-BLEED POSTER (everything on the photo) */
  return (
    <div className={'slide acc-' + ctx.accent} style={{ ...ctx.rootStyle, position: 'relative', display: 'flex', flexDirection: 'column' }}>
      <div style={{ position: 'absolute', inset: 0 }}>
        <ImageSlot value={img('photo')} onChange={(v) => setImg('photo', v)} label={'ФОТО · ' + ev.venue}
          style={{ width: '100%', height: '100%', border: 'none' }} />
      </div>
      <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(26,20,16,.55) 0%, rgba(26,20,16,.05) 32%, rgba(26,20,16,.18) 52%, rgba(26,20,16,.92) 100%)', zIndex: 2 }} aria-hidden="true" />
      <Halftone on={layers.halftone} corner />

      <div style={{ position: 'relative', zIndex: 4, padding: 60, flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
        {/* top — date stamp + tags */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 18 }}>
          <div style={{ transform: 'rotate(-4deg)' }}><DateStamp iso={ev.date} accentVar={accentVar} /></div>
          {layers.stamps && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'flex-end' }}>
              {(ev.tags || []).map((tg, i) => <span key={i} className={'s-stamp s-stamp--lg ' + (i ? 's-stamp--cyan' : 's-stamp--magenta')} style={{ background: 'var(--paper)', transform: `rotate(${i ? 2.5 : -2.5}deg)` }}>{tg}</span>)}
              {isExternal && <span className="s-stamp s-stamp--lg s-stamp--red" style={{ background: 'var(--paper)', transform: 'rotate(3deg)' }}>EXTERNAL</span>}
            </div>
          )}
        </div>

        <Tape on={layers.tape} color="yellow" style={{ position: 'static', alignSelf: 'flex-start', width: 230, height: 42, transform: 'rotate(-3deg)', marginBottom: -6, marginLeft: 16 }} />

        {/* bottom — everything overlaid on the photo */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 26 }}>
          <h1 className="s-event__title" style={{ fontSize: 90, color: 'var(--paper)', textShadow: '5px 5px 0 var(--ink)' }}>
            <EditableText value={T('title', ev.title.toUpperCase())} onCommit={(v) => set('title', v)} />
          </h1>
          <p className="s-event__desc" style={{ fontSize: 28, color: 'var(--paper)', margin: 0, maxWidth: 880, textShadow: '0 2px 8px rgba(0,0,0,.6)' }}>
            <EditableText value={T('short', ev.short || ev.description)} onCommit={(v) => set('short', v)} />
          </p>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center' }}>
            <Pill accent>СТАРТ {ev.time}</Pill>
            <Pill>► {ev.venue}</Pill>
            <Pill>{ev.address}</Pill>
            {ev.price ? <Pill>ВХОД {ev.price}₪</Pill> : null}
          </div>
          <span className="s-btn s-btn--yellow s-btn--full" style={{ fontSize: 32 }}><EditableText value={T('cta', ev.ctaLabel || 'БИЛЕТЫ НА САЙТЕ')} onCommit={(v) => set('cta', v)} single /> →</span>
          <FooterChrome layers={layers.stamps} />
        </div>
      </div>
    </div>
  );
}
EventSolo.variants = ['Афиша', 'Типографика'];
EventSolo.layers = ['grain', 'halftone', 'tape', 'stamps'];

/* ── CONTENT DROP ── */
function ContentDrop({ ctx }) {
  const { T, set, img, setImg, layers, data } = ctx;
  const ep = data.episode;
  const perfs = data.performers || [];
  const vs = perfs.slice(0, 2).map((p) => p.name).join('  ✦  ');
  return (
    <div className="slide acc-magenta" style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
      <Grain on={layers.grain} />
      <Halftone on={layers.halftone} corner />
      <TickerStrip />
      <div style={{ position: 'relative', zIndex: 4, padding: 64, flex: 1, display: 'flex', flexDirection: 'column', gap: 30 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="s-ep-badge" style={{ fontSize: 22 }}>{ep.show} · ЭП. {ep.number}</span>
          {layers.stamps && <span className="s-stamp s-stamp--lg s-stamp--red s-stamp--fill" style={{ transform: 'rotate(3deg)' }}><span>★ НОВЫЙ ВЫПУСК ★</span></span>}
        </div>
        <div style={{ position: 'relative', aspectRatio: '16/9', minHeight: 0, boxShadow: '12px 12px 0 var(--ink)', border: '5px solid var(--ink)' }}>
          <ImageSlot value={img('thumb')} onChange={(v) => setImg('thumb', v)} label="ОБЛОЖКА ВЫПУСКА" style={{ position: 'absolute', inset: 0, border: 'none' }} />
          <Halftone on={layers.halftone} style={{ inset: 0, zIndex: 2 }} />
          <Tape on={layers.tape} color="yellow" style={{ top: -16, left: 40, width: 180, height: 36, transform: 'rotate(-4deg)', zIndex: 5 }} />
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 3 }}><div className="s-playbtn">▶</div></div>
        </div>
        <h1 className="s-event__title" style={{ fontSize: 92 }}>
          <RisoText value={T('show', ep.show)} onCommit={(v) => set('show', v)} shadowColor="var(--cyan)" style={{ color: 'var(--magenta)' }} />
        </h1>
        <div style={{ fontFamily: 'var(--f-display)', fontSize: 40, textTransform: 'uppercase', lineHeight: 1.05 }}>
          <EditableText value={T('title', ep.title)} onCommit={(v) => set('title', v)} />
        </div>
        <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
          <span className="s-btn s-btn--primary" style={{ fontSize: 28 }}><EditableText value={T('cta', 'СМОТРЕТЬ НА ' + ep.platform)} onCommit={(v) => set('cta', v)} single /> →</span>
          <span className="s-handle">{window.YB_DATA.site.handle}</span>
        </div>
      </div>
    </div>
  );
}
ContentDrop.variants = ['Классика'];
ContentDrop.layers = ['grain', 'halftone', 'tape', 'stamps'];

/* ── MERCH DROP ── */
function MerchDrop({ ctx }) {
  const { T, set, img, setImg, layers, data, variant } = ctx;
  const m = data.product;
  const sold = variant === 1 || m.soldOut;
  const accentVar = sold ? 'var(--red)' : 'var(--magenta)';
  return (
    <div className={'slide ' + (sold ? 'acc-magenta' : 'acc-cyan')} style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
      <div style={{ position: 'relative', height: '58%' }}>
        <ImageSlot value={img('photo')} onChange={(v) => setImg('photo', v)} label="ФОТО ТОВАРА"
          style={{ width: '100%', height: '100%', border: 'none', borderBottom: '5px solid var(--ink)' }} />
        <Halftone on={layers.halftone} style={{ inset: 0, zIndex: 2 }} />
        {sold && <div style={{ position: 'absolute', inset: 0, background: 'rgba(26,20,16,.5)', zIndex: 2 }} aria-hidden="true" />}
        {sold
          ? <div style={{ position: 'absolute', top: '46%', left: '50%', transform: 'translate(-50%,-50%) rotate(-8deg)', zIndex: 4 }}><div className="s-soldout" style={{ fontSize: 64 }}>★ SOLD OUT ★</div></div>
          : (layers.stamps && <div style={{ position: 'absolute', top: 36, left: 36, zIndex: 4 }}><span className="s-stamp s-stamp--lg s-stamp--red s-stamp--fill" style={{ transform: 'rotate(-4deg)' }}><span>★ DROP ★</span></span></div>)}
        <div style={{ position: 'absolute', bottom: 28, right: 28, zIndex: 4 }}>
          <div className="s-price-sticker" style={{ fontSize: 72, transform: 'rotate(5deg)' }}><EditableText value={T('price', String(m.price))} onCommit={(v) => set('price', v)} single />₪</div>
        </div>
        <Tape on={layers.tape} color="cyan" style={{ top: 18, right: 70, width: 200, height: 40, transform: 'rotate(5deg)', zIndex: 5 }} />
      </div>
      <Grain on={layers.grain} />
      <Halftone on={layers.halftone} corner />
      <div style={{ position: 'relative', zIndex: 4, padding: '44px 64px 60px', flex: 1, display: 'flex', flexDirection: 'column', gap: 22 }}>
        <EditableText className="s-eyebrow" value={T('eyebrow', sold ? 'РАСХВАТАЛИ ЗА ЧАС' : 'НОВИНКА В МАГАЗИНЕ')} onCommit={(v) => set('eyebrow', v)} single style={{ fontSize: 24 }} />
        <h1 className="s-event__title" style={{ fontSize: 70 }}>
          <RisoText value={T('name', m.name)} onCommit={(v) => set('name', v)} shadowColor={accentVar} style={{ color: 'var(--ink)' }} />
        </h1>
        <p className="s-event__desc" style={{ fontSize: 28, margin: 0 }}><EditableText value={T('short', m.short)} onCommit={(v) => set('short', v)} /></p>
        <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
          {sold
            ? <span className="s-btn" style={{ fontSize: 28, background: 'var(--ink)', color: 'var(--red)', boxShadow: '6px 6px 0 var(--magenta)' }}>РАСПРОДАНО</span>
            : <span className="s-btn s-btn--primary" style={{ fontSize: 28 }}><EditableText value={T('cta', 'КУПИТЬ')} onCommit={(v) => set('cta', v)} single /> →</span>}
          <span className="s-handle">{window.YB_DATA.site.handle}</span>
        </div>
      </div>
    </div>
  );
}
MerchDrop.variants = ['В продаже', 'Sold out'];
MerchDrop.layers = ['grain', 'halftone', 'tape', 'stamps'];

Object.assign(window, { EventSolo, ContentDrop, MerchDrop });
