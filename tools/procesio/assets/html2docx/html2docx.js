// HTML -> DOCX (Word) converter for the PROCESIO Node action.
// Pure JavaScript: the sandbox has no require of fs/zlib/buffer, so base64, UTF-8, CRC-32 and a
// STORED zip are implemented here. Pipeline: parse HTML -> CSS cascade (style blocks, inline
// style, presentational attributes, a browser default sheet) -> layout into Word paragraphs and
// tables -> WordprocessingML -> .docx package -> base64.
var H2D = (function () {
  'use strict';

  // ======================= 1. bytes: base64, UTF-8, CRC-32, zip =======================
  var B64C = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  var B64R = new Int16Array(256);
  (function () {
    var i;
    for (i = 0; i < 256; i++) B64R[i] = -1;
    for (i = 0; i < 64; i++) B64R[B64C.charCodeAt(i)] = i;
    B64R[45] = 62; B64R[95] = 63; // url-safe alphabet
  })();

  function b64decode(s) {
    s = String(s == null ? '' : s);
    var n = s.length, out = new Uint8Array(((n * 3) >> 2) + 4), o = 0, acc = 0, bits = 0;
    for (var i = 0; i < n; i++) {
      var c = s.charCodeAt(i);
      if (c === 61) break;
      var v = c < 256 ? B64R[c] : -1;
      if (v < 0) continue;
      acc = ((acc << 6) | v) & 0xFFFFFF; bits += 6;
      if (bits >= 8) { bits -= 8; out[o++] = (acc >> bits) & 255; }
    }
    return out.subarray(0, o);
  }

  function b64encode(b) {
    var parts = [], n = b.length, CH = 3 * 8192;
    for (var i = 0; i < n; i += CH) {
      var end = Math.min(i + CH, n), arr = [];
      for (var j = i; j < end; j += 3) {
        var a = b[j], has1 = j + 1 < end, has2 = j + 2 < end;
        var t = (a << 16) | ((has1 ? b[j + 1] : 0) << 8) | (has2 ? b[j + 2] : 0);
        arr.push(B64C.charAt((t >> 18) & 63) + B64C.charAt((t >> 12) & 63) +
          (has1 ? B64C.charAt((t >> 6) & 63) : '=') + (has2 ? B64C.charAt(t & 63) : '='));
      }
      parts.push(arr.join(''));
    }
    return parts.join('');
  }

  var CP1252 = [8364, 0, 8218, 402, 8222, 8230, 8224, 8225, 710, 8240, 352, 8249, 338, 0, 381, 0,
    0, 8216, 8217, 8220, 8221, 8226, 8211, 8212, 732, 8482, 353, 8250, 339, 0, 382, 376];

  function fromCP(cp) {
    if (cp > 0xFFFF) { cp -= 0x10000; return String.fromCharCode(0xD800 + (cp >> 10), 0xDC00 + (cp & 1023)); }
    return String.fromCharCode(cp);
  }

  function decodeUtf16(b, start, le) {
    var out = [], chunk = [];
    for (var i = start; i + 1 < b.length; i += 2) {
      chunk.push(le ? (b[i] | (b[i + 1] << 8)) : ((b[i] << 8) | b[i + 1]));
      if (chunk.length >= 8192) { out.push(String.fromCharCode.apply(null, chunk)); chunk = []; }
    }
    out.push(String.fromCharCode.apply(null, chunk));
    return out.join('');
  }

  function decodeText(b) {
    var n = b.length, i = 0;
    if (n >= 2 && b[0] === 0xFF && b[1] === 0xFE) return decodeUtf16(b, 2, true);
    if (n >= 2 && b[0] === 0xFE && b[1] === 0xFF) return decodeUtf16(b, 2, false);
    if (n >= 3 && b[0] === 0xEF && b[1] === 0xBB && b[2] === 0xBF) i = 3;
    else if (n >= 8) {
      var z = 0, m = Math.min(n, 4000);
      for (var k = 1; k < m; k += 2) if (b[k] === 0) z++;
      if (z > m / 4) return decodeUtf16(b, 0, true);
    }
    var out = [], chunk = [];
    while (i < n) {
      var c = b[i++], cp;
      if (c < 0x80) cp = c;
      else if (c >= 0xC2 && c < 0xE0 && i < n && (b[i] & 0xC0) === 0x80) cp = ((c & 31) << 6) | (b[i++] & 63);
      else if (c >= 0xE0 && c < 0xF0 && i + 1 < n && (b[i] & 0xC0) === 0x80 && (b[i + 1] & 0xC0) === 0x80) {
        cp = ((c & 15) << 12) | ((b[i] & 63) << 6) | (b[i + 1] & 63); i += 2;
      } else if (c >= 0xF0 && c < 0xF5 && i + 2 < n && (b[i] & 0xC0) === 0x80 && (b[i + 1] & 0xC0) === 0x80 && (b[i + 2] & 0xC0) === 0x80) {
        cp = ((c & 7) << 18) | ((b[i] & 63) << 12) | ((b[i + 1] & 63) << 6) | (b[i + 2] & 63); i += 3;
      } else cp = (c >= 0x80 && c < 0xA0 && CP1252[c - 0x80]) ? CP1252[c - 0x80] : c; // not UTF-8: Windows-1252
      if (cp > 0xFFFF) { cp -= 0x10000; chunk.push(0xD800 + (cp >> 10), 0xDC00 + (cp & 1023)); } else chunk.push(cp);
      if (chunk.length >= 8192) { out.push(String.fromCharCode.apply(null, chunk)); chunk = []; }
    }
    out.push(String.fromCharCode.apply(null, chunk));
    return out.join('');
  }

  function utf8encode(s) {
    var n = s.length, buf = new Uint8Array(n * 3 + 8), o = 0;
    for (var i = 0; i < n; i++) {
      var c = s.charCodeAt(i);
      if (c < 0x80) buf[o++] = c;
      else if (c < 0x800) { buf[o++] = 0xC0 | (c >> 6); buf[o++] = 0x80 | (c & 63); }
      else if (c >= 0xD800 && c < 0xDC00 && i + 1 < n && (s.charCodeAt(i + 1) & 0xFC00) === 0xDC00) {
        var cp = 0x10000 + ((c - 0xD800) << 10) + (s.charCodeAt(++i) - 0xDC00);
        buf[o++] = 0xF0 | (cp >> 18); buf[o++] = 0x80 | ((cp >> 12) & 63);
        buf[o++] = 0x80 | ((cp >> 6) & 63); buf[o++] = 0x80 | (cp & 63);
      } else {
        if (c >= 0xD800 && c < 0xE000) c = 0xFFFD;
        buf[o++] = 0xE0 | (c >> 12); buf[o++] = 0x80 | ((c >> 6) & 63); buf[o++] = 0x80 | (c & 63);
      }
    }
    return buf.subarray(0, o);
  }

  var CRC_T = (function () {
    var t = new Int32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      t[n] = c;
    }
    return t;
  })();

  function crc32(b) {
    var c = -1;
    for (var i = 0; i < b.length; i++) c = CRC_T[(c ^ b[i]) & 255] ^ (c >>> 8);
    return (c ^ -1) >>> 0;
  }

  // STORED (uncompressed) zip: Word reads it, and it needs no deflate.
  function zipStore(files) {
    var d = new Date();
    var dosTime = (d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1);
    var dosDate = ((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
    var recs = [], total = 22, i;
    for (i = 0; i < files.length; i++) {
      var nm = utf8encode(files[i].name);
      recs.push({ nm: nm, data: files[i].data, crc: crc32(files[i].data), off: 0 });
      total += 30 + nm.length + files[i].data.length + 46 + nm.length;
    }
    var out = new Uint8Array(total), p = 0;
    function u16(v) { out[p++] = v & 255; out[p++] = (v >>> 8) & 255; }
    function u32(v) { out[p++] = v & 255; out[p++] = (v >>> 8) & 255; out[p++] = (v >>> 16) & 255; out[p++] = (v >>> 24) & 255; }
    for (i = 0; i < recs.length; i++) {
      var f = recs[i];
      f.off = p;
      u32(0x04034b50); u16(20); u16(0); u16(0); u16(dosTime); u16(dosDate);
      u32(f.crc); u32(f.data.length); u32(f.data.length); u16(f.nm.length); u16(0);
      out.set(f.nm, p); p += f.nm.length;
      out.set(f.data, p); p += f.data.length;
    }
    var cd = p;
    for (i = 0; i < recs.length; i++) {
      var g = recs[i];
      u32(0x02014b50); u16(20); u16(20); u16(0); u16(0); u16(dosTime); u16(dosDate);
      u32(g.crc); u32(g.data.length); u32(g.data.length); u16(g.nm.length);
      u16(0); u16(0); u16(0); u16(0); u32(0); u32(g.off);
      out.set(g.nm, p); p += g.nm.length;
    }
    var cdSize = p - cd;
    u32(0x06054b50); u16(0); u16(0); u16(recs.length); u16(recs.length); u32(cdSize); u32(cd); u16(0);
    return out;
  }

  // ======================= 2. small helpers =======================
  function toSet(s) { var o = Object.create(null); s.split(/\s+/).forEach(function (k) { if (k) o[k] = true; }); return o; }
  function isSp(c) { return c === 32 || c === 9 || c === 10 || c === 13 || c === 12; }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function twip(pt) { return Math.round(pt * 20); }
  function xesc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return c === '&' ? '&amp;' : c === '<' ? '&lt;' : c === '>' ? '&gt;' : '&quot;'; })
      .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F￾￿]/g, '')
      .replace(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(^|[^\uD800-\uDBFF])[\uDC00-\uDFFF]/g, '$1');
  }

  // ======================= 3. HTML entities + parser =======================
  var ENT = Object.create(null);
  (function () {
    var l1 = ('nbsp iexcl cent pound curren yen brvbar sect uml copy ordf laquo not shy reg macr deg plusmn sup2 sup3 ' +
      'acute micro para middot cedil sup1 ordm raquo frac14 frac12 frac34 iquest Agrave Aacute Acirc Atilde Auml Aring ' +
      'AElig Ccedil Egrave Eacute Ecirc Euml Igrave Iacute Icirc Iuml ETH Ntilde Ograve Oacute Ocirc Otilde Ouml times ' +
      'Oslash Ugrave Uacute Ucirc Uuml Yacute THORN szlig agrave aacute acirc atilde auml aring aelig ccedil egrave eacute ' +
      'ecirc euml igrave iacute icirc iuml eth ntilde ograve oacute ocirc otilde ouml divide oslash ugrave uacute ucirc ' +
      'uuml yacute thorn yuml').split(' ');
    for (var i = 0; i < l1.length; i++) ENT[l1[i]] = 160 + i;
    var more = 'amp:38 lt:60 gt:62 quot:34 apos:39 OElig:338 oelig:339 Scaron:352 scaron:353 Yuml:376 fnof:402 circ:710 ' +
      'tilde:732 ensp:8194 emsp:8195 thinsp:8201 zwnj:8204 zwj:8205 lrm:8206 rlm:8207 ndash:8211 mdash:8212 lsquo:8216 ' +
      'rsquo:8217 sbquo:8218 ldquo:8220 rdquo:8221 bdquo:8222 dagger:8224 Dagger:8225 bull:8226 hellip:8230 permil:8240 ' +
      'prime:8242 Prime:8243 lsaquo:8249 rsaquo:8250 oline:8254 frasl:8260 euro:8364 trade:8482 larr:8592 uarr:8593 ' +
      'rarr:8594 darr:8595 harr:8596 minus:8722 lowast:8727 le:8804 ge:8805 ne:8800 asymp:8776 infin:8734 sum:8721 ' +
      'prod:8719 radic:8730 part:8706 isin:8712 cap:8745 cup:8746 int:8747 there4:8756 sim:8764 equiv:8801 sub:8834 ' +
      'sup:8835 loz:9674 spades:9824 clubs:9827 hearts:9829 diams:9830 check:10003 cross:10007 Abreve:258 abreve:259 ' +
      'Scedil:350 scedil:351 Tcedil:354 tcedil:355 Zcaron:381 zcaron:382 alpha:945 beta:946 gamma:947 delta:948 ' +
      'epsilon:949 lambda:955 mu:956 pi:960 sigma:963 omega:969 Delta:916 Omega:937 nbhy:8209 hyphen:8208 dash:8208 ' +
      'Tab:9 NewLine:10 nobreak:8288 ballot:9744 boxv:9474';
    more.split(' ').forEach(function (kv) { var p = kv.split(':'); ENT[p[0]] = +p[1]; });
  })();

  function decodeEntities(s) {
    if (s.indexOf('&') < 0) return s;
    return s.replace(/&(#[xX][0-9a-fA-F]{1,6}|#[0-9]{1,7}|[a-zA-Z][a-zA-Z0-9]{1,31});?/g, function (m, e) {
      if (e.charAt(0) === '#') {
        var hex = e.charAt(1) === 'x' || e.charAt(1) === 'X';
        var cp = hex ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
        if (!(cp > 0) || cp > 0x10FFFF || (cp >= 0xD800 && cp < 0xE000)) cp = 0xFFFD;
        if (cp >= 0x80 && cp < 0xA0 && CP1252[cp - 0x80]) cp = CP1252[cp - 0x80];
        return fromCP(cp);
      }
      if (ENT[e] !== undefined) return fromCP(ENT[e]);
      return m;
    });
  }

  var VOID = toSet('area base br col embed hr img input keygen link meta param source track wbr');
  var RAWTXT = toSet('script style textarea title xmp noscript iframe noembed noframes template svg math');
  var P_CLOSERS = toSet('address article aside blockquote center details dialog dir div dl fieldset figcaption figure footer ' +
    'form h1 h2 h3 h4 h5 h6 header hgroup hr main menu nav ol p pre section table ul li dd dt');
  var SCOPE = toSet('table td th caption html template applet marquee object button');
  var LIST_SCOPE = toSet('table td th caption html template applet marquee object button ol ul');
  var TABLE_SCOPE = toSet('table html template');
  var ROW_SCOPE = toSet('tr table html template');
  var NO_SCOPE = toSet('html');

  function mkEl(tag, attrs, parent) { return { tag: tag, attrs: attrs || Object.create(null), children: [], parent: parent || null }; }

  function parseStartTag(src, i) {
    var n = src.length, j = i + 1, s0 = j, c;
    while (j < n) { c = src.charCodeAt(j); if (isSp(c) || c === 47 || c === 62) break; j++; }
    var tag = src.slice(s0, j).toLowerCase(), attrs = Object.create(null), selfClose = false;
    while (j < n) {
      c = src.charCodeAt(j);
      if (isSp(c)) { j++; continue; }
      if (c === 62) { j++; break; }
      if (c === 47) { j++; if (src.charCodeAt(j) === 62) { selfClose = true; j++; break; } continue; }
      var a0 = j;
      while (j < n) {
        c = src.charCodeAt(j);
        if (isSp(c) || c === 61 || c === 62 || (c === 47 && src.charCodeAt(j + 1) === 62)) break;
        j++;
      }
      if (j === a0) { j++; continue; }
      var an = src.slice(a0, j).toLowerCase(), av = '';
      while (j < n && isSp(src.charCodeAt(j))) j++;
      if (src.charCodeAt(j) === 61) {
        j++;
        while (j < n && isSp(src.charCodeAt(j))) j++;
        var q = src.charCodeAt(j);
        if (q === 34 || q === 39) {
          var qe = src.indexOf(q === 34 ? '"' : "'", j + 1);
          if (qe < 0) qe = n;
          av = src.slice(j + 1, qe); j = qe + 1;
        } else {
          var v0 = j;
          while (j < n && !isSp(src.charCodeAt(j)) && src.charCodeAt(j) !== 62) j++;
          av = src.slice(v0, j);
        }
      }
      if (!(an in attrs)) attrs[an] = decodeEntities(av);
    }
    return { tag: tag, attrs: attrs, selfClose: selfClose, end: j };
  }

  function parseHTML(src) {
    var root = mkEl('#root'), stack = [root], i = 0, n = src.length, lower = null;
    function top() { return stack[stack.length - 1]; }
    function addText(t) {
      if (!t) return;
      var p = top(), last = p.children[p.children.length - 1];
      if (last && last.tag === '#text') last.text += t; else p.children.push({ tag: '#text', text: t, parent: p });
    }
    function findOpen(tag, scope) {
      for (var k = stack.length - 1; k > 0; k--) {
        var t = stack[k].tag;
        if (t === tag) return k;
        if (scope[t]) return -1;
      }
      return -1;
    }
    function closeTo(k) { if (k > 0) stack.length = k; }
    function start(tag, attrs, selfClose) {
      if (P_CLOSERS[tag]) closeTo(findOpen('p', SCOPE));
      if (tag === 'li') closeTo(findOpen('li', LIST_SCOPE));
      else if (tag === 'dt' || tag === 'dd') { closeTo(findOpen('dt', SCOPE)); closeTo(findOpen('dd', SCOPE)); }
      else if (tag === 'tr') closeTo(findOpen('tr', TABLE_SCOPE));
      else if (tag === 'td' || tag === 'th') { closeTo(findOpen('td', ROW_SCOPE)); closeTo(findOpen('th', ROW_SCOPE)); }
      else if (tag === 'thead' || tag === 'tbody' || tag === 'tfoot') {
        closeTo(findOpen('thead', TABLE_SCOPE)); closeTo(findOpen('tbody', TABLE_SCOPE)); closeTo(findOpen('tfoot', TABLE_SCOPE));
      } else if (tag === 'option') closeTo(findOpen('option', SCOPE));
      else if (tag === 'a') closeTo(findOpen('a', SCOPE));
      else if (/^h[1-6]$/.test(tag) && /^h[1-6]$/.test(top().tag)) stack.pop();
      var p = top(), e = mkEl(tag, attrs, p);
      p.children.push(e);
      if (!VOID[tag] && !selfClose && stack.length < 400) stack.push(e);
      return e;
    }
    function end(tag) {
      if (tag === 'br') { start('br', Object.create(null), true); return; }
      if (VOID[tag]) return;
      if (tag === 'p' && findOpen('p', SCOPE) < 0) { start('p', Object.create(null), true); return; }
      var scope = tag === 'table' ? NO_SCOPE
        : /^(td|th|tr|thead|tbody|tfoot|caption|colgroup)$/.test(tag) ? TABLE_SCOPE : SCOPE;
      closeTo(findOpen(tag, scope));
    }
    while (i < n) {
      var lt = src.indexOf('<', i);
      if (lt < 0) { addText(decodeEntities(src.slice(i))); break; }
      if (lt > i) addText(decodeEntities(src.slice(i, lt)));
      i = lt;
      var c1 = src.charCodeAt(i + 1);
      if (c1 === 33) {
        if (src.substr(i, 4) === '<!--') { var ce = src.indexOf('-->', i + 4); i = ce < 0 ? n : ce + 3; }
        else if (src.substr(i, 9).toUpperCase() === '<![CDATA[') {
          var cd = src.indexOf(']]>', i + 9); addText(src.slice(i + 9, cd < 0 ? n : cd)); i = cd < 0 ? n : cd + 3;
        } else { var ge = src.indexOf('>', i); i = ge < 0 ? n : ge + 1; }
        continue;
      }
      if (c1 === 63) { var qe = src.indexOf('>', i); i = qe < 0 ? n : qe + 1; continue; }
      if (c1 === 47) {
        var j = i + 2, s0 = j;
        while (j < n) { var cc = src.charCodeAt(j); if (isSp(cc) || cc === 62 || cc === 47) break; j++; }
        var ee = src.indexOf('>', j);
        if (j > s0) end(src.slice(s0, j).toLowerCase());
        i = ee < 0 ? n : ee + 1;
        continue;
      }
      if ((c1 >= 65 && c1 <= 90) || (c1 >= 97 && c1 <= 122)) {
        var st = parseStartTag(src, i);
        i = st.end;
        var node = start(st.tag, st.attrs, st.selfClose);
        if (RAWTXT[st.tag] && !st.selfClose) {
          if (!lower) lower = src.toLowerCase();
          var close = lower.indexOf('</' + st.tag, i);
          var raw = src.slice(i, close < 0 ? n : close);
          if (raw) node.children.push({ tag: '#text', text: (st.tag === 'textarea' || st.tag === 'title') ? decodeEntities(raw) : raw, parent: node });
          var k = stack.lastIndexOf(node);
          if (k > 0) stack.length = k;
          if (close < 0) i = n; else { var gt = src.indexOf('>', close); i = gt < 0 ? n : gt + 1; }
        }
        continue;
      }
      addText('<'); i++;
    }
    return root;
  }

  // a fragment without <body> gets one, the way a browser builds it
  function ensureBody(root) {
    var html = null, found = false;
    (function walk(n) {
      if (found) return;
      if (n.tag === 'body') { found = true; return; }
      if (n.tag === 'html' && !html) html = n;
      for (var i = 0; i < n.children.length; i++) if (n.children[i].tag !== '#text') walk(n.children[i]);
    })(root);
    if (found) return;
    var host = html || root, body = mkEl('body', Object.create(null), host), keep = [];
    host.children.forEach(function (c) {
      if (c.tag === 'head' || (c.tag === 'html' && c !== host)) keep.push(c);
      else { c.parent = body; body.children.push(c); }
    });
    keep.push(body);
    host.children = keep;
  }

  function annotate(node) {
    var els = [];
    for (var k = 0; k < node.children.length; k++) {
      var ch = node.children[k];
      ch.parent = node;
      if (ch.tag !== '#text') { ch.eidx = els.length; els.push(ch); annotate(ch); }
    }
    node.els = els;
  }

  // ======================= 4. CSS: values =======================
  var NAMED = Object.create(null);
  ('aliceblue:f0f8ff antiquewhite:faebd7 aqua:00ffff aquamarine:7fffd4 azure:f0ffff beige:f5f5dc bisque:ffe4c4 black:000000 ' +
    'blanchedalmond:ffebcd blue:0000ff blueviolet:8a2be2 brown:a52a2a burlywood:deb887 cadetblue:5f9ea0 chartreuse:7fff00 ' +
    'chocolate:d2691e coral:ff7f50 cornflowerblue:6495ed cornsilk:fff8dc crimson:dc143c cyan:00ffff darkblue:00008b ' +
    'darkcyan:008b8b darkgoldenrod:b8860b darkgray:a9a9a9 darkgreen:006400 darkgrey:a9a9a9 darkkhaki:bdb76b ' +
    'darkmagenta:8b008b darkolivegreen:556b2f darkorange:ff8c00 darkorchid:9932cc darkred:8b0000 darksalmon:e9967a ' +
    'darkseagreen:8fbc8f darkslateblue:483d8b darkslategray:2f4f4f darkslategrey:2f4f4f darkturquoise:00ced1 ' +
    'darkviolet:9400d3 deeppink:ff1493 deepskyblue:00bfff dimgray:696969 dimgrey:696969 dodgerblue:1e90ff ' +
    'firebrick:b22222 floralwhite:fffaf0 forestgreen:228b22 fuchsia:ff00ff gainsboro:dcdcdc ghostwhite:f8f8ff gold:ffd700 ' +
    'goldenrod:daa520 gray:808080 green:008000 greenyellow:adff2f grey:808080 honeydew:f0fff0 hotpink:ff69b4 ' +
    'indianred:cd5c5c indigo:4b0082 ivory:fffff0 khaki:f0e68c lavender:e6e6fa lavenderblush:fff0f5 lawngreen:7cfc00 ' +
    'lemonchiffon:fffacd lightblue:add8e6 lightcoral:f08080 lightcyan:e0ffff lightgoldenrodyellow:fafad2 lightgray:d3d3d3 ' +
    'lightgreen:90ee90 lightgrey:d3d3d3 lightpink:ffb6c1 lightsalmon:ffa07a lightseagreen:20b2aa lightskyblue:87cefa ' +
    'lightslategray:778899 lightslategrey:778899 lightsteelblue:b0c4de lightyellow:ffffe0 lime:00ff00 limegreen:32cd32 ' +
    'linen:faf0e6 magenta:ff00ff maroon:800000 mediumaquamarine:66cdaa mediumblue:0000cd mediumorchid:ba55d3 ' +
    'mediumpurple:9370db mediumseagreen:3cb371 mediumslateblue:7b68ee mediumspringgreen:00fa9a mediumturquoise:48d1cc ' +
    'mediumvioletred:c71585 midnightblue:191970 mintcream:f5fffa mistyrose:ffe4e1 moccasin:ffe4b5 navajowhite:ffdead ' +
    'navy:000080 oldlace:fdf5e6 olive:808000 olivedrab:6b8e23 orange:ffa500 orangered:ff4500 orchid:da70d6 ' +
    'palegoldenrod:eee8aa palegreen:98fb98 paleturquoise:afeeee palevioletred:db7093 papayawhip:ffefd5 peachpuff:ffdab9 ' +
    'peru:cd853f pink:ffc0cb plum:dda0dd powderblue:b0e0e6 purple:800080 rebeccapurple:663399 red:ff0000 ' +
    'rosybrown:bc8f8f royalblue:4169e1 saddlebrown:8b4513 salmon:fa8072 sandybrown:f4a460 seagreen:2e8b57 ' +
    'seashell:fff5ee sienna:a0522d silver:c0c0c0 skyblue:87ceeb slateblue:6a5acd slategray:708090 slategrey:708090 ' +
    'snow:fffafa springgreen:00ff7f steelblue:4682b4 tan:d2b48c teal:008080 thistle:d8bfd8 tomato:ff6347 ' +
    'turquoise:40e0d0 violet:ee82ee wheat:f5deb3 white:ffffff whitesmoke:f5f5f5 yellow:ffff00 yellowgreen:9acd32 ' +
    'windowtext:000000 buttontext:000000 canvastext:000000 canvas:ffffff window:ffffff')
    .split(' ').forEach(function (kv) { var p = kv.split(':'); NAMED[p[0]] = p[1].toUpperCase(); });

  function hex2(n) { n = clamp(Math.round(n), 0, 255); return (n < 16 ? '0' : '') + n.toString(16).toUpperCase(); }
  function blend(r, g, b, a) { // alpha over white
    if (a >= 1) return hex2(r) + hex2(g) + hex2(b);
    if (a <= 0.02) return null;
    return hex2(r * a + 255 * (1 - a)) + hex2(g * a + 255 * (1 - a)) + hex2(b * a + 255 * (1 - a));
  }
  function hsl2rgb(h, s, l) {
    h = ((h % 360) + 360) % 360 / 360; s = clamp(s, 0, 1); l = clamp(l, 0, 1);
    function f(t) { t = (t + 1) % 1; return t < 1 / 6 ? p + (q - p) * 6 * t : t < 0.5 ? q : t < 2 / 3 ? p + (q - p) * (2 / 3 - t) * 6 : p; }
    var q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
    return [f(h + 1 / 3) * 255, f(h) * 255, f(h - 1 / 3) * 255];
  }
  // returns 'RRGGBB', null (transparent) or undefined (not a colour)
  function parseColor(v, current) {
    v = String(v).trim().toLowerCase();
    if (!v) return undefined;
    if (v === 'transparent' || v === 'none') return null;
    if (v === 'currentcolor') return current;
    if (v.charAt(0) === '#') {
      var h = v.slice(1);
      if (!/^[0-9a-f]+$/.test(h)) return undefined;
      if (h.length === 3 || h.length === 4) {
        var a3 = h.length === 4 ? parseInt(h.charAt(3) + h.charAt(3), 16) / 255 : 1;
        return blend(parseInt(h.charAt(0) + h.charAt(0), 16), parseInt(h.charAt(1) + h.charAt(1), 16), parseInt(h.charAt(2) + h.charAt(2), 16), a3);
      }
      if (h.length === 6 || h.length === 8) {
        var a6 = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1;
        return blend(parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), a6);
      }
      return undefined;
    }
    var m = /^(rgba?|hsla?)\(([^)]*)\)$/.exec(v);
    if (m) {
      var parts = m[2].replace(/\//g, ' ').split(/[\s,]+/).filter(Boolean);
      if (parts.length < 3) return undefined;
      var al = parts.length > 3 ? (parts[3].slice(-1) === '%' ? parseFloat(parts[3]) / 100 : parseFloat(parts[3])) : 1;
      if (m[1].charAt(0) === 'r') {
        var ch = parts.slice(0, 3).map(function (x) { return x.slice(-1) === '%' ? parseFloat(x) * 2.55 : parseFloat(x); });
        return blend(ch[0], ch[1], ch[2], al);
      }
      var rgb = hsl2rgb(parseFloat(parts[0]), parseFloat(parts[1]) / 100, parseFloat(parts[2]) / 100);
      return blend(rgb[0], rgb[1], rgb[2], al);
    }
    if (NAMED[v]) return NAMED[v];
    return undefined;
  }

  var PT = { pt: 1, px: 0.75, cm: 28.3464567, mm: 2.83464567, 'in': 72, pc: 12, q: 0.708661 };
  // length -> {pt} | {pct} | {auto:true} | null
  function parseLen(v, fs, rootFs) {
    if (v == null) return null;
    v = String(v).trim().toLowerCase();
    if (!v) return null;
    if (v === 'auto') return { auto: true };
    var m = /^(-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?)\s*([a-z%]*)$/.exec(v);
    if (!m) return null;
    var x = parseFloat(m[1]), u = m[2];
    if (u === '' || u === 'px') return { pt: x * 0.75 };
    if (PT[u]) return { pt: x * PT[u] };
    if (u === 'em') return { pt: x * fs };
    if (u === 'rem') return { pt: x * rootFs };
    if (u === 'ex' || u === 'ch') return { pt: x * fs * 0.5 };
    if (u === '%') return { pct: x };
    if (u === 'vw') return { pct: x };
    return null;
  }
  function res(L, ref) { if (!L || L.auto) return null; return L.pct != null ? L.pct * (ref || 0) / 100 : L.pt; }
  function res0(L, ref) { var r = res(L, ref); return r == null ? 0 : r; }

  var FS_KEY = { 'xx-small': 6.75, 'x-small': 7.5, small: 9.75, medium: 12, large: 13.5, 'x-large': 18, 'xx-large': 24, 'xxx-large': 36 };
  var BW_KEY = { thin: 0.75, medium: 2.25, thick: 3.75 };
  var GENERIC = { serif: 'Times New Roman', 'sans-serif': 'Arial', monospace: 'Courier New', cursive: 'Comic Sans MS',
    fantasy: 'Impact', 'system-ui': 'Arial', '-apple-system': 'Arial', blinkmacsystemfont: 'Arial', 'ui-sans-serif': 'Arial',
    'ui-serif': 'Times New Roman', 'ui-monospace': 'Courier New', 'liberation sans': 'Arial', arimo: 'Arial', helvetica: 'Arial',
    'helvetica neue': 'Arial', 'liberation serif': 'Times New Roman', tinos: 'Times New Roman', 'liberation mono': 'Courier New',
    cousine: 'Courier New', carlito: 'Calibri', caladea: 'Cambria', times: 'Times New Roman' };
  var LINE_FACTOR = { arial: 1.149, 'times new roman': 1.149, calibri: 1.2207, cambria: 1.1724, 'courier new': 1.1328,
    verdana: 1.2153, tahoma: 1.2075, georgia: 1.1362, 'segoe ui': 1.33, 'trebuchet ms': 1.1621, garamond: 1.12,
    'book antiqua': 1.17, 'century gothic': 1.2, 'comic sans ms': 1.394, impact: 1.22, 'palatino linotype': 1.32,
    'dejavu sans': 1.164, 'open sans': 1.362, roboto: 1.172, lato: 1.2, 'arial narrow': 1.149 };

  function splitTop(s, sep) {
    var out = [], depth = 0, q = 0, last = 0;
    for (var i = 0; i < s.length; i++) {
      var c = s.charAt(i);
      if (q) { if (c === '\\') i++; else if (c === q) q = 0; continue; }
      if (c === '"' || c === "'") q = c;
      else if (c === '(' || c === '[') depth++;
      else if (c === ')' || c === ']') depth--;
      else if (c === sep && depth <= 0) { out.push(s.slice(last, i)); last = i + 1; }
    }
    out.push(s.slice(last));
    return out;
  }
  function tokens(v) { return splitTop(String(v).trim().replace(/\s+/g, ' '), ' ').filter(Boolean); }

  function firstFamily(v) {
    var fams = splitTop(v, ',');
    for (var i = 0; i < fams.length; i++) {
      var f = fams[i].trim().replace(/^["']|["']$/g, '').trim();
      if (!f || /^(inherit|initial|unset)$/i.test(f)) continue;
      var g = GENERIC[f.toLowerCase()];
      return g || f;
    }
    return null;
  }

  // ======================= 5. CSS: parser =======================
  var BORDER_STYLES = toSet('none hidden dotted dashed solid double groove ridge inset outset');
  var SIDES = ['top', 'right', 'bottom', 'left'];

  function box4(v) {
    var t = tokens(v);
    if (!t.length) return null;
    return [t[0], t[1] || t[0], t[2] || t[0], t[3] || t[1] || t[0]];
  }

  function expandDecl(name, val, imp, out) {
    function put(p, v) { out.push({ p: p, v: v, imp: imp }); }
    var lv = val.toLowerCase(), t, i, k;
    if (/^(inherit|initial|unset)$/.test(lv) && /^(margin|padding|border|border-(top|right|bottom|left)|background|font|list-style|text-decoration)$/.test(name)) {
      if (name === 'margin' || name === 'padding') { SIDES.forEach(function (s) { put(name + '-' + s, lv); }); return; }
    }
    switch (name) {
      case 'margin': case 'padding':
        t = box4(val); if (t) for (i = 0; i < 4; i++) put(name + '-' + SIDES[i], t[i]);
        return;
      case 'border': case 'border-top': case 'border-right': case 'border-bottom': case 'border-left':
        var w = null, s = null, c = null;
        tokens(val).forEach(function (tk) {
          var l = tk.toLowerCase();
          if (BORDER_STYLES[l]) s = l;
          else if (BW_KEY[l] !== undefined || /^-?[\d.]/.test(l)) w = l;
          else c = tk;
        });
        var sides = name === 'border' ? SIDES : [name.slice(7)];
        sides.forEach(function (sd) {
          put('border-' + sd + '-style', s || 'none');
          put('border-' + sd + '-width', w || 'medium');
          put('border-' + sd + '-color', c || 'currentcolor');
        });
        return;
      case 'border-width': case 'border-style': case 'border-color':
        t = box4(val); k = name.slice(7);
        if (t) for (i = 0; i < 4; i++) put('border-' + SIDES[i] + '-' + k, t[i]);
        return;
      case 'background':
        var col = null;
        tokens(val).forEach(function (tk) { if (col == null && parseColor(tk, null) !== undefined) col = tk; });
        put('background-color', col || 'transparent');
        return;
      case 'font':
        var tk = tokens(val), idx = -1;
        for (i = 0; i < tk.length; i++) {
          var x = tk[i].toLowerCase();
          if (FS_KEY[x] !== undefined || x === 'smaller' || x === 'larger' || /^[\d.]+(px|pt|em|rem|%|cm|mm|in|pc|ex|ch)(\/.*)?$/.test(x)) { idx = i; break; }
        }
        if (idx < 0) return;
        put('font-style', 'normal'); put('font-weight', 'normal'); put('font-variant', 'normal'); put('line-height', 'normal');
        for (i = 0; i < idx; i++) {
          var y = tk[i].toLowerCase();
          if (y === 'italic' || y === 'oblique') put('font-style', y);
          else if (y === 'bold' || y === 'bolder' || y === 'lighter' || /^\d{3}$/.test(y)) put('font-weight', y);
          else if (y === 'small-caps') put('font-variant', y);
        }
        var sz = tk[idx], sl = sz.indexOf('/'), rest = tk.slice(idx + 1);
        if (sl >= 0) { var lh = sz.slice(sl + 1); sz = sz.slice(0, sl); if (lh) put('line-height', lh); else if (rest.length) put('line-height', rest.shift()); }
        else if (rest.length && rest[0].charAt(0) === '/') { var lh2 = rest.shift().slice(1) || rest.shift(); if (lh2) put('line-height', lh2); }
        put('font-size', sz);
        if (rest.length) put('font-family', rest.join(' '));
        return;
      case 'list-style':
        tokens(val).forEach(function (tk2) {
          var l = tk2.toLowerCase();
          if (l === 'inside' || l === 'outside') put('list-style-position', l);
          else if (!/^url\(/.test(l)) put('list-style-type', l);
        });
        return;
      case 'text-decoration':
        var line = [], st = null, cl = null;
        tokens(val).forEach(function (tk3) {
          var l = tk3.toLowerCase();
          if (/^(underline|line-through|overline|none|blink)$/.test(l)) line.push(l);
          else if (/^(solid|double|dotted|dashed|wavy)$/.test(l)) st = l;
          else cl = tk3;
        });
        put('text-decoration-line', line.length ? line.join(' ') : 'none');
        if (st) put('text-decoration-style', st);
        if (cl) put('text-decoration-color', cl);
        return;
      case 'break-before': case 'break-after':
        put('page-break-' + name.slice(6), /^(page|always|left|right|recto|verso)$/.test(lv) ? 'always' : lv === 'avoid' || lv === 'avoid-page' ? 'avoid' : 'auto');
        return;
      case 'break-inside':
        put('page-break-inside', /^avoid/.test(lv) ? 'avoid' : 'auto');
        return;
      case 'background-image': case 'background-repeat': case 'background-position': case 'background-size':
        return;
      case 'margin-inline-start': put('margin-left', val); return;
      case 'margin-inline-end': put('margin-right', val); return;
      case 'margin-block-start': put('margin-top', val); return;
      case 'margin-block-end': put('margin-bottom', val); return;
      case 'padding-inline-start': put('padding-left', val); return;
      case 'padding-inline-end': put('padding-right', val); return;
      case 'padding-block-start': put('padding-top', val); return;
      case 'padding-block-end': put('padding-bottom', val); return;
      case 'word-wrap': case 'overflow-wrap': case 'word-break': case 'hyphens': return;
    }
    put(name, val);
  }

  function parseDecls(body) {
    var out = [], parts = splitTop(body, ';');
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i], k = p.indexOf(':');
      if (k < 0) continue;
      var name = p.slice(0, k).trim().toLowerCase(), val = p.slice(k + 1).trim(), imp = false;
      var m = /!\s*important\s*$/i.exec(val);
      if (m) { imp = true; val = val.slice(0, m.index).trim(); }
      if (!name || !val || name.charAt(0) === '-' && name.indexOf('-webkit-') !== 0 && name.indexOf('-moz-') !== 0 && name.indexOf('--') === 0) continue;
      expandDecl(name, val, imp, out);
    }
    return out;
  }

  function matchBrace(css, open) {
    var depth = 0, q = 0;
    for (var i = open; i < css.length; i++) {
      var c = css.charAt(i);
      if (q) { if (c === '\\') i++; else if (c === q) q = 0; continue; }
      if (c === '"' || c === "'") q = c;
      else if (c === '{') depth++;
      else if (c === '}') { depth--; if (!depth) return i; }
    }
    return css.length;
  }
  function findTop(css, from, chars) {
    var q = 0, depth = 0;
    for (var i = from; i < css.length; i++) {
      var c = css.charAt(i);
      if (q) { if (c === '\\') i++; else if (c === q) q = 0; continue; }
      if (c === '"' || c === "'") q = c;
      else if (c === '(') depth++;
      else if (c === ')') depth--;
      else if (!depth && chars.indexOf(c) >= 0) return i;
    }
    return -1;
  }

  function mediaMatches(prelude, env) {
    var list = splitTop(prelude.toLowerCase(), ',');
    for (var i = 0; i < list.length; i++) {
      var q = list[i].trim(), neg = false, ok = true;
      if (!q) continue;
      if (/^not\s/.test(q)) { neg = true; q = q.slice(4); } else if (/^only\s/.test(q)) q = q.slice(5);
      q.split(/\s+and\s+/).forEach(function (part) {
        part = part.trim();
        if (!part) return;
        if (part.charAt(0) === '(') {
          var f = /^\(\s*([\w-]+)\s*(?::\s*([^)]+))?\)$/.exec(part);
          if (!f) { ok = false; return; }
          var name = f[1], val = f[2] ? f[2].trim() : null, L = val ? parseLen(val, 12, 12) : null, px = L && L.pt != null ? L.pt / 0.75 : null;
          if (name === 'min-width') ok = ok && px != null && env.widthPx >= px;
          else if (name === 'max-width') ok = ok && px != null && env.widthPx <= px;
          else if (name === 'min-height') ok = ok && px != null && env.heightPx >= px;
          else if (name === 'max-height') ok = ok && px != null && env.heightPx <= px;
          else if (name === 'orientation') ok = ok && val === (env.widthPx > env.heightPx ? 'landscape' : 'portrait');
          else if (name === 'color') ok = ok && true;
          else ok = false;
        } else if (part !== 'all' && part !== env.type) ok = false;
      });
      if (neg ? !ok : ok) return true;
    }
    return false;
  }

  var PSEUDO_EL = toSet('before after first-line first-letter marker selection placeholder backdrop');

  function readIdent(s, i) {
    var j = i;
    while (j < s.length) {
      var c = s.charAt(j);
      if (c === '\\') { j += 2; continue; }
      if (/[\w -￿-]/.test(c)) j++; else break;
    }
    return { v: s.slice(i, j).replace(/\\(.)/g, '$1'), i: j };
  }
  function matchParen(s, i) {
    var d = 0;
    for (var j = i; j < s.length; j++) { var c = s.charAt(j); if (c === '(') d++; else if (c === ')') { d--; if (!d) return j; } }
    return s.length;
  }
  function parseAttrSel(body) {
    var m = /^\s*([\w:-]+)\s*(?:([~|^$*]?=)\s*("[^"]*"|'[^']*'|[^\s\]]+)\s*(i)?)?\s*$/.exec(body);
    if (!m) return null;
    var v = m[3] || '';
    if (/^["']/.test(v)) v = v.slice(1, -1);
    return { n: m[1].toLowerCase(), op: m[2] || '', v: v, ci: !!m[4] };
  }
  function parseNth(arg) {
    arg = String(arg || '').replace(/\s+/g, '').toLowerCase();
    if (arg === 'odd') return [2, 1];
    if (arg === 'even') return [2, 0];
    var m = /^([+-]?\d*)n([+-]\d+)?$/.exec(arg);
    if (m) { var a = m[1] === '' || m[1] === '+' ? 1 : m[1] === '-' ? -1 : parseInt(m[1], 10); return [a, m[2] ? parseInt(m[2], 10) : 0]; }
    if (/^[+-]?\d+$/.test(arg)) return [0, parseInt(arg, 10)];
    return null;
  }
  function parseCompoundOnly(s) { var r = parseComplex(s); return r && r.parts.length === 1 ? r.parts[0].c : null; }
  function parseComplex(s) {
    s = s.trim();
    if (!s) return null;
    var parts = [], i = 0, n = s.length, cur = { tag: null, id: null, cls: [], attrs: [], ps: [] }, has = false, comb = null, a = 0, b = 0, c = 0;
    function push() { parts.push({ c: cur, comb: comb }); cur = { tag: null, id: null, cls: [], attrs: [], ps: [] }; has = false; }
    while (i < n) {
      var ch = s.charAt(i), r;
      if (/[\s>+~]/.test(ch)) {
        var cb = ' ';
        while (i < n && /[\s>+~]/.test(s.charAt(i))) { if (!/\s/.test(s.charAt(i))) cb = s.charAt(i); i++; }
        if (has) { push(); comb = cb; }
        continue;
      }
      if (ch === '*') { i++; has = true; continue; }
      if (ch === '#') { r = readIdent(s, i + 1); cur.id = r.v; i = r.i; a++; has = true; continue; }
      if (ch === '.') { r = readIdent(s, i + 1); if (!r.v) return null; cur.cls.push(r.v); i = r.i; b++; has = true; continue; }
      if (ch === '[') {
        var e = s.indexOf(']', i);
        if (e < 0) return null;
        var at = parseAttrSel(s.slice(i + 1, e));
        if (!at) return null;
        cur.attrs.push(at); i = e + 1; b++; has = true; continue;
      }
      if (ch === ':') {
        var dbl = s.charAt(i + 1) === ':';
        i += dbl ? 2 : 1;
        r = readIdent(s, i);
        var name = r.v.toLowerCase(), arg = null;
        i = r.i;
        if (s.charAt(i) === '(') { var pe = matchParen(s, i); arg = s.slice(i + 1, pe); i = pe + 1; }
        if (dbl || PSEUDO_EL[name]) return null;
        var ps = { n: name, a: arg };
        if (name === 'not' && arg) { ps.sub = splitTop(arg, ',').map(parseCompoundOnly); if (ps.sub.some(function (x) { return !x; })) return null; }
        if (/^nth-/.test(name)) { ps.nth = parseNth(arg); if (!ps.nth) return null; }
        cur.ps.push(ps); b++; has = true; continue;
      }
      if (/[\w -￿-]/.test(ch) || ch === '\\') { r = readIdent(s, i); cur.tag = r.v.toLowerCase(); i = r.i; c++; has = true; continue; }
      return null;
    }
    if (has) push(); else return null;
    return { parts: parts, spec: a * 10000 + b * 100 + c };
  }

  function parseCSS(css, sheet, env, origin, pageOnly) {
    css = css.replace(/\/\*[\s\S]*?\*\//g, '').replace(/<!--|-->/g, ' ');
    var i = 0, n = css.length;
    while (i < n) {
      while (i < n && /\s/.test(css.charAt(i))) i++;
      if (i >= n) break;
      if (css.charAt(i) === '@') {
        var km = /^@([\w-]+)/.exec(css.slice(i, i + 40)), kw = km ? km[1].toLowerCase() : '';
        var stop = findTop(css, i, '{;');
        if (stop < 0) break;
        if (css.charAt(stop) === ';') { i = stop + 1; continue; }
        var close = matchBrace(css, stop), prelude = css.slice(i + 1 + kw.length, stop).trim(), inner = css.slice(stop + 1, close);
        if (kw === 'media') parseCSS(inner, sheet, env, origin, pageOnly || !mediaMatches(prelude, env));
        else if (kw === 'supports') parseCSS(inner, sheet, env, origin, pageOnly);
        else if (kw === 'page' && !/:(left|right|blank)/i.test(prelude)) sheet.page.push(parseDecls(inner.replace(/@[\w-]+\s*\{[^}]*\}/g, '')));
        i = close + 1;
        continue;
      }
      var ob = findTop(css, i, '{');
      if (ob < 0) break;
      var cb = matchBrace(css, ob), selText = css.slice(i, ob).trim(), body = css.slice(ob + 1, cb);
      i = cb + 1;
      if (pageOnly || !selText) continue;
      var decls = parseDecls(body);
      if (!decls.length) continue;
      var sels = splitTop(selText, ',');
      for (var k = 0; k < sels.length; k++) {
        var sel = parseComplex(sels[k]);
        if (sel) sheet[origin].push({ parts: sel.parts, spec: sel.spec, decls: decls, order: sheet.seq++ });
      }
    }
  }

  // ======================= 6. selector matching =======================
  function clsSet(e) {
    if (!e.cset) { e.cset = Object.create(null); String(e.attrs['class'] || '').split(/\s+/).forEach(function (c) { if (c) e.cset[c] = true; }); }
    return e.cset;
  }
  function nthOk(nth, pos) { // pos is 1-based
    var a = nth[0], b = nth[1];
    if (a === 0) return pos === b;
    var k = (pos - b) / a;
    return k >= 0 && Math.floor(k) === k;
  }
  function sameTypeIndex(e, fromEnd) {
    var sib = e.parent ? e.parent.els : [e], pos = 0;
    if (!fromEnd) { for (var i = 0; i <= e.eidx; i++) if (sib[i].tag === e.tag) pos++; }
    else { for (var j = sib.length - 1; j >= e.eidx; j--) if (sib[j].tag === e.tag) pos++; }
    return pos;
  }
  function matchCompound(e, c) {
    if (c.tag && c.tag !== e.tag) return false;
    if (c.id && e.attrs.id !== c.id) return false;
    var k;
    if (c.cls.length) { var cs = clsSet(e); for (k = 0; k < c.cls.length; k++) if (!cs[c.cls[k]]) return false; }
    for (k = 0; k < c.attrs.length; k++) {
      var at = c.attrs[k], v = e.attrs[at.n];
      if (v === undefined) return false;
      if (!at.op) continue;
      var x = at.v, y = v;
      if (at.ci) { x = x.toLowerCase(); y = y.toLowerCase(); }
      if (at.op === '=' && y !== x) return false;
      if (at.op === '~=' && y.split(/\s+/).indexOf(x) < 0) return false;
      if (at.op === '|=' && y !== x && y.indexOf(x + '-') !== 0) return false;
      if (at.op === '^=' && (!x || y.indexOf(x) !== 0)) return false;
      if (at.op === '$=' && (!x || y.slice(-x.length) !== x)) return false;
      if (at.op === '*=' && (!x || y.indexOf(x) < 0)) return false;
    }
    for (k = 0; k < c.ps.length; k++) {
      var ps = c.ps[k], sib = e.parent ? e.parent.els : [e];
      switch (ps.n) {
        case 'first-child': if (e.eidx !== 0) return false; break;
        case 'last-child': if (e.eidx !== sib.length - 1) return false; break;
        case 'only-child': if (sib.length !== 1) return false; break;
        case 'nth-child': if (!nthOk(ps.nth, e.eidx + 1)) return false; break;
        case 'nth-last-child': if (!nthOk(ps.nth, sib.length - e.eidx)) return false; break;
        case 'first-of-type': if (sameTypeIndex(e, false) !== 1) return false; break;
        case 'last-of-type': if (sameTypeIndex(e, true) !== 1) return false; break;
        case 'only-of-type': if (sameTypeIndex(e, false) !== 1 || sameTypeIndex(e, true) !== 1) return false; break;
        case 'nth-of-type': if (!nthOk(ps.nth, sameTypeIndex(e, false))) return false; break;
        case 'nth-last-of-type': if (!nthOk(ps.nth, sameTypeIndex(e, true))) return false; break;
        case 'root': if (e.tag !== 'html') return false; break;
        case 'empty':
          for (var q = 0; q < e.children.length; q++) if (e.children[q].tag !== '#text' || e.children[q].text) return false;
          break;
        case 'link': case 'any-link': if (!(e.tag === 'a' && e.attrs.href !== undefined)) return false; break;
        case 'checked': if (e.attrs.checked === undefined && e.attrs.selected === undefined) return false; break;
        case 'disabled': if (e.attrs.disabled === undefined) return false; break;
        case 'not': for (var z = 0; z < ps.sub.length; z++) if (matchCompound(e, ps.sub[z])) return false; break;
        default: return false; // hover, focus, visited ...
      }
    }
    return true;
  }
  function matchComplex(e, parts, idx) {
    if (!matchCompound(e, parts[idx].c)) return false;
    if (idx === 0) return true;
    var comb = parts[idx].comb, p;
    if (comb === ' ') {
      for (p = e.parent; p && p.tag !== '#root'; p = p.parent) if (matchComplex(p, parts, idx - 1)) return true;
      return false;
    }
    if (comb === '>') return !!(e.parent && e.parent.tag !== '#root' && matchComplex(e.parent, parts, idx - 1));
    var sib = e.parent ? e.parent.els : [];
    if (comb === '+') return e.eidx > 0 && matchComplex(sib[e.eidx - 1], parts, idx - 1);
    if (comb === '~') { for (var k = e.eidx - 1; k >= 0; k--) if (matchComplex(sib[k], parts, idx - 1)) return true; return false; }
    return false;
  }

  // ======================= 7. default (browser) stylesheet =======================
  var UA_CSS =
    'html,address,blockquote,body,dd,div,dl,dt,fieldset,form,frame,frameset,h1,h2,h3,h4,h5,h6,noframes,ol,p,ul,center,dir,hr,menu,pre,' +
    'article,aside,footer,header,hgroup,main,nav,section,figure,figcaption,details,summary,legend,address{display:block}' +
    'li{display:list-item}' +
    'head,script,style,title,meta,link,template,noscript,base,param,datalist,map,area,svg,canvas,video,audio,iframe,object,embed,select,math{display:none}' +
    '[hidden]{display:none}' +
    'table{display:table;border-collapse:separate}tr{display:table-row;vertical-align:middle}thead{display:table-header-group;vertical-align:middle}' +
    'tbody{display:table-row-group;vertical-align:middle}tfoot{display:table-footer-group;vertical-align:middle}col{display:table-column}' +
    'colgroup{display:table-column-group}td,th{display:table-cell;padding:1px}caption{display:table-caption;text-align:center}' +
    'th{font-weight:bold;text-align:center}' +
    'body{margin:8px}p{margin:1em 0}' +
    'h1{font-size:2em;margin:.67em 0;font-weight:bold;page-break-after:avoid}h2{font-size:1.5em;margin:.83em 0;font-weight:bold;page-break-after:avoid}' +
    'h3{font-size:1.17em;margin:1em 0;font-weight:bold;page-break-after:avoid}h4{margin:1.33em 0;font-weight:bold;page-break-after:avoid}' +
    'h5{font-size:.83em;margin:1.67em 0;font-weight:bold;page-break-after:avoid}h6{font-size:.67em;margin:2.33em 0;font-weight:bold;page-break-after:avoid}' +
    'blockquote,figure{margin:1em 40px}ul,ol,menu,dir{margin:1em 0;padding-left:40px}ul,menu,dir{list-style-type:disc}ol{list-style-type:decimal}' +
    'ul ul,ol ul,menu ul,ul menu{list-style-type:circle}ul ul ul,ul ol ul,ol ul ul,ol ol ul{list-style-type:square}' +
    'ol ol,ol ul,ul ol,ul ul{margin-top:0;margin-bottom:0}dl{margin:1em 0}dd{margin-left:40px}' +
    'b,strong{font-weight:bold}i,em,cite,var,dfn,address{font-style:italic}u,ins{text-decoration:underline}s,strike,del{text-decoration:line-through}' +
    'sub{vertical-align:sub;font-size:smaller}sup{vertical-align:super;font-size:smaller}small{font-size:smaller}big{font-size:larger}' +
    'pre,code,kbd,samp,tt,xmp,listing,plaintext{font-family:monospace}pre,xmp,listing,plaintext{white-space:pre;margin:1em 0}' +
    'a[href]{color:#0000EE;text-decoration:underline}mark{background-color:yellow;color:black}center{text-align:center}' +
    'hr{border:1px inset gray;margin:.5em 0}nobr{white-space:nowrap}fieldset{margin:0 2px;padding:.35em .75em .625em;border:2px groove #c0c0c0}';
  var QUIRKS_CSS = 'table{font-size:medium;font-weight:normal;font-style:normal;font-variant:normal;line-height:normal;white-space:normal;text-align:left}';
  var FROALA_CSS =
    '.fr-view table{border:none;border-collapse:collapse;empty-cells:show}.fr-view table td,.fr-view table th{border:1px solid #dddddd}' +
    '.fr-view table th{background:#ececec}.fr-view table.fr-dashed-borders td,.fr-view table.fr-dashed-borders th{border-style:dashed}' +
    '.fr-view table.fr-alternate-rows tbody tr:nth-child(2n){background:#f5f5f5}.fr-view table td.fr-thick,.fr-view table th.fr-thick{border-width:2px}' +
    '.fr-view table td.fr-highlighted,.fr-view table th.fr-highlighted{border:1px double red}' +
    '.fr-view blockquote{border-left:solid 2px #5e35b1;margin-left:0;padding-left:5px;color:#5e35b1}' +
    '.fr-view .fr-text-gray{color:#AAA}.fr-view .fr-text-bordered{border-top:solid 1px #222;border-bottom:solid 1px #222;padding:10px 0}' +
    '.fr-view .fr-text-spaced{letter-spacing:1px}.fr-view .fr-text-uppercase{text-transform:uppercase}' +
    '.fr-view img.fr-dib{display:block;margin:5px auto}.fr-view img.fr-dib.fr-fil{margin-left:0}.fr-view img.fr-dib.fr-fir{margin-right:0}' +
    '.fr-view hr{border:0;border-bottom:1px solid #cccccc}';

  // ======================= 8. presentational attributes =======================
  var FONT_SIZE_ATTR = { 1: '7.5pt', 2: '10pt', 3: '12pt', 4: '13.5pt', 5: '18pt', 6: '24pt', 7: '36pt' };
  function pxOrPct(v) { v = String(v).trim(); return /%$/.test(v) ? v : /^[\d.]+$/.test(v) ? v + 'px' : v; }
  function hintDecls(e, out) {
    var a = e.attrs, t = e.tag;
    function put(p, v) { expandDecl(p, v, false, out); }
    if (a.align) {
      var al = a.align.toLowerCase();
      if (t === 'table') { if (al === 'center') { put('margin-left', 'auto'); put('margin-right', 'auto'); } else if (al === 'right') put('margin-left', 'auto'); }
      else if (t === 'img') { if (al === 'middle' || al === 'top' || al === 'bottom') put('vertical-align', al); }
      else if (/^(p|div|h[1-6]|td|th|tr|tbody|thead|tfoot|caption|li|legend|center)$/.test(t)) put('text-align', al === 'middle' ? 'center' : al);
    }
    if (a.valign && /^(td|th|tr|tbody|thead|tfoot|col)$/.test(t)) put('vertical-align', a.valign.toLowerCase());
    if (a.bgcolor) put('background-color', a.bgcolor);
    if (t === 'font') {
      if (a.color) put('color', a.color);
      if (a.face) put('font-family', a.face);
      if (a.size) {
        var sz = String(a.size).trim(), base = /^[+-]/.test(sz) ? 3 + parseInt(sz, 10) : parseInt(sz, 10);
        if (base > 0) put('font-size', FONT_SIZE_ATTR[clamp(base, 1, 7)]);
      }
    }
    if (t === 'body' && a.text) put('color', a.text);
    if (a.width && /^(table|td|th|col|colgroup|img|hr)$/.test(t)) put('width', pxOrPct(a.width));
    if (a.height && /^(td|th|tr|img|table)$/.test(t)) put('height', pxOrPct(a.height));
    if (t === 'table' && a.border !== undefined) {
      var bw = a.border === '' ? 1 : parseInt(a.border, 10);
      if (bw > 0) put('border', bw + 'px outset gray');
    }
    if (t === 'img' && a.border && parseInt(a.border, 10) > 0) put('border', parseInt(a.border, 10) + 'px solid');
    if ((t === 'td' || t === 'th') && a.nowrap !== undefined) put('white-space', 'nowrap');
    if (t === 'td' || t === 'th') {
      var tbl = e.parent;
      while (tbl && tbl.tag !== 'table' && tbl.tag !== '#root') tbl = tbl.parent;
      if (tbl && tbl.tag === 'table') {
        if (tbl.attrs.border !== undefined && (tbl.attrs.border === '' || parseInt(tbl.attrs.border, 10) > 0)) put('border', '1px inset gray');
        if (tbl.attrs.cellpadding !== undefined) put('padding', pxOrPct(tbl.attrs.cellpadding));
      }
    }
    if (t === 'hr') { if (a.color) { put('border-color', a.color); } if (a.size) put('border-top-width', pxOrPct(a.size)); }
    if ((t === 'ol' || t === 'li') && a.type) {
      var tp = { '1': 'decimal', a: 'lower-alpha', A: 'upper-alpha', i: 'lower-roman', I: 'upper-roman' }[a.type];
      if (tp) put('list-style-type', tp);
    }
    if ((t === 'ul' || t === 'li') && /^(disc|circle|square)$/i.test(a.type || '')) put('list-style-type', a.type.toLowerCase());
  }

  // ======================= 9. computed style =======================
  var INHERITED = toSet('color font-family font-size font-weight font-style font-variant line-height text-align text-indent ' +
    'text-transform letter-spacing white-space visibility list-style-type list-style-position border-collapse direction');

  function rootStyle(o) {
    return {
      display: 'block', fontSize: o.fontSizePt || 12, fontFamily: o.fontFamily || 'Times New Roman', fontWeight: 400,
      fontStyle: 'normal', fontVariant: 'normal', color: null, lineHeight: null, textAlign: 'left', textIndent: null,
      textTransform: 'none', letterSpacing: 0, whiteSpace: 'normal', visibility: 'visible', listStyleType: 'disc',
      listStylePosition: 'outside', borderCollapse: 'separate', deco: { u: null, s: false }, direction: 'ltr'
    };
  }

  var U_STYLE = { solid: 'single', double: 'double', dotted: 'dotted', dashed: 'dash', wavy: 'wave' };

  function computeStyle(e, d, p, rootFs) {
    var cs = {};
    function sv(prop) { var v = d[prop]; return v === undefined ? undefined : v; }
    function isInh(v) { return v === 'inherit'; }
    // font-size first (em units depend on it)
    var fsv = sv('font-size'), fs = p.fontSize;
    if (fsv !== undefined && !isInh(fsv) && fsv !== 'unset') {
      var lf = fsv.toLowerCase();
      if (lf === 'initial') fs = 12;
      else if (FS_KEY[lf] !== undefined) fs = FS_KEY[lf];
      else if (lf === 'smaller') fs = p.fontSize / 1.2;
      else if (lf === 'larger') fs = p.fontSize * 1.2;
      else { var L = parseLen(lf, p.fontSize, rootFs); if (L) fs = L.pct != null ? p.fontSize * L.pct / 100 : L.pt; }
    }
    cs.fontSize = Math.max(0, fs);
    var ff = sv('font-family');
    cs.fontFamily = ff && !isInh(ff) ? (firstFamily(ff) || p.fontFamily) : p.fontFamily;
    var fw = sv('font-weight'), w = p.fontWeight;
    if (fw && !isInh(fw)) {
      fw = fw.toLowerCase();
      w = fw === 'bold' ? 700 : fw === 'normal' ? 400 : fw === 'bolder' ? (p.fontWeight < 600 ? 700 : 900) : fw === 'lighter' ? (p.fontWeight > 500 ? 400 : 100) : (parseInt(fw, 10) || w);
    }
    cs.fontWeight = w;
    var fst = sv('font-style');
    cs.fontStyle = fst && !isInh(fst) ? (/italic|oblique/i.test(fst) ? 'italic' : 'normal') : p.fontStyle;
    var fv = sv('font-variant');
    cs.fontVariant = fv && !isInh(fv) ? (/small-caps/i.test(fv) ? 'small-caps' : 'normal') : p.fontVariant;
    var col = sv('color');
    if (col && !isInh(col)) { var pc = parseColor(col, p.color); cs.color = pc === undefined ? p.color : pc; } else cs.color = p.color;
    var lh = sv('line-height');
    if (lh && !isInh(lh)) {
      var ll = lh.toLowerCase();
      if (ll === 'normal' || ll === 'initial') cs.lineHeight = null;
      else if (/^[\d.]+$/.test(ll)) cs.lineHeight = { m: parseFloat(ll) };
      else { var LL = parseLen(ll, cs.fontSize, rootFs); cs.lineHeight = LL ? (LL.pct != null ? { pt: cs.fontSize * LL.pct / 100 } : { pt: LL.pt }) : p.lineHeight; }
    } else cs.lineHeight = p.lineHeight;
    var ta = sv('text-align');
    if (ta && !isInh(ta)) {
      ta = ta.toLowerCase().replace('-webkit-', '').replace('-moz-', '');
      cs.textAlign = ta === 'start' ? 'left' : ta === 'end' ? 'right' : /^(left|right|center|justify)$/.test(ta) ? ta : p.textAlign;
    } else cs.textAlign = p.textAlign;
    var ti = sv('text-indent');
    cs.textIndent = ti && !isInh(ti) ? parseLen(ti, cs.fontSize, rootFs) : p.textIndent;
    var tt = sv('text-transform');
    cs.textTransform = tt && !isInh(tt) ? tt.toLowerCase() : p.textTransform;
    var ls = sv('letter-spacing');
    cs.letterSpacing = ls && !isInh(ls) ? (ls === 'normal' ? 0 : res0(parseLen(ls, cs.fontSize, rootFs), 0)) : p.letterSpacing;
    var ws = sv('white-space');
    cs.whiteSpace = ws && !isInh(ws) ? ws.toLowerCase() : p.whiteSpace;
    var vis = sv('visibility');
    cs.visibility = vis && !isInh(vis) ? vis.toLowerCase() : p.visibility;
    var lst = sv('list-style-type');
    cs.listStyleType = lst && !isInh(lst) ? lst.toLowerCase() : p.listStyleType;
    var lsp = sv('list-style-position');
    cs.listStylePosition = lsp && !isInh(lsp) ? lsp.toLowerCase() : p.listStylePosition;
    var bc = sv('border-collapse');
    cs.borderCollapse = bc && !isInh(bc) ? bc.toLowerCase() : p.borderCollapse;
    cs.direction = p.direction;
    // decorations propagate (union with the parent's)
    var tdl = sv('text-decoration-line'), tds = (sv('text-decoration-style') || 'solid').toLowerCase();
    var deco = { u: p.deco.u, s: p.deco.s };
    if (tdl && !isInh(tdl)) {
      tdl = tdl.toLowerCase();
      if (/underline/.test(tdl)) deco.u = U_STYLE[tds] || 'single';
      if (/line-through/.test(tdl)) deco.s = true;
    }
    cs.deco = deco;
    // non-inherited
    var disp = sv('display');
    cs.display = disp && !isInh(disp) ? disp.toLowerCase().replace(/^(-webkit-|-moz-)/, '') : 'inline';
    if (cs.display === 'contents') cs.display = 'inline';
    var bg = sv('background-color');
    cs.background = bg && !isInh(bg) ? (parseColor(bg, cs.color) || null) : null;
    cs.verticalAlign = (sv('vertical-align') || 'baseline').toLowerCase();
    if (cs.verticalAlign === 'inherit') cs.verticalAlign = p.verticalAlign || 'baseline';
    var fsz = cs.fontSize;
    function len(prop) { var v = sv(prop); if (v === undefined || v === 'initial' || v === 'unset') return null; if (isInh(v)) return p['_' + prop] || null; return parseLen(v, fsz, rootFs); }
    cs.m = [len('margin-top'), len('margin-right'), len('margin-bottom'), len('margin-left')];
    cs.pd = [len('padding-top'), len('padding-right'), len('padding-bottom'), len('padding-left')];
    cs.bd = SIDES.map(function (sd) {
      var st = (sv('border-' + sd + '-style') || 'none').toLowerCase();
      if (st === 'none' || st === 'hidden' || !BORDER_STYLES[st]) return null;
      var wv = (sv('border-' + sd + '-width') || 'medium').toLowerCase();
      var wpt = BW_KEY[wv] !== undefined ? BW_KEY[wv] : res0(parseLen(wv, fsz, rootFs), 0);
      if (!(wpt > 0)) return null;
      var cv = sv('border-' + sd + '-color'), cc = cv ? parseColor(cv, cs.color) : cs.color;
      if (cc === undefined) cc = cs.color;
      if (cc === null && cv && /transparent/i.test(cv)) return null;
      return { w: wpt, s: st, c: cc || '000000' };
    });
    cs.width = len('width'); cs.height = len('height');
    cs.minHeight = len('min-height'); cs.maxWidth = len('max-width'); cs.maxHeight = len('max-height');
    cs.pbBefore = (sv('page-break-before') || 'auto').toLowerCase();
    cs.pbAfter = (sv('page-break-after') || 'auto').toLowerCase();
    cs.pbInside = (sv('page-break-inside') || 'auto').toLowerCase();
    cs.tableLayout = (sv('table-layout') || 'auto').toLowerCase();
    cs.boxSizing = (sv('box-sizing') || 'content-box').toLowerCase();
    cs.float = (sv('float') || 'none').toLowerCase();
    var ta2 = sv('text-align-last');
    cs.textAlignLast = ta2 ? ta2.toLowerCase() : null;
    return cs;
  }

  function computeAll(root, sheet, opts) {
    var rcs = rootStyle(opts), rootFs = 12;
    var uaRules = sheet.ua.slice().sort(function (a, b) { return a.spec - b.spec || a.order - b.order; });
    var auRules = sheet.author.slice().sort(function (a, b) { return a.spec - b.spec || a.order - b.order; });
    function matched(e, rules) {
      var out = [];
      for (var i = 0; i < rules.length; i++) { var r = rules[i]; if (matchComplex(e, r.parts, r.parts.length - 1)) out.push(r); }
      return out;
    }
    function walk(e, pcs) {
      var d = Object.create(null), i, j, k, dd;
      var mu = matched(e, uaRules), ma = matched(e, auRules), hints = [], inline = [];
      hintDecls(e, hints);
      if (e.attrs.style) inline = parseDecls(e.attrs.style);
      function apply(list, imp) { for (j = 0; j < list.length; j++) { dd = list[j]; if (dd.imp === imp) d[dd.p] = dd.v; } }
      for (i = 0; i < mu.length; i++) apply(mu[i].decls, false);
      apply(hints, false);
      for (i = 0; i < ma.length; i++) apply(ma[i].decls, false);
      apply(inline, false);
      for (i = 0; i < mu.length; i++) apply(mu[i].decls, true);
      for (i = 0; i < ma.length; i++) apply(ma[i].decls, true);
      apply(inline, true);
      var cs = computeStyle(e, d, pcs, rootFs);
      if (e.tag === 'html') rootFs = cs.fontSize;
      e.cs = cs;
      for (k = 0; k < e.els.length; k++) walk(e.els[k], cs);
    }
    root.cs = rcs;
    for (var k = 0; k < root.els.length; k++) walk(root.els[k], rcs);
  }

  // ======================= 10. images =======================
  function imageInfo(bytes) {
    var b = bytes, n = b.length;
    if (n > 24 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4E && b[3] === 0x47)
      return { ext: 'png', mime: 'image/png', w: ((b[16] << 24) | (b[17] << 16) | (b[18] << 8) | b[19]) >>> 0, h: ((b[20] << 24) | (b[21] << 16) | (b[22] << 8) | b[23]) >>> 0 };
    if (n > 10 && b[0] === 0x47 && b[1] === 0x49 && b[2] === 0x46) return { ext: 'gif', mime: 'image/gif', w: b[6] | (b[7] << 8), h: b[8] | (b[9] << 8) };
    if (n > 26 && b[0] === 0x42 && b[1] === 0x4D) return { ext: 'bmp', mime: 'image/bmp', w: Math.abs(b[18] | (b[19] << 8) | (b[20] << 16) | (b[21] << 24)), h: Math.abs(b[22] | (b[23] << 8) | (b[24] << 16) | (b[25] << 24)) };
    if (n > 4 && b[0] === 0xFF && b[1] === 0xD8) {
      var i = 2;
      while (i + 9 < n) {
        if (b[i] !== 0xFF) { i++; continue; }
        var m = b[i + 1];
        if (m === 0xD8 || m === 0x01 || (m >= 0xD0 && m <= 0xD7) || m === 0xFF) { i += m === 0xFF ? 1 : 2; continue; }
        var len = (b[i + 2] << 8) | b[i + 3];
        if ((m >= 0xC0 && m <= 0xCF) && m !== 0xC4 && m !== 0xC8 && m !== 0xCC)
          return { ext: 'jpeg', mime: 'image/jpeg', h: (b[i + 5] << 8) | b[i + 6], w: (b[i + 7] << 8) | b[i + 8] };
        i += 2 + len;
      }
      return { ext: 'jpeg', mime: 'image/jpeg', w: 0, h: 0 };
    }
    return null;
  }

  function loadImageSrc(src, remote) {
    src = String(src || '').trim();
    var m = /^data:([^;,]*)((?:;[^;,]*)*?);base64,/i.exec(src.slice(0, 200));
    if (m) {
      var bytes = b64decode(src.slice(m[0].length));
      var info = imageInfo(bytes);
      if (!info) return { error: 'unsupported image type ' + (m[1] || '?') };
      info.bytes = bytes;
      return info;
    }
    if (/^data:/i.test(src)) return { error: 'non-base64 data URI (' + src.slice(5, 30) + ')' };
    if (remote && remote[src]) {
      var rb = remote[src];
      if (rb.error) return rb;
      var inf = imageInfo(rb);
      if (!inf) return { error: 'unsupported image type at ' + src.slice(0, 80) };
      inf.bytes = rb;
      return inf;
    }
    return { error: 'image not embedded: ' + src.slice(0, 80) };
  }

  // ======================= 11. layout =======================
  var JC = { left: 'left', right: 'right', center: 'center', justify: 'both' };
  var HL = { FFFF00: 'yellow', '00FF00': 'green', '00FFFF': 'cyan', FF00FF: 'magenta', '0000FF': 'blue', FF0000: 'red',
    '000080': 'darkBlue', '008080': 'darkCyan', '008000': 'darkGreen', '800080': 'darkMagenta', '800000': 'darkRed',
    '808000': 'darkYellow', '808080': 'darkGray', C0C0C0: 'lightGray', '000000': 'black' };
  var LIST_FMT = {
    disc: ['bullet', '•', 'Arial'], circle: ['bullet', 'o', 'Courier New'], square: ['bullet', '▪', 'Arial'],
    decimal: ['decimal', '.'], 'decimal-leading-zero': ['decimalZero', '.'], 'lower-alpha': ['lowerLetter', '.'],
    'lower-latin': ['lowerLetter', '.'], 'upper-alpha': ['upperLetter', '.'], 'upper-latin': ['upperLetter', '.'],
    'lower-roman': ['lowerRoman', '.'], 'upper-roman': ['upperRoman', '.'], none: ['none', '']
  };

  function Layout(opts, page, warn) {
    this.opts = opts; this.page = page; this.warn = warn;
    this.media = []; this.mediaBySrc = Object.create(null); this.links = []; this.linkByUrl = Object.create(null);
    this.lists = []; this.absByFmt = Object.create(null); this.stats = { paragraphs: 0, tables: 0, images: 0, links: 0, lists: 0 };
    this.remote = null;
  }

  function Flow() { this.items = []; this.para = null; this.pb = 0; this.pbFixed = 0; this.brk = false; }

  function isBlockDisplay(d) { return d === 'block' || d === 'list-item' || d === 'table-caption' || d === 'flex' || d === 'grid' || d === 'flow-root' || d === 'table-row' || d === 'table-cell' || d === 'table-row-group' || d === 'table-header-group' || d === 'table-footer-group'; }

  function hasBlockChild(e) {
    for (var i = 0; i < e.els.length; i++) {
      var c = e.els[i];
      if (c.cs.display !== 'none' && (isBlockDisplay(c.cs.display) || c.cs.display === 'table' || c.tag === 'table' || c.tag === 'hr')) return true;
    }
    return false;
  }

  function hasContent(e) {
    if (e._hc !== undefined) return e._hc;
    var r = false;
    for (var i = 0; i < e.children.length && !r; i++) {
      var c = e.children[i];
      if (c.tag === '#text') { if (/[^ \t\n\r\f]/.test(c.text)) r = true; }
      else if (c.cs && c.cs.display === 'none') continue;
      else if (/^(img|br|hr|table|input|textarea)$/.test(c.tag)) r = true;
      else if (hasContent(c)) r = true;
      else if (isBlockDisplay(c.cs.display) && (res0(c.cs.height, 0) > 0 || res0(c.cs.minHeight, 0) > 0)) r = true;
    }
    e._hc = r;
    return r;
  }

  Layout.prototype.runProps = function (cs, ctx) {
    var rp = {
      f: cs.fontFamily, sz: cs.fontSize, b: cs.fontWeight >= 600, i: cs.fontStyle === 'italic', u: cs.deco.u, s: cs.deco.s,
      c: cs.color, bg: ctx.bg || null, va: ctx.va || null, caps: cs.textTransform === 'uppercase',
      sc: cs.fontVariant === 'small-caps', ls: cs.letterSpacing || 0, hid: cs.visibility === 'hidden'
    };
    if (ctx.va && ctx.vaBase) rp.sz = ctx.vaBase;
    return rp;
  };

  Layout.prototype.openPara = function (flow, ctx) {
    var b = ctx.block, cs = b.cs;
    var p = {
      kind: 'p', runs: [], cs: cs, before: flow.pbFixed + flow.pb, after: 0, lastSpace: true,
      ind: { l: ctx.indL, r: ctx.indR, first: 0, hang: 0 }, jc: cs.textAlign, lh: cs.lineHeight, family: cs.fontFamily,
      shd: ctx.blockBg || null, outline: b.outline, markRp: this.runProps(cs, { bg: null, va: null })
    };
    flow.pb = 0; flow.pbFixed = 0;
    if (flow.brk) { p.pageBreakBefore = true; flow.brk = false; }
    if (!b.used) { b.used = true; p.ind.first = res0(cs.textIndent, ctx.W); }
    if (ctx.li && !ctx.li.used) {
      ctx.li.used = true;
      if (ctx.li.numId) { p.num = { id: ctx.li.numId, ilvl: ctx.li.ilvl }; p.ind.hang = Math.min(18, Math.max(0, p.ind.l)); }
    }
    if (b.keepNext) p.keepNextBlock = true;
    flow.para = p;
    this.stats.paragraphs++;
    return p;
  };

  function runVisible(r) { return r.img || r.tab || r.br || (r.t && /[^ ]/.test(r.t)); }

  Layout.prototype.flush = function (flow) {
    var p = flow.para;
    if (!p) return;
    flow.para = null;
    var runs = p.runs;
    while (runs.length) { // trim trailing collapsible spaces
      var r = runs[runs.length - 1];
      if (r.t !== undefined && !r.pre) {
        r.t = r.t.replace(/ +$/, '');
        if (!r.t) { runs.pop(); continue; }
      }
      break;
    }
    var vis = runs.some(runVisible);
    if (!vis) {
      this.stats.paragraphs--;
      flow.pb = Math.max(flow.pb, p.before);
      if (p.pageBreakBefore) flow.brk = true;
      return;
    }
    if (runs.length > 1 && runs[runs.length - 1].br && !runs[runs.length - 1].pageBr) runs.pop();
    else if (runs.length === 1 && runs[0].br) runs.pop(); // a lone <br> is an empty line
    flow.items.push(p);
  };

  Layout.prototype.addRun = function (flow, ctx, run) {
    var p = flow.para || this.openPara(flow, ctx);
    if (ctx.link) run.link = ctx.link;
    p.runs.push(run);
    return p;
  };

  Layout.prototype.addText = function (text, cs, ctx, flow) {
    var ws = cs.whiteSpace || 'normal';
    var pre = ws === 'pre' || ws === 'pre-wrap' || ws === 'break-spaces', preLine = ws === 'pre-line';
    if (!pre) text = preLine ? text.replace(/[ \t\f\r]+/g, ' ').replace(/ ?\n ?/g, '\n') : text.replace(/[ \t\n\r\f]+/g, ' ');
    if (!text) return;
    var p = flow.para;
    if (!pre) {
      if (!p || p.lastSpace) text = text.replace(/^ /, '');
      if (!text) return;
    }
    var endsSpace = !pre && / $/.test(text);
    if (ws === 'nowrap') text = text.replace(/ (?=.)/g, ' ');
    if (cs.textTransform === 'lowercase') text = text.toLowerCase();
    else if (cs.textTransform === 'capitalize') {
      var prevSpace = !p || p.lastSpace;
      text = text.replace(/(^|[\s ("'“„«\[-])([^\s ])/g, function (m, a, c, off) {
        return off === 0 && !a && !prevSpace ? m : a + c.toUpperCase();
      });
    }
    var rp = this.runProps(cs, ctx), self = this;
    if (pre || preLine) {
      var lines = text.split('\n');
      lines.forEach(function (ln, idx) {
        if (idx > 0) self.addRun(flow, ctx, { br: true, rp: rp });
        if (pre) {
          ln.split('\t').forEach(function (seg, k) {
            if (k > 0) self.addRun(flow, ctx, { tab: true, rp: rp });
            if (seg) self.addRun(flow, ctx, { t: seg, rp: rp, pre: true });
          });
        } else if (ln) self.addRun(flow, ctx, { t: ln, rp: rp });
      });
      if (flow.para) flow.para.lastSpace = false;
      return;
    }
    p = this.addRun(flow, ctx, { t: text, rp: rp });
    p.lastSpace = endsSpace;
  };

  Layout.prototype.children = function (e, ctx, flow) {
    for (var k = 0; k < e.children.length; k++) {
      var ch = e.children[k];
      if (ch.tag === '#text') this.addText(ch.text, e.cs, ctx, flow);
      else this.node(ch, ctx, flow);
    }
  };

  Layout.prototype.node = function (e, ctx, flow) {
    var cs = e.cs, d = cs.display, t = e.tag;
    if (d === 'none') return;
    if (t === 'br') { var p = this.addRun(flow, ctx, { br: true, rp: this.runProps(cs, ctx) }); p.lastSpace = true; return; }
    if (t === 'img') { this.image(e, ctx, flow); return; }
    if (t === 'hr') { this.hr(e, ctx, flow); return; }
    if (t === 'input') { this.input(e, ctx, flow); return; }
    if (t === 'table' || d === 'table' || d === 'inline-table') { this.table(e, ctx, flow); return; }
    if (isBlockDisplay(d) || (d === 'inline-block' && hasBlockChild(e))) { this.block(e, ctx, flow); return; }
    // inline
    var c2 = ctx, va = cs.verticalAlign;
    var isVa = va === 'super' || va === 'sub';
    var href = t === 'a' && e.attrs.href ? String(e.attrs.href).trim() : null;
    if (href && (href.charAt(0) === '#' || /^javascript:/i.test(href))) href = null;
    if (cs.background || isVa || href) {
      c2 = Object.create(ctx);
      if (cs.background) c2.bg = cs.background;
      if (isVa && !ctx.va) { c2.va = va; c2.vaBase = e.parent && e.parent.cs ? e.parent.cs.fontSize : cs.fontSize; }
      if (href) { c2.link = href; this.stats.links++; }
    }
    this.children(e, c2, flow);
    if (d === 'inline-block' && cs.width && !cs.width.auto && res0(cs.width, ctx.W) > 0) {
      var pp = this.addRun(flow, c2, { tab: true, rp: this.runProps(cs, c2) });
      pp.lastSpace = true;
    }
  };

  Layout.prototype.input = function (e, ctx, flow) {
    var ty = String(e.attrs.type || 'text').toLowerCase(), on = e.attrs.checked !== undefined, txt;
    if (ty === 'hidden') return;
    if (ty === 'checkbox') txt = on ? '☒' : '☐';
    else if (ty === 'radio') txt = on ? '◉' : '○';
    else txt = e.attrs.value || '';
    if (!txt) return;
    var p = this.addRun(flow, ctx, { t: txt, rp: this.runProps(e.cs, ctx) });
    p.lastSpace = false;
  };

  function boxH(cs, W, folded) {
    if (folded) return { ml: 0, mr: 0, pl: 0, pr: 0, bl: 0, br: 0 };
    return {
      ml: res0(cs.m[3], W), mr: res0(cs.m[1], W), pl: Math.max(0, res0(cs.pd[3], W)), pr: Math.max(0, res0(cs.pd[1], W)),
      bl: cs.bd[3] ? cs.bd[3].w : 0, br: cs.bd[1] ? cs.bd[1].w : 0
    };
  }
  function isBreak(v) { return v === 'always' || v === 'page' || v === 'left' || v === 'right'; }

  Layout.prototype.newList = function (e, cs) {
    var type = LIST_FMT[cs.listStyleType] ? cs.listStyleType : (e.tag === 'ol' ? 'decimal' : 'disc');
    if (!this.absByFmt[type]) this.absByFmt[type] = { id: Object.keys(this.absByFmt).length, type: type };
    var start = parseInt(e.attrs.start, 10);
    var lst = { numId: this.lists.length + 1, abs: this.absByFmt[type].id, start: start > 0 ? start : 1, ilvl: 0 };
    this.lists.push(lst);
    this.stats.lists++;
    return lst;
  };

  Layout.prototype.block = function (e, ctx, flow) {
    var cs = e.cs, W = ctx.W;
    this.flush(flow);
    var h = boxH(cs, W, e.folded);
    var mt = res0(cs.m[0], W), mb = res0(cs.m[2], W), ptop = Math.max(0, res0(cs.pd[0], W)), pbot = Math.max(0, res0(cs.pd[2], W));
    var bt = cs.bd[0] ? cs.bd[0].w : 0, bb = cs.bd[2] ? cs.bd[2].w : 0;
    var wv = e.folded ? null : res(cs.width, W);
    if (wv != null && wv > 0) {
      var cw = cs.boxSizing === 'border-box' ? wv - h.pl - h.pr - h.bl - h.br : wv;
      var free = W - (cw + h.pl + h.pr + h.bl + h.br);
      var la = cs.m[3] && cs.m[3].auto, ra = cs.m[1] && cs.m[1].auto;
      if (la && ra) h.ml = h.mr = free / 2; else if (la) h.ml = free - h.mr; else h.mr = free - h.ml;
    }
    if (isBreak(cs.pbBefore)) flow.brk = true;
    if (ptop > 0 || bt > 0) { flow.pbFixed += Math.max(flow.pb, mt) + ptop + bt; flow.pb = 0; }
    else flow.pb = Math.max(flow.pb, mt);
    var start = flow.items.length;
    var hl = /^h([1-6])$/.exec(e.tag);
    var nctx = Object.create(ctx);
    nctx.W = Math.max(1, W - h.ml - h.mr - h.pl - h.pr - h.bl - h.br);
    nctx.indL = ctx.indL + h.ml + h.bl + h.pl;
    nctx.indR = ctx.indR + h.mr + h.br + h.pr;
    nctx.block = { cs: cs, el: e, used: false, outline: hl ? +hl[1] - 1 : null, keepNext: cs.pbAfter === 'avoid' };
    nctx.bg = null; nctx.va = null; nctx.vaBase = 0;
    if (cs.background) nctx.blockBg = cs.background;
    if (e.tag === 'ul' || e.tag === 'ol' || e.tag === 'menu' || e.tag === 'dir') {
      var lst = this.newList(e, cs);
      lst.ilvl = ctx.listDepth || 0;
      nctx.list = lst; nctx.listDepth = (ctx.listDepth || 0) + 1; nctx.li = null;
    } else if (cs.display === 'list-item') {
      var L = ctx.list;
      if (!L) { L = this.newList(e, cs); ctx.list = L; }
      var none = cs.listStyleType === 'none';
      nctx.li = { numId: none ? 0 : L.numId, ilvl: Math.min(8, L.ilvl), used: false };
      if (!none && cs.listStyleType !== this.lists[L.numId - 1].typeName) this.lists[L.numId - 1].typeName = cs.listStyleType;
    }
    if (!hasContent(e)) {
      var hh = res(cs.height, W);
      if (hh == null) hh = res(cs.minHeight, W);
      if (hh > 0.5) {
        var sp = { kind: 'p', runs: [], cs: cs, before: flow.pbFixed + flow.pb, after: 0, ind: { l: nctx.indL, r: nctx.indR, first: 0, hang: 0 }, exact: hh, markRp: { f: cs.fontFamily, sz: 1 }, shd: nctx.blockBg || null };
        if (flow.brk) { sp.pageBreakBefore = true; flow.brk = false; }
        flow.pb = 0; flow.pbFixed = 0;
        flow.items.push(sp);
      }
    } else this.children(e, nctx, flow);
    this.flush(flow);
    var last = flow.items.length > start ? flow.items[flow.items.length - 1] : null;
    var edgeB = pbot + bb;
    if (last && last.kind === 'p') {
      var a = Math.max(last.after, flow.pb);
      flow.pb = 0;
      last.after = edgeB > 0 ? a + edgeB + mb : Math.max(a, mb);
      if (flow.pbFixed) { last.after += flow.pbFixed; flow.pbFixed = 0; }
    } else if (last) flow.pb = Math.max(flow.pb, mb + edgeB);
    else { flow.pb = Math.max(flow.pb, mb); flow.pbFixed += edgeB; }
    if (isBreak(cs.pbAfter)) flow.brk = true;
    var bds = cs.bd;
    if (!e.folded && (bds[0] || bds[1] || bds[2] || bds[3])) {
      var bd = { t: bds[0], r: bds[1], b: bds[2], l: bds[3], sp: [ptop, h.pr, pbot, h.pl] };
      for (var k = start; k < flow.items.length; k++) if (flow.items[k].kind === 'p' && !flow.items[k].bdr) flow.items[k].bdr = bd;
    }
    if (cs.pbInside === 'avoid') applyKeep(flow.items, start);
    if (cs.pbAfter === 'avoid' && last && last.kind === 'p') last.keepNext = true;
  };

  function eachPara(item, fn) {
    if (item.kind === 'p') { fn(item); return; }
    item.rows.forEach(function (r) { r.cells.forEach(function (c) { c.items.forEach(function (it) { eachPara(it, fn); }); }); });
  }
  function applyKeep(items, start) {
    for (var k = start; k < items.length; k++) {
      var it = items[k], isLast = k === items.length - 1;
      if (it.kind === 'p') { it.keepLines = true; if (!isLast) it.keepNext = true; }
      else {
        it.rows.forEach(function (r, ri) {
          r.cant = true;
          if (!isLast || ri < it.rows.length - 1) r.cells.forEach(function (c) { c.items.forEach(function (x) { eachPara(x, function (p) { p.keepNext = true; }); }); });
        });
      }
    }
  }

  Layout.prototype.hr = function (e, ctx, flow) {
    var cs = e.cs, W = ctx.W;
    this.flush(flow);
    flow.pb = Math.max(flow.pb, res0(cs.m[0], W));
    var b = cs.bd[0] || cs.bd[2] || { w: 0.75, s: 'solid', c: '808080' };
    var p = { kind: 'p', runs: [], cs: cs, before: flow.pbFixed + flow.pb, after: 0, ind: { l: ctx.indL, r: ctx.indR, first: 0, hang: 0 }, exact: 1, markRp: { f: cs.fontFamily, sz: 1 }, bdr: { b: { w: b.w, s: b.s === 'inset' || b.s === 'outset' ? 'solid' : b.s, c: b.c }, sp: [0, 0, 0, 0] } };
    flow.pb = 0; flow.pbFixed = 0;
    if (flow.brk) { p.pageBreakBefore = true; flow.brk = false; }
    flow.items.push(p);
    p.after = res0(cs.m[2], W);
  };

  Layout.prototype.image = function (e, ctx, flow) {
    var cs = e.cs, src = e.attrs.src || '';
    var info = this.mediaBySrc[src];
    if (!info) {
      info = loadImageSrc(src, this.remote);
      if (info.error) { this.warn(info.error); info = { error: info.error }; }
      else {
        info.idx = this.media.length + 1;
        info.name = 'image' + info.idx + '.' + info.ext;
        info.rid = 'rIdImg' + info.idx;
        this.media.push(info);
      }
      this.mediaBySrc[src] = info;
    }
    if (info.error) {
      var alt = e.attrs.alt;
      if (alt) { var pa = this.addRun(flow, ctx, { t: '[' + alt + ']', rp: this.runProps(cs, ctx) }); pa.lastSpace = false; }
      return;
    }
    var W = ctx.W;
    var w = res(cs.width, W), hgt = res(cs.height, null);
    var iw = info.w * 0.75, ih = info.h * 0.75;
    if (w == null && hgt == null) { w = iw; hgt = ih; }
    else if (w == null) w = ih ? hgt * iw / ih : hgt;
    else if (hgt == null) hgt = iw ? w * ih / iw : w;
    var mw = res(cs.maxWidth, W);
    if (mw != null && w > mw) { hgt = hgt * mw / w; w = mw; }
    if (w > W && W > 10) { hgt = hgt * W / w; w = W; }
    if (!(w > 0) || !(hgt > 0)) { w = w || 72; hgt = hgt || 72; }
    this.stats.images++;
    var run = { img: info, w: w, h: hgt, alt: e.attrs.alt || '', rp: this.runProps(cs, ctx) };
    if (cs.display === 'block') {
      this.flush(flow);
      var mt = res0(cs.m[0], W), mb = res0(cs.m[2], W);
      flow.pb = Math.max(flow.pb, mt);
      var bctx = Object.create(ctx);
      var la = cs.m[3] && cs.m[3].auto, ra = cs.m[1] && cs.m[1].auto;
      var jc = la && ra ? 'center' : la ? 'right' : 'left';
      bctx.block = { cs: Object.create(ctx.block.cs, { textAlign: { value: jc }, textIndent: { value: null }, lineHeight: { value: null } }), used: true };
      var p = this.openPara(flow, bctx);
      p.runs.push(run); p.lastSpace = false;
      this.flush(flow);
      p.after = Math.max(p.after, mb);
      return;
    }
    var pp = this.addRun(flow, ctx, run);
    pp.lastSpace = false;
    pp.hasImage = true;
  };

  // ---------- tables ----------
  function textMetrics(e) { // rough min/max content widths in pt
    var mn = 0, mx = 0, line = 0;
    function walk(n, fs, bold) {
      if (n.tag === '#text') {
        var t = n.text.replace(/[ \t\n\r\f]+/g, ' ');
        var k = fs * (bold ? 0.56 : 0.52);
        t.split(' ').forEach(function (wd) { if (wd) mn = Math.max(mn, wd.length * k); });
        line += t.length * k;
        mx = Math.max(mx, line);
        return;
      }
      if (!n.cs || n.cs.display === 'none') return;
      if (n.tag === 'br') { line = 0; return; }
      if (n.tag === 'img') { var iw = res(n.cs.width, null) || 72; mn = Math.max(mn, iw); line += iw; mx = Math.max(mx, line); return; }
      var blk = isBlockDisplay(n.cs.display) || n.tag === 'table';
      if (blk) line = 0;
      for (var i = 0; i < n.children.length; i++) walk(n.children[i], n.cs.fontSize, n.cs.fontWeight >= 600);
      if (blk) line = 0;
    }
    walk(e, e.cs.fontSize, e.cs.fontWeight >= 600);
    return { min: mn, max: mx };
  }

  Layout.prototype.table = function (e, ctx, flow) {
    var cs = e.cs, W = ctx.W, self = this;
    this.flush(flow);
    if (isBreak(cs.pbBefore)) flow.brk = true;
    var mt = res0(cs.m[0], W), mb = res0(cs.m[2], W);
    var before = flow.pbFixed + Math.max(flow.pb, mt);
    flow.pb = 0; flow.pbFixed = 0;
    var prev = flow.items[flow.items.length - 1];
    if (flow.brk) { flow.items.push(this.tinyPara(ctx, true)); flow.brk = false; }
    else if (before > 0.5) {
      if (prev && prev.kind === 'p') prev.after = Math.max(prev.after, before);
      else flow.items.push({ kind: 'p', runs: [], cs: cs, before: 0, after: 0, ind: { l: ctx.indL, r: ctx.indR, first: 0, hang: 0 }, exact: before, markRp: { f: cs.fontFamily, sz: 1 } });
    }
    // rows and columns
    var head = [], body = [], foot = [], cols = [], caption = null;
    function rowOf(tr, header) { return { el: tr, header: header, cells: tr.els.filter(function (c) { return (c.tag === 'td' || c.tag === 'th') && c.cs.display !== 'none'; }) }; }
    function scan(container, target, header) {
      var loose = null;
      container.els.forEach(function (c) {
        if (c.cs.display === 'none') return;
        if (c.tag === 'tr') { loose = null; target.push(rowOf(c, header)); }
        else if (c.tag === 'td' || c.tag === 'th') { if (!loose) { loose = { el: null, header: header, cells: [] }; target.push(loose); } loose.cells.push(c); }
        else if (c.tag === 'thead') scan(c, head, true);
        else if (c.tag === 'tbody') scan(c, body, false);
        else if (c.tag === 'tfoot') scan(c, foot, false);
        else if (c.tag === 'caption') caption = c;
        else if (c.tag === 'colgroup') {
          if (c.els.length) c.els.forEach(function (col) { if (col.tag === 'col') cols.push({ el: col, span: Math.max(1, parseInt(col.attrs.span, 10) || 1) }); });
          else cols.push({ el: c, span: Math.max(1, parseInt(c.attrs.span, 10) || 1) });
        } else if (c.tag === 'col') cols.push({ el: c, span: Math.max(1, parseInt(c.attrs.span, 10) || 1) });
        else if (c.tag === 'form') scan(c, target, header);
      });
    }
    scan(e, body, false);
    if (caption) this.block(caption, ctx, flow);
    var rows = head.concat(body, foot).filter(function (r) { return r.cells.length; });
    if (!rows.length) { flow.pb = Math.max(flow.pb, mb); return; }
    var R = rows.length, grid = [], cells = [], nC = 0, r, c;
    for (r = 0; r < R; r++) grid[r] = grid[r] || [];
    for (r = 0; r < R; r++) {
      c = 0;
      rows[r].cells.forEach(function (td) {
        while (grid[r][c]) c++;
        var csn = clamp(parseInt(td.attrs.colspan, 10) || 1, 1, 1000);
        var rsn = parseInt(td.attrs.rowspan, 10);
        rsn = isNaN(rsn) ? 1 : rsn === 0 ? R - r : clamp(rsn, 1, R - r);
        var cell = { el: td, r: r, c: c, cs: csn, rs: rsn };
        for (var rr = r; rr < r + rsn; rr++) for (var cc = c; cc < c + csn; cc++) grid[rr][cc] = (rr === r && cc === c) ? cell : { cont: cell, top: rr === r };
        cells.push(cell);
        c += csn;
      });
    }
    for (r = 0; r < R; r++) nC = Math.max(nC, grid[r].length);
    // widths
    var tw = res(cs.width, W);
    var mlL = cs.m[3], mrL = cs.m[1];
    var colL = new Array(nC), colPt = new Array(nC), i;
    for (i = 0; i < nC; i++) colL[i] = null;
    var ci = 0;
    cols.forEach(function (col) { for (var k = 0; k < col.span && ci < nC; k++, ci++) if (col.el.cs.width && !col.el.cs.width.auto) colL[ci] = col.el.cs.width; });
    cells.forEach(function (cl) {
      if (cl.cs === 1 && !colL[cl.c] && cl.el.cs.width && !cl.el.cs.width.auto) {
        var L = cl.el.cs.width;
        if (L.pt != null && cl.el.cs.boxSizing !== 'border-box') {
          var ccs = cl.el.cs, ref = tw || W;
          L = { pt: L.pt + res0(ccs.pd[1], ref) + res0(ccs.pd[3], ref) };
        }
        colL[cl.c] = L;
      }
    });
    var ref = tw != null ? tw : W, known = 0, unknown = [];
    for (i = 0; i < nC; i++) {
      var v = res(colL[i], ref);
      if (v != null && v > 0) { colPt[i] = v; known += v; } else { colPt[i] = null; unknown.push(i); }
    }
    if (unknown.length) {
      var mins = [], maxs = [];
      for (i = 0; i < nC; i++) { mins[i] = 0; maxs[i] = 0; }
      cells.forEach(function (cl) {
        if (cl.cs !== 1) return;
        var m = textMetrics(cl.el), ccs = cl.el.cs, padx = res0(ccs.pd[1], W) + res0(ccs.pd[3], W) + 2;
        mins[cl.c] = Math.max(mins[cl.c], m.min + padx);
        maxs[cl.c] = Math.max(maxs[cl.c], m.max + padx);
      });
      var avail = (tw != null ? tw : W) - known, smin = 0, smax = 0;
      unknown.forEach(function (k) { mins[k] = Math.max(mins[k], 14); maxs[k] = Math.max(maxs[k], mins[k]); smin += mins[k]; smax += maxs[k]; });
      if (tw == null && smax <= avail) unknown.forEach(function (k) { colPt[k] = maxs[k]; });
      else if (tw != null && smax <= avail) unknown.forEach(function (k) { colPt[k] = maxs[k] + (avail - smax) * (smax ? maxs[k] / smax : 1 / unknown.length); });
      else if (smin >= avail) unknown.forEach(function (k) { colPt[k] = Math.max(14, avail > 0 ? mins[k] * avail / smin : mins[k]); });
      else unknown.forEach(function (k) { colPt[k] = mins[k] + (maxs[k] - mins[k]) * (avail - smin) / (smax - smin); });
    }
    var sum = 0;
    for (i = 0; i < nC; i++) sum += colPt[i];
    if (tw == null) tw = sum;
    if (sum > 0 && Math.abs(sum - tw) > 0.5) for (i = 0; i < nC; i++) colPt[i] = colPt[i] * tw / sum;
    // position
    var ind;
    if (mlL && mlL.auto && mrL && mrL.auto) ind = ctx.indL + (W - tw) / 2;
    else if (mlL && mlL.auto) ind = ctx.indL + W - tw - res0(mrL, W);
    else ind = ctx.indL + res0(mlL, W);
    // twips grid
    var colTw = colPt.map(function (x) { return Math.max(1, twip(x)); });
    var tbl = { kind: 'tbl', ind: ind, cols: colTw, rows: [], borders: cs.bd, bg: cs.background };
    this.stats.tables++;
    var tableBg = cs.background;
    for (r = 0; r < R; r++) {
      var rowEl = rows[r].el, rcs = rowEl ? rowEl.cs : null;
      var row = { cells: [], h: rcs ? res0(rcs.height, null) : 0, cant: !!(rcs && rcs.pbInside === 'avoid'), header: rows[r].header && r < head.length };
      var rowBg = (rcs && rcs.background) || (rowEl && rowEl.parent && rowEl.parent.cs && rowEl.parent.tag !== 'table' ? rowEl.parent.cs.background : null);
      for (c = 0; c < nC;) {
        var g = grid[r][c];
        if (!g) {
          var c0 = c;
          while (c < nC && !grid[r][c]) c++;
          row.cells.push({ w: sumTw(colTw, c0, c), span: c - c0, items: [this.tinyPara(ctx, false)], bd: [null, null, null, null], pad: [0, 0, 0, 0], vAlign: 'top' });
          continue;
        }
        var cell = g.cont || g;
        var info = this.cell(cell, colTw, rowBg || tableBg, g.cont ? 'continue' : (cell.rs > 1 ? 'restart' : null), ctx);
        if (!g.cont) row.h = Math.max(row.h, info.h || 0);
        row.cells.push(info);
        c += cell.cs;
      }
      tbl.rows.push(row);
    }
    flow.items.push(tbl);
    flow.pb = mb;
    if (isBreak(cs.pbAfter)) flow.brk = true;
    if (cs.pbInside === 'avoid') applyKeep(flow.items, flow.items.length - 1);
  };

  function sumTw(arr, a, b) { var s = 0; for (var i = a; i < b; i++) s += arr[i]; return s; }

  Layout.prototype.tinyPara = function (ctx, pageBreak) {
    var p = { kind: 'p', runs: [], cs: ctx.block.cs, before: 0, after: 0, ind: { l: 0, r: 0, first: 0, hang: 0 }, exact: 1, markRp: { f: ctx.block.cs.fontFamily, sz: 1 } };
    if (pageBreak) p.pageBreakBefore = true;
    return p;
  };

  Layout.prototype.cell = function (cell, colTw, bgFallback, vMerge, ctx) {
    var td = cell.el, ccs = td.cs;
    var wTw = sumTw(colTw, cell.c, cell.c + cell.cs), wPt = wTw / 20;
    var pad = [res0(ccs.pd[0], wPt), res0(ccs.pd[1], wPt), res0(ccs.pd[2], wPt), res0(ccs.pd[3], wPt)].map(function (x) { return Math.max(0, x); });
    var va = ccs.verticalAlign, vAlign = va === 'middle' ? 'center' : va === 'bottom' ? 'bottom' : 'top';
    var info = { w: wTw, span: cell.cs, vMerge: vMerge, bd: ccs.bd, pad: pad, shd: ccs.background || bgFallback || null, vAlign: vAlign, noWrap: ccs.whiteSpace === 'nowrap', h: res0(ccs.height, null) };
    var cflow = new Flow();
    var cctx = Object.create(ctx);
    cctx.W = Math.max(1, wPt - pad[1] - pad[3]); cctx.indL = 0; cctx.indR = 0;
    cctx.block = { cs: ccs, el: td, used: false, outline: null };
    cctx.bg = null; cctx.va = null; cctx.vaBase = 0; cctx.link = null; cctx.blockBg = null; cctx.li = null; cctx.list = null; cctx.listDepth = 0;
    if (vMerge !== 'continue') { this.children(td, cctx, cflow); this.flush(cflow); }
    var items = cflow.items, last = items[items.length - 1];
    if (last && last.kind === 'p' && cflow.pb > 0) last.after = Math.max(last.after, cflow.pb);
    if (!last || last.kind !== 'p') {
      var ep = { kind: 'p', runs: [], cs: ccs, before: 0, after: 0, ind: { l: 0, r: 0, first: 0, hang: 0 }, jc: ccs.textAlign, lh: ccs.lineHeight, family: ccs.fontFamily, markRp: this.runProps(ccs, { bg: null, va: null }) };
      if (last) { ep.exact = 1; ep.markRp = { f: ccs.fontFamily, sz: 1 }; }
      items.push(ep);
    }
    info.items = items;
    return info;
  };

  // ======================= 12. serialization =======================
  var BSTYLE = { solid: 'single', dashed: 'dashed', dotted: 'dotted', double: 'double', groove: 'threeDEngrave', ridge: 'threeDEmboss', inset: 'single', outset: 'single' };

  function bdrXml(tag, b, space) {
    if (!b) return '<w:' + tag + ' w:val="nil"/>';
    var st = BSTYLE[b.s] || 'single', w = b.w;
    if (st === 'double') w = w / 3;
    var sz = clamp(Math.round(w * 8), 2, 96);
    return '<w:' + tag + ' w:val="' + st + '" w:sz="' + sz + '" w:space="' + clamp(Math.round(space || 0), 0, 31) + '" w:color="' + (b.c || 'auto') + '"/>';
  }

  function Writer(layout, defaults) {
    this.L = layout; this.D = defaults; this.docPr = 0; this.rels = []; this.relByUrl = Object.create(null);
  }
  Writer.prototype.rPr = function (rp) {
    if (!rp) return '';
    var D = this.D, x = '';
    if (rp.f && rp.f !== D.f) { var f = xesc(rp.f); x += '<w:rFonts w:ascii="' + f + '" w:hAnsi="' + f + '" w:eastAsia="' + f + '" w:cs="' + f + '"/>'; }
    if (rp.b) x += '<w:b/><w:bCs/>';
    if (rp.i) x += '<w:i/><w:iCs/>';
    if (rp.caps) x += '<w:caps/>';
    if (rp.sc) x += '<w:smallCaps/>';
    if (rp.s) x += '<w:strike/>';
    if (rp.hid) x += '<w:vanish/>';
    if (rp.c && rp.c !== '000000') x += '<w:color w:val="' + rp.c + '"/>';
    if (rp.ls) x += '<w:spacing w:val="' + twip(rp.ls) + '"/>';
    var hs = Math.max(2, Math.round((rp.sz || 1) * 2));
    if (hs !== D.sz2) x += '<w:sz w:val="' + hs + '"/><w:szCs w:val="' + hs + '"/>';
    if (rp.bg && HL[rp.bg]) x += '<w:highlight w:val="' + HL[rp.bg] + '"/>';
    if (rp.u) x += '<w:u w:val="' + rp.u + '"/>';
    if (rp.bg && !HL[rp.bg]) x += '<w:shd w:val="clear" w:color="auto" w:fill="' + rp.bg + '"/>';
    if (rp.va) x += '<w:vertAlign w:val="' + (rp.va === 'super' ? 'superscript' : 'subscript') + '"/>';
    return x ? '<w:rPr>' + x + '</w:rPr>' : '';
  };
  Writer.prototype.linkRel = function (url) {
    if (!this.relByUrl[url]) { var id = 'rIdLnk' + (this.rels.length + 1); this.relByUrl[url] = id; this.rels.push({ id: id, url: url }); }
    return this.relByUrl[url];
  };
  Writer.prototype.drawing = function (r) {
    var id = ++this.docPr, img = r.img, cx = Math.max(1, Math.round(r.w * 12700)), cy = Math.max(1, Math.round(r.h * 12700));
    return '<w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="' + cx + '" cy="' + cy + '"/>' +
      '<wp:effectExtent l="0" t="0" r="0" b="0"/><wp:docPr id="' + id + '" name="Picture ' + id + '"' + (r.alt ? ' descr="' + xesc(r.alt) + '"' : '') + '/>' +
      '<wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>' +
      '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">' +
      '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="' + id + '" name="' + img.name + '"/><pic:cNvPicPr/></pic:nvPicPr>' +
      '<pic:blipFill><a:blip r:embed="' + img.rid + '"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>' +
      '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="' + cx + '" cy="' + cy + '"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>' +
      '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>';
  };
  Writer.prototype.runs = function (runs, out) {
    // merge adjacent text runs with identical formatting
    var merged = [], i;
    for (i = 0; i < runs.length; i++) {
      var r = runs[i];
      r.key = this.rPr(r.rp);
      var prev = merged[merged.length - 1];
      if (r.t !== undefined && prev && prev.t !== undefined && prev.key === r.key && prev.link === r.link) prev.t += r.t;
      else merged.push({ t: r.t, tab: r.tab, br: r.br, img: r.img ? r : null, key: r.key, link: r.link });
    }
    i = 0;
    while (i < merged.length) {
      var link = merged[i].link;
      if (link) {
        out.push('<w:hyperlink r:id="' + this.linkRel(link) + '" w:history="1">');
        while (i < merged.length && merged[i].link === link) this.run(merged[i++], out);
        out.push('</w:hyperlink>');
      } else this.run(merged[i++], out);
    }
  };
  Writer.prototype.run = function (m, out) {
    var body;
    if (m.t !== undefined) body = '<w:t xml:space="preserve">' + xesc(m.t) + '</w:t>';
    else if (m.tab) body = '<w:tab/>';
    else if (m.br) body = '<w:br/>';
    else if (m.img) body = this.drawing(m.img);
    else return;
    out.push('<w:r>' + m.key + body + '</w:r>');
  };
  Writer.prototype.para = function (p, out) {
    var x = '';
    if (p.keepNext) x += '<w:keepNext/>';
    if (p.keepLines) x += '<w:keepLines/>';
    if (p.pageBreakBefore) x += '<w:pageBreakBefore/>';
    if (p.num) x += '<w:numPr><w:ilvl w:val="' + p.num.ilvl + '"/><w:numId w:val="' + p.num.id + '"/></w:numPr>';
    if (p.bdr) {
      var b = p.bdr;
      x += '<w:pBdr>' + (b.t ? bdrXml('top', b.t, b.sp[0]) : '') + (b.l ? bdrXml('left', b.l, b.sp[3]) : '') +
        (b.b ? bdrXml('bottom', b.b, b.sp[2]) : '') + (b.r ? bdrXml('right', b.r, b.sp[1]) : '') + '</w:pBdr>';
    }
    if (p.shd) x += '<w:shd w:val="clear" w:color="auto" w:fill="' + p.shd + '"/>';
    var line = 240, rule = 'auto';
    if (p.exact != null) { line = Math.max(2, twip(p.exact)); rule = 'exact'; }
    else if (p.lh && p.lh.pt != null && p.lh.pt > 0) { line = Math.max(2, twip(p.lh.pt)); rule = p.hasImage ? 'atLeast' : 'exact'; }
    else if (p.lh && p.lh.m > 0) {
      var fac = LINE_FACTOR[String(p.family || '').toLowerCase()] || 1.15;
      line = Math.max(24, Math.round(240 * p.lh.m / fac));
    }
    x += '<w:spacing w:before="' + clamp(twip(p.before), 0, 31680) + '" w:after="' + clamp(twip(p.after), 0, 31680) + '" w:line="' + line + '" w:lineRule="' + rule + '"/>';
    var l = twip(p.ind.l), r = twip(p.ind.r), f = twip(p.ind.first || 0);
    if (p.num) x += '<w:ind w:left="' + l + '" w:right="' + r + '" w:hanging="' + twip(p.ind.hang) + '"/>';
    else if (l || r || f) x += '<w:ind w:left="' + l + '" w:right="' + r + '"' + (f > 0 ? ' w:firstLine="' + f + '"' : f < 0 ? ' w:hanging="' + (-f) + '"' : '') + '/>';
    var jc = JC[p.jc];
    if (jc && jc !== 'left') x += '<w:jc w:val="' + jc + '"/>';
    if (p.outline != null) x += '<w:outlineLvl w:val="' + p.outline + '"/>';
    x += this.rPr(p.markRp);
    out.push('<w:p>' + (x ? '<w:pPr>' + x + '</w:pPr>' : ''));
    this.runs(p.runs, out);
    out.push('</w:p>');
  };
  Writer.prototype.table = function (t, out) {
    var W = 0;
    t.cols.forEach(function (c) { W += c; });
    var x = '<w:tbl><w:tblPr><w:tblW w:w="' + W + '" w:type="dxa"/><w:tblInd w:w="' + twip(t.ind) + '" w:type="dxa"/>';
    var b = t.borders || [];
    x += '<w:tblBorders>' + bdrXml('top', b[0]) + bdrXml('left', b[3]) + bdrXml('bottom', b[2]) + bdrXml('right', b[1]) +
      '<w:insideH w:val="nil"/><w:insideV w:val="nil"/></w:tblBorders>';
    if (t.bg) x += '<w:shd w:val="clear" w:color="auto" w:fill="' + t.bg + '"/>';
    x += '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="0" w:type="dxa"/>' +
      '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/></w:tblCellMar><w:tblLook w:val="0000"/></w:tblPr><w:tblGrid>';
    t.cols.forEach(function (c) { x += '<w:gridCol w:w="' + c + '"/>'; });
    out.push(x + '</w:tblGrid>');
    var self = this;
    t.rows.forEach(function (row) {
      var tr = '';
      if (row.cant) tr += '<w:cantSplit/>';
      if (row.h > 0.5) tr += '<w:trHeight w:val="' + twip(row.h) + '" w:hRule="atLeast"/>';
      if (row.header) tr += '<w:tblHeader/>';
      out.push('<w:tr>' + (tr ? '<w:trPr>' + tr + '</w:trPr>' : ''));
      row.cells.forEach(function (cl) {
        var bd = cl.bd || [], pd = cl.pad || [0, 0, 0, 0];
        var tc = '<w:tcW w:w="' + cl.w + '" w:type="dxa"/>';
        if (cl.span > 1) tc += '<w:gridSpan w:val="' + cl.span + '"/>';
        if (cl.vMerge === 'restart') tc += '<w:vMerge w:val="restart"/>';
        else if (cl.vMerge === 'continue') tc += '<w:vMerge/>';
        tc += '<w:tcBorders>' + bdrXml('top', bd[0]) + bdrXml('left', bd[3]) + bdrXml('bottom', bd[2]) + bdrXml('right', bd[1]) + '</w:tcBorders>';
        if (cl.shd) tc += '<w:shd w:val="clear" w:color="auto" w:fill="' + cl.shd + '"/>';
        if (cl.noWrap) tc += '<w:noWrap/>';
        tc += '<w:tcMar><w:top w:w="' + twip(pd[0]) + '" w:type="dxa"/><w:left w:w="' + twip(pd[3]) + '" w:type="dxa"/>' +
          '<w:bottom w:w="' + twip(pd[2]) + '" w:type="dxa"/><w:right w:w="' + twip(pd[1]) + '" w:type="dxa"/></w:tcMar>';
        tc += '<w:vAlign w:val="' + (cl.vAlign || 'top') + '"/>';
        out.push('<w:tc><w:tcPr>' + tc + '</w:tcPr>');
        self.items(cl.items, out);
        out.push('</w:tc>');
      });
      out.push('</w:tr>');
    });
    out.push('</w:tbl>');
  };
  Writer.prototype.items = function (items, out) {
    for (var i = 0; i < items.length; i++) {
      if (items[i].kind === 'p') this.para(items[i], out); else this.table(items[i], out);
    }
  };

  function collapse(items) {
    for (var k = 0; k < items.length; k++) {
      var b = items[k], a = items[k - 1];
      if (b.kind === 'p') {
        b.before = Math.max(0, b.before); b.after = Math.max(0, b.after);
        if (b.keepNextBlock) b.keepNext = true;
        if (a && a.kind === 'p' && !b.pageBreakBefore) b.before = Math.max(0, b.before - Math.max(0, a.after));
      } else b.rows.forEach(function (r) { r.cells.forEach(function (c) { collapse(c.items); }); });
    }
  }

  function countFonts(items, acc) {
    items.forEach(function (it) {
      if (it.kind === 'p') it.runs.forEach(function (r) {
        if (r.t && r.rp) { var k = r.rp.f + '|' + Math.round(r.rp.sz * 2); acc[k] = (acc[k] || 0) + r.t.length; }
      });
      else it.rows.forEach(function (r) { r.cells.forEach(function (c) { countFonts(c.items, acc); }); });
    });
  }

  function lvlXml(fmt, ilvl, start) {
    var F = LIST_FMT[fmt] || LIST_FMT.disc, isBullet = F[0] === 'bullet';
    var text = isBullet ? F[1] : F[0] === 'none' ? '' : '%' + (ilvl + 1) + F[1];
    var x = '<w:lvl w:ilvl="' + ilvl + '"><w:start w:val="' + (start || 1) + '"/><w:numFmt w:val="' + F[0] + '"/><w:lvlText w:val="' + xesc(text) + '"/>' +
      '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="' + (720 * (ilvl + 1)) + '" w:hanging="360"/></w:pPr>';
    if (isBullet) x += '<w:rPr><w:rFonts w:ascii="' + F[2] + '" w:hAnsi="' + F[2] + '" w:hint="default"/></w:rPr>';
    return x + '</w:lvl>';
  }

  function numberingXml(L) {
    var x = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">';
    var abs = L.absByFmt;
    Object.keys(abs).forEach(function (fmt) {
      x += '<w:abstractNum w:abstractNumId="' + abs[fmt].id + '"><w:multiLevelType w:val="hybridMultilevel"/>';
      for (var i = 0; i < 9; i++) x += lvlXml(fmt, i, 1);
      x += '</w:abstractNum>';
    });
    L.lists.forEach(function (l) {
      var absId = l.abs;
      if (l.typeName && LIST_FMT[l.typeName]) {
        if (!abs[l.typeName]) { /* registered lazily below */ } else absId = abs[l.typeName].id;
      }
      x += '<w:num w:numId="' + l.numId + '"><w:abstractNumId w:val="' + absId + '"/><w:lvlOverride w:ilvl="' + Math.min(8, l.ilvl) + '"><w:startOverride w:val="' + l.start + '"/></w:lvlOverride></w:num>';
    });
    return x + '</w:numbering>';
  }

  var PAGE_SIZES = { a3: [841.89, 1190.55], a4: [595.28, 841.89], a5: [419.53, 595.28], letter: [612, 792], legal: [612, 1008], b5: [498.9, 708.66] };

  function pageSetup(sheet, opts) {
    var w = 595.28, h = 841.89, m = { t: 28.35, r: 28.35, b: 28.35, l: 28.35 }, land = false;
    sheet.page.forEach(function (decls) {
      decls.forEach(function (d) {
        if (d.p === 'size') {
          var tk = tokens(d.v.toLowerCase()), lens = [];
          tk.forEach(function (x) {
            if (PAGE_SIZES[x]) { w = PAGE_SIZES[x][0]; h = PAGE_SIZES[x][1]; }
            else if (x === 'landscape') land = true;
            else if (x === 'portrait') land = false;
            else { var L = parseLen(x, 12, 12); if (L && L.pt) lens.push(L.pt); }
          });
          if (lens.length) { w = lens[0]; h = lens[1] || lens[0]; }
        }
        var mm = /^margin-(top|right|bottom|left)$/.exec(d.p);
        if (mm) { var L2 = parseLen(d.v, 12, 12); if (L2 && L2.pt != null) m[mm[1].charAt(0)] = L2.pt; }
      });
    });
    if (opts.pageSize) {
      var ps = opts.pageSize;
      if (typeof ps === 'string' && PAGE_SIZES[ps.toLowerCase()]) { w = PAGE_SIZES[ps.toLowerCase()][0]; h = PAGE_SIZES[ps.toLowerCase()][1]; }
      else if (ps && ps.widthCm && ps.heightCm) { w = ps.widthCm * PT.cm; h = ps.heightCm * PT.cm; }
    }
    if (opts.orientation) land = String(opts.orientation).toLowerCase() === 'landscape';
    if (land && w < h) { var tmp = w; w = h; h = tmp; }
    if (!land && opts.orientation && w > h) { var tmp2 = w; w = h; h = tmp2; }
    return { w: w, h: h, m: m, landscape: w > h };
  }

  function findBody(root) {
    var stack = [root];
    while (stack.length) {
      var n = stack.shift();
      if (n.tag === 'body') return n;
      if (n.els) for (var i = 0; i < n.els.length; i++) stack.push(n.els[i]);
    }
    return null;
  }

  // fold body + single wrapper chain horizontal box into the page margins
  function foldChain(body, page, contentW) {
    var el = body, addL = 0, addR = 0, W = contentW;
    while (el) {
      var cs = el.cs, h = boxH(cs, W, false);
      if (cs.width && !cs.width.auto && el !== body) break;
      if (h.ml < 0 || h.mr < 0) break;
      el.folded = true;
      addL += h.ml + h.bl + h.pl; addR += h.mr + h.br + h.pr;
      W -= h.ml + h.bl + h.pl + h.mr + h.br + h.pr;
      var kids = el.els.filter(function (c) { return c.cs.display !== 'none'; });
      var textual = el.children.some(function (c) { return c.tag === '#text' && /\S/.test(c.text); });
      if (kids.length !== 1 || textual) break;
      var k = kids[0];
      if (k.cs.display !== 'block' || k.tag === 'p' || /^h[1-6]$/.test(k.tag) || k.tag === 'ul' || k.tag === 'ol' || k.tag === 'pre' || k.tag === 'blockquote') break;
      if (k.cs.bd.some(Boolean) || k.cs.background) break;
      el = k;
    }
    page.m.l += addL; page.m.r += addR;
  }

  // ======================= 13. driver =======================
  function normalizeOpts(o) {
    if (typeof o === 'string') { try { o = JSON.parse(o); } catch (e) { o = {}; } }
    if (!o || typeof o !== 'object') o = {};
    if (o.v && typeof o.v === 'object' && !o.pageSize && !o.marginsCm) o = o.v;
    return o;
  }

  function collectRemote(root, out) {
    (function walk(n) {
      if (n.tag === 'img' && /^https:\/\//i.test(String(n.attrs.src || '').trim())) out[String(n.attrs.src).trim()] = true;
      if (n.els) n.els.forEach(walk);
    })(root);
    return Object.keys(out);
  }

  function fetchAll(urls, done) {
    var req = null;
    try { req = typeof require === 'function' ? require('https') : null; } catch (e) { req = null; }
    var result = Object.create(null);
    if (!req || !urls.length) { done(result); return; }
    var pending = urls.length, finished = false;
    var timer = setTimeout(function () { if (!finished) { finished = true; done(result); } }, 30000);
    function one(url, hops) {
      var fin = function (val) { result[url] = val; if (--pending === 0 && !finished) { finished = true; clearTimeout(timer); done(result); } };
      try {
        req.get(url, { timeout: 15000 }, function (res) {
          if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location && hops < 3) {
            res.resume();
            var loc = res.headers.location;
            if (/^https:/i.test(loc)) { pending++; one(loc, hops + 1); result[url] = null; var redirected = loc; pending--; setTimeout(function () { result[url] = result[redirected]; }, 0); }
            else fin({ error: 'redirect to non-https ' + loc });
            return;
          }
          if (res.statusCode !== 200) { res.resume(); fin({ error: 'HTTP ' + res.statusCode + ' for ' + url }); return; }
          var chunks = [], total = 0;
          res.on('data', function (c) { chunks.push(c); total += c.length; });
          res.on('end', function () { var b = new Uint8Array(total), o = 0; chunks.forEach(function (c) { b.set(c, o); o += c.length; }); fin(b); });
          res.on('error', function (e) { fin({ error: String(e && e.message || e) }); });
        }).on('error', function (e) { fin({ error: String(e && e.message || e) }); });
      } catch (e) { fin({ error: String(e && e.message || e) }); }
    }
    urls.forEach(function (u) { one(u, 0); });
  }

  function build(html, opts, remote) {
    var t0 = Date.now(), warnings = [];
    function warn(m) { if (warnings.length < 50 && warnings.indexOf(m) < 0) warnings.push(m); }
    var root = parseHTML(html);
    ensureBody(root);
    annotate(root);
    // style sources
    var styles = [];
    (function walk(n) { if (n.tag === 'style' && n.children[0]) styles.push(n.children[0].text); if (n.tag === 'svg') warn('inline <svg> is not rendered'); if (n.els) n.els.forEach(walk); })(root);
    var pageGuess = PAGE_SIZES.a4;
    var env = { type: opts.media === 'print' ? 'print' : 'screen', widthPx: pageGuess[0] / 0.75, heightPx: pageGuess[1] / 0.75 };
    var sheet = { ua: [], author: [], page: [], seq: 0 };
    parseCSS(UA_CSS + (opts.quirks === false ? '' : QUIRKS_CSS), sheet, env, 'ua', false);
    parseCSS(FROALA_CSS, sheet, env, 'author', false);
    styles.forEach(function (css) { parseCSS(css, sheet, env, 'author', false); });
    if (opts.css) parseCSS(String(opts.css), sheet, env, 'author', false);
    computeAll(root, sheet, opts);
    (function preflight(n) {
      var cs = n.cs;
      if (cs && cs.display !== 'none') {
        if (cs.display === 'flex' || cs.display === 'inline-flex') warn('CSS flex layout is not supported: flex items stack as blocks. Use a table for side-by-side layout.');
        else if (cs.display === 'grid' || cs.display === 'inline-grid') warn('CSS grid layout is not supported: grid items stack as blocks. Use a table for side-by-side layout.');
        if (cs.float === 'left' || cs.float === 'right') warn('CSS float is not supported: floated elements stay in normal flow.');
      }
      if (n.els) n.els.forEach(preflight);
    })(root);
    var page = pageSetup(sheet, opts);
    var body = findBody(root) || root;
    if (!body.cs) body.cs = root.cs;
    var contentW = page.w - page.m.l - page.m.r;
    var userMargins = opts.marginsCm != null;
    if (opts.foldWrapper !== false && !userMargins) foldChain(body, page, contentW);
    if (userMargins) {
      var mc = opts.marginsCm, all = typeof mc === 'number' ? mc : null;
      ['top', 'right', 'bottom', 'left'].forEach(function (s) {
        var v = all != null ? all : mc[s];
        if (typeof v === 'number' && v >= 0) page.m[s.charAt(0)] = v * PT.cm;
      });
      if (opts.foldWrapper !== false) foldChain(body, { m: { l: 0, r: 0 } }, contentW); // still neutralise the wrapper indents
    }
    contentW = Math.max(36, page.w - page.m.l - page.m.r);
    var L = new Layout(opts, page, warn);
    L.remote = remote;
    var flow = new Flow();
    var ctx = { W: contentW, indL: 0, indR: 0, block: { cs: body.cs, el: body, used: false }, bg: null, va: null, vaBase: 0, link: null, blockBg: null, li: null, list: null, listDepth: 0 };
    if (body === root) L.children(root, ctx, flow); else L.block(body, ctx, flow);
    L.flush(flow);
    var items = flow.items;
    if (!items.length) items.push({ kind: 'p', runs: [], cs: body.cs, before: 0, after: 0, ind: { l: 0, r: 0, first: 0, hang: 0 }, markRp: L.runProps(body.cs, {}) });
    if (items[items.length - 1].kind === 'tbl') items.push(L.tinyPara(ctx, false));
    collapse(items);
    // document defaults = dominant font
    var acc = {};
    countFonts(items, acc);
    var best = null, bn = -1;
    Object.keys(acc).forEach(function (k) { if (acc[k] > bn) { bn = acc[k]; best = k; } });
    var D = { f: best ? best.split('|')[0] : body.cs.fontFamily, sz2: best ? +best.split('|')[1] : Math.round(body.cs.fontSize * 2) };
    var lang = opts.lang || (function () {
      var h = root.els.filter(function (e) { return e.tag === 'html'; })[0], l = h && h.attrs.lang ? h.attrs.lang : 'ro';
      l = l.replace('_', '-');
      if (!/-/.test(l)) l = { ro: 'ro-RO', en: 'en-US', de: 'de-DE', fr: 'fr-FR', it: 'it-IT', es: 'es-ES', hu: 'hu-HU', ru: 'ru-RU' }[l.toLowerCase()] || l;
      return l;
    })();
    var Wr = new Writer(L, D), out = [];
    Wr.items(items, out);
    var mT = twip(page.m.t), mB = twip(page.m.b);
    var sect = '<w:sectPr><w:pgSz w:w="' + twip(page.w) + '" w:h="' + twip(page.h) + '"' + (page.landscape ? ' w:orient="landscape"' : '') + '/>' +
      '<w:pgMar w:top="' + mT + '" w:right="' + twip(page.m.r) + '" w:bottom="' + mB + '" w:left="' + twip(page.m.l) + '" w:header="' + Math.min(708, mT) + '" w:footer="' + Math.min(708, mB) + '" w:gutter="0"/>' +
      '<w:cols w:space="708"/></w:sectPr>';
    var NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ' +
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ' +
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"';
    var docXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document ' + NS + '><w:body>' + out.join('') + sect + '</w:body></w:document>';
    // most common paragraph spacing for the Normal style
    var fam = xesc(D.f);
    var stylesXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' +
      '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="' + fam + '" w:hAnsi="' + fam + '" w:eastAsia="' + fam + '" w:cs="' + fam + '"/>' +
      '<w:sz w:val="' + D.sz2 + '"/><w:szCs w:val="' + D.sz2 + '"/><w:lang w:val="' + xesc(lang) + '" w:eastAsia="en-US" w:bidi="ar-SA"/></w:rPr></w:rPrDefault>' +
      '<w:pPrDefault><w:pPr><w:widowControl/><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>' +
      '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>' +
      '<w:style w:type="character" w:default="1" w:styleId="DefaultParagraphFont"><w:name w:val="Default Paragraph Font"/><w:uiPriority w:val="1"/><w:semiHidden/><w:unhideWhenUsed/></w:style>' +
      '<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/><w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/>' +
      '<w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>' +
      '<w:style w:type="numbering" w:default="1" w:styleId="NoList"><w:name w:val="No List"/><w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/></w:style>' +
      '</w:styles>';
    var settingsXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' +
      '<w:zoom w:percent="100"/><w:defaultTabStop w:val="720"/><w:characterSpacingControl w:val="doNotCompress"/>' +
      '<w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>' +
      '<w:compatSetting w:name="overrideTableStyleFontSizeAndJustification" w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>' +
      '<w:compatSetting w:name="enableOpenTypeFeatures" w:uri="http://schemas.microsoft.com/office/word" w:val="1"/>' +
      '<w:compatSetting w:name="doNotFlipMirrorIndents" w:uri="http://schemas.microsoft.com/office/word" w:val="1"/></w:compat></w:settings>';
    var hasNum = L.lists.length > 0;
    var rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' +
      '<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>' +
      (hasNum ? '<Relationship Id="rIdNumbering" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>' : '');
    L.media.forEach(function (m) { rels += '<Relationship Id="' + m.rid + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/' + m.name + '"/>'; });
    Wr.rels.forEach(function (l) { rels += '<Relationship Id="' + l.id + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="' + xesc(l.url) + '" TargetMode="External"/>'; });
    rels += '</Relationships>';
    var title = opts.title;
    if (!title) { var te = null; (function f(n) { if (te) return; if (n.tag === 'title') te = n; else if (n.els) n.els.forEach(f); })(root); title = te && te.children[0] ? te.children[0].text.trim() : ''; }
    var now = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
    var core = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" ' +
      'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">' +
      (title ? '<dc:title>' + xesc(title) + '</dc:title>' : '') + '<dc:creator>' + xesc(opts.author || 'PROCESIO') + '</dc:creator>' +
      '<dcterms:created xsi:type="dcterms:W3CDTF">' + now + '</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">' + now + '</dcterms:modified></cp:coreProperties>';
    var app = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" ' +
      'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>PROCESIO HTML to DOCX</Application></Properties>';
    var exts = {};
    L.media.forEach(function (m) { exts[m.ext] = m.mime; });
    var ct = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>';
    Object.keys(exts).forEach(function (e) { ct += '<Default Extension="' + e + '" ContentType="' + exts[e] + '"/>'; });
    ct += '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>' +
      '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>' +
      '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>' +
      (hasNum ? '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>' : '') +
      '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>' +
      '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>';
    var rootRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' +
      '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>' +
      '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>';
    var files = [
      { name: '[Content_Types].xml', data: utf8encode(ct) },
      { name: '_rels/.rels', data: utf8encode(rootRels) },
      { name: 'docProps/core.xml', data: utf8encode(core) },
      { name: 'docProps/app.xml', data: utf8encode(app) },
      { name: 'word/document.xml', data: utf8encode(docXml) },
      { name: 'word/styles.xml', data: utf8encode(stylesXml) },
      { name: 'word/settings.xml', data: utf8encode(settingsXml) },
      { name: 'word/_rels/document.xml.rels', data: utf8encode(rels) }
    ];
    if (hasNum) files.push({ name: 'word/numbering.xml', data: utf8encode(numberingXml(L)) });
    L.media.forEach(function (m) { files.push({ name: 'word/media/' + m.name, data: m.bytes }); });
    var zip = zipStore(files);
    var st = L.stats;
    return {
      base64: b64encode(zip),
      report: {
        ok: true, bytes: zip.length, ms: Date.now() - t0, paragraphs: st.paragraphs, tables: st.tables, images: st.images,
        links: st.links, lists: st.lists, page: { widthCm: +(page.w / PT.cm).toFixed(2), heightCm: +(page.h / PT.cm).toFixed(2),
          marginsCm: { top: +(page.m.t / PT.cm).toFixed(3), right: +(page.m.r / PT.cm).toFixed(3), bottom: +(page.m.b / PT.cm).toFixed(3), left: +(page.m.l / PT.cm).toFixed(3) } },
        defaultFont: D.f + ' ' + (D.sz2 / 2) + 'pt', warnings: warnings
      }
    };
  }

  // html: the HTML text, or { base64: '...' } when it arrives base64-encoded
  function convert(htmlOrB64, opts, isB64) {
    opts = normalizeOpts(opts);
    var html = isB64 ? decodeText(b64decode(htmlOrB64)) : String(htmlOrB64 == null ? '' : htmlOrB64);
    if (!/\S/.test(html)) throw new Error('HTML input is empty');
    var remoteUrls = opts.fetchImages === true ? collectRemote(annotateQuick(html), {}) : [];
    if (!remoteUrls.length) return build(html, opts, null);
    return new Promise(function (resolve, reject) {
      fetchAll(remoteUrls, function (remote) { try { resolve(build(html, opts, remote)); } catch (e) { reject(e); } });
    });
  }
  function annotateQuick(html) {
    var r = parseHTML(html);
    annotate(r);
    return r;
  }

  return { convert: convert, b64decode: b64decode, decodeText: decodeText, _parseHTML: parseHTML };
})();
