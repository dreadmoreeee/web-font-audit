() => {
  const vh = window.innerHeight;
  const vw = window.innerWidth;
  const sheets = [];
  const seen = new Set();

  function walk(rules, out, owner) {
    for (const rule of rules) {
      if (rule.constructor.name === "CSSFontFaceRule") {
        out.push(rule.cssText);
      } else if (rule.constructor.name === "CSSImportRule") {
        if (rule.styleSheet) handleSheet(rule.styleSheet, owner);
      } else if (rule.cssRules) {
        walk(rule.cssRules, out, owner);
      }
    }
  }

  function handleSheet(sheet, parentHref) {
    if (seen.has(sheet)) return;
    seen.add(sheet);
    const href = sheet.href || null;
    let rules = null;
    try {
      rules = sheet.cssRules;
    } catch (e) {
      rules = null;
    }
    if (rules === null) {
      sheets.push({ href: href, base: href || document.baseURI, faces: [], crossOrigin: true });
      return;
    }
    const entry = { href: href, base: href || parentHref || document.baseURI, faces: [], crossOrigin: false };
    sheets.push(entry);
    walk(rules, entry.faces, entry.base);
  }

  for (const sheet of Array.from(document.styleSheets)) handleSheet(sheet, null);
  for (const sheet of Array.from(document.adoptedStyleSheets || [])) handleSheet(sheet, null);

  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "HEAD", "TITLE", "META", "LINK", "SVG"]);
  const usage = new Map();

  function transform(text, tt) {
    if (tt === "uppercase") return text.toUpperCase();
    if (tt === "lowercase") return text.toLowerCase();
    if (tt === "capitalize") return text + text.toUpperCase();
    return text;
  }

  function add(cs, text, above) {
    text = transform(text, cs.textTransform).replace(/[\n\r\t\f\v]/g, "");
    if (!text) return;
    const key = cs.fontFamily + "|" + cs.fontWeight + "|" + cs.fontStyle;
    let item = usage.get(key);
    if (!item) {
      item = { family: cs.fontFamily, weight: cs.fontWeight, style: cs.fontStyle, chars: new Set(), above: new Set(), elements: 0 };
      usage.set(key, item);
    }
    item.elements += 1;
    for (const ch of text) {
      item.chars.add(ch);
      if (above) item.above.add(ch);
    }
  }

  function contentText(value, el) {
    if (!value || value === "none" || value === "normal") return "";
    let out = "";
    const re = /"((?:[^"\\]|\\.)*)"|attr\(\s*([\w-]+)\s*\)/g;
    let m;
    while ((m = re.exec(value)) !== null) {
      if (m[1] !== undefined) {
        out += m[1].replace(/\\([0-9a-fA-F]{1,6})\s?/g, (_, h) => String.fromCodePoint(parseInt(h, 16)))
                   .replace(/\\(.)/g, "$1");
      } else if (m[2]) {
        out += el.getAttribute(m[2]) || "";
      }
    }
    return out;
  }

  function visible(el, cs) {
    if (el.checkVisibility) return el.checkVisibility({ visibilityProperty: true, opacityProperty: false });
    return cs.display !== "none" && cs.visibility !== "hidden";
  }

  function isAbove(el) {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.top < vh && r.bottom > 0 && r.left < vw && r.right > 0;
  }

  const all = document.body ? document.body.querySelectorAll("*") : [];
  const elements = document.body ? [document.body, ...all] : [];
  for (const el of elements) {
    if (SKIP.has(el.tagName.toUpperCase())) continue;
    if (el.closest("svg")) continue;
    const cs = getComputedStyle(el);
    if (cs.display === "none") continue;
    const shown = visible(el, cs);
    let text = "";
    for (const node of el.childNodes) {
      if (node.nodeType === 3) text += node.data;
    }
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (type !== "hidden" && type !== "password") {
        text += el.value || "";
        text += el.getAttribute("placeholder") || "";
      }
    }
    if (el.tagName === "SELECT" && el.selectedOptions && el.selectedOptions[0]) {
      text += el.selectedOptions[0].textContent || "";
    }
    const above = shown && isAbove(el);
    if (shown && text.trim()) add(cs, text, above);
    for (const pseudo of ["::before", "::after"]) {
      const pcs = getComputedStyle(el, pseudo);
      const t = contentText(pcs.content, el);
      if (t && pcs.display !== "none" && pcs.visibility !== "hidden" && shown) add(pcs, t, above);
    }
  }

  const preloads = [];
  for (const link of document.querySelectorAll("link[rel~='preload' i]")) {
    if ((link.getAttribute("as") || "").toLowerCase() !== "font") continue;
    preloads.push({
      href: link.href,
      crossorigin: link.hasAttribute("crossorigin"),
      type: link.getAttribute("type") || "",
    });
  }

  const faces = [];
  if (document.fonts) {
    for (const f of document.fonts) {
      faces.push({ family: f.family, weight: f.weight, style: f.style, display: f.display, unicodeRange: f.unicodeRange, status: f.status });
    }
  }

  return {
    viewport: [vw, vh],
    sheets: sheets,
    usage: Array.from(usage.values()).map(u => ({
      family: u.family, weight: u.weight, style: u.style, elements: u.elements,
      chars: Array.from(u.chars).join(""), above: Array.from(u.above).join(""),
    })),
    preloads: preloads,
    documentFonts: faces,
  };
}
