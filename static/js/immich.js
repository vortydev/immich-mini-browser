// static/js/immich.js
(() => {
    "use strict";

    const AUTO_PREWARM = true;

    const albumId = document.querySelector('meta[name="immich-album-id"]')?.content;
    const perPageFromServer = parseInt(document.querySelector('meta[name="immich-per-page"]')?.content || "20", 10);
    if (!albumId) return;

    const perPageSelect = document.getElementById('perPage');
    const grid = document.getElementById('grid');
    const pageInfo = document.getElementById('pageInfo');
    const countEl = document.getElementById('count');

    const firstBtn = document.getElementById('firstBtn');
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const lastBtn = document.getElementById('lastBtn');

    const modal = document.getElementById('progressModal');
    const prog = document.getElementById('prog');
    const progText = document.getElementById('progText');

    if (!perPageSelect || !grid) return;

    // shared lightbox
    const lb = window.Lightbox?.bind?.({
        onNavigate: (dir) => navigateLightbox(dir),
    }) || null;

    let items = [];
    let page = 1;
    let perPage = parseInt(perPageSelect.value || String(perPageFromServer || 20), 10);

    let currentSubset = [];
    let currentIndex = -1;

    function totalPages() {
        return Math.max(1, Math.ceil((items.length || 0) / perPage));
    }

    function subsetForPage(p) {
        const tp = totalPages();
        const pp = Math.max(1, Math.min(p, tp));
        const start = (pp - 1) * perPage;
        return items.slice(start, start + perPage);
    }

    async function openAtIndex(i) {
        if (!lb) return;
        if (!currentSubset.length) return;
        const idx = Math.max(0, Math.min(i, currentSubset.length - 1));
        currentIndex = idx;
        const id = currentSubset[currentIndex]?.id;
        if (id) await lb.open(id);
    }

    function toggleBtn(el, disabled, handler) {
        if (!el) return;

        el.classList.toggle('disabled', disabled);

        // If these are <button>, prefer: el.disabled = disabled;
        // This version remains compatible with <a> or <button>.
        el.replaceWith(el.cloneNode(true));
        const fresh = document.getElementById(el.id);
        if (!fresh) return;

        if (disabled) {
            fresh.setAttribute("tabindex", "-1");
            fresh.onclick = null;
            fresh.setAttribute("disabled", "disabled");
            if (fresh.tagName === "A") fresh.removeAttribute("href");
        }
        else {
            fresh.removeAttribute("tabindex");
            fresh.onclick = handler;
            fresh.removeAttribute("disabled");
        }
    }

    function renderPage(p) {
        const total = items.length;
        const totalPages = Math.max(1, Math.ceil(total / perPage));
        page = Math.max(1, Math.min(p, totalPages));

        const start = (page - 1) * perPage;
        // const subset = items.slice(start, start + perPage);
        currentSubset = items.slice(start, start + perPage);
        const subset = currentSubset;

        const thumbUrl = (id) => (lb?.thumbUrl ? lb.thumbUrl(id) : `/thumb/${id}?size=preview`);

        grid.innerHTML = subset
            .map(
                (it) => `
            <article data-id="${it.id}" class="card thumb-card" title="${String(it.originalFileName || it.id).replace(/"/g, "&quot;")}">
                <button class="thumb-btn" data-id="${it.id}" style="all:unset;cursor:zoom-in;display:block">
                <img class="card-img" src="${thumbUrl(it.id)}"
                    loading="lazy" decoding="async"
                    alt="${String(it.originalFileName || it.id).replace(/"/g, "&quot;")}" />
                </button>
                <div class="card-body">
                <h4 style="margin:.5rem 0 0;">${it.originalFileName || it.id}</h4>
                <p class="muted">${it.fileCreatedAt || ''}</p>
                </div>
            </article>
            `)
            .join('');

        if (pageInfo) pageInfo.textContent = `Page ${page} of ${totalPages}`;
        if (countEl) countEl.textContent = `${total} items`;

        toggleBtn(firstBtn, page === 1, () => renderPage(1));
        toggleBtn(prevBtn, page === 1, () => renderPage(page - 1));
        toggleBtn(nextBtn, page === totalPages, () => renderPage(page + 1));
        toggleBtn(lastBtn, page === totalPages, () => renderPage(totalPages));
    }

    function navigateLightbox(dir) {
        if (!lb) return;

        // If we don't know the current index yet, infer it from the visible dialog
        if (currentIndex < 0) {
            // best-effort: if the last opened asset id is stored, use it
            // otherwise do nothing
            return;
        }

        const next = currentIndex + (dir > 0 ? 1 : -1);

        // within current page
        if (next >= 0 && next < currentSubset.length) {
            openAtIndex(next);
            return;
        }

        // cross page
        const tp = totalPages();
        if (dir > 0 && page < tp) {
            const nextPage = page + 1;
            renderPage(nextPage);
            // open first item on next page
            currentIndex = 0;
            // wait one tick so state is updated
            setTimeout(() => openAtIndex(0), 0);
            return;
        }

        if (dir < 0 && page > 1) {
            const prevPage = page - 1;
            renderPage(prevPage);
            // open last item on prev page
            setTimeout(() => openAtIndex(currentSubset.length - 1), 0);
            return;
        }
    }

    perPageSelect.addEventListener('change', () => {
        perPage = parseInt(perPageSelect.value, 10);
        currentIndex = -1;
        renderPage(1);

        const q = new URLSearchParams(location.search);
        q.set('per_page', perPage);
        history.replaceState(null, '', location.pathname + '?' + q.toString());
    });

    function startPrewarm() {
        if (!prog || !progText) return;

        prog.value = 0;
        prog.max = 100;
        progText.textContent = 'Warming thumbnails...';

        const es = new EventSource(`/api/albums/${albumId}/prewarm?size=preview`);

        es.addEventListener('progress', ev => {
            const p = JSON.parse(ev.data || '{}');
            if (p.total) {
                const pct = Math.floor((p.done / p.total) * 100);
                prog.value = pct;
                progText.textContent = `Caching ${p.done}/${p.total}...`;
            }
        });

        const done = () => {
            es.close();
            modal?.removeAttribute("open");
            currentIndex = -1;
            renderPage(1);
        };

        es.addEventListener("complete", done);
        es.addEventListener("error", done);
    }

    // Grid clicks
    grid.addEventListener('click', (e) => {
        const btn = e.target.closest('.thumb-btn');
        if (!btn) return;
        const id = btn.getAttribute('data-id');
        if (!id || !lb) return;

        currentIndex = currentSubset.findIndex(x => x.id === id);
        lb.open(id);
    });

    // Fetch assets then prewarm
    fetch(`/api/albums/${albumId}/assets.json`)
        .then(r => r.json())
        .then(data => {
            if (data.error) throw new Error(data.error);
            items = data.items || [];
            if (AUTO_PREWARM) startPrewarm();
        })
        .catch(err => {
            if (progText) progText.textContent = 'Error: ' + err.message;
        });

})();
