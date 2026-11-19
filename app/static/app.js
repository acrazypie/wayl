/* WAYL front end: a small single-page app, no build step.
 * Rule: never use innerHTML with data. Everything is built with h(), so user-supplied text
 * (song titles, usernames, bios...) always ends up in text nodes. */
(() => {
    "use strict";

    // --- DOM helpers ----------------------------------------------------------------

    function h(tag, attrs = {}, ...children) {
        const node = document.createElement(tag);
        for (const [key, value] of Object.entries(attrs || {})) {
            if (value === null || value === undefined || value === false) continue;
            if (key === "class") node.className = value;
            else if (key.startsWith("on") && typeof value === "function")
                node.addEventListener(key.slice(2), value);
            else node.setAttribute(key, value === true ? "" : value);
        }
        append(node, children);
        return node;
    }

    function append(node, children) {
        for (const child of children.flat(Infinity)) {
            if (child === null || child === undefined || child === false) continue;
            node.append(child instanceof Node ? child : document.createTextNode(String(child)));
        }
        return node;
    }

    function clear(node, ...children) {
        node.replaceChildren();
        return append(node, children);
    }

    const SVG_NS = "http://www.w3.org/2000/svg";
    const ICONS = {
        search: ["c:11,11,7", "m20 20-3.5-3.5"],
        users: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "c:9,7,4", "M22 21v-2a4 4 0 0 0-3-3.87", "M16 3.13a4 4 0 0 1 0 7.75"],
        playlist: ["M21 15V6", "c:18.5,15.5,2.5", "M12 12H3", "M16 6H3", "M12 18H3"],
        music: ["M9 18V5l12-2v13", "c:6,18,3", "c:18,16,3"],
        user: ["c:12,8,4", "M4 21a8 8 0 0 1 16 0"],
        heart: ["M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"],
        headphones: ["M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"],
        plus: ["M12 5v14", "M5 12h14"],
        trash: ["M3 6h18", "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6", "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"],
        x: ["M18 6 6 18", "m6 6 12 12"],
        external: ["M15 3h6v6", "M10 14 21 3", "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"],
        eye: ["M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z", "c:12,12,3"],
        eyeOff: ["m3 3 18 18", "M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.2", "M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a10 10 0 0 0 5.4-1.6", "M9.9 9.9a3 3 0 0 0 4.2 4.2"],
        lock: ["r:3,11,18,11,2", "M7 11V7a5 5 0 0 1 10 0v4"],
        logout: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "m16 17 5-5-5-5", "M21 12H9"],
        link: ["M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7", "M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"],
        edit: ["M12 20h9", "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"],
        activity: ["M22 12h-4l-3 9L9 3l-3 9H2"],
        disc: ["c:12,12,10", "c:12,12,2"],
        play: ["m7 4 13 8-13 8z"],
        userPlus: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "c:9,7,4", "M19 8v6", "M22 11h-6"],
        check: ["M20 6 9 17l-5-5"],
        server: ["r:2,13,20,8,2", "M2 13 5.5 5h13L22 13", "M6 17h.01", "M10 17h.01"],
        pause: ["r:6,4,4,16,1", "r:14,4,4,16,1"],
        skipNext: ["m5 4 10 8-10 8z", "M19 5v14"],
        skipPrev: ["m19 20-10-8 10-8z", "M5 19V5"],
        sliders: ["M4 21v-7", "M4 10V3", "M12 21v-9", "M12 8V3", "M20 21v-5", "M20 12V3", "M1 14h6", "M9 8h6", "M17 16h6"],
        refresh: ["M21 12a9 9 0 1 1-3-6.7L21 8", "M21 3v5h-5"],
        key: ["c:7.5,15.5,5.5", "m21 2-9.6 9.6", "m15.5 7.5 3 3L22 7l-3-3"],
        copy: ["r:9,9,13,13,2", "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"],
        share: ["c:18,5,3", "c:6,12,3", "c:18,19,3", "m8.6 13.5 6.8 4", "m15.4 6.5-6.8 4"],
        arrowLeft: ["m12 19-7-7 7-7", "M19 12H5"],
    };

    function icon(name, label) {
        const svg = document.createElementNS(SVG_NS, "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("class", "icon");
        if (label) {
            svg.setAttribute("role", "img");
            svg.setAttribute("aria-label", label);
        } else svg.setAttribute("aria-hidden", "true");
        for (const def of ICONS[name] || []) {
            let el;
            if (def.startsWith("c:")) {
                const [cx, cy, r] = def.slice(2).split(",");
                el = document.createElementNS(SVG_NS, "circle");
                el.setAttribute("cx", cx);
                el.setAttribute("cy", cy);
                el.setAttribute("r", r);
            } else if (def.startsWith("r:")) {
                const [x, y, w, hh, rx] = def.slice(2).split(",");
                el = document.createElementNS(SVG_NS, "rect");
                Object.entries({ x, y, width: w, height: hh, rx }).forEach(([k, v]) => el.setAttribute(k, v));
            } else {
                el = document.createElementNS(SVG_NS, "path");
                el.setAttribute("d", def);
            }
            svg.append(el);
        }
        return svg;
    }

    const $ = (sel, root = document) => root.querySelector(sel);
    const main = $("#main");
    const appEl = $("#app");

    // --- state & API ------------------------------------------------------------------

    const state = { me: null, playlists: null, instance: null };

    /** Per-browser preferences (e.g. the search filter). Storage can be unavailable: ignore. */
    const prefs = {
        get(key) {
            try {
                return localStorage.getItem("wayl-" + key);
            } catch {
                return null;
            }
        },
        set(key, value) {
            try {
                if (value) localStorage.setItem("wayl-" + key, value);
                else localStorage.removeItem("wayl-" + key);
            } catch {
                /* private mode etc. */
            }
        },
    };

    async function api(path, { method = "GET", body } = {}) {
        const init = {
            method,
            credentials: "same-origin",
            headers: { Accept: "application/json", "Content-Type": "application/json" },
        };
        if (body !== undefined) init.body = JSON.stringify(body);
        else if (method !== "GET") init.body = "{}";

        let res;
        try {
            res = await fetch(path, init);
        } catch {
            throw Object.assign(new Error("You seem to be offline. Check your connection."), { status: 0 });
        }
        let data = null;
        try {
            data = await res.json();
        } catch {
            /* empty or non-JSON body */
        }
        if (!res.ok) {
            const err = new Error((data && (data.error || data.message)) || res.statusText || "Something went wrong");
            err.status = res.status;
            if (res.status === 401 && state.me && !path.startsWith("/auth/")) {
                state.me = null; // session expired or signed out elsewhere
                go("/login?next=" + encodeURIComponent(location.pathname + location.search), true);
            }
            throw err;
        }
        return data;
    }

    let toastTimer;
    function toast(message, kind = "") {
        const el = $("#toast");
        el.textContent = message;
        el.className = "toast " + kind;
        el.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => (el.hidden = true), 3200);
    }

    // --- formatting --------------------------------------------------------------------

    const fmtNumber = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

    function duration(seconds) {
        if (!seconds) return "";
        const s = Math.round(seconds);
        return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }

    function timeAgo(iso) {
        if (!iso) return "";
        const diff = (new Date(iso).getTime() - Date.now()) / 1000;
        const steps = [
            [60, "second"],
            [60, "minute"],
            [24, "hour"],
            [7, "day"],
            [4.35, "week"],
            [12, "month"],
            [Infinity, "year"],
        ];
        let value = diff;
        for (const [size, unit] of steps) {
            if (Math.abs(value) < size) return unit === "second" ? "just now" : rtf.format(Math.round(value), unit);
            value /= size;
        }
        return "";
    }

    function monthYear(iso) {
        return iso ? new Date(iso).toLocaleDateString(undefined, { month: "long", year: "numeric" }) : "";
    }

    function hue(text) {
        let n = 0;
        for (const ch of String(text)) n = (n * 31 + ch.codePointAt(0)) % 360;
        return n;
    }

    function initials(name) {
        const parts = String(name || "?").replace(/[_.]/g, " ").trim().split(/\s+/);
        return ((parts[0] || "?")[0] + (parts.length > 1 ? parts[1][0] : "")).toUpperCase();
    }

    const isHttpUrl = (url) => typeof url === "string" && /^https?:\/\//i.test(url);

    // --- small components ------------------------------------------------------------------

    function avatar(name, cls = "") {
        return h("span", { class: `avatar ${cls}`, style: `--hue:${hue(name)}`, "aria-hidden": "true" }, initials(name));
    }

    function cover(url, cls = "") {
        const box = h("span", { class: `cover ${cls}`, "aria-hidden": "true" }, icon("music"));
        if (isHttpUrl(url)) {
            const img = h("img", { src: url, alt: "", loading: "lazy", decoding: "async", referrerpolicy: "no-referrer" });
            // Fade in once loaded; until then (or if there's no cover) the gradient shows.
            img.addEventListener("load", () => img.classList.add("loaded"), { once: true });
            img.addEventListener("error", () => img.remove(), { once: true });
            box.append(img);
        }
        return box;
    }

    function mosaic(covers) {
        const urls = (covers || []).filter(isHttpUrl);
        const box = h("div", { class: "mosaic" + (urls.length >= 4 ? " has-4" : ""), "aria-hidden": "true" });
        if (!urls.length) box.append(icon("playlist"));
        else
            for (const url of urls.length >= 4 ? urls.slice(0, 4) : urls.slice(0, 1)) {
                const img = h("img", { src: url, alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
                img.addEventListener("load", () => img.classList.add("loaded"), { once: true });
                box.append(img);
            }
        return box;
    }

    function empty(iconName, title, text, action) {
        return h(
            "div",
            { class: "empty" },
            h("span", { class: "empty-icon" }, icon(iconName)),
            h("strong", {}, title),
            text && h("p", {}, text),
            action
        );
    }

    function skeleton(rows = 5) {
        return h(
            "div",
            { "aria-busy": "true", "aria-label": "Loading" },
            Array.from({ length: rows }, () =>
                h(
                    "div",
                    { class: "skeleton-row" },
                    h("div", { class: "sk sk-cover" }),
                    h(
                        "div",
                        { class: "sk-lines" },
                        h("div", { class: "sk-line", style: `width:${40 + Math.random() * 30}%` }),
                        h("div", { class: "sk-line", style: `width:${20 + Math.random() * 20}%` })
                    )
                )
            )
        );
    }

    function errorBox(err, retry) {
        return empty(
            "activity",
            "Couldn't load this",
            err.message,
            retry && h("button", { class: "btn", type: "button", onclick: retry }, "Try again")
        );
    }

    /** Title with one word in the accent colour: the last one, or an accent full stop for one-word titles. */
    function accentTitle(title) {
        const cut = title.lastIndexOf(" ");
        if (cut < 0) return [title, h("span", { class: "accent" }, ".")];
        return [title.slice(0, cut + 1), h("span", { class: "accent" }, title.slice(cut + 1))];
    }

    /** Screen opening: tag → big title → lede → actions. */
    function pageHead(tag, title, subtitle, ...actions) {
        return h(
            "header",
            { class: "page-head" },
            h("div", {}, h("span", { class: "eyebrow" }, tag), h("h1", {}, accentTitle(title)), subtitle && h("p", {}, subtitle)),
            actions.length ? h("div", { class: "actions" }, actions) : null
        );
    }

    function segmented(tabs, active, onChange) {
        const bar = h("div", { class: "segmented", role: "tablist" });
        for (const [key, label] of tabs) {
            bar.append(
                h(
                    "button",
                    {
                        type: "button",
                        role: "tab",
                        "aria-selected": String(key === active),
                        onclick: () => {
                            for (const b of bar.children) b.setAttribute("aria-selected", "false");
                            bar.querySelector(`[data-key="${key}"]`).setAttribute("aria-selected", "true");
                            onChange(key);
                        },
                        "data-key": key,
                    },
                    label
                )
            );
        }
        return bar;
    }

    function busy(button, on, text) {
        if (on) {
            button.dataset.label = button.textContent;
            button.disabled = true;
            if (text) button.textContent = text;
        } else {
            button.disabled = false;
            if (button.dataset.label) button.textContent = button.dataset.label;
        }
    }

    // --- song actions ------------------------------------------------------------------------

    async function logListen(song) {
        try {
            const res = await api("/api/history", { method: "POST", body: { song_id: song.id } });
            toast(`🎧 Logged “${song.title}”`);
            return res;
        } catch (err) {
            toast(err.message, "error");
            return null;
        }
    }

    function saveButton(song) {
        const btn = h("button", { type: "button", class: "icon-btn" });
        const paint = () => {
            btn.classList.toggle("is-on", !!song.saved);
            btn.setAttribute("aria-pressed", String(!!song.saved));
            btn.setAttribute("aria-label", song.saved ? `Remove “${song.title}” from My songs` : `Save “${song.title}” to My songs`);
            btn.title = song.saved ? "Saved to My songs" : "Save to My songs";
        };
        btn.append(icon("heart"));
        paint();
        btn.addEventListener("click", async () => {
            const was = !!song.saved;
            song.saved = !was;
            paint();
            try {
                await api(`/api/me/songs/${song.id}`, { method: was ? "DELETE" : "PUT" });
                toast(was ? "Removed from My songs" : "Saved to My songs");
            } catch (err) {
                song.saved = was;
                paint();
                toast(err.message, "error");
            }
        });
        return btn;
    }

    /** "On your server" badge. Only songs that have the flag get one (it's only sent when the
     * viewer has a server connected). */
    function ownedBadge(song) {
        if (!song.owned) return null;
        const where = song.server ? serverLabel(song.server) : "your server";
        return h("span", { class: "owned", title: `In your library on ${where}`, role: "img", "aria-label": `In your library on ${where}` }, icon("server"));
    }

    function serverLabel(kind) {
        return kind === "plex" ? "Plex" : kind === "navidrome" ? "Navidrome" : "your server";
    }

    const canPlay = (song) => !!(state.me && state.me.has_servers && (song.owned || song.track_id));

    /** Library-only tracks (on your server, not found in MusicBrainz yet) get matched on demand. */
    async function ensureCatalog(song) {
        if (song.id) return true;
        try {
            const res = await api(`/api/library/tracks/${song.track_id}/match`, { method: "POST" });
            Object.assign(song, res, { library_only: false });
            return true;
        } catch (err) {
            toast(err.message, "error");
            return false;
        }
    }

    function songRow(song, opts = {}) {
        const sub = [];
        if (song.artist_id) sub.push(h("a", { href: `/artist/${song.artist_id}` }, song.artist));
        else sub.push(song.artist);
        if (song.album) sub.push(" · ", song.album);

        const playable = canPlay(song);
        const lead = playable
            ? h(
                  "button",
                  { type: "button", class: "cover-btn", "aria-label": `Play “${song.title}”`, title: "Play from your server", onclick: () => playQueue(opts.queue || [song], opts.queueIndex || 0) },
                  cover(song.cover),
                  h("span", { class: "cover-play" }, icon("play"))
              )
            : cover(song.cover);

        const actions = h(
            "div",
            { class: "row-meta row-actions" },
            h("span", { class: "row-time" }, opts.time || duration(song.duration)),
            song.id ? saveButton(song) : h("span", { class: "icon-btn-spacer", "aria-hidden": "true" }),
            h(
                "button",
                {
                    type: "button",
                    class: "icon-btn",
                    title: "I'm listening to this",
                    "aria-label": `Log a listen of “${song.title}”`,
                    onclick: async () => (await ensureCatalog(song)) && logListen(song),
                },
                icon("headphones")
            ),
            opts.onRemove
                ? h("button", { type: "button", class: "icon-btn", title: "Remove", "aria-label": `Remove “${song.title}”`, onclick: opts.onRemove }, icon("x"))
                : h(
                      "button",
                      {
                          type: "button",
                          class: "icon-btn",
                          title: "Add to playlist",
                          "aria-label": `Add “${song.title}” to a playlist`,
                          onclick: async () => (await ensureCatalog(song)) && addToPlaylistDialog(song),
                      },
                      icon("plus")
                  )
        );

        const title = song.id
            ? h("a", { class: "row-title", href: `/song/${song.id}` }, song.title)
            : h("span", { class: "row-title", title: "On your server, not found in MusicBrainz" }, song.title);
        return h(
            "li",
            { class: "row" + (player.current && player.current === song ? " is-playing" : "") },
            h("div", { class: "row-lead" }, opts.index ? h("span", { class: "row-index" }, opts.index) : null, lead),
            h(
                "div",
                { class: "row-main" },
                h("div", { class: "row-title-line" }, title, ownedBadge(song), opts.showMissing && song.owned === false && h("span", { class: "chip chip-missing" }, "Not in your library")),
                h("span", { class: "row-sub" }, sub)
            ),
            actions
        );
    }

    function songList(songs, opts = {}) {
        return h(
            "ul",
            { class: "list" },
            songs.map((s, i) =>
                songRow(s, { index: opts.numbered ? i + 1 : null, queue: songs, queueIndex: i, ...(opts.rowOpts ? opts.rowOpts(s, i) : {}) })
            )
        );
    }

    // --- player ---------------------------------------------------------------------------------
    // Streams from the user's own server through /api/stream (the server's login stays on the
    // WAYL server). A listen is logged once half the song (or 4 minutes) has played.

    const player = { queue: [], index: -1, current: null, logged: false, audio: new Audio(), bar: null };
    player.audio.preload = "auto";

    async function streamUrl(song) {
        if (song.track_id) return `/api/stream/${song.track_id}`;
        const sources = (await api(`/api/songs/${song.id}/sources`)).items;
        if (!sources.length) return null;
        song.track_id = sources[0].track_id;
        song.server = song.server || sources[0].server;
        return sources[0].stream_url;
    }

    function playQueue(songs, start) {
        player.queue = songs.filter(canPlay);
        const first = songs[start];
        player.index = Math.max(0, player.queue.indexOf(first));
        playAt(player.index);
    }

    async function playAt(i, tries = 0) {
        if (i < 0 || i >= player.queue.length) return;
        const song = player.queue[i];
        player.index = i;
        player.current = song;
        player.logged = false;
        renderPlayer();
        let url;
        try {
            url = await streamUrl(song);
        } catch (err) {
            toast(err.message, "error");
        }
        if (player.current !== song) return; // user picked another song meanwhile
        if (!url) {
            toast(`“${song.title}” isn't on your server`, "error");
            if (tries < 3 && i + 1 < player.queue.length) playAt(i + 1, tries + 1);
            return;
        }
        player.audio.src = url;
        try {
            await player.audio.play();
        } catch (err) {
            if (err.name !== "AbortError") toast("Couldn't play this track. Your browser may not support its format.", "error");
        }
        if ("mediaSession" in navigator) {
            navigator.mediaSession.metadata = new MediaMetadata({
                title: song.title,
                artist: song.artist,
                album: song.album || "",
                artwork: isHttpUrl(song.cover) ? [{ src: song.cover, sizes: "250x250", type: "image/jpeg" }] : [],
            });
        }
        markPlayingRows();
    }

    function markPlayingRows() {
        for (const row of document.querySelectorAll(".row.is-playing")) row.classList.remove("is-playing");
    }

    async function maybeLogPlay() {
        const a = player.audio;
        const song = player.current;
        if (player.logged || !song || !a.duration || !isFinite(a.duration)) return;
        if (a.currentTime < Math.min(a.duration / 2, 240)) return;
        player.logged = true;
        try {
            const body = song.id ? { song_id: song.id, source: "player" } : { track_id: song.track_id, source: "player" };
            const res = await api("/api/history", { method: "POST", body });
            if (res.item && !song.id) Object.assign(song, res.item.song); // it got matched on the way
        } catch {
            /* not in MusicBrainz: nothing to log */
        }
    }

    function fmtClock(sec) {
        if (!isFinite(sec) || sec < 0) return "0:00";
        return duration(Math.floor(sec)) || "0:00";
    }

    function buildPlayer() {
        const audio = player.audio;
        const playBtn = h("button", { type: "button", class: "icon-btn play-main", "aria-label": "Pause" }, icon("pause"));
        const prevBtn = h("button", { type: "button", class: "icon-btn", "aria-label": "Previous", onclick: () => (audio.currentTime > 5 ? (audio.currentTime = 0) : playAt(player.index - 1)) }, icon("skipPrev"));
        const nextBtn = h("button", { type: "button", class: "icon-btn", "aria-label": "Next", onclick: () => playAt(player.index + 1) }, icon("skipNext"));
        const closeBtn = h("button", { type: "button", class: "icon-btn", "aria-label": "Close player", onclick: () => {
            audio.pause();
            audio.removeAttribute("src");
            audio.load();
            player.current = null;
            renderPlayer();
        } }, icon("x"));
        const seek = h("input", { type: "range", min: "0", max: "1000", value: "0", class: "seek", "aria-label": "Seek" });
        const time = h("span", { class: "player-time" }, "0:00");
        const total = h("span", { class: "player-time" }, "0:00");
        const info = h("div", { class: "player-info" });
        const art = h("div", { class: "player-art" });
        const bar = h(
            "div",
            { class: "player", role: "region", "aria-label": "Player", hidden: true },
            h("div", { class: "player-track" }, art, info),
            h("div", { class: "player-center" }, h("div", { class: "player-controls" }, prevBtn, playBtn, nextBtn), h("div", { class: "player-progress" }, time, seek, total)),
            h("div", { class: "player-end" }, closeBtn)
        );
        playBtn.addEventListener("click", () => (audio.paused ? audio.play() : audio.pause()));
        let seeking = false;
        seek.addEventListener("input", () => (seeking = true));
        seek.addEventListener("change", () => {
            if (audio.duration) audio.currentTime = (seek.value / 1000) * audio.duration;
            seeking = false;
        });
        audio.addEventListener("timeupdate", () => {
            if (!seeking && audio.duration) seek.value = String(Math.round((audio.currentTime / audio.duration) * 1000));
            time.textContent = fmtClock(audio.currentTime);
            total.textContent = fmtClock(audio.duration);
            maybeLogPlay();
        });
        const paint = () => {
            playBtn.replaceChildren(icon(audio.paused ? "play" : "pause"));
            playBtn.setAttribute("aria-label", audio.paused ? "Play" : "Pause");
        };
        audio.addEventListener("play", paint);
        audio.addEventListener("pause", paint);
        audio.addEventListener("ended", () => playAt(player.index + 1));
        audio.addEventListener("error", () => player.current && audio.src && toast("Playback failed. Is your server reachable?", "error"));
        if ("mediaSession" in navigator) {
            navigator.mediaSession.setActionHandler("previoustrack", () => playAt(player.index - 1));
            navigator.mediaSession.setActionHandler("nexttrack", () => playAt(player.index + 1));
        }
        document.body.append(bar);
        player.bar = { bar, info, art, prevBtn, nextBtn };
    }

    function renderPlayer() {
        const { bar, info, art, prevBtn, nextBtn } = player.bar;
        const song = player.current;
        bar.hidden = !song;
        document.body.classList.toggle("has-player", !!song);
        if (!song) return;
        clear(art, cover(song.cover));
        clear(
            info,
            song.id ? h("a", { class: "row-title", href: `/song/${song.id}` }, song.title) : h("span", { class: "row-title" }, song.title),
            h("span", { class: "row-sub" }, song.artist)
        );
        prevBtn.disabled = player.index <= 0;
        nextBtn.disabled = player.index >= player.queue.length - 1;
    }

    async function loadPlaylists(force = false) {
        if (!state.playlists || force) state.playlists = (await api("/api/playlists")).items;
        return state.playlists;
    }

    // --- dialogs ------------------------------------------------------------------------------

    const dialog = $("#dialog");
    dialog.addEventListener("click", (e) => {
        if (e.target === dialog) dialog.close(); // click on the backdrop
    });

    function openDialog(...content) {
        clear(dialog, h("div", { class: "dialog-body" }, content));
        if (!dialog.open) dialog.showModal();
        return dialog;
    }

    function confirmDialog({ title, text, confirm = "Confirm", danger = false, password = false }) {
        return new Promise((resolve) => {
            const input = password
                ? h("input", { class: "input", type: "password", placeholder: "Your password", autocomplete: "current-password", required: true, "aria-label": "Password" })
                : null;
            const form = h(
                "form",
                { class: "form", method: "dialog" },
                input,
                h(
                    "div",
                    { class: "dialog-actions" },
                    h("button", { type: "button", class: "btn btn-ghost", onclick: () => dialog.close() }, "Cancel"),
                    h("button", { type: "submit", class: danger ? "btn btn-danger solid" : "btn btn-primary" }, confirm)
                )
            );
            let result = null;
            form.addEventListener("submit", (e) => {
                e.preventDefault();
                result = password ? input.value : true;
                dialog.close();
            });
            dialog.addEventListener("close", () => resolve(result), { once: true });
            openDialog(h("h2", {}, title), text && h("p", {}, text), form);
            (input || form.querySelector("[type=submit]")).focus();
        });
    }

    async function addToPlaylistDialog(song) {
        const list = h("ul", { class: "pick-list" }, h("li", {}, skeleton(2)));
        const name = h("input", { class: "input", placeholder: "New playlist name", maxlength: "120", required: true, "aria-label": "New playlist name" });
        const create = h(
            "form",
            { class: "inline-form" },
            name,
            h("button", { class: "btn btn-primary", type: "submit" }, "Create")
        );

        async function addTo(playlist) {
            try {
                const res = await api(`/api/playlists/${playlist.id}`, { method: "POST", body: { song_id: song.id } });
                dialog.close();
                toast(res.message);
                state.playlists = null;
            } catch (err) {
                toast(err.message, "error");
            }
        }

        create.addEventListener("submit", async (e) => {
            e.preventDefault();
            const button = create.querySelector("button");
            busy(button, true);
            try {
                const res = await api("/api/playlists", { method: "POST", body: { name: name.value } });
                await addTo(res.playlist);
            } catch (err) {
                toast(err.message, "error");
            } finally {
                busy(button, false);
            }
        });

        openDialog(
            h("h2", {}, "Add to playlist"),
            h("p", {}, `“${song.title}” by ${song.artist}`),
            list,
            create
        );

        try {
            const playlists = await loadPlaylists();
            clear(
                list,
                playlists.length
                    ? playlists.map((p) =>
                          h(
                              "li",
                              {},
                              h(
                                  "button",
                                  { type: "button", onclick: () => addTo(p) },
                                  cover(p.covers[0]),
                                  h("span", { class: "row-main" }, h("span", { class: "row-title" }, p.name), h("span", { class: "row-sub" }, `${p.song_count} songs`))
                              )
                          )
                      )
                    : h("li", { class: "muted small", style: "padding:0 8px" }, "No playlists yet. Create your first one below.")
            );
            if (!playlists.length) name.focus();
        } catch (err) {
            clear(list, h("li", { class: "form-error" }, err.message));
        }
    }

    // --- router --------------------------------------------------------------------------------

    /** Social features (follows, feed) are optional per instance: see /api/instance. */
    const social = () => !!(state.instance && state.instance.features && state.instance.features.social);

    // [path, label, icon, needs social]
    const NAV = [
        ["/search", "Search", "search"],
        ["/friends", "Friends", "share"],
        ["/following", "Following", "users", true],
        ["/playlists", "Playlists", "playlist"],
        ["/songs", "My songs", "music"],
        ["/profile", "Profile", "user"],
    ];
    const navItems = () => NAV.filter((item) => !item[3] || social());

    const routes = [
        [/^\/$/, () => go(state.me ? "/search" : "/login", true)],
        [/^\/login$/, pageLogin, "guest"],
        [/^\/register$/, pageRegister, "guest"],
        [/^\/forgot$/, pageForgot, "guest"],
        [/^\/reset$/, pageReset, "any"],
        [/^\/search$/, pageSearch],
        [/^\/following$/, pageFollowing, undefined, "social"],
        [/^\/playlists$/, pagePlaylists],
        [/^\/playlists\/(\d+)$/, pagePlaylist],
        [/^\/songs$/, pageMySongs],
        [/^\/profile$/, pageProfile],
        [/^\/settings$/, pageSettings],
        [/^\/friends$/, pageFriends],
        [/^\/friends\/(\d+)$/, pageSubscription],
        [/^\/song\/([0-9a-f-]{36})$/, pageSong],
        [/^\/artist\/([0-9a-f-]{36})$/, pageArtist],
        [/^\/user\/(\d+)$/, pageUser],
    ];

    let renderSeq = 0;

    function go(path, replace = false) {
        if (replace) history.replaceState(null, "", path);
        else history.pushState(null, "", path);
        render();
    }

    function setQuery(params) {
        const url = new URL(location.href);
        for (const [k, v] of Object.entries(params)) {
            if (v) url.searchParams.set(k, v);
            else url.searchParams.delete(k);
        }
        history.replaceState(null, "", url.pathname + url.search);
    }

    function buildNav() {
        const link = ([href, label, ic]) => h("a", { href }, icon(ic), h("span", {}, label));
        clear($("#nav"), navItems().map(link));
        clear($("#tabbar"), navItems().map(link));
        clear($("#nav-settings"), h("a", { href: "/settings", class: "icon-btn", "aria-label": "Settings", title: "Settings" }, icon("sliders")));
    }

    function markNav(path) {
        for (const a of document.querySelectorAll("#nav a, #tabbar a, #nav-settings a")) {
            const href = a.getAttribute("href");
            const active = path === href || path.startsWith(href + "/");
            if (active) a.setAttribute("aria-current", "page");
            else a.removeAttribute("aria-current");
        }
    }

    function render() {
        const path = location.pathname;
        const params = new URLSearchParams(location.search);
        // routes marked "social" only exist when the instance has social features on
        const match = routes.find(([re, , , needs]) => re.test(path) && (needs !== "social" || social()));
        if (!match) {
            appEl.dataset.state = "user";
            clear(main, empty("disc", "Page not found", "That page doesn't exist.", h("a", { class: "btn", href: "/search" }, "Go to search")));
            return;
        }
        const [re, page, access] = match;
        if (access === "guest" && state.me) return go("/search", true);
        if (!access && !state.me && page !== routes[0][1]) {
            return go("/login?next=" + encodeURIComponent(path + location.search), true);
        }

        const seq = ++renderSeq;
        const alive = () => seq === renderSeq;
        document.title = "WAYL · What Are You Listening?";
        appEl.dataset.state = access === "guest" || access === "any" ? "guest" : "user";
        markNav(path);
        main.replaceChildren();
        window.scrollTo(0, 0);
        const result = page({ args: path.match(re).slice(1), params, alive });
        if (result instanceof Promise) result.catch((err) => alive() && clear(main, errorBox(err, render)));
    }

    // Same-origin links are handled by the router.
    document.addEventListener("click", (e) => {
        const a = e.target.closest("a[href]");
        if (!a || a.target || a.hasAttribute("download") || e.defaultPrevented) return;
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        const url = new URL(a.href, location.href);
        if (url.origin !== location.origin) return;
        e.preventDefault();
        if (dialog.open) dialog.close();
        if (url.pathname + url.search !== location.pathname + location.search) go(url.pathname + url.search);
    });
    window.addEventListener("popstate", render);

    // --- auth pages -------------------------------------------------------------------------------

    function authLayout(title, lede, form, foot) {
        clear(
            main,
            h(
                "div",
                { class: "auth" },
                h(
                    "section",
                    { class: "auth-art", "aria-hidden": "true" },
                    h("span", { class: "eyebrow" }, "Your music log"),
                    h("h2", {}, h("span", {}, "What are you"), h("span", { class: "accent" }, "listening"), h("span", {}, "to?")),
                    h(
                        "p",
                        {},
                        social()
                            ? "Log the songs you love, build playlists, and see what your friends are playing right now."
                            : "Your own music log: track what you listen to, build playlists, and stream your library from your own server."
                    )
                ),
                h(
                    "section",
                    { class: "auth-panel" },
                    h(
                        "div",
                        { class: "auth-card" },
                        h("h1", {}, accentTitle(title)),
                        h("p", { class: "lede" }, lede),
                        form,
                        foot && h("p", { class: "auth-foot" }, foot)
                    )
                )
            )
        );
    }

    /** A labelled form control. `control` is what gets shown, `input` what the label points at. */
    function field(label, control, extra, input = control) {
        const id = "f-" + Math.random().toString(36).slice(2, 8);
        input.id = id;
        return h("div", { class: "field" }, h("div", { class: "field-row" }, h("label", { for: id }, label), extra), control);
    }

    function passwordInput(attrs) {
        const input = h("input", { class: "input", type: "password", required: true, ...attrs });
        const toggle = h("button", { type: "button", class: "icon-btn", "aria-label": "Show password" }, icon("eye"));
        toggle.addEventListener("click", () => {
            const show = input.type === "password";
            input.type = show ? "text" : "password";
            toggle.setAttribute("aria-label", show ? "Hide password" : "Show password");
            toggle.replaceChildren(icon(show ? "eyeOff" : "eye"));
        });
        const group = h("div", { class: "input-group" }, input, toggle);
        group.input = input;
        return group;
    }

    function pwField(label, attrs, extra) {
        const group = passwordInput(attrs);
        return field(label, group, extra, group.input);
    }

    function authForm(fields, submitLabel, onSubmit) {
        const error = h("div", { class: "form-error", role: "alert", hidden: true });
        const button = h("button", { type: "submit", class: "btn btn-primary btn-block" }, submitLabel);
        const form = h("form", { class: "form", novalidate: false }, error, fields, button);
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            error.hidden = true;
            busy(button, true, "Please wait…");
            try {
                await onSubmit(new FormData(form), form);
            } catch (err) {
                error.textContent = err.message;
                error.hidden = false;
            } finally {
                busy(button, false);
            }
        });
        return form;
    }

    function safeNext(params) {
        const next = params.get("next") || "";
        return next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : "/search";
    }

    function pageLogin({ params }) {
        const form = authForm(
            [
                field("Email", h("input", { class: "input", name: "email", type: "email", autocomplete: "email", required: true, autofocus: true })),
                pwField("Password", { name: "password", autocomplete: "current-password" }, h("a", { class: "link small", href: "/forgot" }, "Forgot password?")),
            ],
            "Sign in",
            async (data) => {
                const res = await api("/auth/login", { method: "POST", body: { email: data.get("email"), password: data.get("password") } });
                state.me = res.user;
                state.playlists = null;
                go(safeNext(params), true);
            }
        );
        authLayout("Welcome back", "Sign in to keep logging what you listen to.", form, ["New here? ", h("a", { class: "link", href: "/register" }, "Create an account")]);
    }

    function pageRegister() {
        const form = authForm(
            [
                field("Username", h("input", { class: "input", name: "username", autocomplete: "username", required: true, minlength: "2", maxlength: "30", pattern: "[A-Za-z0-9_.]{2,30}", autofocus: true }), h("span", { class: "hint" }, "Letters, numbers, _ and .")),
                field("Email", h("input", { class: "input", name: "email", type: "email", autocomplete: "email", required: true })),
                pwField("Password", { name: "password", autocomplete: "new-password", minlength: "8", maxlength: "128" }, h("span", { class: "hint" }, "At least 8 characters")),
            ],
            "Create account",
            async (data) => {
                const res = await api("/auth/register", {
                    method: "POST",
                    body: { username: data.get("username"), email: data.get("email"), password: data.get("password") },
                });
                state.me = res.user;
                go("/search", true);
                toast("Welcome to WAYL! Search for a song to get started.");
            }
        );
        authLayout("Create your account", "It's free. Start logging your music in seconds.", form, ["Already have an account? ", h("a", { class: "link", href: "/login" }, "Sign in")]);
    }

    function pageForgot() {
        const form = authForm(
            [field("Email", h("input", { class: "input", name: "email", type: "email", autocomplete: "email", required: true, autofocus: true }))],
            "Send reset link",
            async (data, formEl) => {
                const res = await api("/auth/forgot", { method: "POST", body: { email: data.get("email") } });
                formEl.replaceWith(
                    h(
                        "div",
                        { class: "form" },
                        h("div", { class: "form-success", role: "status" }, res.message),
                        h("p", { class: "muted small" }, "The link expires in 1 hour. Don't forget to check your spam folder."),
                        h("a", { class: "btn btn-block", href: "/login" }, "Back to sign in")
                    )
                );
            }
        );
        authLayout("Forgot your password?", "Enter your account's email and we'll send you a link to choose a new one.", form, [h("a", { class: "link", href: "/login" }, "Back to sign in")]);
    }

    function pageReset({ params }) {
        const token = params.get("token");
        // Keep the token out of the address bar and history once we've read it.
        if (token) history.replaceState(null, "", "/reset");
        const resetToken = token || sessionStorage.getItem("wayl-reset-token");
        if (token) sessionStorage.setItem("wayl-reset-token", token);

        if (!resetToken) {
            authLayout("Link not valid", "This reset link is missing its code. Request a new one and use the link from the email.", h("a", { class: "btn btn-primary btn-block", href: "/forgot" }, "Request a new link"));
            return;
        }
        const form = authForm(
            [
                pwField("New password", { name: "password", autocomplete: "new-password", minlength: "8", maxlength: "128", autofocus: true }, h("span", { class: "hint" }, "At least 8 characters")),
                pwField("Confirm new password", { name: "confirm", autocomplete: "new-password", minlength: "8", maxlength: "128" }),
            ],
            "Set new password",
            async (data) => {
                if (data.get("password") !== data.get("confirm")) throw new Error("The two passwords don't match");
                const res = await api("/auth/reset", { method: "POST", body: { token: resetToken, password: data.get("password") } });
                sessionStorage.removeItem("wayl-reset-token");
                state.me = res.user;
                state.playlists = null;
                go("/search", true);
                toast(res.message);
            }
        );
        authLayout("Choose a new password", "You'll be signed in right after, and signed out everywhere else.", form, [h("a", { class: "link", href: "/forgot" }, "Need a new link?")]);
    }

    // --- search ----------------------------------------------------------------------------------

    const SUGGESTIONS = ["Bohemian Rhapsody", "Radiohead", "Teardrop Massive Attack", "Lucio Battisti", "Kendrick Lamar", "Daft Punk"];

    function artistCard(artist) {
        const sub = [artist.type, artist.country].filter(Boolean).join(" · ");
        return h(
            "a",
            { class: "artist-card", href: `/artist/${artist.id}` },
            avatar(artist.name),
            h("span", { class: "name", title: artist.name }, artist.name),
            sub && h("span", { class: "muted small" }, sub)
        );
    }

    async function pageSearch({ params, alive }) {
        const input = h("input", {
            class: "input",
            type: "search",
            name: "q",
            placeholder: "Search a song, an artist, or both…",
            autocomplete: "off",
            "aria-label": "Search songs and artists",
            value: params.get("q") || "",
        });
        const form = h("form", { class: "search-box", role: "search" }, icon("search"), input);
        const results = h("div", { class: "section" });

        // "In my library" filter: kept (in this browser) until switched off by hand.
        let libraryOnly = state.me.has_servers && prefs.get("search-library") === "1";
        const filterBtn = h("button", { type: "button", class: "chip filter-chip" });
        const paintFilter = () => {
            filterBtn.classList.toggle("is-on", libraryOnly);
            filterBtn.setAttribute("aria-pressed", String(libraryOnly));
            filterBtn.replaceChildren(...[icon("server"), "In my library", libraryOnly && icon("x")].filter(Boolean));
            filterBtn.title = libraryOnly ? "Showing only songs on your server. Click to search everything." : "Only show songs on your server";
            input.placeholder = libraryOnly ? "Search your library…" : "Search a song, an artist, or both…";
        };
        filterBtn.addEventListener("click", () => {
            libraryOnly = !libraryOnly;
            prefs.set("search-library", libraryOnly ? "1" : "");
            paintFilter();
            run();
        });
        paintFilter();
        const filters = state.me.has_servers ? h("div", { class: "hint-row" }, filterBtn) : null;
        clear(
            main,
            pageHead("Discover", "Search", state.me.has_servers ? "Find any song, or just the ones on your server." : "Find any song in the open MusicBrainz database."),
            form,
            filters,
            results
        );

        let seq = 0;
        let timer;

        async function runLibrary(q, mine, offset = 0, list = null) {
            if (!list) clear(results, skeleton(6));
            let res;
            try {
                res = await api(`/api/library?limit=50&offset=${offset}&q=${encodeURIComponent(q)}`);
            } catch (err) {
                if (mine === seq && alive()) clear(results, errorBox(err, run));
                return;
            }
            if (mine !== seq || !alive()) return;
            const songs = list ? list.concat(res.items) : res.items;
            const more =
                songs.length < res.total
                    ? h("button", { type: "button", class: "btn", onclick: (e) => { e.target.disabled = true; runLibrary(q, mine, songs.length, songs); } }, `Load more (${res.total - songs.length} left)`)
                    : null;
            clear(
                results,
                h("h2", { class: "section-title" }, q ? "In your library" : "Your library", h("span", { class: "muted small" }, `${res.total} ${res.total === 1 ? "track" : "tracks"}`)),
                songs.length
                    ? songList(songs)
                    : empty("server", q ? "Not in your library" : "Your library is empty", q ? "Nothing on your server matches. Switch the filter off to search everything." : "WAYL hasn't indexed your server yet. Check Settings → Music servers."),
                more && h("div", { class: "section" }, more)
            );
        }

        async function idle() {
            const chips = h(
                "div",
                { class: "hint-row" },
                h("span", { class: "muted small" }, "Try"),
                h("div", { class: "chips" }, SUGGESTIONS.map((s) => h("button", { type: "button", class: "chip", onclick: () => { input.value = s; run(); } }, s)))
            );
            clear(results, chips);
            try {
                const recent = (await api("/api/history?limit=6")).items;
                if (!alive() || input.value.trim()) return;
                if (recent.length) {
                    results.append(
                        h(
                            "div",
                            { class: "section" },
                            h("h2", { class: "section-title" }, "Jump back in", h("a", { class: "link small", href: "/songs?tab=recent" }, "See all")),
                            songList(dedupeSongs(recent.map((r) => r.song)))
                        )
                    );
                }
            } catch {
                /* the suggestions are enough */
            }
        }

        async function run() {
            const q = input.value.trim();
            setQuery({ q });
            const mine = ++seq;
            if (libraryOnly) return runLibrary(q, mine);
            if (q.length < 2) return idle();
            clear(results, skeleton(6));

            const artistsPromise = api("/api/artists?q=" + encodeURIComponent(q)).catch(() => ({ items: [] }));
            let songs;
            try {
                songs = (await api("/api/songs?q=" + encodeURIComponent(q))).items;
            } catch (err) {
                if (mine === seq && alive()) clear(results, errorBox(err, run));
                return;
            }
            if (mine !== seq || !alive()) return;

            const songSection = h(
                "div",
                {},
                h("h2", { class: "section-title" }, "Songs"),
                songs.length ? songList(songs) : empty("search", "No songs found", "Check the spelling, or try adding the artist's name.")
            );
            const artistSection = h("div", { class: "section", hidden: true });
            clear(results, songSection, artistSection);

            const artists = (await artistsPromise).items;
            if (mine !== seq || !alive() || !artists.length) return;
            clear(artistSection, h("h2", { class: "section-title" }, "Artists"), h("div", { class: "artist-strip" }, artists.map(artistCard)));
            artistSection.hidden = false;
        }

        form.addEventListener("submit", (e) => {
            e.preventDefault();
            clearTimeout(timer);
            run();
        });
        input.addEventListener("input", () => {
            clearTimeout(timer);
            timer = setTimeout(run, 450);
        });
        input.focus();
        run();
    }

    function dedupeSongs(songs) {
        const seen = new Set();
        return songs.filter((s) => !seen.has(s.id) && seen.add(s.id));
    }

    // --- song page --------------------------------------------------------------------------------

    async function pageSong({ args: [id], alive }) {
        clear(main, skeleton(4));
        const song = await api(`/api/songs/${id}`);
        if (!alive()) return;
        document.title = `${song.title} · ${song.artist} · WAYL`;

        const q = encodeURIComponent(`${song.artist} ${song.title}`);
        const listenLinks = [
            ["YouTube", `https://www.youtube.com/results?search_query=${q}`],
            ["Spotify", `https://open.spotify.com/search/${q}`],
            ["Apple Music", `https://music.apple.com/search?term=${q}`],
        ];
        const year = (song.release_date || "").slice(0, 4) || song.year;

        const hero = h(
            "section",
            { class: "hero" },
            cover(song.cover_large || song.cover, "cover-lg"),
            h(
                "div",
                { class: "hero-body" },
                h("span", { class: "eyebrow" }, "Song", song.owned ? h("span", { class: "chip chip-ok" }, icon("server"), "In your library") : null),
                h("h1", {}, song.title),
                h("div", { class: "by" }, song.artist_id ? h("a", { href: `/artist/${song.artist_id}` }, song.artist) : song.artist),
                h("div", { class: "dot-list" }, song.album && h("span", {}, song.album), year && h("span", {}, year), song.duration && h("span", {}, duration(song.duration))),
                h(
                    "div",
                    { class: "actions" },
                    canPlay(song) && h("button", { type: "button", class: "btn btn-primary", onclick: () => playQueue([song], 0) }, icon("play"), "Play"),
                    h("button", { type: "button", class: canPlay(song) ? "btn" : "btn btn-primary", onclick: async () => {
                        const res = await logListen(song);
                        // a repeat within 30 seconds isn't counted twice
                        if (res && res.created) {
                            song.my_plays += 1;
                            song.wayl_plays += 1;
                            playsStat.textContent = song.my_plays;
                            waylStat.textContent = song.wayl_plays;
                        }
                    } }, icon("headphones"), "I'm listening"),
                    saveButton(song),
                    h("button", { type: "button", class: "btn", onclick: () => addToPlaylistDialog(song) }, icon("plus"), "Add to playlist")
                ),
                song.genres && song.genres.length ? h("div", { class: "chips" }, song.genres.map((g) => h("span", { class: "chip" }, g))) : null
            )
        );
        const playsStat = h("b", {}, song.my_plays);
        const waylStat = h("b", {}, song.wayl_plays);
        const stats = h(
            "div",
            { class: "stats" },
            h("div", { class: "stat" }, playsStat, h("span", {}, "your plays")),
            h("div", { class: "stat" }, waylStat, h("span", {}, "plays on WAYL")),
            song.listenbrainz_listens != null && h("div", { class: "stat" }, h("b", {}, fmtNumber.format(song.listenbrainz_listens)), h("span", {}, "listens on ListenBrainz"))
        );

        const listen = h(
            "div",
            { class: "section" },
            h("h2", { class: "section-title" }, "Listen on"),
            h(
                "div",
                { class: "chips" },
                listenLinks.map(([label, url]) => h("a", { class: "btn btn-sm", href: url, target: "_blank", rel: "noopener noreferrer" }, icon("play"), label)),
                (song.artist_links || [])
                    .filter((l) => isHttpUrl(l.url))
                    .map((l) => h("a", { class: "btn btn-sm btn-ghost", href: l.url, target: "_blank", rel: "noopener noreferrer" }, icon("external"), `Artist · ${l.label}`))
            )
        );

        const credits =
            song.credits && song.credits.length
                ? h(
                      "div",
                      { class: "section" },
                      h("h2", { class: "section-title" }, "Credits"),
                      h(
                          "ul",
                          { class: "credits" },
                          song.credits.map((c) =>
                              h("li", {}, c.artist_id ? h("a", { href: `/artist/${c.artist_id}`, class: "row-title" }, c.name) : h("strong", {}, c.name), h("span", {}, c.role))
                          )
                      )
                  )
                : null;

        const about = h(
            "p",
            { class: "section muted small" },
            song.release_date && `First released ${song.release_date}. `,
            song.isrc && `ISRC ${song.isrc}. `,
            "Data from ",
            h("a", { class: "link", href: song.musicbrainz_url, target: "_blank", rel: "noopener" }, "MusicBrainz"),
            "."
        );

        clear(main, hero, stats, listen, credits, about);
    }

    // --- artist page -------------------------------------------------------------------------------

    async function pageArtist({ args: [id], alive }) {
        clear(main, skeleton(6));
        const artist = await api(`/api/artists/${id}`);
        if (!alive()) return;
        document.title = `${artist.name} · WAYL`;
        const meta = [artist.type, artist.country, artist.begin && `since ${artist.begin}`].filter(Boolean);
        clear(
            main,
            h(
                "section",
                { class: "hero" },
                avatar(artist.name, "avatar-lg"),
                h(
                    "div",
                    { class: "hero-body" },
                    h("span", { class: "eyebrow" }, "Artist"),
                    h("h1", {}, artist.name),
                    artist.disambiguation && h("p", { class: "muted" }, artist.disambiguation),
                    meta.length ? h("div", { class: "dot-list" }, meta.map((m) => h("span", {}, m))) : null,
                    artist.genres.length ? h("div", { class: "chips" }, artist.genres.map((g) => h("span", { class: "chip" }, g))) : null
                )
            ),
            h(
                "div",
                { class: "section" },
                h("h2", { class: "section-title" }, "Most listened"),
                artist.top_tracks.length
                    ? songList(artist.top_tracks, { numbered: true })
                    : empty("music", "No listening data yet", "ListenBrainz doesn't have play counts for this artist yet. Search for their songs instead.")
            )
        );
    }

    // --- following ---------------------------------------------------------------------------------

    function personRow(user, { onToggle } = {}) {
        const btn =
            state.me && user.id !== state.me.id
                ? followButton(user, onToggle)
                : null;
        return h(
            "li",
            { class: "person" },
            avatar(user.username),
            h("div", { class: "row-main" }, h("a", { class: "row-title", href: `/user/${user.id}` }, user.username), user.bio && h("span", { class: "row-sub" }, user.bio)),
            btn
        );
    }

    function followButton(user, onToggle, big = false) {
        const btn = h("button", { type: "button" });
        const paint = () => {
            btn.className = `btn ${big ? "" : "btn-sm"} ${user.is_following ? "" : "btn-primary"}`;
            btn.replaceChildren(user.is_following ? "Following" : "Follow");
            btn.setAttribute("aria-pressed", String(!!user.is_following));
        };
        paint();
        btn.addEventListener("click", async () => {
            btn.disabled = true;
            try {
                const res = await api(`/api/users/${user.id}/follow`, { method: user.is_following ? "DELETE" : "POST" });
                user.is_following = res.is_following;
                paint();
                if (onToggle) onToggle(user);
            } catch (err) {
                toast(err.message, "error");
            } finally {
                btn.disabled = false;
            }
        });
        return btn;
    }

    function feedItem(item) {
        const song = item.song;
        return h(
            "li",
            { class: "feed-item" },
            avatar(item.user.username),
            h(
                "div",
                {},
                h("div", { class: "feed-head" }, h("a", { href: `/user/${item.user.id}` }, item.user.username), h("span", { class: "muted" }, ` listened ${timeAgo(item.listened_at)}`)),
                h(
                    "div",
                    { class: "feed-song" },
                    canPlay(song)
                        ? h("button", { type: "button", class: "cover-btn", "aria-label": `Play “${song.title}”`, onclick: () => playQueue([song], 0) }, cover(song.cover), h("span", { class: "cover-play" }, icon("play")))
                        : cover(song.cover),
                    h("div", { class: "row-main" }, h("div", { class: "row-title-line" }, h("a", { class: "row-title", href: `/song/${song.id}` }, song.title), ownedBadge(song)), h("span", { class: "row-sub" }, song.artist)),
                    saveButton(song),
                    h("button", { type: "button", class: "icon-btn", title: "I'm listening to this too", "aria-label": `Log a listen of “${song.title}”`, onclick: () => logListen(song) }, icon("headphones"))
                )
            )
        );
    }

    async function pageFollowing({ params, alive }) {
        const body = h("div", {});
        const tab = params.get("tab") || "activity";
        const tabs = [
            ["activity", "Activity"],
            ["following", "Following"],
            ["followers", "Followers"],
            ["find", "Find people"],
        ];
        clear(
            main,
            pageHead("Feed", "Following", "What the people you follow are listening to."),
            segmented(tabs, tab, (key) => {
                setQuery({ tab: key === "activity" ? "" : key });
                show(key);
            }),
            body
        );

        async function show(key) {
            const seq = ++showSeq;
            const ok = () => seq === showSeq && alive();
            if (key === "find") return showFind();
            clear(body, skeleton(5));
            try {
                if (key === "activity") {
                    const items = (await api("/api/feed?limit=50")).items;
                    if (!ok()) return;
                    clear(
                        body,
                        items.length
                            ? h("ul", { class: "list" }, items.map(feedItem))
                            : empty("activity", "Nothing here yet", "Follow some people and their listens will show up here.", h("button", { type: "button", class: "btn btn-primary", onclick: () => main.querySelector('[data-key="find"]').click() }, icon("userPlus"), "Find people"))
                    );
                } else {
                    const items = (await api(`/api/me/${key}`)).items;
                    if (!ok()) return;
                    clear(
                        body,
                        items.length
                            ? h("ul", { class: "list" }, items.map((u) => personRow(u)))
                            : key === "following"
                              ? empty("users", "You're not following anyone", "Find friends by their username.", h("button", { type: "button", class: "btn btn-primary", onclick: () => main.querySelector('[data-key="find"]').click() }, icon("userPlus"), "Find people"))
                              : empty("users", "No followers yet", "Share your username so friends can find you.")
                    );
                }
            } catch (err) {
                if (ok()) clear(body, errorBox(err, () => show(key)));
            }
        }
        let showSeq = 0;

        function showFind() {
            const input = h("input", { class: "input", type: "search", placeholder: "Search by username…", autocomplete: "off", "aria-label": "Search people by username" });
            const out = h("ul", { class: "list section" });
            let timer;
            let seq = 0;
            async function run() {
                const q = input.value.trim();
                const mine = ++seq;
                if (q.length < 2) return clear(out);
                try {
                    const items = (await api("/api/users?q=" + encodeURIComponent(q))).items;
                    if (mine !== seq) return;
                    clear(out, items.length ? items.map((u) => personRow(u)) : h("li", {}, empty("search", "No one found", `Nobody's username contains “${q}”.`)));
                } catch (err) {
                    if (mine === seq) clear(out, h("li", {}, errorBox(err, run)));
                }
            }
            input.addEventListener("input", () => {
                clearTimeout(timer);
                timer = setTimeout(run, 300);
            });
            clear(body, h("form", { class: "search-box", role: "search", onsubmit: (e) => { e.preventDefault(); run(); } }, icon("search"), input), out);
            input.focus();
        }

        show(tab);
    }

    // --- playlists ---------------------------------------------------------------------------------

    function playlistTile(p) {
        return h(
            "a",
            { class: "tile", href: `/playlists/${p.id}` },
            mosaic(p.covers),
            h("span", { class: "tile-title" }, p.name),
            h("span", { class: "tile-sub" }, `${p.song_count} ${p.song_count === 1 ? "song" : "songs"}${p.is_public ? " · Public" : ""}`)
        );
    }

    async function pagePlaylists({ alive }) {
        const grid = h("div", {}, skeleton(3));
        const name = h("input", { class: "input", name: "name", placeholder: "Name your playlist", maxlength: "120", required: true, "aria-label": "New playlist name" });
        const createForm = h("form", { class: "inline-form card", hidden: true, style: "margin-bottom:24px" }, name, h("button", { class: "btn btn-primary", type: "submit" }, "Create"));
        const newBtn = h("button", { type: "button", class: "btn btn-primary", onclick: () => { createForm.hidden = false; name.focus(); } }, icon("plus"), "New playlist");
        clear(main, pageHead("Collections", "Playlists", "Your collections of songs.", newBtn), createForm, grid);

        createForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                const res = await api("/api/playlists", { method: "POST", body: { name: name.value } });
                state.playlists = null;
                go(`/playlists/${res.id}`);
            } catch (err) {
                toast(err.message, "error");
            }
        });

        const playlists = await loadPlaylists(true);
        if (!alive()) return;
        clear(
            grid,
            playlists.length
                ? h("div", { class: "grid" }, playlists.map(playlistTile))
                : empty("playlist", "No playlists yet", "Create one, then add songs with the + button next to any song.", h("button", { type: "button", class: "btn btn-primary", onclick: () => newBtn.click() }, icon("plus"), "New playlist"))
        );
    }

    async function pagePlaylist({ args: [id], alive }) {
        clear(main, skeleton(5));
        const p = await api(`/api/playlists/${id}`);
        if (!alive()) return;
        document.title = `${p.name} · WAYL`;

        const title = h("h1", {}, p.name);
        const eyebrow = h("span", { class: "eyebrow" }, p.is_public ? "Public playlist" : "Private playlist");
        const countLine = h("span", {}, `${p.song_count} ${p.song_count === 1 ? "song" : "songs"}`);
        const totalSecs = p.songs.reduce((n, s) => n + (s.duration || 0), 0);
        const listWrap = h("div", { class: "section" });

        function renderSongs() {
            countLine.textContent = `${p.songs.length} ${p.songs.length === 1 ? "song" : "songs"}`;
            clear(
                listWrap,
                p.songs.length
                    ? songList(p.songs, {
                          numbered: true,
                          rowOpts: (s) =>
                              p.is_owner
                                  ? {
                                        onRemove: async () => {
                                            try {
                                                await api(`/api/playlists/${p.id}/songs/${s.id}`, { method: "DELETE" });
                                                p.songs = p.songs.filter((x) => x.id !== s.id);
                                                state.playlists = null;
                                                renderSongs();
                                                toast("Removed from playlist");
                                            } catch (err) {
                                                toast(err.message, "error");
                                            }
                                        },
                                    }
                                  : {},
                      })
                    : empty("music", "This playlist is empty", p.is_owner ? "Search for songs and add them with the + button." : "", p.is_owner && h("a", { class: "btn btn-primary", href: "/search" }, icon("search"), "Find songs"))
            );
        }

        let ownerTools = null;
        if (p.is_owner) {
            const toggle = h("input", { type: "checkbox", checked: p.is_public, role: "switch" });
            const copyBtn = h("button", { type: "button", class: "btn btn-sm", hidden: !p.is_public, onclick: async () => {
                try {
                    await navigator.clipboard.writeText(location.origin + `/playlists/${p.id}`);
                    toast("Link copied");
                } catch {
                    toast("Couldn't copy the link", "error");
                }
            } }, icon("link"), "Copy link");
            toggle.addEventListener("change", async () => {
                try {
                    const res = await api(`/api/playlists/${p.id}`, { method: "PATCH", body: { is_public: toggle.checked } });
                    p.is_public = res.is_public;
                    copyBtn.hidden = !p.is_public;
                    eyebrow.textContent = p.is_public ? "Public playlist" : "Private playlist";
                    state.playlists = null;
                    toast(p.is_public ? "Playlist is public: anyone signed in with the link can see it" : "Playlist is private");
                } catch (err) {
                    toggle.checked = !toggle.checked;
                    toast(err.message, "error");
                }
            });
            ownerTools = h(
                "div",
                { class: "actions" },
                h("label", { class: "switch", title: "Visible to people signed in to this WAYL" }, toggle, "Public"),
                copyBtn,
                shareControls(p),
                h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: async () => {
                    const name = window.prompt("Rename playlist", p.name);
                    if (!name || !name.trim() || name === p.name) return;
                    try {
                        const res = await api(`/api/playlists/${p.id}`, { method: "PATCH", body: { name } });
                        p.name = res.name;
                        title.textContent = res.name;
                        state.playlists = null;
                    } catch (err) {
                        toast(err.message, "error");
                    }
                } }, icon("edit"), "Rename"),
                h("button", { type: "button", class: "btn btn-sm btn-danger", onclick: async () => {
                    const ok = await confirmDialog({ title: "Delete this playlist?", text: `“${p.name}” will be deleted. The songs stay in the catalog.`, confirm: "Delete", danger: true });
                    if (!ok) return;
                    try {
                        await api(`/api/playlists/${p.id}`, { method: "DELETE" });
                        state.playlists = null;
                        toast("Playlist deleted");
                        go("/playlists", true);
                    } catch (err) {
                        toast(err.message, "error");
                    }
                } }, icon("trash"), "Delete")
            );
        }

        const coverBox = mosaic(p.covers);
        coverBox.classList.add("cover-lg");
        clear(
            main,
            h(
                "section",
                { class: "hero" },
                coverBox,
                h(
                    "div",
                    { class: "hero-body" },
                    eyebrow,
                    title,
                    h("div", { class: "dot-list" }, h("a", { href: p.is_owner ? "/profile" : `/user/${p.owner.id}` }, p.owner.username), countLine, totalSecs > 0 && h("span", {}, `${Math.round(totalSecs / 60)} min`), p.synced_from && h("span", {}, `Synced from ${serverLabel(p.synced_from)}`)),
                    p.songs.some(canPlay) && h("div", { class: "actions" }, h("button", { type: "button", class: "btn btn-primary", onclick: () => playQueue(p.songs, 0) }, icon("play"), "Play all")),
                    ownerTools
                )
            ),
            listWrap
        );
        renderSongs();
    }

    // --- my songs ----------------------------------------------------------------------------------

    async function pageMySongs({ params, alive }) {
        const body = h("div", {});
        const tab = params.get("tab") === "recent" ? "recent" : "saved";
        clear(
            main,
            pageHead("Your log", "My songs", "Songs you've saved and what you've played lately."),
            segmented([["saved", "Saved"], ["recent", "Recently played"]], tab, (key) => {
                setQuery({ tab: key === "saved" ? "" : key });
                show(key);
            }),
            body
        );
        let seq = 0;

        async function show(key) {
            const mine = ++seq;
            clear(body, skeleton(6));
            try {
                if (key === "saved") {
                    const res = await api("/api/me/songs?limit=200");
                    if (mine !== seq || !alive()) return;
                    clear(
                        body,
                        res.items.length
                            ? songList(res.items)
                            : empty("heart", "No saved songs yet", "Tap the heart next to any song to keep it here.", h("a", { class: "btn btn-primary", href: "/search" }, icon("search"), "Find songs"))
                    );
                } else {
                    const res = await api("/api/history?limit=100");
                    if (mine !== seq || !alive()) return;
                    clear(
                        body,
                        res.items.length
                            ? h("ul", { class: "list" }, res.items.map((e) => songRow(e.song, { time: timeAgo(e.listened_at) })))
                            : empty("headphones", "Nothing played yet", "Press the headphones button on a song when you're listening to it.", h("a", { class: "btn btn-primary", href: "/search" }, icon("search"), "Find songs"))
                    );
                }
            } catch (err) {
                if (mine === seq) clear(body, errorBox(err, () => show(key)));
            }
        }
        show(tab);
    }

    // --- profile -------------------------------------------------------------------------------------

    function topBars(items, label, linkFor) {
        const max = Math.max(1, ...items.map((i) => i.plays));
        return h(
            "ol",
            { class: "bars" },
            items.map((i) =>
                h(
                    "li",
                    {},
                    h("a", { class: "ellipsis", href: linkFor(i) }, label(i)),
                    h("span", { class: "muted small" }, `${i.plays} ${i.plays === 1 ? "play" : "plays"}`),
                    h("span", { class: "bar" }, h("i", { style: `width:${Math.max(4, (i.plays / max) * 100)}%` }))
                )
            )
        );
    }

    function profileHero(user, { isMe, extra } = {}) {
        return h(
            "section",
            { class: "hero" },
            avatar(user.username, "avatar-lg"),
            h(
                "div",
                { class: "hero-body" },
                h("span", { class: "eyebrow" }, isMe ? "Your profile" : "Profile"),
                h("h1", {}, user.username),
                user.bio && h("p", {}, user.bio),
                h(
                    "div",
                    { class: "counts" },
                    // follower counts only exist when social features are on
                    user.followers !== undefined && h("span", {}, h("b", { class: "followers-count" }, user.followers), " followers"),
                    user.following !== undefined && h("span", {}, h("b", {}, user.following), " following"),
                    user.joined_at && h("span", {}, `Joined ${monthYear(user.joined_at)}`)
                ),
                extra
            )
        );
    }

    async function pageProfile({ alive }) {
        clear(main, skeleton(4));
        const me = await api("/api/me");
        if (!alive()) return;
        state.me = { ...state.me, ...me };

        const statsBody = h("div", {});
        const range = h(
            "select",
            { class: "input", "aria-label": "Time range" },
            h("option", { value: "7" }, "Last 7 days"),
            h("option", { value: "30", selected: true }, "Last 30 days"),
            h("option", { value: "365" }, "Last year"),
            h("option", { value: "3650" }, "All time")
        );
        range.addEventListener("change", () => loadStats());

        async function loadStats() {
            clear(statsBody, skeleton(3));
            try {
                const s = await api(`/api/stats?days=${range.value}`);
                if (!alive()) return;
                clear(
                    statsBody,
                    h(
                        "div",
                        { class: "stats" },
                        h("div", { class: "stat" }, h("b", {}, s.total_listens), h("span", {}, "listens")),
                        h("div", { class: "stat" }, h("b", {}, s.total_minutes), h("span", {}, "minutes")),
                        h("div", { class: "stat" }, h("b", {}, me.saved_songs), h("span", {}, "saved songs")),
                        h("div", { class: "stat" }, h("b", {}, me.playlists), h("span", {}, "playlists"))
                    ),
                    s.total_listens
                        ? h(
                              "div",
                              { class: "two-col section" },
                              h("div", { class: "card" }, h("h3", {}, "Top songs"), h("p", { class: "muted" }, "Most played in this period"), topBars(s.top_songs, (i) => `${i.title} · ${i.artist}`, (i) => `/song/${i.id}`)),
                              h("div", { class: "card" }, h("h3", {}, "Top artists"), h("p", { class: "muted" }, "Most played in this period"), topBars(s.top_artists, (i) => i.name, (i) => (i.id ? `/artist/${i.id}` : "/profile")))
                          )
                        : empty("headphones", "No listens in this period", "Log what you're listening to and your top songs and artists will appear here.")
                );
            } catch (err) {
                clear(statsBody, errorBox(err, loadStats));
            }
        }

        clear(
            main,
            profileHero(me, {
                isMe: true,
                extra: h("div", { class: "actions" }, h("a", { class: "btn btn-sm", href: "/settings" }, icon("sliders"), "Edit profile & settings")),
            }),
            h("div", { class: "section" }, h("h2", { class: "section-title" }, "Your stats", range), statsBody)
        );
        loadStats();
    }

    /** Account cards for the settings page: profile, password, sign out, delete. */
    function accountCards(me) {
        // edit profile
        const username = h("input", { class: "input", name: "username", value: me.username, required: true, minlength: "2", maxlength: "30", pattern: "[A-Za-z0-9_.]{2,30}", autocomplete: "username" });
        const bio = h("textarea", { class: "input", name: "bio", maxlength: "160", rows: "2", placeholder: "A few words about your taste in music" });
        bio.value = me.bio || "";
        const profileForm = h(
            "form",
            { class: "form" },
            field("Username", username),
            field("Bio", bio, h("span", { class: "hint" }, "160 characters max")),
            h("div", {}, h("button", { type: "submit", class: "btn btn-primary" }, "Save changes"))
        );
        profileForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                const res = await api("/api/me", { method: "PATCH", body: { username: username.value.trim(), bio: bio.value } });
                state.me = { ...state.me, ...res };
                toast("Profile saved");
            } catch (err) {
                toast(err.message, "error");
            }
        });

        // change password
        const current = pwField("Current password", { name: "current", autocomplete: "current-password" });
        const next = pwField("New password", { name: "next", autocomplete: "new-password", minlength: "8", maxlength: "128" }, h("span", { class: "hint" }, "At least 8 characters"));
        const pwForm = h("form", { class: "form" }, current, next, h("div", {}, h("button", { type: "submit", class: "btn" }, icon("lock"), "Change password")));
        pwForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const data = new FormData(pwForm);
            try {
                await api("/api/me/password", { method: "POST", body: { current_password: data.get("current"), new_password: data.get("next") } });
                pwForm.reset();
                toast("Password changed. Other devices have been signed out.");
            } catch (err) {
                toast(err.message, "error");
            }
        });

        return [
            h("div", { class: "card" }, h("h3", {}, "Edit profile"), h("p", { class: "muted" }, "Your username and bio are visible to everyone on WAYL."), profileForm),
            h("div", { class: "card" }, h("h3", {}, "Password"), h("p", { class: "muted" }, "Changing it signs you out on every other device."), pwForm),
            h(
                "div",
                { class: "card" },
                h("h3", {}, "Session"),
                h("p", { class: "muted" }, `Signed in as ${me.email}. Only you can see your email.`),
                h("button", { type: "button", class: "btn", onclick: signOut }, icon("logout"), "Sign out")
            ),
            h(
                "div",
                { class: "card" },
                h("h3", {}, "Delete account"),
                h("p", { class: "muted" }, "Permanently deletes your account, listens, saved songs, playlists and server connections. This can't be undone."),
                h("button", { type: "button", class: "btn btn-danger", onclick: deleteAccount }, icon("trash"), "Delete account")
            ),
        ];
    }

    async function signOut() {
        try {
            await api("/auth/logout", { method: "POST" });
        } catch {
            /* signed out anyway */
        }
        state.me = null;
        state.playlists = null;
        go("/login", true);
    }

    async function deleteAccount() {
        const password = await confirmDialog({
            title: "Delete your account?",
            text: `Everything will be deleted: listens, saved songs, playlists${social() ? ", followers" : ""} and server connections. Enter your password to confirm.`,
            confirm: "Delete forever",
            danger: true,
            password: true,
        });
        if (!password) return;
        try {
            await api("/api/me", { method: "DELETE", body: { password } });
            state.me = null;
            go("/register", true);
            toast("Your account has been deleted");
        } catch (err) {
            toast(err.message, "error");
        }
    }

    // --- settings ------------------------------------------------------------------------------------

    async function pageSettings({ alive }) {
        clear(main, skeleton(4));
        const [me, servers, token, unmatched, sharing] = await Promise.all([
            api("/api/me"),
            api("/api/servers"),
            api("/api/me/listen-token"),
            api("/api/me/unmatched"),
            api("/api/me/sharing"),
        ]);
        if (!alive()) return;
        state.me = { ...state.me, ...me };

        const serversBox = h("div", {});
        const refresh = async () => {
            const [fresh, meNow] = await Promise.all([api("/api/servers"), api("/auth/session")]);
            state.me = meNow.user;
            if (alive()) renderServers(fresh.items);
        };

        function renderServers(items) {
            const byKind = Object.fromEntries(items.map((s) => [s.kind, s]));
            clear(
                serversBox,
                byKind.plex ? serverCard(byKind.plex, refresh, token) : plexConnectCard(refresh),
                byKind.navidrome ? serverCard(byKind.navidrome, refresh, token) : navidromeConnectCard(refresh)
            );
            // keep the status fresh while a sync runs
            if (items.some((s) => s.syncing)) setTimeout(() => alive() && refresh(), 4000);
        }
        renderServers(servers.items);

        clear(
            main,
            pageHead("Account", "Settings", "Connect your music server, share with friends and manage your account."),
            h(
                "div",
                { class: "section", id: "servers" },
                h("h2", { class: "section-title" }, "Music servers"),
                h("p", { class: "muted small section-lede" }, "Connect Plex or Navidrome to log what you play there, import your playlists, and stream your own music in WAYL."),
                serversBox
            ),
            h("div", { class: "section" }, h("h2", { class: "section-title" }, "Scrobbling"), scrobbleCard(token)),
            h("div", { class: "section", id: "sharing" }, h("h2", { class: "section-title" }, "Sharing"), sharingCard(sharing)),
            unmatchedSection(unmatched),
            h("div", { class: "section" }, h("h2", { class: "section-title" }, "Account"), accountCards(me))
        );
    }

    function ago(iso) {
        return iso ? timeAgo(iso) : "never";
    }

    function serverCard(server, refresh, token) {
        const label = serverLabel(server.kind);
        const toggle = (key, text, hint) => {
            const input = h("input", { type: "checkbox", role: "switch", checked: server[key] });
            input.addEventListener("change", async () => {
                try {
                    await api(`/api/servers/${server.id}`, { method: "PATCH", body: { [key]: input.checked } });
                    toast(input.checked ? `${text}: on` : `${text}: off`);
                    refresh();
                } catch (err) {
                    input.checked = !input.checked;
                    toast(err.message, "error");
                }
            });
            return h("div", { class: "setting-row" }, h("div", {}, h("strong", {}, text), h("span", { class: "muted small" }, hint)), h("label", { class: "switch" }, input, h("span", { class: "visually-hidden" }, text)));
        };
        const status = [
            `${fmtNumber.format(server.library_count)} tracks indexed`,
            `library ${ago(server.last_library_sync_at)}`,
            server.sync_listens && `listens checked ${ago(server.last_listen_sync_at)}`,
            server.sync_playlists && `${server.imported_playlists} playlists imported`,
        ].filter(Boolean);

        const syncBtn = h("button", { type: "button", class: "btn btn-sm", disabled: server.syncing, onclick: async () => {
            syncBtn.disabled = true;
            try {
                await api(`/api/servers/${server.id}/sync`, { method: "POST" });
                toast("Sync started");
                refresh();
            } catch (err) {
                syncBtn.disabled = false;
                toast(err.message, "error");
            }
        } }, icon("refresh"), server.syncing ? "Syncing…" : "Sync now");

        const disconnect = h("button", { type: "button", class: "btn btn-sm btn-danger", onclick: async () => {
            const ok = await confirmDialog({
                title: `Disconnect ${label}?`,
                text: "WAYL forgets this server's login and library. Your listens and imported playlists stay.",
                confirm: "Disconnect",
                danger: true,
            });
            if (!ok) return;
            try {
                await api(`/api/servers/${server.id}`, { method: "DELETE" });
                toast(`${label} disconnected`);
                refresh();
            } catch (err) {
                toast(err.message, "error");
            }
        } }, "Disconnect");

        return h(
            "div",
            { class: "card server-card" },
            h(
                "div",
                { class: "server-head" },
                h("span", { class: `server-logo ${server.kind}`, "aria-hidden": "true" }, label[0]),
                h(
                    "div",
                    { class: "row-main" },
                    h("h3", {}, label, " ", h("span", { class: "chip chip-ok" }, icon("check"), "Connected")),
                    h("span", { class: "muted small ellipsis" }, server.name !== label ? `${server.name} · ` : "", server.url, server.username ? ` · ${server.username}` : "")
                )
            ),
            server.last_error && h("div", { class: "form-error", role: "alert" }, server.last_error),
            h("p", { class: "muted small" }, server.syncing ? "Syncing now… " : "", status.join(" · ")),
            toggle("sync_listens", "Log my listens", server.kind === "plex" ? "Imports your Plex play history every few minutes" : "Checks what you're playing every minute"),
            toggle("sync_playlists", "Import playlists", "Mirrors your server's playlists in WAYL (they're re-synced, so edit them on the server)"),
            server.kind === "navidrome" ? navidromeScrobbleHelp(token) : null,
            h("div", { class: "actions" }, syncBtn, disconnect)
        );
    }

    function navidromeScrobbleHelp(token) {
        return h(
            "details",
            { class: "help" },
            h("summary", {}, "Instant scrobbling (recommended)"),
            h(
                "ol",
                {},
                h("li", {}, "In Navidrome's configuration, set ", h("code", {}, `ND_LISTENBRAINZ_BASEURL=${token.api_url}`), " and restart it. (This sends everyone's ListenBrainz scrobbles on that Navidrome to WAYL.)"),
                h("li", {}, "Create a scrobble token below, under Scrobbling."),
                h("li", {}, "In Navidrome, open Personal settings, turn on ", h("strong", {}, "Scrobble to ListenBrainz"), " and paste the token.")
            ),
            h("p", { class: "muted small" }, "Without this, WAYL still logs what you play by checking Navidrome every minute, but very short tracks can slip through.")
        );
    }

    function plexConnectCard(refresh) {
        const manual = h("form", { class: "form", hidden: true },
            field("Server address", h("input", { class: "input", name: "url", placeholder: "http://192.168.1.10:32400", required: true })),
            field("Plex token", h("input", { class: "input", name: "token", required: true, autocomplete: "off" }), h("a", { class: "link small", href: "https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/", target: "_blank", rel: "noopener" }, "Where do I find it?")),
            h("label", { class: "switch" }, h("input", { type: "checkbox", name: "owned", checked: true }), "I own this server (only my own plays get imported)"),
            h("div", {}, h("button", { type: "submit", class: "btn btn-primary" }, "Connect"))
        );
        manual.addEventListener("submit", async (e) => {
            e.preventDefault();
            const data = new FormData(manual);
            const btn = manual.querySelector("[type=submit]");
            busy(btn, true, "Connecting…");
            try {
                await api("/api/servers", { method: "POST", body: { kind: "plex", url: data.get("url"), token: data.get("token"), owned: data.get("owned") === "on" } });
                toast("Plex connected. Indexing your library…");
                refresh();
            } catch (err) {
                toast(err.message, "error");
            } finally {
                busy(btn, false);
            }
        });
        const signIn = h("button", { type: "button", class: "btn btn-primary", onclick: () => plexSignIn(refresh) }, "Sign in with Plex");
        return h(
            "div",
            { class: "card server-card" },
            h("div", { class: "server-head" }, h("span", { class: "server-logo plex", "aria-hidden": "true" }, "P"), h("div", { class: "row-main" }, h("h3", {}, "Plex"), h("span", { class: "muted small" }, "Sign in with your Plex account, then pick a server."))),
            h("div", { class: "actions" }, signIn, h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: () => (manual.hidden = !manual.hidden) }, "Enter address and token instead")),
            manual
        );
    }

    async function plexSignIn(refresh) {
        // Open the window right away (inside the click), or popup blockers step in.
        const popup = window.open("", "plex-auth", "width=600,height=720");
        let pin;
        try {
            pin = await api("/api/servers/plex/pin", { method: "POST" });
        } catch (err) {
            if (popup) popup.close();
            return toast(err.message, "error");
        }
        if (popup) popup.location.href = pin.auth_url;
        else window.open(pin.auth_url, "_blank", "noopener");

        const status = h("p", { class: "muted" }, "Approve WAYL in the Plex window. This page will continue by itself.");
        openDialog(h("h2", {}, "Sign in with Plex"), status, h("div", { class: "dialog-actions" }, h("button", { type: "button", class: "btn btn-ghost", onclick: () => dialog.close() }, "Cancel")));

        const deadline = Date.now() + 5 * 60 * 1000;
        while (dialog.open && Date.now() < deadline) {
            await new Promise((r) => setTimeout(r, 2000));
            let res;
            try {
                res = await api(`/api/servers/plex/pin/${pin.pin_id}`);
            } catch (err) {
                status.textContent = err.message;
                return;
            }
            if (res.status !== "ready") continue;
            if (popup && !popup.closed) popup.close();
            if (!res.servers.length) {
                status.textContent = "This Plex account has no servers WAYL can use.";
                return;
            }
            return pickPlexServer(res.servers, refresh);
        }
        if (dialog.open) status.textContent = "Timed out. Try again.";
    }

    function pickPlexServer(servers, refresh) {
        const list = h(
            "ul",
            { class: "pick-list" },
            servers.map((s) =>
                h(
                    "li",
                    {},
                    h("button", { type: "button", onclick: async (e) => {
                        const btn = e.currentTarget;
                        btn.disabled = true;
                        clear(note, "Finding a way to reach this server…");
                        try {
                            await api("/api/servers", { method: "POST", body: { kind: "plex", server: s.id } });
                            dialog.close();
                            toast(`${s.name} connected. Indexing your library…`);
                            refresh();
                        } catch (err) {
                            btn.disabled = false;
                            clear(note, h("span", { class: "form-error" }, err.message));
                        }
                    } },
                    h("span", { class: "server-logo plex" }, "P"),
                    h("span", { class: "row-main" }, h("span", { class: "row-title" }, s.name), h("span", { class: "row-sub" }, s.owned ? "Your server" : "Shared with you")))
                )
            )
        );
        const note = h("p", { class: "muted small" });
        openDialog(h("h2", {}, "Choose a Plex server"), list, note);
    }

    function navidromeConnectCard(refresh) {
        const form = h(
            "form",
            { class: "form" },
            field("Server address", h("input", { class: "input", name: "url", placeholder: "http://192.168.1.10:4533", required: true }), h("span", { class: "hint" }, "As WAYL's server can reach it")),
            h("div", { class: "two-col" },
                field("Username", h("input", { class: "input", name: "username", required: true, autocomplete: "off" })),
                pwField("Password", { name: "password", autocomplete: "off" })),
            h("div", {}, h("button", { type: "submit", class: "btn btn-primary" }, "Connect Navidrome"))
        );
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const data = new FormData(form);
            const btn = form.querySelector("[type=submit]");
            busy(btn, true, "Connecting…");
            try {
                await api("/api/servers", { method: "POST", body: { kind: "navidrome", url: data.get("url"), username: data.get("username"), password: data.get("password") } });
                toast("Navidrome connected. Indexing your library…");
                refresh();
            } catch (err) {
                toast(err.message, "error");
            } finally {
                busy(btn, false);
            }
        });
        return h(
            "div",
            { class: "card server-card" },
            h("div", { class: "server-head" }, h("span", { class: "server-logo navidrome", "aria-hidden": "true" }, "N"), h("div", { class: "row-main" }, h("h3", {}, "Navidrome"), h("span", { class: "muted small" }, "Or any Subsonic-compatible server. Your password is stored encrypted."))),
            form
        );
    }

    function scrobbleCard(token) {
        const body = h("div", { class: "form" });
        const card = h(
            "div",
            { class: "card" },
            h("h3", {}, "Scrobble token"),
            h("p", { class: "muted" }, "WAYL speaks the ListenBrainz scrobbling API, so any player that lets you change the ListenBrainz server can log listens here."),
            body
        );
        const paint = (t, fresh) => {
            clear(
                body,
                field("API URL", copyable(t.api_url)),
                fresh
                    ? h("div", {}, field("Your token", copyable(fresh)), h("p", { class: "form-success small" }, "Copy it now: it won't be shown again."))
                    : h("p", { class: "muted small" }, t.exists ? `Token created ${ago(t.created_at)}, last used ${ago(t.last_used_at)}.` : "No token yet."),
                h(
                    "div",
                    { class: "actions" },
                    h("button", { type: "button", class: "btn btn-sm", onclick: async () => {
                        if (t.exists && !(await confirmDialog({ title: "Replace the token?", text: "Players using the old one will stop scrobbling until you paste the new one.", confirm: "Replace" }))) return;
                        const res = await api("/api/me/listen-token", { method: "POST" });
                        paint({ ...t, exists: true, created_at: new Date().toISOString(), last_used_at: null }, res.token);
                    } }, icon("key"), t.exists ? "Replace token" : "Create token"),
                    t.exists && h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: async () => {
                        await api("/api/me/listen-token", { method: "DELETE" });
                        paint({ ...t, exists: false }, null);
                        toast("Token revoked");
                    } }, "Revoke")
                )
            );
        };
        paint(token, null);
        return card;
    }

    function copyable(text) {
        const input = h("input", { class: "input mono", value: text, readonly: true });
        const btn = h("button", { type: "button", class: "icon-btn", "aria-label": "Copy", title: "Copy", onclick: async () => {
            try {
                await navigator.clipboard.writeText(text);
                toast("Copied");
            } catch {
                input.select();
            }
        } }, icon("copy"));
        return h("div", { class: "input-group" }, input, btn);
    }

    function unmatchedSection(data) {
        const box = h("div", { class: "section", hidden: !data.unmatched && !data.pending });
        const paint = (d) => {
            box.hidden = !d.unmatched && !d.pending;
            clear(
                box,
                h("h2", { class: "section-title" }, "Listens WAYL couldn't match"),
                h(
                    "div",
                    { class: "card" },
                    h("p", { class: "muted" }, `${d.unmatched} unmatched${d.pending ? `, ${d.pending} waiting to be matched` : ""}. These tracks weren't found in MusicBrainz, so they're not in your history yet. Fixing their tags on your server usually helps.`),
                    h("ul", { class: "list compact" }, d.items.filter((i) => i.status === "unmatched").slice(0, 10).map((i) =>
                        h("li", { class: "row" }, h("div", { class: "row-main" }, h("span", { class: "row-title" }, i.title), h("span", { class: "row-sub" }, `${i.artist}${i.album ? " · " + i.album : ""} · ${serverLabel(i.source) === "your server" ? i.source : serverLabel(i.source)} · ${timeAgo(i.listened_at)}`)))
                    )),
                    h(
                        "div",
                        { class: "actions" },
                        h("button", { type: "button", class: "btn btn-sm", onclick: async (e) => {
                            busy(e.currentTarget, true, "Matching…");
                            try {
                                const res = await api("/api/me/unmatched", { method: "POST" });
                                toast(`${res.added} added to your history`);
                                paint(await api("/api/me/unmatched"));
                            } catch (err) {
                                toast(err.message, "error");
                            }
                        } }, icon("refresh"), "Try again"),
                        h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: async () => {
                            await api("/api/me/unmatched", { method: "DELETE" });
                            paint(await api("/api/me/unmatched"));
                        } }, "Dismiss all")
                    )
                )
            );
        };
        paint(data);
        return box;
    }

    // --- sharing (publishing) ---------------------------------------------------------------------------

    function warningBox(info) {
        return info && info.warning ? h("div", { class: "form-error", role: "alert" }, info.warning) : null;
    }

    /** Owner controls on a playlist page: a read-only link anyone (on any WAYL) can open. */
    function shareControls(p) {
        const box = h("span", { class: "share-controls" });
        const paint = (info) => {
            p.share = info;
            const toggle = h("input", { type: "checkbox", role: "switch", checked: info.shared });
            toggle.addEventListener("change", async () => {
                try {
                    paint(await api(`/api/playlists/${p.id}/share`, { method: toggle.checked ? "PUT" : "DELETE" }));
                    toast(toggle.checked ? "Share link on: anyone with the link can see this playlist" : "Share link off: the old link stops working");
                } catch (err) {
                    toggle.checked = !toggle.checked;
                    toast(err.message, "error");
                }
            });
            clear(
                box,
                h("label", { class: "switch", title: "A read-only link friends can open from their own WAYL" }, toggle, "Share link"),
                info.shared && h("button", { type: "button", class: "btn btn-sm", onclick: () => copyText(info.url, "Share link copied") }, icon("copy"), "Copy share link"),
                info.shared && h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: async () => {
                    const ok = await confirmDialog({ title: "Reset the share link?", text: "The current link stops working. Friends who subscribed will need the new one.", confirm: "Reset" });
                    if (ok) {
                        paint(await api(`/api/playlists/${p.id}/share/reset`, { method: "POST" }));
                        toast("New share link created");
                    }
                } }, "Reset link"),
                info.shared && info.warning && h("span", { class: "chip chip-warn", title: info.warning }, "Not reachable by friends")
            );
        };
        paint(p.share || { shared: false, url: null });
        return box;
    }

    async function copyText(text, done = "Copied") {
        try {
            await navigator.clipboard.writeText(text);
            toast(done);
        } catch {
            window.prompt("Copy this link:", text);
        }
    }

    function sharingCard(info) {
        const body = h("div", { class: "form" });
        const card = h(
            "div",
            { class: "card" },
            h("h3", {}, "Your profile link"),
            h("p", { class: "muted" }, "A read-only page friends can subscribe to from their own WAYL: your name, the playlists you share, and only what you turn on below. Only song information is shared, never your music files or your server."),
            body
        );
        const save = async (patch, message) => {
            try {
                paint(await api("/api/me/sharing", { method: "PATCH", body: patch }));
                if (message) toast(message);
            } catch (err) {
                toast(err.message, "error");
                paint(info);
            }
        };
        const row = (key, text, hint) => {
            const input = h("input", { type: "checkbox", role: "switch", checked: info[key] });
            input.addEventListener("change", () => save({ [key]: input.checked }));
            return h("div", { class: "setting-row" }, h("div", {}, h("strong", {}, text), h("span", { class: "muted small" }, hint)), h("label", { class: "switch" }, input, h("span", { class: "visually-hidden" }, text)));
        };
        function paint(next) {
            info = next;
            const name = h("input", { class: "input", name: "display_name", value: info.display_name, maxlength: "60" });
            const nameForm = h("form", { class: "inline-form" }, name, h("button", { type: "submit", class: "btn" }, "Save name"));
            nameForm.addEventListener("submit", (e) => {
                e.preventDefault();
                save({ display_name: name.value }, "Display name saved");
            });
            clear(
                body,
                warningBox(info),
                row("enabled", "Share my profile", "Anyone with the link can see it"),
                info.enabled && field("Profile link", copyable(info.url)),
                info.enabled && h("div", { class: "actions" }, h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: async () => {
                    const ok = await confirmDialog({ title: "Reset your profile link?", text: "The current link stops working right away.", confirm: "Reset" });
                    if (ok) paint(await api("/api/me/sharing/reset", { method: "POST" }));
                } }, "Reset link")),
                row("share_listens", "Share my recent listens", "Your last 50 listens, visible to anyone with your profile link. Off by default."),
                row("share_top_artists", "Share my top artists", "Your 10 most played artists of the last 30 days, visible to anyone with the link."),
                field("Display name", nameForm, h("span", { class: "hint" }, "Shown to friends instead of your username")),
                h("p", { class: "muted small" }, "To share a playlist, open it and turn on its share link.")
            );
        }
        paint(info);
        return card;
    }

    // --- friends (subscriptions to other people's share links) ----------------------------------------

    const FRIENDS_IDEA = "Paste a link a friend shared from their WAYL to see their playlists and which songs you already have.";

    async function pageFriends({ alive }) {
        const input = h("input", { class: "input", type: "url", name: "url", placeholder: "https://their-wayl.example/share/v1/…", required: true, "aria-label": "Share link" });
        const addBtn = h("button", { type: "submit", class: "btn btn-primary" }, icon("plus"), "Add");
        const form = h("form", { class: "inline-form card" }, input, addBtn);
        const list = h("div", { class: "section" }, skeleton(3));
        clear(main, pageHead("Sharing", "Friends", FRIENDS_IDEA), form, list);

        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            busy(addBtn, true, "Adding…");
            try {
                const sub = await api("/api/subscriptions", { method: "POST", body: { url: input.value.trim() } });
                go(`/friends/${sub.id}`);
            } catch (err) {
                toast(err.message, "error");
            } finally {
                busy(addBtn, false);
            }
        });

        const items = (await api("/api/subscriptions")).items;
        if (!alive()) return;
        clear(
            list,
            items.length
                ? h("ul", { class: "list sub-list" }, items.map((sub) => subscriptionRow(sub, () => render())))
                : empty("share", "No friends added yet", FRIENDS_IDEA + " You can share your own from Settings → Sharing.", h("a", { class: "btn", href: "/settings#sharing" }, icon("share"), "Share yours"))
        );
    }

    function subscriptionRow(sub, onChange) {
        const what = sub.kind === "profile" ? `${sub.count} shared ${sub.count === 1 ? "playlist" : "playlists"}` : `${sub.count} ${sub.count === 1 ? "song" : "songs"}`;
        return h(
            "li",
            { class: "person" },
            sub.kind === "profile" ? avatar(sub.title) : h("span", { class: "cover" }, icon("playlist")),
            h(
                "div",
                { class: "row-main" },
                h("div", { class: "row-title-line" }, h("a", { class: "row-title", href: `/friends/${sub.id}` }, sub.title), sub.last_error && h("span", { class: "chip chip-warn", title: sub.last_error }, "Can't update")),
                h("span", { class: "row-sub" }, [sub.kind === "profile" ? "Profile" : `Playlist by ${sub.owner_name || "someone"}`, what, sub.updated_at && `updated ${timeAgo(sub.updated_at)}`].filter(Boolean).join(" · "))
            ),
            h("button", { type: "button", class: "icon-btn", title: "Check for updates", "aria-label": `Refresh ${sub.title}`, onclick: async (e) => {
                e.currentTarget.disabled = true;
                try {
                    const res = await api(`/api/subscriptions/${sub.id}/refresh`, { method: "POST" });
                    toast(res.last_error ? res.last_error : "Up to date", res.last_error ? "error" : "");
                    onChange();
                } catch (err) {
                    toast(err.message, "error");
                }
            } }, icon("refresh")),
            h("button", { type: "button", class: "icon-btn", title: "Remove", "aria-label": `Remove ${sub.title}`, onclick: async () => {
                const ok = await confirmDialog({ title: `Remove “${sub.title}”?`, text: "You can add it again with the same link.", confirm: "Remove", danger: true });
                if (!ok) return;
                await api(`/api/subscriptions/${sub.id}`, { method: "DELETE" });
                toast("Removed");
                onChange();
            } }, icon("trash"))
        );
    }

    async function pageSubscription({ args: [id], alive }) {
        clear(main, skeleton(5));
        const sub = await api(`/api/subscriptions/${id}`);
        if (!alive()) return;
        document.title = `${sub.title} · WAYL`;
        const back = h("a", { class: "btn btn-sm btn-ghost back-link", href: sub.parent_id ? `/friends/${sub.parent_id}` : "/friends" }, icon("arrowLeft"), sub.parent_id ? "Back to profile" : "Friends");
        const stale = sub.last_error && h("div", { class: "form-error", role: "status" }, `Couldn't update this (${sub.last_error}). Showing the copy from ${timeAgo(sub.fetched_at)}.`);
        if (sub.kind === "profile") return renderProfileSub(sub, back, stale, alive);

        const tracks = sub.tracks;
        const owned = tracks.filter((t) => t.owned);
        const ownedLine =
            sub.owned_count === null
                ? h("span", {}, h("a", { class: "link", href: "/settings#servers" }, "Connect your server"), " to see which songs you own")
                : h("span", {}, `You own ${sub.owned_count} of ${sub.total}`);
        const coverBox = mosaic(tracks.map((t) => t.cover).filter(Boolean).slice(0, 4));
        coverBox.classList.add("cover-lg");
        const actions = h(
            "div",
            { class: "actions" },
            owned.length && state.me.has_servers ? h("button", { type: "button", class: "btn btn-primary", onclick: () => playQueue(tracks, tracks.indexOf(owned[0])) }, icon("play"), "Play what you own") : null,
            h("button", { type: "button", class: owned.length ? "btn" : "btn btn-primary", onclick: async (e) => {
                busy(e.currentTarget, true, "Copying…");
                try {
                    const res = await api(`/api/subscriptions/${sub.id}/copy`, { method: "POST" });
                    state.playlists = null;
                    toast(res.skipped ? `${res.message} (${res.skipped} not found in MusicBrainz)` : res.message);
                    go(`/playlists/${res.playlist_id}`);
                } catch (err) {
                    toast(err.message, "error");
                    busy(e.currentTarget, false);
                }
            } }, icon("copy"), "Copy to my playlists"),
            sub.owner_profile_url && !sub.parent_id && h("button", { type: "button", class: "btn btn-ghost", onclick: async () => {
                try {
                    const prof = await api("/api/subscriptions", { method: "POST", body: { url: sub.owner_profile_url } });
                    go(`/friends/${prof.id}`);
                } catch (err) {
                    toast(err.message, "error");
                }
            } }, icon("user"), `${sub.owner_name || "Owner"}'s profile`)
        );
        clear(
            main,
            back,
            h(
                "section",
                { class: "hero" },
                coverBox,
                h(
                    "div",
                    { class: "hero-body" },
                    h("span", { class: "eyebrow" }, "Shared playlist"),
                    h("h1", {}, sub.title),
                    h("div", { class: "dot-list" }, sub.owner_name && h("span", {}, `by ${sub.owner_name}`), h("span", {}, `${sub.total} ${sub.total === 1 ? "song" : "songs"}`), sub.updated_at && h("span", {}, `updated ${timeAgo(sub.updated_at)}`)),
                    h("div", { class: "dot-list" }, ownedLine),
                    actions
                )
            ),
            stale,
            h("div", { class: "section" }, tracks.length ? songList(tracks, { numbered: true, rowOpts: () => ({ showMissing: true }) }) : empty("music", "This playlist is empty", ""))
        );
    }

    function renderProfileSub(sub, back, stale, alive) {
        const openPlaylist = async (p) => {
            try {
                const child = p.subscription_id ? { id: p.subscription_id } : await api(`/api/subscriptions/${sub.id}/open`, { method: "POST", body: { url: p.url } });
                if (alive()) go(`/friends/${child.id}`);
            } catch (err) {
                toast(err.message, "error");
            }
        };
        const tiles = sub.playlists.map((p) =>
            h(
                "button",
                { type: "button", class: "tile", onclick: () => openPlaylist(p) },
                mosaic([]),
                h("span", { class: "tile-title" }, p.name),
                h("span", { class: "tile-sub" }, [p.track_count != null && `${p.track_count} songs`, p.updated_at && `updated ${timeAgo(p.updated_at)}`].filter(Boolean).join(" · "))
            )
        );
        const listens = sub.recent_listens;
        const artists = sub.top_artists;
        clear(
            main,
            back,
            h(
                "section",
                { class: "hero" },
                avatar(sub.title, "avatar-lg"),
                h(
                    "div",
                    { class: "hero-body" },
                    h("span", { class: "eyebrow" }, "Friend"),
                    h("h1", {}, sub.title),
                    sub.bio && h("p", {}, sub.bio),
                    h("div", { class: "dot-list" }, h("span", {}, `${sub.playlists.length} shared ${sub.playlists.length === 1 ? "playlist" : "playlists"}`), sub.updated_at && h("span", {}, `updated ${timeAgo(sub.updated_at)}`))
                )
            ),
            stale,
            h("div", { class: "section" }, h("h2", { class: "section-title" }, "Playlists"), tiles.length ? h("div", { class: "grid" }, tiles) : h("p", { class: "muted" }, "No shared playlists yet.")),
            listens &&
                h(
                    "div",
                    { class: "section" },
                    h("h2", { class: "section-title" }, "Recent listens"),
                    listens.length ? h("ul", { class: "list" }, listens.map((l, i) => songRow(l.song, { time: timeAgo(l.listened_at), queue: listens.map((x) => x.song), queueIndex: i, showMissing: true }))) : h("p", { class: "muted" }, "Nothing yet.")
                ),
            artists &&
                artists.length > 0 &&
                h(
                    "div",
                    { class: "section" },
                    h("h2", { class: "section-title" }, "Top artists", h("span", { class: "muted small" }, "last 30 days")),
                    h("div", { class: "card" }, topBars(artists, (a) => a.name, (a) => (a.mbid ? `/artist/${a.mbid}` : "/friends")))
                )
        );
    }

    // --- someone else's profile ------------------------------------------------------------------------

    async function pageUser({ args: [id], alive }) {
        if (state.me && String(state.me.id) === id) return go("/profile", true);
        clear(main, skeleton(4));
        const user = await api(`/api/users/${id}`);
        if (!alive()) return;
        document.title = `${user.username} · WAYL`;

        const listens = h("div", {});
        const playlists = h("div", {});
        const followersCount = () => main.querySelector(".followers-count");

        async function loadListens() {
            if (!user.listens_visible) {
                clear(listens, empty("lock", `Follow ${user.username} to see their listens`, "Listens are only visible to followers."));
                return;
            }
            clear(listens, skeleton(4));
            try {
                const items = (await api(`/api/users/${id}/listens?limit=30`)).items;
                if (!alive()) return;
                clear(
                    listens,
                    items.length
                        ? h("ul", { class: "list" }, items.map((e) => songRow(e.song, { time: timeAgo(e.listened_at) })))
                        : empty("headphones", "No listens yet", `${user.username} hasn't logged anything yet.`)
                );
            } catch (err) {
                clear(listens, errorBox(err, loadListens));
            }
        }

        const follow = social() && followButton(
            user,
            (u) => {
                user.followers += u.is_following ? 1 : -1;
                followersCount().textContent = user.followers;
                user.listens_visible = u.is_following;
                loadListens();
            },
            true
        );

        clear(
            main,
            profileHero(user, { extra: follow && h("div", { class: "actions" }, follow) }),
            social() && h("div", { class: "section" }, h("h2", { class: "section-title" }, "Recent listens"), listens),
            h("div", { class: "section" }, h("h2", { class: "section-title" }, "Public playlists"), playlists)
        );
        if (social()) loadListens();

        try {
            const items = (await api(`/api/users/${id}/playlists`)).items;
            if (!alive()) return;
            clear(playlists, items.length ? h("div", { class: "grid" }, items.map(playlistTile)) : h("p", { class: "muted" }, "No public playlists."));
        } catch (err) {
            clear(playlists, errorBox(err));
        }
    }

    // --- theme ------------------------------------------------------------------------------------------
    // The inline script in <head> sets data-theme before the first paint; this only handles the toggle.

    function applyTheme(theme) {
        document.documentElement.dataset.theme = theme;
        $('meta[name="theme-color"]').setAttribute("content", theme === "light" ? "#fafafa" : "#0a0a0a");
        $("#theme-toggle").setAttribute("aria-label", theme === "light" ? "Switch to dark theme" : "Switch to light theme");
    }

    function setupTheme() {
        const button = $("#theme-toggle");
        applyTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark");
        button.addEventListener("click", (e) => {
            const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
            prefsRaw("theme", next);
            const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
            if (!document.startViewTransition || still) return applyTheme(next);
            // A circle grows from the click point (or the button's centre for keyboard use).
            const box = button.getBoundingClientRect();
            const pointer = e.detail > 0;
            const x = pointer ? e.clientX : box.left + box.width / 2;
            const y = pointer ? e.clientY : box.top + box.height / 2;
            const r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
            document.startViewTransition(() => applyTheme(next)).ready.then(() => {
                document.documentElement.animate(
                    { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
                    { duration: 600, easing: "cubic-bezier(0.22, 1, 0.36, 1)", pseudoElement: "::view-transition-new(root)" }
                );
            });
        });
    }

    /** The theme uses the plain "theme" key (as in the design system), read by the <head> script. */
    function prefsRaw(key, value) {
        try {
            localStorage.setItem(key, value);
        } catch {
            /* private mode etc. */
        }
    }

    // --- boot -------------------------------------------------------------------------------------------

    async function boot() {
        // The Plex sign-in popup lands back here when done: the main window takes over.
        if (window.opener && new URLSearchParams(location.search).get("plex") === "done") {
            window.close();
            return;
        }
        buildPlayer();
        setupTheme();
        const [session, instance] = await Promise.all([
            api("/auth/session").catch(() => ({ user: null })),
            api("/api/instance").catch(() => null),
        ]);
        state.me = session.user;
        state.instance = instance || { features: { social: false, sharing: true, streaming: true } };
        buildNav();
        render();
    }

    boot();
})();
