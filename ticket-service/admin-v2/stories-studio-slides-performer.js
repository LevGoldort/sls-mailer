/* Performer spotlight: intro · bio · upcoming shows · content · merch */
const { Grain, Halftone, Tape, EditableText, RisoText, ImageSlot,
        BrandBox, BrandLockup, FooterChrome, SwipeHint, StubMeta } = window;

function PerfSocials({ socials, layers }) {
  if (!layers) return null;
  const items = [];
  if (socials.ig) items.push(['IG', socials.ig]);
  if (socials.tg) items.push(['TG', socials.tg]);
  if (socials.yt) items.push(['YT', socials.yt]);
  if (socials.fb) items.push(['FB', socials.fb]);
  return (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
      {items.map(([k], i) => (
        <span key={k} className="s-social-chip" style={{ transform: `rotate(${i % 2 ? 1.5 : -1.5}deg)` }}>{k}</span>
      ))}
    </div>
  );
}

/* ── INTRO ── */
function PerfIntro({ ctx }) {
  const { T, set, img, setImg, layers, data, variant } = ctx;
  const p = data.performer;
  const NameBlock = ({ size }) => (
    <h1 className="s-event__title" style={{ fontSize: size, lineHeight: .86 }}>
      <RisoText value={T('name', p.name)} onCommit={(v) => set('name', v)} shadowColor="var(--cyan)" style={{ color: 'var(--magenta)' }} />
    </h1>
  );

  if (variant === 1) {
    /* type-forward, portrait as inset */
    return (
      <div className="slide acc-magenta" style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
        <Grain on={layers.grain} />
        <Halftone on={layers.halftone} corner />
        <div style={{ position: 'relative', zIndex: 4, padding: 72, display: 'flex', flexDirection: 'column', height: '100%', gap: 30 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <BrandBox />
            <span className="s-stamp s-stamp--lg s-stamp--yellow-bg" style={{ transform: 'rotate(3deg)' }}>★ ARTIST ★</span>
          </div>
          <EditableText className="s-eyebrow" value={T('role', p.role)} onCommit={(v) => set('role', v)} single style={{ fontSize: 24 }} />
          <NameBlock size={132} />
          <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
            <ImageSlot value={img('photo') || p.photo} onChange={(v) => setImg('photo', v)} label={'ПОРТРЕТ'}
              cropW={800} cropH={1000} style={{ position: 'absolute', inset: 0, boxShadow: '12px 12px 0 var(--ink)' }} />
            <Halftone on={layers.halftone} style={{ inset: 0, zIndex: 2 }} />
            <div style={{ position: 'absolute', bottom: 24, left: 24, zIndex: 3 }}>
              <span className="s-stamp s-stamp--lg" style={{ background: 'rgba(26,20,16,.6)', color: 'var(--paper)', borderColor: 'var(--paper)' }}>{p.city}</span>
            </div>
          </div>
          <p className="s-event__desc" style={{ fontSize: 30, margin: 0 }}>
            <EditableText value={T('tagline', p.tagline)} onCommit={(v) => set('tagline', v)} />
          </p>
          <PerfSocials socials={p.socials} layers={layers.stamps} />
        </div>
      </div>
    );
  }

  /* variant 0 — portrait dominant top */
  return (
    <div className="slide acc-magenta" style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
      <Grain on={layers.grain} />
      <div style={{ position: 'relative', height: '56%', minHeight: 0 }}>
        <ImageSlot value={img('photo') || p.photo} onChange={(v) => setImg('photo', v)} label="ПОРТРЕТ ИСПОЛНИТЕЛЯ"
          cropW={1080} cropH={1080} style={{ width: '100%', height: '100%', border: 'none', borderBottom: '5px solid var(--ink)' }} />
        <Halftone on={layers.halftone} style={{ inset: 0, zIndex: 2 }} />
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(26,20,16,0) 55%, rgba(26,20,16,.55) 100%)' }} aria-hidden="true" />
        {layers.stamps && (
          <div style={{ position: 'absolute', top: 36, left: 36, zIndex: 4 }}>
            <span className="s-stamp s-stamp--lg s-stamp--yellow-bg" style={{ transform: 'rotate(-4deg)', boxShadow: '4px 4px 0 var(--ink)' }}>★ ARTIST ★</span>
          </div>
        )}
        <Tape on={layers.tape} color="cyan" style={{ top: 18, right: 60, width: 220, height: 42, transform: 'rotate(5deg)', zIndex: 5 }} />
        <div style={{ position: 'absolute', bottom: 28, right: 32, zIndex: 4 }}>
          <span className="s-stamp" style={{ background: 'rgba(26,20,16,.6)', color: 'var(--paper)', borderColor: 'var(--paper)' }}>{p.city}</span>
        </div>
      </div>
      <Halftone on={layers.halftone} corner />
      <div style={{ position: 'relative', zIndex: 4, padding: '46px 64px 64px', flex: 1, display: 'flex', flexDirection: 'column', gap: 22 }}>
        <EditableText className="s-eyebrow" value={T('role', p.role)} onCommit={(v) => set('role', v)} single style={{ fontSize: 24 }} />
        <NameBlock size={118} />
        <p className="s-event__desc" style={{ fontSize: 28, margin: 0 }}>
          <EditableText value={T('tagline', p.tagline)} onCommit={(v) => set('tagline', v)} />
        </p>
        <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 16 }}>
          <PerfSocials socials={p.socials} layers={layers.stamps} />
          <span className="s-handle">{window.YB_DATA.site.handle}</span>
        </div>
      </div>
    </div>
  );
}
PerfIntro.variants = ['Портрет', 'Тайтл'];
PerfIntro.layers = ['grain', 'halftone', 'tape', 'stamps'];

/* ── BIO (photo + full bio as toast + short-bio statement) ── */
function PerfBio({ ctx }) {
  const { T, set, img, setImg, layers, data, safeBottom } = ctx;
  const p = data.performer;
  return (
    <div className="slide acc-cyan" style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
      <Grain on={layers.grain} />
      <Halftone on={layers.halftone} corner />

      {/* header */}
      <div style={{ position: 'relative', zIndex: 4, padding: '60px 64px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <BrandBox />
          <h2 className="s-display" style={{ fontSize: 92 }}>
            <RisoText value={T('heading', 'БИО')} onCommit={(v) => set('heading', v)} shadowColor="var(--magenta)" style={{ color: 'var(--ink)' }} />
          </h2>
        </div>
        <span className="s-eyebrow" style={{ fontSize: 22 }}>{T('role', p.role)}</span>
      </div>

      {/* photo with full-bio toast overlaid */}
      <div style={{ position: 'relative', zIndex: 4, margin: '34px 64px 0', flex: 1, minHeight: 0 }}>
        <ImageSlot value={img('photo') || p.photo} onChange={(v) => setImg('photo', v)} label={'ФОТО · ' + p.name}
          style={{ width: '100%', height: '100%', boxShadow: '12px 12px 0 var(--ink)' }} />
        <Halftone on={layers.halftone} style={{ inset: 0, zIndex: 2 }} />
        <Tape on={layers.tape} color="yellow" style={{ top: -16, left: 50, width: 200, height: 40, transform: 'rotate(-4deg)', zIndex: 5 }} />
        <div style={{ position: 'absolute', top: 24, right: 24, zIndex: 5 }}>
          <span className="s-stamp s-stamp--lg" style={{ background: 'rgba(26,20,16,.6)', color: 'var(--paper)', borderColor: 'var(--paper)' }}>{p.city}</span>
        </div>
        <div className="s-bio-toast">
          <div className="s-bio-toast__tag">★ КТО ЭТО</div>
          <p className="s-bio-toast__txt"><EditableText value={T('bio', p.bio)} onCommit={(v) => set('bio', v)} /></p>
        </div>
      </div>

      {/* short bio statement */}
      <div style={{ position: 'relative', zIndex: 4, padding: '34px 64px ' + safeBottom + 'px' }}>
        <p className="s-bio-short">
          «<EditableText value={T('tagline', p.tagline)} onCommit={(v) => set('tagline', v)} />»
        </p>
      </div>
    </div>
  );
}
PerfBio.variants = ['Фото + тост'];
PerfBio.layers = ['grain', 'halftone', 'tape', 'stamps'];

/* ── UPCOMING SHOWS ── */
function PerfShows({ ctx }) {
  const { T, set, layers, data, safeBottom } = ctx;
  const evs = data.events;
  return (
    <div className="slide acc-magenta" style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
      <Grain on={layers.grain} />
      <Halftone on={layers.halftone} corner />
      <div style={{ position: 'relative', zIndex: 4, padding: '72px 72px ' + safeBottom + 'px', flex: 1, display: 'flex', flexDirection: 'column', gap: 38 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <EditableText className="s-eyebrow" value={T('eyebrow', 'ГДЕ ПОЙМАТЬ ВЖИВУЮ')} onCommit={(v) => set('eyebrow', v)} single style={{ fontSize: 26 }} />
            <h2 className="s-display" style={{ fontSize: 110, marginTop: 14 }}>
              <RisoText value={T('heading', 'БЛИЖАЙШИЕ')} onCommit={(v) => set('heading', v)} shadowColor="var(--magenta)" style={{ color: 'var(--ink)' }} />
            </h2>
          </div>
          <BrandBox />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 28, justifyContent: 'center', flex: 1 }}>
          {evs.length === 0 && <div className="s-eyebrow" style={{ fontSize: 30, opacity: .6 }}>НЕТ АНОНСОВ — СКОРО ОБЪЯВИМ</div>}
          {evs.map((ev, i) => {
            const d = window.parseDate(ev.date);
            const tape = ['cyan', 'magenta', 'yellow'][i % 3];
            return (
              <div key={ev.id} className="s-list-row" style={{ position: 'relative', transform: `rotate(${i % 2 ? .5 : -.5}deg)` }}>
                <Tape on={layers.tape} color={tape} style={{ top: -16, left: 30, width: 140, height: 32, transform: 'rotate(-4deg)' }} />
                <div className="s-list-row__date">{d.num}<small>{d.monthAbbr}</small></div>
                <div style={{ minWidth: 0 }}>
                  <div className="s-list-row__title">{ev.title.toUpperCase()}</div>
                  <div className="s-list-row__sub">► {ev.venue} · {ev.city || ''}</div>
                </div>
                <div style={{ fontFamily: 'var(--f-mono)', fontSize: 26, fontWeight: 700, opacity: .7, whiteSpace: 'nowrap' }}>{ev.time}</div>
              </div>
            );
          })}
        </div>
        <FooterChrome layers={layers.stamps} />
      </div>
    </div>
  );
}
PerfShows.variants = ['Список'];
PerfShows.layers = ['grain', 'halftone', 'tape', 'stamps'];

/* ── CONTENT (latest episode) ── */
function PerfContent({ ctx }) {
  const { T, set, img, setImg, layers, data, safeBottom } = ctx;
  const ep = data.episodes[0];
  if (!ep) return <div className="slide acc-cyan" style={{ ...ctx.rootStyle, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Grain on={layers.grain} /><span className="s-eyebrow" style={{ fontSize: 30 }}>НЕТ КОНТЕНТА</span></div>;
  return (
    <div className="slide acc-cyan" style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
      <Grain on={layers.grain} />
      <div style={{ position: 'relative', height: '46%' }}>
        <ImageSlot value={img('thumb') || ep.thumbnail} onChange={(v) => setImg('thumb', v)} label={'ОБЛОЖКА · ' + ep.show}
          cropW={1280} cropH={720} style={{ width: '100%', height: '100%', border: 'none', borderBottom: '5px solid var(--ink)' }} />
        <Halftone on={layers.halftone} style={{ inset: 0, zIndex: 2 }} />
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 3 }}>
          <div className="s-playbtn" style={{ width: 150, height: 150, fontSize: 64 }}>▶</div>
        </div>
        {layers.stamps && <div style={{ position: 'absolute', top: 32, left: 32, zIndex: 4 }}><span className="s-stamp s-stamp--lg s-stamp--red s-stamp--fill" style={{ transform: 'rotate(-3deg)' }}><span>НОВЫЙ ВЫПУСК</span></span></div>}
      </div>
      <Halftone on={layers.halftone} corner />
      <div style={{ position: 'relative', zIndex: 4, padding: '48px 64px ' + safeBottom + 'px', flex: 1, display: 'flex', flexDirection: 'column', gap: 26 }}>
        <div className="s-ep-badge" style={{ fontSize: 28 }}>{ep.show} · ЭП. {ep.number} · {ep.duration}</div>
        <h1 className="s-event__title" style={{ fontSize: 96 }}>
          <RisoText value={T('title', ep.title.toUpperCase())} onCommit={(v) => set('title', v)} shadowColor="var(--magenta)" style={{ color: 'var(--ink)' }} />
        </h1>
        <p className="s-event__desc" style={{ fontSize: 38, margin: 0 }}>
          <EditableText value={T('desc', ep.description)} onCommit={(v) => set('desc', v)} />
        </p>
        <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
          <span className="s-btn s-btn--primary" style={{ fontSize: 34 }}><EditableText value={T('cta', 'СМОТРЕТЬ НА ' + ep.platform)} onCommit={(v) => set('cta', v)} single /> →</span>
          <span className="s-handle" style={{ fontSize: 24 }}>{window.YB_DATA.site.handle}</span>
        </div>
      </div>
    </div>
  );
}
PerfContent.variants = ['Классика'];
PerfContent.layers = ['grain', 'halftone', 'tape', 'stamps'];

/* ── MERCH (photo grid — 1 / 2 / 4 products) ── */
function PerfMerch({ ctx }) {
  const { T, set, img, setImg, layers, data, variant, safeBottom } = ctx;
  const count = [1, 2, 4][variant] || 1;
  const items = data.merch.filter((m) => !m.soldOut).slice(0, count);
  const size = count === 1 ? { name: 50, price: 60, desc: 30 } : count === 2 ? { name: 34, price: 42, desc: 0 } : { name: 26, price: 32, desc: 0 };

  const Card = ({ m, idx }) => (
    <div className="s-merch-card" style={{ transform: `rotate(${idx % 2 ? .5 : -.5}deg)` }}>
      <div className="s-merch-card__img">
        <ImageSlot value={img('m' + idx)} onChange={(v) => setImg('m' + idx, v)} label="ФОТО ТОВАРА"
          style={{ position: 'absolute', inset: 0, border: 'none' }} />
        <Halftone on={layers.halftone} style={{ inset: 0, zIndex: 2 }} />
        <div className="s-merch-card__price" style={{ fontSize: size.price }}>{m.price}<span style={{ fontSize: '.5em' }}>₪</span></div>
      </div>
      <div className="s-merch-card__body">
        <div className="s-merch-card__name" style={{ fontSize: size.name }}>{m.name}</div>
        {size.desc ? <div className="s-merch-card__desc" style={{ fontSize: size.desc }}>{m.short}</div> : null}
      </div>
    </div>
  );

  return (
    <div className="slide acc-yellow" style={{ ...ctx.rootStyle, display: 'flex', flexDirection: 'column' }}>
      <Grain on={layers.grain} />
      <Halftone on={layers.halftone} corner />
      <Tape on={layers.tape} color="magenta" style={{ top: 130, right: -30, width: 250, height: 44, transform: 'rotate(6deg)' }} />
      <div style={{ position: 'relative', zIndex: 4, padding: '64px 64px ' + safeBottom + 'px', flex: 1, display: 'flex', flexDirection: 'column', gap: 28 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <EditableText className="s-eyebrow" value={T('eyebrow', 'ПОДДЕРЖИ КОМИКА')} onCommit={(v) => set('eyebrow', v)} single style={{ fontSize: 26 }} />
            <h2 className="s-display" style={{ fontSize: 120, marginTop: 12 }}>
              <RisoText value={T('heading', 'МЕРЧ')} onCommit={(v) => set('heading', v)} shadowColor="var(--magenta)" style={{ color: 'var(--ink)' }} />
            </h2>
          </div>
          <BrandBox />
        </div>
        <div className={'s-merch-grid s-merch-grid--' + count}>
          {items.map((m, i) => <Card key={m.id} m={m} idx={i} />)}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
          <span className="s-btn s-btn--primary" style={{ fontSize: 32 }}><EditableText value={T('cta', 'ВСЁ В МАГАЗИНЕ')} onCommit={(v) => set('cta', v)} single /> →</span>
          <FooterChrome layers={layers.stamps} />
        </div>
      </div>
    </div>
  );
}
PerfMerch.variants = ['1 товар', '2 товара', '4 товара'];
PerfMerch.layers = ['grain', 'halftone', 'tape', 'stamps'];

Object.assign(window, { PerfIntro, PerfBio, PerfShows, PerfContent, PerfMerch, PerfSocials });
