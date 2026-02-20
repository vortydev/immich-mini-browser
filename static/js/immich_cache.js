/* static/js/immich_cache.js */
(() => {
    "use strict";
    const Core = window.UiCore;

    const els = {
        // Stats
        thumbsEl: document.getElementById("statsThumbs"),
        metaEl: document.getElementById("statsMeta"),
        ttlEl: document.getElementById("statsTtl"),
        msg: document.getElementById("msg"),

        // Thumbs
        btnClearThumbsAll: document.getElementById("btnClearThumbsAll"),
        btnClearThumbsAlbums: document.getElementById("btnClearThumbsAlbums"),
        btnClearThumbsImages: document.getElementById("btnClearThumbsImages"),

        // Meta
        btnRefreshAlbumsMeta: document.getElementById("btnRefreshAlbumsMeta"),
        btnClearMeta: document.getElementById("btnClearMeta"),
    };

    if (!els.thumbsEl || !els.metaEl || !els.ttlEl) return;

    const setMsg = Core.setMsgFactory(els.msg);
    const esc = Core.esc;

    async function jget(url) {
        const r = await fetch(url, { headers: { "Accept": "application/json" } });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j?.error || `HTTP ${r.status}`);
        return j;
    }

    async function jpost(url, body) {
        const r = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json", "Accept": "application/json" },
            body: JSON.stringify(body || {}),
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(j?.error || `HTTP ${r.status}`);
        return j;
    }

    function fmtBytes(n) {
        n = Number(n || 0);
        const units = ["B", "KB", "MB", "GB"];
        let u = 0;
        while (n >= 1024 && u < units.length - 1) { n /= 1024; u++; }
        return `${n.toFixed(u === 0 ? 0 : 1)} ${units[u]}`;
    }

    function renderStats(s) {        
        const thumbs = s.thumbs || {};
        const meta = s.meta || {};
        const ttl = s.ttl || {};

        // ---- Thumbnails column ----
        els.thumbsEl.innerHTML = `
            <div class="label">Total files</div>
            <div class="value">${esc(String(thumbs.total_files || 0))}</div>
            <div class="size">${esc(fmtBytes(thumbs.total_bytes || 0))}</div>

            <div class="label">Album thumbs</div>
            <div class="value">${esc(String(thumbs.albums?.files || 0))}</div>
            <div class="size">${esc(fmtBytes(thumbs.albums?.bytes || 0))}</div>

            <div class="label">Image thumbs</div>
            <div class="value">${esc(String(thumbs.images?.files || 0))}</div>
            <div class="size">${esc(fmtBytes(thumbs.images?.bytes || 0))}</div>
        `;

        // ---- Metadata column ----
        els.metaEl.innerHTML = `
            <div class="label">Total files</div>
            <div class="value">${esc(String(meta.files || 0))}</div>
            <div class="size">${esc(fmtBytes(meta.bytes || 0))}</div>
        `;

        // ---- TTL column ----
        els.ttlEl.innerHTML = `
            <div class="label">Thumbnails</div>
            <div class="value">${esc(String(ttl.thumbs ?? "-"))} s</div>
            <div class="label">Metadata</div>
            <div class="value">${esc(String(ttl.meta ?? "-"))} s</div>
        `;
    }


    async function load() {
        const s = await jget("/api/cache/stats.json");
        renderStats(s);
    }

    async function act(label, fn) {
        try {
            setMsg(label + "…");
            await fn();
            await load();
            setMsg("Done ✓", true);
            setTimeout(() => setMsg(""), 900);
        }
        catch (e) {
            setMsg(e.message || "Failed", false);
        }
    }

    // Buttons
    els.btnClearThumbsAll?.addEventListener("click", () =>
        act("Clearing thumbs (all)", () => jpost("/api/cache/clear-thumbs.json", {}))
    );

    els.btnClearThumbsAlbums?.addEventListener("click", () =>
        act("Clearing thumbs (albums)", () => jpost("/api/cache/clear-thumbs.json", { kind: "albums" }))
    );

    els.btnClearThumbsImages?.addEventListener("click", () =>
        act("Clearing thumbs (images)", () => jpost("/api/cache/clear-thumbs.json", { kind: "images" }))
    );

    els.btnClearMeta?.addEventListener("click", () =>
        act("Clearing meta (all)", () => jpost("/api/cache/clear-meta.json", {}))
    );

    els.btnRefreshAlbumsMeta?.addEventListener("click", () =>
        act("Refreshing albums meta", () => jpost("/api/cache/refresh-albums.json", {}))
    );

    // Add .js-confirm + data-confirm="..." on any button/link you want protected
    document.addEventListener("click", (e) => {
        const el = e.target.closest(".js-confirm");
        if (!el) return;

        const msg = el.getAttribute("data-confirm") || "Are you sure?";
        if (!window.confirm(msg)) {
            e.preventDefault();
            e.stopPropagation();
        }
    }, true);

    // Boot
    (async () => {
        try { await load(); }
        catch (e) { setMsg(e.message || "Failed to load", false); }
    })();
})();
