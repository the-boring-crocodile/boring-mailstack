/* boring-mailstack: HTML mail in dark mode (see mailstack_darkmail.php).
 *
 * Setting "auto": sorts each HTML part once, whether Roundcube shows light
 * or dark right now (the CSS applies only in dark mode, so switching between
 * them needs no reload); "invert" only marks background pictures (turned
 * back by the CSS); "off" loads nothing. The sorting:
 *   designed  some element has a background colour other than (near) white,
 *             or a background picture: left as it is (white in dark mode)
 *   dark      otherwise: white backgrounds cleared, dark text colours made
 *             light with their hue kept
 * The verdict is in the part's data-mailstack-darkmail attribute.
 */
(function () {
    var SENTINEL = 'rgb(1, 2, 3)';

    function parse(text) {
        var m = /rgba?\(\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\s*\)/.exec(text || '');
        return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null;
    }

    function luminance(c) {
        var v = c.slice(0, 3).map(function (x) {
            x /= 255;
            return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
    }

    function nearWhite(c) {
        return c[0] >= 240 && c[1] >= 240 && c[2] >= 240;
    }

    // The same hue, lightness mirrored (and at least 65 %): dark blue ->
    // light blue, black -> light grey.
    function lightened(c) {
        var r = c[0] / 255, g = c[1] / 255, b = c[2] / 255,
            max = Math.max(r, g, b), min = Math.min(r, g, b),
            l = (max + min) / 2, d = max - min, h = 0, s = 0;
        if (d) {
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            h = max == r ? (g - b) / d + (g < b ? 6 : 0) : max == g ? (b - r) / d + 2 : (r - g) / d + 4;
            h *= 60;
        }
        l = Math.max(1 - l, 0.65);
        return 'hsl(' + Math.round(h) + ', ' + Math.round(s * 100) + '%, ' + Math.round(l * 100) + '%)';
    }

    function sort(part) {
        var saved = part.getAttribute('style'), designed = false, clear = [], recolor = [];
        // Mark what the mail does not colour itself: it inherits these.
        part.style.setProperty('color', SENTINEL, 'important');
        part.style.setProperty('background-color', 'transparent', 'important');
        var nodes = part.querySelectorAll('*');
        for (var i = 0; i < nodes.length; i++) {
            var cs = window.getComputedStyle(nodes[i]);
            if (cs.backgroundImage && cs.backgroundImage != 'none') {
                designed = true;
                break;
            }
            var bg = parse(cs.backgroundColor);
            if (bg && bg[3] > 0) {
                if (!nearWhite(bg)) {
                    designed = true;
                    break;
                }
                clear.push(nodes[i]);
            }
            var fg = parse(cs.color);
            if (cs.color != SENTINEL && fg && luminance(fg) < 0.18) {
                recolor.push([nodes[i], fg]);
            }
        }
        if (saved === null) part.removeAttribute('style'); else part.setAttribute('style', saved);

        if (designed) {
            part.setAttribute('data-mailstack-darkmail', 'designed');
            return;
        }
        clear.forEach(function (el) { el.classList.add('mailstack-darkmail-clear'); });
        recolor.forEach(function (item) {
            item[0].style.setProperty('--mailstack-darkmail-color', lightened(item[1]));
            item[0].classList.add('mailstack-darkmail-recolor');
        });
        part.classList.add('mailstack-darkmail-dark');
        part.setAttribute('data-mailstack-darkmail', 'dark');
    }

    function invert(part) {
        var nodes = part.querySelectorAll('*');
        for (var i = 0; i < nodes.length; i++) {
            var image = window.getComputedStyle(nodes[i]).backgroundImage;
            if (image && image != 'none' && /url\(/.test(image)) {
                nodes[i].classList.add('mailstack-darkmail-picture');
            }
        }
        part.classList.add('mailstack-darkmail-invert');
        part.setAttribute('data-mailstack-darkmail', 'invert');
    }

    function run() {
        var mode = window.rcmail && rcmail.env.mailstack_darkmail;
        var parts = document.querySelectorAll('.message-htmlpart');
        for (var i = 0; i < parts.length; i++) {
            try {
                (mode == 'invert' ? invert : sort)(parts[i]);
            } catch (e) {
                // Never in the way of reading the mail: left as Roundcube shows it.
                parts[i].setAttribute('data-mailstack-darkmail', 'error');
            }
        }
    }

    if (document.readyState == 'loading') {
        document.addEventListener('DOMContentLoaded', run);
    } else {
        run();
    }
})();
