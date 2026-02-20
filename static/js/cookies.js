// static/js/cookies.js
function getCookie(name) {
    const m = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&') + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : null;
}

function setCookie(name, value, days = 180) {
    const maxAge = days ? `; max-age=${days * 86400}` : '';
    document.cookie = `${name}=${encodeURIComponent(value)}; path=/; SameSite=Lax${maxAge}`;
}