// static/js/lightbox.js
(() => {
    "use strict";

    // Usage:
    //   const lb = window.Lightbox.bind();
    //   lb.open(assetId);  // fetches /full/:id and shows modal
    //   lb.openUrl(url, fallbackThumbUrl); // optional
    //
    // Expects markup IDs:
    //   #lightbox (dialog), #lightboxImg (img), #lightboxVideo (video),
    //   #lightboxStatus (div/span), #lightboxClose (button)

    function bind(opts = {}) {
        const {
            dlgId = "lightbox",
            imgId = "lightboxImg",
            vidId = "lightboxVideo",
            statusId = "lightboxStatus",
            closeId = "lightboxClose",
            // default endpoints
            fullUrl = (assetId) => `/full/${assetId}`,
            thumbUrl = (assetId) => `/thumb/${assetId}?size=preview`,
            credentials = "same-origin",
            // behavior
            clickOutsideCloses = true,
            escapeCloses = true,
            autoplayVideo = true,
            muteVideo = true,
            onNavigate = null,
        } = opts;

        const dlg = document.getElementById(dlgId);
        const img = document.getElementById(imgId);
        const vid = document.getElementById(vidId);
        const statusEl = document.getElementById(statusId);
        const closeBtn = document.getElementById(closeId);

        if (!dlg) {
            return {
                open: async () => { },
                openFromUrl: async () => { },
                close: () => { },
            };
        }

        let objectUrl = null;

        function clearObjectUrl() {
            if (vid && !vid.hidden) {
                try { vid.pause(); } catch { }
                vid.removeAttribute("src");
                vid.load();
            }
            if (objectUrl) {
                URL.revokeObjectURL(objectUrl);
                objectUrl = null;
            }
        }

        function setStatus(t) {
            if (statusEl) statusEl.textContent = t || "";
        }

        function resetMedia() {
            setStatus("Loading...");
            if (img) { img.hidden = true; img.removeAttribute("src"); }
            if (vid) { vid.hidden = true; vid.removeAttribute("src"); vid.load(); }
        }

        function close() {
            try { dlg.close(); } catch { }
        }

        closeBtn?.addEventListener("click", close);

        dlg.addEventListener("close", clearObjectUrl);

        if (clickOutsideCloses) {
            dlg.addEventListener("click", (e) => {
                const rect = dlg.getBoundingClientRect();
                const inDialog =
                    e.clientX >= rect.left && e.clientX <= rect.right &&
                    e.clientY >= rect.top && e.clientY <= rect.bottom;
                if (!inDialog) close();
            });
        }

        if (escapeCloses) {
            dlg.addEventListener("keydown", (e) => {
                if (e.key === "Escape") close();
            });
        }

        function onKeydown(e) {
            if (e.key === "ArrowLeft") {
                e.preventDefault();
                onNavigate?.(-1);
            } else if (e.key === "ArrowRight") {
                e.preventDefault();
                onNavigate?.(1);
            } else if (e.key === "Escape") {
                e.preventDefault();
                close();
            }
        }

        dlg.addEventListener("close", () => {
            clearObjectUrl();
            document.removeEventListener("keydown", onKeydown);
        });

        dlg.addEventListener("show", () => {
            // (dialog doesn't emit "show" everywhere; we’ll attach on open instead)
        });


        async function open(assetId) {
            return openFromUrl(fullUrl(assetId), { fallback: thumbUrl(assetId) });
        }

        async function openFromUrl(url, { fallback = null } = {}) {
            resetMedia();
            dlg.showModal();

            document.removeEventListener("keydown", onKeydown);
            document.addEventListener("keydown", onKeydown);

            try {
                const res = await fetch(url, { credentials });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);

                const headerType = (res.headers.get("Content-Type") || "").toLowerCase();
                const blob = await res.blob();
                const mime = (blob.type || headerType).toLowerCase();

                clearObjectUrl();
                objectUrl = URL.createObjectURL(blob);

                if (mime.startsWith("video/")) {
                    if (!vid) throw new Error("No <video> element");
                    vid.hidden = false;
                    vid.src = objectUrl;
                    setStatus("");
                    vid.muted = !!muteVideo;

                    if (autoplayVideo) {
                        try { await vid.play(); } catch { }
                    }
                    return;
                }

                if (mime.startsWith("image/")) {
                    if (!img) throw new Error("No <img> element");
                    img.hidden = false;
                    img.src = objectUrl;
                    setStatus("");
                    return;
                }

                throw new Error(`Unsupported type: ${mime || "unknown"}`);
            }
            catch (err) {
                if (fallback && img) {
                    img.hidden = false;
                    img.src = fallback;
                    if (vid) vid.hidden = true;
                    setStatus("(Full media failed — showing preview)");
                    return;
                }
                setStatus(`Error: ${err.message || "failed to load"}`);
                throw err;
            }
        }

        return { open, openFromUrl, close, thumbUrl };
    }

    window.Lightbox = { bind };
})();
