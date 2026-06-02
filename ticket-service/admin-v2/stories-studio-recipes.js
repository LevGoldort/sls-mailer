/* Recipe + slide-type registries.
   A recipe turns a data subject into an ordered list of slide descriptors. */

const SLIDE_TYPES = {
  'weekly-cover':  { Comp: window.WeeklyCover,  label: 'Обложка' },
  'weekly-board':  { Comp: window.WeeklyBoard,  label: 'Все события' },
  'weekly-event':  { Comp: window.WeeklyEvent,  label: 'Событие' },
  'weekly-outro':  { Comp: window.WeeklyOutro,  label: 'Финал' },
  'perf-intro':    { Comp: window.PerfIntro,    label: 'Исполнитель' },
  'perf-bio':      { Comp: window.PerfBio,      label: 'Био' },
  'perf-shows':    { Comp: window.PerfShows,    label: 'Концерты' },
  'perf-content':  { Comp: window.PerfContent,  label: 'Контент' },
  'perf-merch':    { Comp: window.PerfMerch,    label: 'Мерч' },
  'event-solo':    { Comp: window.EventSolo,    label: 'Анонс' },
  'content-drop':  { Comp: window.ContentDrop,  label: 'Выпуск' },
  'merch-drop':    { Comp: window.MerchDrop,    label: 'Дроп' },
  'html-template': { Comp: window.HtmlTemplateSlide, label: 'HTML-шаблон' },
};

const ACCENTS = ['cyan', 'yellow', 'magenta'];

const RECIPES = [
  {
    id: 'weekly',
    label: 'Неделя',
    ico: 'W',
    subjectKind: 'none',
    build() {
      const D = window.YB_DATA;
      const events = D.events;
      const slides = [{ key: 'weekly:_:board', type: 'weekly-board', label: 'Все события', accent: 'magenta', data: { events } }];
      events.forEach((ev, i) => {
        slides.push({
          key: 'weekly:_:ev-' + ev.id,
          type: 'weekly-event',
          label: ev.venue,
          accent: ACCENTS[i % ACCENTS.length],
          data: { event: ev, index: i + 1, total: events.length },
        });
      });
      return slides;
    },
  },
  {
    id: 'performer',
    label: 'Исполнитель',
    ico: 'A',
    subjectKind: 'performer',
    build(pid) {
      const D = window.YB_DATA;
      const p = D.performerById(pid) || D.performers[0];
      const events = (p.eventIds || []).map(D.eventById).filter(Boolean);
      const episodes = (p.episodeIds || []).map(D.episodeById).filter(Boolean);
      const merch = (p.productIds || []).map(D.merchById).filter(Boolean);
      const base = 'performer:' + p.id + ':';
      const slides = [
        { key: base + 'intro', type: 'perf-intro', label: 'Исполнитель', accent: 'magenta', data: { performer: p } },
        { key: base + 'bio', type: 'perf-bio', label: 'Био', accent: 'cyan', data: { performer: p } },
      ];
      if (events.length) slides.push({ key: base + 'shows', type: 'perf-shows', label: 'Концерты', accent: 'magenta', data: { events } });
      if (episodes.length) slides.push({ key: base + 'content', type: 'perf-content', label: 'Контент', accent: 'cyan', data: { episodes } });
      if (merch.length) slides.push({ key: base + 'merch', type: 'perf-merch', label: 'Мерч', accent: 'yellow', data: { merch } });
      return slides;
    },
  },
  {
    id: 'event',
    label: 'Анонс',
    ico: 'E',
    subjectKind: 'event',
    build(eid) {
      const D = window.YB_DATA;
      const ev = D.eventById(eid) || D.events[0];
      return [{ key: 'event:' + ev.id + ':solo', type: 'event-solo', label: ev.venue, accent: 'cyan', data: { event: ev } }];
    },
  },
  {
    id: 'content',
    label: 'Выпуск',
    ico: 'C',
    subjectKind: 'episode',
    build(epid) {
      const D = window.YB_DATA;
      const ep = D.episodeById(epid) || D.episodes[0];
      const performers = (ep.performerIds || []).map(D.performerById).filter(Boolean);
      return [{ key: 'content:' + ep.id + ':drop', type: 'content-drop', label: ep.show, accent: 'magenta', data: { episode: ep, performers } }];
    },
  },
  {
    id: 'merch',
    label: 'Мерч',
    ico: 'M',
    subjectKind: 'product',
    build(mid) {
      const D = window.YB_DATA;
      const m = D.merchById(mid) || D.merch[0];
      return [{ key: 'merch:' + m.id + ':drop', type: 'merch-drop', label: m.name.slice(0, 16), accent: 'cyan', data: { product: m } }];
    },
  },
  {
    id: 'html',
    label: 'Шаблон',
    ico: 'H',
    subjectKind: 'event',
    build(eid) {
      const D = window.YB_DATA;
      const ev = D.eventById(eid) || D.events[0];
      if (!ev) return [];
      const tplId = window.__activeTemplateId || null;
      return [{
        key: 'html:' + (tplId || 'none') + ':' + ev.id,
        type: 'html-template',
        label: ev.title.slice(0, 20),
        accent: 'cyan',
        data: { event: ev, templateId: tplId },
      }];
    },
  },
];

/* subject option lists for the header dropdown */
function subjectOptions(kind) {
  const D = window.YB_DATA;
  switch (kind) {
    case 'performer': return D.performers.map((p) => ({ id: p.id, label: p.name }));
    case 'event': {
      const today = new Date().toISOString().slice(0, 10);
      return D.events
        .filter(e => e.date >= today)
        .sort((a, b) => a.date.localeCompare(b.date))
        .map(e => ({ id: e.id, label: window.parseDate(e.date).num + '.' + window.parseDate(e.date).monthAbbr + ' · ' + e.venue }));
    }
    case 'episode':   return D.episodes.map((e) => ({ id: e.id, label: e.show + ' · ЭП.' + e.number }));
    case 'product':   return D.merch.map((m) => ({ id: m.id, label: m.name }));
    default:          return [];
  }
}

const FORMATS = {
  story:    { label: 'Story 9:16', w: 1080, h: 1920 },
  portrait: { label: 'Post 4:5', w: 1080, h: 1350 },
  square:   { label: 'Post 1:1', w: 1080, h: 1080 },
};

Object.assign(window, { SLIDE_TYPES, RECIPES, subjectOptions, FORMATS });
