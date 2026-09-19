const load = (key) => { try { return JSON.parse(localStorage.getItem(key)) } catch { return null } };
const store = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)) } catch {} };

// Dates are local-time "YYYY-MM-DD" strings; parsing them with new Date(iso) would use UTC.
const todayISO = () => new Date().toLocaleDateString("en-CA");
const parseISO = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d) };
const toISO = (date) => date.toLocaleDateString("en-CA");

// The page's language picks both the UI strings and the word list, so each language
// has its own daily puzzle and its own saved games.
const LANG = document.documentElement.lang;
const gameKey = (iso) => `slid:${LANG}:${iso}`;

// UI strings come from the server (index.html) in the picked language; see slid/i18n.py.
const I18N = window.I18N ?? {};
const t = (key, vars = {}) => (I18N[key] ?? key).replace(/\{(\w+)\}/g, (_, name) => vars[name]);
const movesWord = (n) => t(n === 1 ? "move_one" : "move_other");
// Dates follow the picked language. For English, keep the browser's own English variant
// (en-GB writes dd/mm/yyyy, en-US mm/dd/yyyy).
const LOCALE = LANG === "en"
  ? navigator.languages.find((l) => l.startsWith("en")) ?? "en-US"
  : LANG;

// Only called when the player picks a language, so detection keeps working until they do.
function setLanguage(lang) {
  if (lang === LANG) return;
  document.cookie = `slid_lang=${encodeURIComponent(lang)}; path=/; max-age=31536000; samesite=lax`;
  // Drop a ?lang= from a shared link, or it would keep overriding the choice.
  location.replace(location.pathname);
}

// Every URL gets the same page shell and the view is picked here: "/" is today's puzzle,
// "/19" is game #19, "/calendar" is the past-games page. Dated URLs ("/2026-09-19") still work
// for old links. Game numbers count days from launch, which is #1.
const CALENDAR = "/calendar";
const LAUNCH = document.documentElement.dataset.launch;
const DAY_MS = 864e5;
// Rounded, so a daylight-saving change between the two dates can't shift the count.
const numberOf = (iso) => Math.round((parseISO(iso) - parseISO(LAUNCH)) / DAY_MS) + 1;
const dateOf = (number) => { const d = parseISO(LAUNCH); d.setDate(d.getDate() + number - 1); return toISO(d) };
function pathDate() {
  const path = location.pathname.slice(1);
  if (/^\d{4}-\d{2}-\d{2}$/.test(path)) return path;
  if (/^[1-9]\d*$/.test(path)) return dateOf(Number(path));
  return todayISO();
}
const dayURL = (iso) => (iso === todayISO() ? "/" : `/${numberOf(iso)}`);
const currentView = () => (location.pathname === CALENDAR ? "calendar" : "board");

function render() {
  const show = (view) => {
    Alpine.store("view", view);
    scrollTo(0, 0);
  };
  if (currentView() === "calendar") {
    document.title = `Slid · ${t("past_games")}`;
    show("calendar");
  } else {
    // Switch views only once the new board is in, so the previous one never flashes.
    // The board is asked for in the page's language, which may come from a shared link's ?lang=.
    htmx.ajax("GET", `/board?date=${pathDate()}&lang=${encodeURIComponent(LANG)}`, "#game").then(() => show("board"));
  }
}

function navigate(url) {
  if (location.pathname !== url) history.pushState(null, "", url);
  render();
}
const openDay = (iso) => navigate(dayURL(iso));

// Back/forward: the URL has already changed, so just render whatever it names.
addEventListener("popstate", render);
document.addEventListener("DOMContentLoaded", render);

if ("serviceWorker" in navigator) {
  addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}

// Phone/tablet vs desktop, by operating system rather than pointer type: stylus phones such as
// Samsung's S Pen models report a fine, hovering pointer, just like a mouse.
const isMobileOS = () =>
  navigator.userAgentData?.mobile ||
  /Android|iPhone|iPad|iPod/i.test(navigator.userAgent) ||
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1); // iPadOS identifies as a Mac
// Lets CSS pick the swipe hint over the keyboard one (see .hint-touch in style.css).
document.documentElement.classList.toggle("mobile", Boolean(isMobileOS()));

// Days in a row solved on the day itself, in this language: solving a past game later doesn't
// count. While today is still unsolved the streak runs up to yesterday, so it isn't lost yet.
function streak() {
  const onTime = (iso) => {
    const game = load(gameKey(iso));
    return game?.status === "won" && (!game.solvedOn || game.solvedOn === iso); // older saves have no date
  };
  const day = parseISO(todayISO());
  const today = onTime(toISO(day));
  if (!today) day.setDate(day.getDate() - 1);
  let count = 0;
  while (onTime(toISO(day))) {
    count++;
    day.setDate(day.getDate() - 1);
  }
  return { count, today };
}
function streakTitle() {
  const { count, today } = Alpine.store("streak");
  const label = t(count === 1 ? "streak_one" : "streak_other", { n: count });
  return today ? label : `${label}. ${t("streak_pending")}`;
}

// Share grid: how often you moved the tile in each spot, like a heatmap of where you worked.
const HEAT = ["⬜", "🟨", "🟨", "🟧", "🟧", "🟧"]; // by moves out of a spot; 6 or more is 🟥

// Cuelume loads as an ES module and sets window.cuelume; until then this is a no-op.
const sfx = (name, volume = 1) => window.cuelume?.play(name, { volume });

// Words this short only count when the gap shares their line (GAP_RULE_LENGTH in puzzle.py).
const GAP_RULE_LENGTH = 3;

// Directions a tile travels, as [row, col] steps. Keys and swipes both name one:
// ArrowUp (or swiping up) moves the tile *below* the gap up into it.
const DIRS = { up: [-1, 0], down: [1, 0], left: [0, -1], right: [0, 1] };
const KEYS = {
  ArrowUp: "up", w: "up", W: "up",
  ArrowDown: "down", s: "down", S: "down",
  ArrowLeft: "left", a: "left", A: "left",
  ArrowRight: "right", d: "right", D: "right",
};
// How far a finger has to travel before it counts as a swipe rather than a tap.
const SWIPE_MIN = 24;

document.addEventListener("alpine:init", () => {
  Alpine.store("view", currentView());
  Alpine.store("streak", streak());
  addEventListener("slid-update", () => Alpine.store("streak", streak()));

  // Tiles keep an id (their order in the starting board) and move between cells, so the
  // DOM node for a letter stays the same and CSS can animate it to its new spot.
  Alpine.data("slid", (cfg) => ({
    ...cfg,
    storeKey: "",
    pos: [],     // pos[id] = cell the tile sits in
    moves: 0,
    hits: [],    // cells spelling the word, in reading order; non-empty means solved
    shake: null,
    swipe: null,  // the touch in progress: where it started and on which tile
    swipedAt: 0,
    ready: false,
    copied: false,
    now: Date.now(),
    touches: null, // touches[cell] = tiles moved out of that spot; null for games saved before it was tracked
    solvedOn: null, // the local date the word was solved, for streaks

    init() {
      this.storeKey = gameKey(this.date);
      this.letters = [...this.start].filter((ch) => ch !== ".");
      const startPos = [...this.start].flatMap((ch, cell) => (ch === "." ? [] : [cell]));
      const saved = load(this.storeKey);
      const valid = Array.isArray(saved?.pos) && saved.pos.length === startPos.length;
      this.pos = valid ? saved.pos : startPos;
      this.moves = valid ? saved.moves : 0;
      const tracked = valid && Array.isArray(saved.touches) && saved.touches.length === this.size;
      this.touches = tracked ? saved.touches : this.moves === 0 ? Array(this.size).fill(0) : null;
      this.solvedOn = (valid && saved.solvedOn) || null;
      this.check();
      this.clock = setInterval(() => (this.now = Date.now()), 1000);
      // Turn transitions on after the saved layout is painted, so reloading doesn't animate it.
      requestAnimationFrame(() => requestAnimationFrame(() => (this.ready = true)));
      // A finished game (reload, or reopened from the calendar) shows its result right away;
      // one that ends during play pops it after the word has had a moment to light up.
      if (this.won) this.$nextTick(() => this.showResult());
      this.$watch("won", (won) => won && setTimeout(() => this.showResult(), 1100));
      document.title = `Slid #${this.number}`;
      this.$dispatch("slid-open", this.date);
    },

    destroy() { clearInterval(this.clock) },

    showResult() {
      const modal = this.$refs.modal;
      if (modal.isConnected && !modal.open) modal.showModal(); // the board may have been swapped out
    },

    save() {
      if (this.won && !this.solvedOn) this.solvedOn = todayISO();
      store(this.storeKey, {
        status: this.won ? "won" : "playing",
        pos: this.pos,
        moves: this.moves,
        touches: this.touches,
        solvedOn: this.solvedOn,
      });
      this.$dispatch("slid-update");
    },

    get size() { return this.rows * this.cols },
    get gap() {
      const taken = new Set(this.pos);
      for (let cell = 0; cell < this.size; cell++) if (!taken.has(cell)) return cell;
    },
    get won() { return this.hits.length > 0 },
    get movesWord() { return movesWord(this.moves) },
    get challengeResult() {
      const key = this.moves < this.challenge ? "challenge_beaten"
        : this.moves === this.challenge ? "challenge_matched" : "challenge_missed";
      return t(key, { n: this.challenge });
    },
    get isToday() { return this.date === todayISO() },
    // dd/mm/yyyy, or whatever order and separator the browser's locale uses.
    get shortDate() {
      return parseISO(this.date).toLocaleDateString(LOCALE, { day: "2-digit", month: "2-digit", year: "numeric" });
    },
    get countdown() {
      const midnight = new Date(this.now);
      midnight.setHours(24, 0, 0, 0);
      const s = Math.max(0, Math.floor((midnight - this.now) / 1000));
      return [s / 3600, (s % 3600) / 60, s % 60].map((v) => String(Math.floor(v)).padStart(2, "0")).join(":");
    },

    // The word must read left-to-right in a row or top-to-bottom in a column,
    // mirroring word_cells() in puzzle.py.
    check() {
      const board = Array(this.size).fill(".");
      this.pos.forEach((cell, id) => (board[cell] = this.letters[id]));
      const lines = [];
      for (let r = 0; r < this.rows; r++) lines.push(Array.from({ length: this.cols }, (_, c) => r * this.cols + c));
      for (let c = 0; c < this.cols; c++) lines.push(Array.from({ length: this.rows }, (_, r) => r * this.cols + c));
      for (const line of lines) {
        const text = line.map((i) => board[i]).join("");
        if (this.word.length <= GAP_RULE_LENGTH && !text.includes(".")) continue;
        const at = text.indexOf(this.word);
        if (at !== -1) return (this.hits = line.slice(at, at + this.word.length));
      }
      this.hits = [];
    },

    adjacent(a, b) {
      const [ra, ca, rb, cb] = [Math.floor(a / this.cols), a % this.cols, Math.floor(b / this.cols), b % this.cols];
      return Math.abs(ra - rb) + Math.abs(ca - cb) === 1;
    },

    tap(id) {
      // A swipe that ends on the tile it started on also fires a click; the swipe already acted.
      if (this.won || Date.now() - this.swipedAt < 500) return;
      const [cell, gap] = [this.pos[id], this.gap];
      if (!this.adjacent(cell, gap)) return this.reject(id);
      const step = gap - cell;
      this.push(cell, Math.abs(step) === 1 ? [0, step] : [Math.sign(step), 0]);
    },

    reject(id = null) {
      sfx("error", 0.6);
      if (id === null) return;
      // Clear first so rejecting the same tile twice replays the shake.
      this.shake = null;
      this.$nextTick(() => (this.shake = id));
      setTimeout(() => this.shake === id && (this.shake = null), 320);
    },

    // Moves the tile at `cell` one step in direction [dr, dc], carrying along every tile
    // between it and the gap, so the gap must lie ahead of it in the same row or column.
    // Each tile that moves counts as one move. Returns whether anything moved.
    push(cell, [dr, dc]) {
      const line = []; // cells from `cell` up to, not including, the gap
      let [r, c] = [Math.floor(cell / this.cols), cell % this.cols];
      for (;;) {
        // Bounds first: stepping off the right edge would otherwise wrap into the next row.
        if (r < 0 || r >= this.rows || c < 0 || c >= this.cols) return false;
        if (r * this.cols + c === this.gap) break;
        line.push(r * this.cols + c);
        [r, c] = [r + dr, c + dc];
      }
      // The tile nearest the gap goes first, so each one steps into the space just vacated.
      const ids = line.map((at) => this.pos.indexOf(at));
      for (const id of ids.reverse()) this.pos[id] += dr * this.cols + dc;
      if (this.touches) for (const at of line) this.touches[at]++;
      this.moves += line.length;
      this.check();
      this.save();
      sfx(this.won ? "success" : "tick");
      return true;
    },

    // Keys and swipes that don't start on a tile move whichever tile can enter the gap from
    // the opposite side, like sliding the board in that direction.
    move(dir) {
      const [dr, dc] = DIRS[dir];
      const [r, c] = [Math.floor(this.gap / this.cols) - dr, (this.gap % this.cols) - dc];
      if (r < 0 || r >= this.rows || c < 0 || c >= this.cols) return this.reject();
      this.push(r * this.cols + c, [dr, dc]);
    },

    onKey(e) {
      const dir = KEYS[e.key];
      if (!dir || e.ctrlKey || e.metaKey || e.altKey || document.querySelector("dialog[open]")) return;
      if (Alpine.store("view") !== "board") return;
      e.preventDefault();
      if (!this.won) this.move(dir);
    },

    // Touch and pen only: the mouse keeps clicking, and a drag with it does nothing.
    swipeStart(e) {
      if (e.pointerType === "mouse" || !e.isPrimary || this.won) return;
      const id = e.target.closest(".tile")?.dataset.id;
      this.swipe = { x: e.clientX, y: e.clientY, pointer: e.pointerId, id: id === undefined ? null : Number(id) };
    },

    // Acts as soon as the finger has travelled far enough, not on release, so it feels immediate.
    // One swipe is one action, however far the finger keeps going.
    swipeMove(e) {
      const s = this.swipe;
      if (!s || e.pointerId !== s.pointer) return;
      const [dx, dy] = [e.clientX - s.x, e.clientY - s.y];
      if (Math.max(Math.abs(dx), Math.abs(dy)) < SWIPE_MIN) return;
      this.swipe = null;
      this.swipedAt = Date.now();
      const dir = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : dy > 0 ? "down" : "up";
      if (s.id === null) return this.move(dir);
      if (!this.push(this.pos[s.id], DIRS[dir])) this.reject(s.id);
    },

    place(id) {
      const cell = this.pos[id];
      const k = this.hits.indexOf(cell);
      return `--r: ${Math.floor(cell / this.cols)}; --c: ${cell % this.cols}; --k: ${k}`;
    },

    cls(id) {
      const cell = this.pos[id];
      return {
        movable: !this.won && this.adjacent(cell, this.gap),
        hit: this.hits.includes(cell),
        err: this.shake === id,
      };
    },

    label(id) {
      const cell = this.pos[id];
      return t("tile_label", { letter: this.letters[id], row: Math.floor(cell / this.cols) + 1, col: (cell % this.cols) + 1 });
    },

    // Spoiler-free: moves over the challenge, a heatmap of where you worked (the word's final
    // spot in green, never its letters), your streak, and a short link.
    get shareText() {
      const badge = this.moves < this.challenge ? " 🏆" : this.moves === this.challenge ? " 🎯" : "";
      const lines = [`Slid #${this.number}${badge} ${this.moves}/${this.challenge}`];
      if (this.touches) {
        for (let r = 0; r < this.rows; r++) {
          let row = "";
          for (let c = 0; c < this.cols; c++) {
            const cell = r * this.cols + c;
            row += this.hits.includes(cell) ? "🟩" : cell === this.gap ? "⬛" : HEAT[this.touches[cell]] ?? "🟥";
          }
          lines.push(row);
        }
      }
      const { count } = Alpine.store("streak");
      if (this.isToday && count >= 2) lines.push(t("share_streak", { n: count }));
      // Today's game links to the home page, a past one to its number. No language in the link:
      // it opens game #N in the language of whoever follows it.
      lines.push(`${location.origin}${this.isToday ? "/" : `/${this.number}`}`);
      return lines.join("\n");
    },

    async share() {
      const text = this.shareText;
      // Native share sheet on phones and tablets, clipboard on desktop
      // (desktop browsers also have navigator.share, but it opens the OS share dialog).
      if (isMobileOS() && navigator.share) {
        try {
          return await navigator.share({ text });
        } catch (err) {
          if (err.name === "AbortError") return; // user closed the sheet
        }
      }
      if (await this.copy(text)) {
        sfx("success");
        this.copied = true;
        setTimeout(() => (this.copied = false), 2000);
      }
    },

    // navigator.clipboard and navigator.share only exist on HTTPS/localhost,
    // so fall back to execCommand for plain http (e.g. testing over the LAN).
    async copy(text) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch {}
      // A modal dialog makes everything outside it inert, so the textarea goes inside it.
      const host = this.$refs.modal.open ? this.$refs.modal : document.body;
      const ta = Object.assign(document.createElement("textarea"), { value: text, readOnly: true });
      ta.style.cssText = "position:fixed;opacity:0;pointer-events:none";
      host.append(ta);
      ta.select();
      ta.setSelectionRange(0, text.length); // iOS ignores select()
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    },
  }));

  // Language menu: opens on the current language, arrows move between options,
  // Escape or a click outside closes it.
  Alpine.data("langMenu", () => ({
    open: false,
    // $root, not $el: $el is whichever element fired the event (e.g. the button).
    items() { return [...this.$root.querySelectorAll('[role="menuitemradio"]')] },
    toggle() {
      this.open = !this.open;
      if (this.open) this.focusCurrent();
    },
    // x-show's transition unhides the menu a couple of frames later, and hidden items can't take focus.
    focusCurrent(tries = 6) {
      const current = this.items().find((el) => el.ariaChecked === "true");
      if (current?.offsetParent) current.focus();
      else if (tries && this.open) requestAnimationFrame(() => this.focusCurrent(tries - 1));
    },
    close(refocus) {
      if (!this.open) return;
      this.open = false;
      if (refocus) this.$refs.button.focus();
    },
    step(delta) {
      if (!this.open) return this.toggle();
      const items = this.items();
      const i = items.indexOf(document.activeElement);
      items[(i + delta + items.length) % items.length].focus();
    },
  }));

  // How-to-play dialog: opens by itself while there are no saved games on this device.
  Alpine.data("help", () => ({
    init() {
      let played = false;
      try { played = Object.keys(localStorage).some((k) => /^slid:[\w-]+:\d{4}-\d{2}-\d{2}$/.test(k)) } catch {}
      if (!played) this.$nextTick(() => this.$refs.dialog.showModal());
    },
  }));

  // Month view of past games. Solved days open read-only (the board locks once won),
  // so they can be reviewed but not replayed.
  Alpine.data("calendar", (launch) => ({
    launch,
    today: todayISO(),
    current: todayISO(),
    month: null,
    version: 0, // bumped on every save so statuses re-read localStorage
    // Narrow weekday names in the browser's locale, Sunday first (2026-09-13 is a Sunday).
    weekdays: Array.from({ length: 7 }, (_, k) => new Date(2026, 8, 13 + k).toLocaleDateString(LOCALE, { weekday: "narrow" })),

    init() {
      const t = parseISO(this.today);
      this.month = new Date(t.getFullYear(), t.getMonth(), 1);
      this.refresh();
    },

    refresh() { this.version++ },

    status(iso) {
      this.version;
      return load(gameKey(iso))?.status ?? null;
    },

    get monthLabel() {
      const label = this.month.toLocaleDateString(LOCALE, { month: "long", year: "numeric" });
      return label[0].toUpperCase() + label.slice(1);
    },
    get canPrev() { return toISO(this.month) > this.launch },
    get canNext() { return toISO(new Date(this.month.getFullYear(), this.month.getMonth() + 1, 1)) <= this.today },
    // Called whenever a board loads, so the calendar follows direct links and back/forward.
    show(iso) {
      this.current = iso;
      const d = parseISO(iso);
      this.month = new Date(d.getFullYear(), d.getMonth(), 1);
    },

    shift(delta) { this.month = new Date(this.month.getFullYear(), this.month.getMonth() + delta, 1) },

    get days() {
      const y = this.month.getFullYear(), m = this.month.getMonth();
      const blanks = Array.from({ length: this.month.getDay() }, (_, k) => ({ key: `b${k}` }));
      const count = new Date(y, m + 1, 0).getDate();
      const days = Array.from({ length: count }, (_, k) => {
        const iso = toISO(new Date(y, m, k + 1));
        const status = this.status(iso);
        return {
          key: iso,
          iso,
          day: k + 1,
          label: `${parseISO(iso).toLocaleDateString(LOCALE, { day: "numeric", month: "long" })}: ${t(status ?? "not_played")}`,
          disabled: iso < this.launch || iso > this.today,
          cls: { [status]: !!status, today: iso === this.today, current: iso === this.current },
        };
      });
      return [...blanks, ...days];
    },

    open(iso) { openDay(iso) },
  }));
});

// Visit with ?debug for a button that clears today's saved game.
if (new URLSearchParams(location.search).has("debug")) {
  const reset = Object.assign(document.createElement("button"), { id: "debug-reset", textContent: "Reset today" });
  reset.addEventListener("click", () => {
    try { localStorage.removeItem(gameKey(todayISO())) } catch {}
    location.reload();
  });
  document.addEventListener("DOMContentLoaded", () => document.body.append(reset));
}
