// static/js/ui_core.js
(() => {
    "use strict";

    const Core = {
        esc(s) {
            return String(s ?? "")
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#039;");
        },

        norm(v) {
            return (v ?? "").toString().trim();
        },

        debounce(fn, ms = 200) {
            let t = null;
            return (...args) => {
                clearTimeout(t);
                t = setTimeout(() => fn(...args), ms);
            };
        },

        setMsgFactory(msgEl, { okColor = "", errColor = "var(--pico-color-red-500)" } = {}) {
            return (text, ok = true) => {
                if (!msgEl) return;
                msgEl.textContent = text || "";
                msgEl.style.color = ok ? okColor : errColor;
            };
        },

        rank(value, order, fallback = 999) {
            const i = order.indexOf((value || "").toLowerCase());
            return i === -1 ? fallback : i;
        },

        parseList(raw, { split = /[, \n\r\t]+/ } = {}) {
            const s = (raw ?? "").toString().trim();
            if (!s) return [];
            return s.split(split).map(x => x.trim()).filter(Boolean);
        },

        parseCsv(raw) {
            return Core.parseList(raw, { split: /,/ }).map(x => x.trim()).filter(Boolean);
        },

        joinCsv(arr) {
            return (Array.isArray(arr) ? arr : []).map(x => (x ?? "").toString().trim()).filter(Boolean).join(", ");
        },

        parseIds(raw) {
            // commas + whitespace/newlines
            return Core.unique(Core.parseList(raw, { split: /[, \n\r\t]+/ }));
        },

        unique(arr) {
            const seen = new Set();
            const out = [];
            for (const x of (arr || [])) {
                const v = (x ?? "").toString().trim();
                if (!v || seen.has(v)) continue;
                seen.add(v);
                out.push(v);
            }
            return out;
        },
        
    };

    window.UiCore = Core;
})();
