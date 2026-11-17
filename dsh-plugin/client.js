/*
 * dsh-vocab-app client half.
 *
 * One browser-side bundle served by the DSH Web host; renders the vocabulary
 * view model produced by the host (`GET /api/vocab-app/state`) as a floating
 * overlay and sends user intents back (`POST /api/vocab-app/action`).
 *
 * Rules kept from the DSH contract:
 *  - lazy module factory, no JSX / TypeScript / relative require / npm deps
 *    (only `react` and `react/jsx-runtime` are provided by the shell);
 *  - all business state lives in the host: this file only renders `view`,
 *    echoes `rev`, and degrades gracefully when optional fields are missing;
 *  - no browser persistence, no second HTTP service, no hard-coded port/token.
 */
window.__ModuleLoader__.load({
  id: 'dsh-vocab-app',
  factory: (require) => {
    'use strict';

    const React = require('react');
    const h = React.createElement;
    const module = { exports: {} };
    const exports = module.exports;

    // ---- Protocol constants ----
    const STATE_URL = '/api/vocab-app/state';
    const ACTION_URL = '/api/vocab-app/action';
    const STYLE_ID = 'dsh-vocab-app:styles';
    const PLUGIN_ID = 'vocab-app';

    const FALLBACK_WINDOW_PRESETS = [
      { key: 'mini', label: '迷你', width: 400, height: 400 },
    ];
    const EDGE_GAP = 18;
    const VIEWPORT_PAD = 8;
    const ENTRY_ICON_SIZE = 46;
    const ENTRY_MOVE_TOLERANCE = 4;

    // app/theme.py KEYS — every theme must provide all of them.
    const THEME_KEYS = [
      'bg', 'border',
      'fg_word', 'fg_ipa', 'fg_mean', 'fg_empty', 'fg_sub', 'muted',
      'bar', 'bar_hover', 'bar_hover_bg',
      'btn_bg', 'btn_fg', 'btn_hover', 'btn_pressed',
      'rem_bg', 'rem_hover', 'rem_fg',
      'fgt_bg', 'fgt_hover', 'fgt_fg',
      'wrong_fg', 'wrong_dis',
      'link', 'close', 'close_hover',
      'opt_bg', 'opt_fg', 'opt_hover',
      'opt_ok_bg', 'opt_ok_fg', 'opt_bad_bg', 'opt_bad_fg',
      'dk_bg', 'dk_hover', 'dk_pressed', 'dk_fg', 'dk_pick', 'dk_pick_fg',
      'chip_bg', 'chip_fg', 'chip_hover', 'chip_sel', 'chip_sel_fg',
      'dock_bg', 'dock_border', 'dock_fg', 'dock_hover',
      'chart_bg', 'chart_grid', 'chart_text', 'chart_date', 'chart_line',
      'ok', 'accent',
    ];

    // app/theme.py THEMES (dark / light / sepia / green), values verbatim.
    const THEMES = {
      dark: {
        bg: '#353d49', border: '#596575',
        fg_word: '#eef1f5', fg_ipa: '#bec8d6', fg_mean: '#dee5ef',
        fg_empty: '#c0d9cc', fg_sub: '#bdc7d5', muted: '#b2bece',
        bar: '#bdc7d5', bar_hover: '#f0f3f8', bar_hover_bg: '#495568',
        btn_bg: '#434f5f', btn_fg: '#e0e7f0', btn_hover: '#4e5b6d', btn_pressed: '#3c4655',
        rem_bg: '#3e5654', rem_hover: '#48615e', rem_fg: '#d5e7dc',
        fgt_bg: '#5a4954', fgt_hover: '#65525e', fgt_fg: '#f0dae1',
        wrong_fg: '#bdc7d5', wrong_dis: '#778292',
        link: '#bdc7d5', close: '#b2bece', close_hover: '#e0e7f0',
        opt_bg: '#3c4655', opt_fg: '#dee5ef', opt_hover: '#465365',
        opt_ok_bg: '#425950', opt_ok_fg: '#d5e7dc',
        opt_bad_bg: '#604c59', opt_bad_fg: '#f0dae1',
        dk_bg: '#566a81', dk_hover: '#5d7188', dk_pressed: '#4b6078', dk_fg: '#f6f8fb',
        dk_pick: '#6d604d', dk_pick_fg: '#f8edd7',
        chip_bg: '#414d5d', chip_fg: '#d3dce8', chip_hover: '#4b586b',
        chip_sel: '#52627a', chip_sel_fg: '#edf2f8',
        dock_bg: '#424e5f', dock_border: '#788ba4', dock_fg: '#e1e8f1', dock_hover: '#4f5d71',
        chart_bg: '#2f3641', chart_grid: '#475363', chart_text: '#acb8ca',
        chart_date: '#bbc6d4', chart_line: '#abbfd9',
        ok: '#c0d9cc', accent: '#b4c7df',
      },
      light: {
        bg: '#f3f6fa', border: '#cbd4df',
        fg_word: '#293547', fg_ipa: '#596b83', fg_mean: '#34445b',
        fg_empty: '#355e62', fg_sub: '#596b83', muted: '#586981',
        bar: '#596b83', bar_hover: '#293547', bar_hover_bg: '#e0e7f0',
        btn_bg: '#e0e7f0', btn_fg: '#3c516d', btn_hover: '#d4deeb', btn_pressed: '#c9d5e4',
        rem_bg: '#dbe7e9', rem_hover: '#ccdde0', rem_fg: '#355e62',
        fgt_bg: '#eee0e4', fgt_hover: '#e6d3d9', fgt_fg: '#814d60',
        wrong_fg: '#596b83', wrong_dis: '#a2afbf',
        link: '#596b83', close: '#586981', close_hover: '#3c516d',
        opt_bg: '#eaf0f7', opt_fg: '#34445b', opt_hover: '#dce6f1',
        opt_ok_bg: '#d5e4e3', opt_ok_fg: '#355c5a',
        opt_bad_bg: '#e8d7df', opt_bad_fg: '#814d60',
        dk_bg: '#b7c8dd', dk_hover: '#adbed6', dk_pressed: '#a2b5ce', dk_fg: '#2e425d',
        dk_pick: '#dcccb4', dk_pick_fg: '#694d2c',
        chip_bg: '#e4ebf4', chip_fg: '#475d79', chip_hover: '#d5e0ed',
        chip_sel: '#cad9eb', chip_sel_fg: '#355173',
        dock_bg: '#dce5f0', dock_border: '#9baec5', dock_fg: '#415977', dock_hover: '#ccd9e9',
        chart_bg: '#f8fafd', chart_grid: '#dbe3ed', chart_text: '#5c6e86',
        chart_date: '#586b84', chart_line: '#4d6c92',
        ok: '#355e62', accent: '#4d6c92',
      },
      sepia: {
        bg: '#f3ecdf', border: '#d8c7ac',
        fg_word: '#45382b', fg_ipa: '#7a654d', fg_mean: '#554433',
        fg_empty: '#78571f', fg_sub: '#7a654d', muted: '#746149',
        bar: '#7a644c', bar_hover: '#45382b', bar_hover_bg: '#e9decb',
        btn_bg: '#e9decb', btn_fg: '#61482e', btn_hover: '#dfd0b7', btn_pressed: '#d6c5a8',
        rem_bg: '#eaddc0', rem_hover: '#e2d0aa', rem_fg: '#684b22',
        fgt_bg: '#ebd9d0', fgt_hover: '#e1c7bb', fgt_fg: '#7c4333',
        wrong_fg: '#76604a', wrong_dis: '#b6a58e',
        link: '#74583b', close: '#7a644c', close_hover: '#45382b',
        opt_bg: '#eee4d3', opt_fg: '#624b34', opt_hover: '#e6d8c0',
        opt_ok_bg: '#e6d5af', opt_ok_fg: '#684b22',
        opt_bad_bg: '#e6cdc1', opt_bad_fg: '#7c4333',
        dk_bg: '#cbbba2', dk_hover: '#beab8d', dk_pressed: '#b39e7c', dk_fg: '#45301a',
        dk_pick: '#d4bf9e', dk_pick_fg: '#644523',
        chip_bg: '#e9dfce', chip_fg: '#70563a', chip_hover: '#e1d2b9',
        chip_sel: '#dcc49b', chip_sel_fg: '#65471f',
        dock_bg: '#e8dcc5', dock_border: '#b39b77', dock_fg: '#6d5030', dock_hover: '#ddcbae',
        chart_bg: '#faf4e9', chart_grid: '#e0d3be', chart_text: '#7b6549',
        chart_date: '#7b6549', chart_line: '#886134',
        ok: '#78571f', accent: '#886134',
      },
      green: {
        bg: '#eaf0e8', border: '#cbd9c8',
        fg_word: '#314137', fg_ipa: '#5b6e5e', fg_mean: '#3d5042',
        fg_empty: '#365c43', fg_sub: '#5a6d5d', muted: '#596b5c',
        bar: '#5a6d5d', bar_hover: '#314137', bar_hover_bg: '#dce6db',
        btn_bg: '#dce6db', btn_fg: '#425b48', btn_hover: '#cfddce', btn_pressed: '#c3d3c2',
        rem_bg: '#d5e3d7', rem_hover: '#c5d8c9', rem_fg: '#365c43',
        fgt_bg: '#e9ddd6', fgt_hover: '#dfccc1', fgt_fg: '#754936',
        wrong_fg: '#536858', wrong_dis: '#a7b5a7',
        link: '#536c59', close: '#5b6e5e', close_hover: '#425b48',
        opt_bg: '#f0f4ed', opt_fg: '#3d5042', opt_hover: '#e1eadd',
        opt_ok_bg: '#cfdfd1', opt_ok_fg: '#365c43',
        opt_bad_bg: '#e1cfc5', opt_bad_fg: '#754936',
        dk_bg: '#b3c6af', dk_hover: '#a9bda5', dk_pressed: '#9eb39a', dk_fg: '#2b422e',
        dk_pick: '#d1c9a8', dk_pick_fg: '#5e4d2c',
        chip_bg: '#dfe8dc', chip_fg: '#49654e', chip_hover: '#d2dfcf',
        chip_sel: '#c7d8c6', chip_sel_fg: '#35563f',
        dock_bg: '#dce6d9', dock_border: '#9fb29c', dock_fg: '#415b46', dock_hover: '#cddcca',
        chart_bg: '#f5f8f1', chart_grid: '#dfe8d7', chart_text: '#5c715e',
        chart_date: '#5b6e5e', chart_line: '#506f59',
        ok: '#365c43', accent: '#506f59',
      },
    };
    const THEME_ORDER = ['light', 'dark', 'sepia', 'green'];
    const THEME_NAMES = { light: '亮色', dark: '暗色', sepia: '米黄', green: '护眼绿' };
    const DEFAULT_THEME = 'light';

    // app/keybindings.py defaults (PortableText canonical form).
    const DEFAULT_KEYS = {
      remember: 'Enter',
      forget: 'Space',
      choice1: '1',
      choice2: '2',
      choice3: '3',
      choice4: '4',
      unknown: 'Space',
      next: 'Enter',
    };
    const BINDING_KEYS = ['remember', 'forget', 'choice1', 'choice2', 'choice3', 'choice4', 'unknown', 'next'];

    const SCHOOL_LEVELS = [
      ['off', '关闭'],
      ['primary', '小学'],
      ['middle', '小初'],
      ['high', '小初高'],
    ];
    const CATEGORIES = [
      ['all', '全部'],
      ['learned', '已学习'],
      ['unlearned', '待学习'],
    ];
    const STRATEGY_LABELS = { conservative: '保守 · 估计减误差', estimate: '按估计', optimistic: '宽松 · 估计加误差' };
    const NAV_SCREENS = ['settings', 'books', 'catalog', 'history'];
    const SCREEN_TITLES = {
      welcome: '背单词',
      front: '背单词',
      back: '背单词',
      empty: '背单词',
      choice: '刷词 · 选择题',
      choice_back: '刷词 · 选择题',
      settings: '设置',
      books: '选择词书',
      catalog: '词书内容',
      history: '历史记录',
      quiz: '词汇量测试',
      result: '测试结果',
      summary: '本次测试已完成',
      building: '准备测试',
    };

    // ---- Small helpers (pure) ----
    function asString(value, fallback) {
      return typeof value === 'string' ? value : (typeof value === 'number' && isFinite(value) ? String(value) : (fallback || ''));
    }
    function asArray(value) {
      return Array.isArray(value) ? value : [];
    }
    function asNumber(value, fallback) {
      return typeof value === 'number' && isFinite(value) ? value : fallback;
    }
    function formatNumber(value) {
      const number = asNumber(value, null);
      if (number === null) return '';
      const rounded = Math.round(number);
      return String(Math.abs(rounded)).replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '';
    }
    function clamp(value, low, high) {
      return Math.min(Math.max(value, low), high);
    }
    function themeStyle(themeKey) {
      const theme = THEMES[themeKey] || THEMES[DEFAULT_THEME];
      const style = {};
      for (let i = 0; i < THEME_KEYS.length; i += 1) {
        const key = THEME_KEYS[i];
        style['--va-' + key.replace(/_/g, '-')] = theme[key];
      }
      return style;
    }
    function isEditableTarget(target) {
      if (!target || typeof target !== 'object') return false;
      const tag = asString(target.tagName, '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
      if (target.isContentEditable === true) return true;
      if (typeof target.closest === 'function') {
        const holder = target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"], [role="combobox"], [role="searchbox"]');
        if (holder) return true;
      }
      const role = asString(target.getAttribute ? target.getAttribute('role') : '', '');
      return role === 'textbox' || role === 'searchbox' || role === 'combobox';
    }

    // Keyboard: PortableText canonicalization / matching (see app/keybindings.py).
    const NAMED_KEYS = {
      ' ': 'Space', Spacebar: 'Space', Enter: 'Enter', Escape: 'Esc', Tab: 'Tab',
      Backspace: 'Backspace', Delete: 'Del', Insert: 'Ins', Home: 'Home', End: 'End',
      PageUp: 'PgUp', PageDown: 'PgDown',
      ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right',
    };
    const NORMALIZED_BASE = {
      RETURN: 'ENTER', ESC: 'ESCAPE', DEL: 'DELETE', INS: 'INSERT',
      PGUP: 'PAGEUP', PGDOWN: 'PAGEDOWN',
    };
    const CAPTION_MAP = {
      SPACE: '空格', ESC: 'Esc', DEL: 'Del', INS: 'Ins', TAB: 'Tab', BACKSPACE: '退格',
      UP: '↑', DOWN: '↓', LEFT: '←', RIGHT: '→', ENTER: 'Enter', RETURN: 'Enter',
      PAGEUP: 'PgUp', PAGEDOWN: 'PgDn',
    };
    function baseFromEvent(ev) {
      if (!ev) return '';
      const raw = asString(ev.key, '');
      if (!raw) return '';
      if (NAMED_KEYS[raw]) return NAMED_KEYS[raw];
      if (raw.length === 1) {
        if (/[a-z]/i.test(raw)) return raw.toUpperCase();
        return raw;
      }
      if (/^F\d{1,2}$/.test(raw)) return raw;
      return raw;
    }
    function modsFromEvent(ev) {
      const mods = [];
      if (ev && ev.ctrlKey) mods.push('ctrl');
      if (ev && ev.altKey) mods.push('alt');
      if (ev && ev.shiftKey) mods.push('shift');
      if (ev && ev.metaKey) mods.push('meta');
      return mods.sort();
    }
    function normalizeBase(base) {
      const text = asString(base, '').trim();
      if (!text) return '';
      return NORMALIZED_BASE[text.toUpperCase()] || text.toUpperCase();
    }

    function parseBinding(binding) {
      const raw = asString(binding, '').trim();
      if (!raw) return null;
      const parts = raw.split('+');
      const mods = [];
      let base = '';
      for (let i = 0; i < parts.length; i += 1) {
        const token = parts[i].trim();
        if (!token) continue;
        const lower = token.toLowerCase();
        if (lower === 'ctrl' || lower === 'control') mods.push('ctrl');
        else if (lower === 'alt') mods.push('alt');
        else if (lower === 'shift') mods.push('shift');
        else if (lower === 'meta' || lower === 'win' || lower === 'super') mods.push('meta');
        else base = token;
      }
      if (!base) return null;
      mods.sort();
      return { mods: mods, base: normalizeBase(base) };
    }
    function eventMatchesBinding(ev, binding) {
      if (!ev || ev.repeat || ev.isComposing) return false;
      const parsed = parseBinding(binding);
      if (!parsed) return false;
      const base = baseFromEvent(ev);
      if (!base || normalizeBase(base) !== parsed.base) return false;
      const mods = modsFromEvent(ev);
      if (mods.length !== parsed.mods.length) return false;
      for (let i = 0; i < mods.length; i += 1) {
        if (mods[i] !== parsed.mods[i]) return false;
      }
      return true;
    }
    function captionOf(binding) {
      const raw = asString(binding, '');
      if (!raw) return '';
      const parts = raw.split('+');
      const last = parts.pop();
      const normalized = normalizeBase(last);
      parts.push(CAPTION_MAP[normalized] || CAPTION_MAP[normalized.toUpperCase()] || last);
      return parts.join('+');
    }

    function isPlainKey(event, key) {
      if (!event) return false;
      if (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return false;
      const base = normalizeBase(baseFromEvent(event));
      if (!base) return false;
      return base === normalizeBase(key);
    }
    function mergedKeys(rawKeys) {
      const source = rawKeys && typeof rawKeys === 'object' ? rawKeys : {};
      const merged = {};
      for (let i = 0; i < BINDING_KEYS.length; i += 1) {
        const key = BINDING_KEYS[i];
        const value = asString(source[key], '');
        merged[key] = value || DEFAULT_KEYS[key];
      }
      return merged;
    }
    function keyCaption(keys, keyCaptions, action) {
      const captions = keyCaptions && typeof keyCaptions === 'object' ? keyCaptions : {};
      const text = asString(captions[action], '');
      if (text) return text;
      return captionOf(keys[action] || DEFAULT_KEYS[action] || '');
    }
    function wordOf(view) {
      const word = view && typeof view.word === 'object' && view.word ? view.word : {};
      return {
        caption: asString(word.w, ''),
        ipa: asString(word.ipa, ''),
        meaning: asString(word.meaning, ''),
      };
    }
    function optionStateClass(state) {
      const value = asString(state, '');
      if (value === 'ok' || value === 'bad' || value === 'picked') return ' is-' + value;
      return '';
    }
    function dateLabel(ts) {
      const number = asNumber(ts, null);
      if (number === null) return '';
      const date = new Date(number > 1e12 ? number : number * 1000);
      if (isNaN(date.getTime())) return '';
      const pad = (value) => (value < 10 ? '0' + value : String(value));
      return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate());
    }

    // ---- CSS (injected once, owned by ctx.effect) ----
    const CSS_TEXT = [
      '.dsh-vocab-root{position:fixed;inset:0;z-index:2147483000;pointer-events:none;  font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Segoe UI",system-ui,sans-serif;  font-size:14px;line-height:1.5;color:var(--va-fg-mean);-webkit-font-smoothing:antialiased;} .dsh-vocab-root *{box-sizing:border-box;} .dsh-vocab-root :where(button){font:inherit;color:inherit;background:none;border:0;margin:0;} .dsh-vocab-root button:focus{outline:none;}',
      '.dsh-vocab-root button:focus-visible,.dsh-vocab-root input:focus-visible{  outline:2px solid var(--va-accent);outline-offset:2px;} .dsh-vocab-root .va-sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;  overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;}',
      '.dsh-vocab-panel{position:absolute;pointer-events:auto;display:flex;flex-direction:column;  overflow:hidden;background:var(--va-bg);  border:1px solid var(--va-border);border-radius:18px;  box-shadow:0 18px 48px rgba(15,23,42,.30),0 2px 8px rgba(15,23,42,.18);}',
      '.dsh-vocab-reopen{position:absolute;pointer-events:auto;right:18px;bottom:18px;width:46px;height:46px;  display:flex;align-items:center;justify-content:center;border:1px solid var(--va-dock-border);  border-radius:14px;background:var(--va-dock-bg);color:var(--va-dock-fg);cursor:pointer;  box-shadow:0 8px 22px rgba(15,23,42,.28);} .dsh-vocab-reopen:hover{background:var(--va-dock-hover);} .va-head{display:flex;align-items:center;gap:8px;padding:8px 10px 4px 12px;flex:none;min-height:40px;}',
      '.va-head-left{display:flex;align-items:center;gap:8px;min-width:0;flex:1;} .va-title{font-size:15px;font-weight:600;color:var(--va-fg-word);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;} .va-head-right{display:flex;align-items:center;gap:4px;flex:none;}',
      '.va-iconbtn{border:1px solid var(--va-border);width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;  color:var(--va-close);cursor:pointer;font-size:16px;line-height:1;} .va-iconbtn:hover{color:var(--va-close-hover);background:var(--va-bar-hover-bg);} .va-iconbtn.va-back{display:inline-flex;align-items:center;justify-content:center;line-height:1;} .va-back svg{display:block;flex:none;} .va-linkbtn{border:1px solid var(--va-border);color:var(--va-link);font-size:12px;padding:4px 8px;border-radius:8px;cursor:pointer;white-space:nowrap;} .va-linkbtn:hover{color:var(--va-bar-hover);background:var(--va-bar-hover-bg);}',
      '.va-statusbar{padding:0 14px 6px;flex:none;color:var(--va-muted);font-size:12px;  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-height:16px;} .va-errorbar{flex:none;display:flex;align-items:center;gap:8px;margin:0 10px 6px;padding:6px 10px;  border-radius:10px;background:var(--va-opt-bad-bg);color:var(--va-opt-bad-fg);font-size:12px;} .va-errorbar.is-info{background:var(--va-chip-bg);color:var(--va-chip-fg);}',
      '.va-error-text{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;} .va-errorbar button{border:1px solid var(--va-border);flex:none;font-size:12px;padding:3px 8px;border-radius:8px;cursor:pointer;  background:var(--va-btn-bg);color:var(--va-btn-fg);} .va-errorbar button:hover{background:var(--va-btn-hover);} .va-body{flex:1;min-height:0;display:flex;flex-direction:column;padding:0 14px 12px;} .va-screen{flex:1;min-height:0;display:flex;flex-direction:column;}',
      '.va-scroll{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding:2px 2px 8px;} .va-scroll::-webkit-scrollbar{width:7px;height:7px;} .va-scroll::-webkit-scrollbar-thumb{background:var(--va-muted);border-radius:4px;opacity:.7;} .va-center{flex:1;min-height:0;display:flex;flex-direction:column;align-items:center;justify-content:center;  text-align:center;gap:8px;padding:4px 6px;overflow:auto;}',
      '.va-word{font-family:Georgia,"Times New Roman",serif;color:var(--va-fg-word);font-size:38px;  line-height:1.15;word-break:break-word;max-width:100%;} .va-ipa{font-family:"Segoe UI","Microsoft YaHei UI",sans-serif;color:var(--va-fg-ipa);font-size:18px;  min-height:22px;word-break:break-word;} .va-meaning{color:var(--va-fg-mean);font-size:20px;line-height:1.4;max-width:100%;word-break:break-word;  min-height:2.8em;animation:va-fade-in .18s ease-out;} .va-meaning.is-placeholder{visibility:hidden;}',
      '.va-grow{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;} .va-chart-wrap{flex:none;} @keyframes va-fade-in{from{opacity:0;transform:translateY(2px);}to{opacity:1;transform:none;}} .va-actions{flex:none;display:flex;gap:10px;padding-top:10px;flex-wrap:wrap;}',
      '.va-btn{flex:1;min-width:0;border:1px solid var(--va-border);min-height:46px;padding:8px 18px;border-radius:18px;cursor:pointer;display:flex;  align-items:center;justify-content:center;gap:6px;font-size:16px;  transition:background-color .12s ease,color .12s ease,opacity .12s ease;} .va-btn:disabled{opacity:.55;cursor:default;} .va-btn .va-key{font-size:11px;font-weight:400;opacity:.72;white-space:nowrap;} .va-btn-remember{background:var(--va-rem-bg);color:var(--va-rem-fg);} .va-btn-remember:hover:not(:disabled){background:var(--va-rem-hover);}',
      '.va-btn-forget{background:var(--va-btn-bg);color:var(--va-btn-fg);} .va-btn-forget:hover:not(:disabled){background:var(--va-btn-hover);} .va-btn-plain{flex:none;background:var(--va-btn-bg);color:var(--va-btn-fg);} .va-btn-plain:hover:not(:disabled){background:var(--va-btn-hover);} .va-btn-dk{background:var(--va-dk-bg);color:var(--va-dk-fg);border:1px solid var(--va-border);} .va-btn-dk:hover:not(:disabled){background:var(--va-dk-hover);}',
      '.va-brush-actions{flex-wrap:nowrap;} .va-brush-actions .va-btn{flex:1 1 0;} .va-brush-actions .va-btn-centered{gap:0;} .va-brush-actions .va-btn-centered>.va-key{margin-left:6px;} .va-btn-correct{background:transparent;color:var(--va-wrong-fg);} .va-btn-correct:hover:not(:disabled){background:transparent;color:var(--va-fg-word);} .va-btn-centered{display:flex;align-items:center;justify-content:center;} .va-btn-label{display:inline-block;text-align:center;}',
      '.va-btn-dk.is-picked{background:var(--va-dk-pick);color:var(--va-dk-pick-fg);border:1px solid var(--va-border);} .va-btn-ok{background:var(--va-chip-bg);color:var(--va-chip-fg);} .va-btn-ok:hover:not(:disabled){background:var(--va-chip-hover);color:var(--va-fg-word);} .va-options{flex:1;min-height:0;display:flex;flex-direction:column;gap:7px;padding:8px 0 4px;overflow:auto;}',
      '.va-opt{flex:none;min-width:0;min-height:40px;display:flex;align-items:center;gap:10px;text-align:left;padding:8px 14px;  border-radius:12px;background:var(--va-opt-bg);color:var(--va-opt-fg);font-size:15px;cursor:pointer;  border:1px solid var(--va-border);transition:background-color .12s ease;} .va-opt:hover:not(:disabled){background:var(--va-opt-hover);} .va-opt:disabled{cursor:default;} .va-opt.is-ok{background:var(--va-opt-ok-bg);color:var(--va-opt-ok-fg);} .va-opt.is-bad{background:var(--va-opt-bad-bg);color:var(--va-opt-bad-fg);}',
      '.va-opt.is-picked{background:var(--va-chip-sel);color:var(--va-chip-sel-fg);border:1px solid var(--va-border);} .va-opt .va-letter{flex:none;font-size:12px;font-weight:600;opacity:.8;} .va-opt .va-opt-text{flex:1;min-width:0;word-break:break-word;} .va-opt .va-key{flex:none;font-size:11px;opacity:.72;} .va-lead{margin:2px 0 6px;color:var(--va-muted);font-size:12px;} .va-section{margin:0 0 10px;} .va-section-title{margin:0 0 5px;color:var(--va-muted);font-size:12px;font-weight:600;}',
      '.va-chips{display:flex;flex-wrap:wrap;gap:6px;} .va-chip{min-height:28px;padding:4px 12px;border-radius:13px;font-size:13px;cursor:pointer;  background:var(--va-chip-bg);color:var(--va-chip-fg);border:1px solid var(--va-border);} .va-chip:hover{background:var(--va-chip-hover);color:var(--va-fg-word);} .va-chip.is-on{background:var(--va-chip-sel);color:var(--va-chip-sel-fg);} .va-chip:disabled{opacity:.5;cursor:default;} .va-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}',
      '.va-row-grow{display:flex;align-items:center;gap:8px;} .va-row-grow .va-grow{flex:1;min-width:0;} .va-muted{color:var(--va-muted);font-size:12px;} .va-strong{color:var(--va-fg-mean);font-size:13px;word-break:break-word;} .va-section-note{margin:4px 0 0;color:var(--va-muted);font-size:11px;line-height:1.5;} .va-storage{margin:6px 0 0;color:var(--va-muted);font-size:11px;line-height:1.5;word-break:break-word;} .va-main{margin:0 0 8px;}',
      '.va-main-title{margin:0 0 4px;color:var(--va-fg-sub);font-size:12px;font-weight:600;} .va-bookbtn{border:1px solid var(--va-border);display:flex;align-items:center;gap:8px;width:100%;text-align:left;padding:6px 12px;  margin:0 0 4px;border-radius:10px;background:var(--va-opt-bg);color:var(--va-opt-fg);font-size:14px;cursor:pointer;} .va-bookbtn:hover{background:var(--va-opt-hover);} .va-bookbtn.is-on{background:var(--va-chip-sel);color:var(--va-chip-sel-fg);} .va-bookbtn .va-count{margin-left:auto;font-size:12px;opacity:.8;flex:none;}',
      '.va-foot{flex:none;padding-top:8px;border-top:1px solid var(--va-border);display:flex;flex-direction:column;gap:6px;} .va-catalog{flex:1;min-height:0;display:flex;flex-direction:column;gap:6px;padding-top:2px;} .va-search-input{width:100%;min-height:30px;padding:4px 10px;border-radius:9px;border:1px solid var(--va-border);  background:var(--va-opt-bg);color:var(--va-fg-mean);font-size:13px;} .va-search-input::placeholder{color:var(--va-muted);}',
      '.va-table{flex:1;min-height:0;display:flex;flex-direction:column;border:1px solid var(--va-border);  border-radius:10px;overflow:hidden;background:var(--va-chart-bg);} .va-thead{flex:none;display:grid;grid-template-columns:minmax(92px,1.1fr) minmax(120px,2.2fr) minmax(84px,.9fr);  gap:8px;padding:6px 10px;color:var(--va-muted);font-size:11px;border-bottom:1px solid var(--va-border);  background:var(--va-bg);} .va-vlist{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;}',
      '.va-vlist-inner{position:relative;width:100%;} .va-vlist-item{position:absolute;left:0;right:0;overflow:hidden;} .va-tr{display:grid;grid-template-columns:minmax(92px,1.1fr) minmax(120px,2.2fr) minmax(84px,.9fr);  gap:8px;align-items:center;height:100%;padding:4px 10px;border-bottom:1px solid var(--va-chart-grid);  color:var(--va-fg-mean);font-size:12px;} .va-tr .va-cell{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;} .va-tr .va-cell.caption{color:var(--va-fg-word);font-weight:600;}',
      '.va-tr .va-cell.level{color:var(--va-muted);text-align:right;} .va-chart{flex:none;width:100%;height:124px;margin:0 0 8px;border:1px solid var(--va-border);  border-radius:10px;background:var(--va-chart-bg);overflow:hidden;} .va-chart-empty{display:flex;align-items:center;justify-content:center;height:100%;color:var(--va-muted);font-size:12px;} .va-hist{border:1px solid var(--va-border);border-radius:9px;margin:0 0 5px;background:var(--va-opt-bg);  color:var(--va-opt-fg);overflow:hidden;}',
      '.va-hist-row{display:flex;align-items:flex-start;margin:0 0 5px;} .va-hist-row>.va-hist{flex:1;min-width:0;margin:0;} .va-hist-row.has-delete>.va-hist{border-radius:9px 0 0 9px;} .va-hist summary{min-height:32px;padding:6px 10px;font-size:12px;cursor:pointer;list-style:none;display:flex;gap:8px;align-items:center;} .va-hist summary::-webkit-details-marker{display:none;} .va-hist summary:hover{background:var(--va-opt-hover);} .va-hist .va-hist-date{flex:none;color:var(--va-muted);} .va-hist .va-hist-value{margin-left:auto;font-weight:600;min-width:0;overflow-wrap:anywhere;} .va-hist .va-hist-body{padding:2px 10px 8px;color:var(--va-muted);font-size:11px;line-height:1.6;overflow-wrap:anywhere;} .va-hist-delete{flex:none;display:flex;align-items:center;justify-content:center;min-height:34px;padding:6px 10px;border:1px solid var(--va-border);border-left:0;border-radius:0 9px 9px 0;background:var(--va-opt-bg);color:var(--va-opt-fg);font-size:12px;line-height:1.5;white-space:nowrap;cursor:pointer;} .va-hist-delete:hover{background:var(--va-opt-hover);} .va-hist-delete:active{background:var(--va-btn-pressed);} .va-note{margin:0 0 8px;color:var(--va-muted);font-size:12px;}',
      '.va-quiz{flex:1;min-height:0;display:flex;flex-direction:column;} .va-progress{flex:none;height:6px;border-radius:3px;background:var(--va-opt-bg);overflow:hidden;margin:2px 0 10px;} .va-progress-fill{height:100%;border-radius:3px;background:var(--va-chart-line);transition:width .2s ease;}',
      '.va-quiz-word{font-family:Georgia,"Times New Roman",serif;color:var(--va-fg-word);font-size:34px;  text-align:center;line-height:1.2;word-break:break-word;padding:2px 4px 10px;} .va-quiz-actions{flex:none;display:flex;gap:8px;padding-top:8px;} .va-quiz-actions .va-btn{min-height:38px;} .va-result{flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column;align-items:center;  text-align:center;gap:6px;padding:6px 2px;}',
      '.va-big{font-family:Georgia,"Times New Roman",serif;color:var(--va-fg-word);font-size:30px;line-height:1.25;word-break:break-word;} .va-sub{color:var(--va-fg-sub);font-size:13px;line-height:1.5;white-space:pre-wrap;} .va-info{width:100%;margin:0;padding:0;list-style:none;text-align:left;font-size:12px;color:var(--va-muted);} .va-info li{padding:3px 2px;border-bottom:1px dashed var(--va-chart-grid);word-break:break-word;} .va-info li:last-child{border-bottom:0;}',
      '.va-actions-result{flex:none;width:100%;display:flex;flex-wrap:wrap;gap:6px;justify-content:center;padding-top:8px;} .va-actions-result .va-btn{flex:0 1 auto;min-height:40px;} .va-summary{flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column;align-items:center;  justify-content:center;text-align:center;gap:8px;padding:8px;} .va-summary-title{color:var(--va-fg-word);font-size:16px;font-weight:600;} .va-summary-body{color:var(--va-fg-sub);font-size:13px;line-height:1.6;white-space:pre-wrap;}',
      '.va-summary-ok{flex:none;min-width:120px;min-height:40px;padding:8px 22px;border-radius:16px;cursor:pointer;  background:var(--va-chip-bg);color:var(--va-chip-fg);font-size:15px;} .va-summary-ok:hover{background:var(--va-chip-hover);color:var(--va-fg-word);} .va-building{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;} .va-building-text{color:var(--va-fg-sub);font-size:13px;} .va-building .va-progress{width:70%;}',
      '.va-building .va-progress-fill{transition:width .26s linear;} @media (prefers-reduced-motion:reduce){.va-building .va-progress-fill{transition:none;}}',
      '.va-loading{flex:1;display:flex;align-items:center;justify-content:center;color:var(--va-muted);font-size:13px;} .va-unknown{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;text-align:center;} .va-unknown small{color:var(--va-muted);} .va-foot-row{flex:none;display:flex;gap:8px;align-items:center;padding-top:8px;} .dsh-vocab-root:focus,.dsh-vocab-panel:focus{outline:none;} .va-head{cursor:grab;}',
      '.dsh-vocab-panel.va-dragging,.dsh-vocab-panel.va-dragging .va-head{cursor:grabbing;user-select:none;} .va-ipa-block{width:100%;text-align:center;min-height:22px;} .dsh-vocab-reopen{cursor:grab;} .dsh-vocab-reopen.is-dragging{cursor:grabbing;} .va-danger{background:var(--va-opt-bad-bg);color:var(--va-opt-bad-fg);} .va-danger:hover{background:var(--va-fgt-hover);color:var(--va-fgt-fg);}',
      '.va-opt-unknown{justify-content:center;text-align:center;} .va-unknown-label{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-width:0;} .va-opt-unknown.is-picked{background:var(--va-dk-pick);color:var(--va-dk-pick-fg);} .va-summary-ok{border:1px solid var(--va-border);}',
      '.va-books-lead{flex:none;margin:0 0 6px;} .va-books-list{padding-top:0;} .va-books-stats{flex:none;min-width:0;margin:4px 0 0;overflow-wrap:anywhere;} .va-books-toolbar{flex:none;display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding-top:8px;} .va-books-order{display:flex;align-items:center;gap:6px;flex:none;} .va-books-spacer{flex:1;min-width:0;} .va-books-actions{display:flex;align-items:center;justify-content:flex-end;gap:6px;flex-wrap:wrap;min-width:0;max-width:100%;} .va-books-actions .va-btn{height:36px;min-height:36px;min-width:0;flex:0 1 auto;padding:6px 10px;font-size:13px;white-space:nowrap;border-radius:12px;}',
      '.va-mini .va-body{padding:0 10px 10px;} .va-mini .va-head{padding-left:10px;} .va-mini .va-btn{min-width:0;padding:7px 10px;font-size:14px;gap:6px;} .va-mini .va-btn .va-key{font-size:10px;} .va-mini .va-options{gap:6px;padding:4px 0;} .va-mini .va-opt{min-height:36px;padding:6px 10px;font-size:14px;gap:8px;} .va-mini .va-quiz-word{flex:none;font-size:28px;padding:2px 4px 6px;} .va-mini .va-word{font-size:32px;} .va-mini .va-meaning{font-size:17px;} .va-mini .va-center,.va-mini .va-summary{justify-content:safe center;} .va-mini .va-lead{font-size:12px;overflow-wrap:anywhere;}',
      '.va-mini .va-thead,.va-mini .va-tr{grid-template-columns:minmax(64px,1fr) minmax(90px,1.8fr) minmax(62px,.8fr);gap:6px;padding-left:8px;padding-right:8px;} .va-mini .va-books-toolbar{padding-top:6px;} .va-mini .va-books-order{gap:4px;} .va-mini .va-books-actions .va-btn{padding:6px 8px;font-size:13px;} .va-mini .va-search-input{min-width:0;width:100%;}',
    ].join('\n');

    // Deterministic SVG icon (same motif as assets/vocab-card.svg, no network).
    function brandIcon(size) {
      const px = asNumber(size, 18);
      return h('svg', { width: px, height: px, viewBox: '0 0 256 256', 'aria-hidden': 'true', focusable: 'false' },
        h('rect', { x: 8, y: 8, width: 240, height: 240, rx: 54, fill: 'var(--va-dock-bg)', stroke: 'var(--va-dock-border)', strokeWidth: 6 }),
        h('rect', { x: 64, y: 46, width: 128, height: 150, rx: 16, fill: 'var(--va-dock-fg)', opacity: 0.9 }),
        h('path', { d: 'M84 144 L109 80 H123 L149 144 H135 L130 129 H102 L97 144 Z M106 117 H126 L116 89 Z', fill: 'var(--va-dock-bg)' }),
        h('path', { d: 'M160 46 H176 V88 L168 81 L160 88 Z', fill: 'var(--va-accent)' })
      );
    }
    function installStyles() {
      if (typeof document === 'undefined' || !document.head) return function noop() {};
      const previous = document.getElementById(STYLE_ID);
      if (previous && previous.parentNode) previous.parentNode.removeChild(previous);
      const tag = document.createElement('style');
      tag.id = STYLE_ID;
      tag.setAttribute('data-plugin', PLUGIN_ID);
      tag.textContent = CSS_TEXT;
      document.head.appendChild(tag);
      return function disposeStyles() {
        const parent = tag.parentNode;
        if (!parent) return;
        if (typeof parent.removeChild === 'function') parent.removeChild(tag);
        else if (typeof tag.remove === 'function') tag.remove();
      };
    }

    // ---- Pure view renderers: view model -> React element tree ----
    function buttonEl(label, options) {
      const opts = options || {};
      const children = [label];
      if (opts.keyHint) {
        children.push(h('span', { className: 'va-key', 'aria-hidden': 'true' }, '[' + opts.keyHint + ']'));
      }
      return h('button', {
        type: 'button',
        key: opts.key,
        className: ('va-btn ' + (opts.className || 'va-btn-plain')).trim(),
        onClick: opts.onClick,
        style: opts.style,
        disabled: opts.disabled === true,
        tabIndex: opts.tabIndex,
        title: opts.title || undefined,
        'aria-label': opts.ariaLabel || asString(label, ''),
        'aria-pressed': opts.pressed === undefined ? undefined : (opts.pressed ? 'true' : 'false'),
      }, children);
    }
    function chipEl(label, options) {
      const opts = options || {};
      return h('button', {
        type: 'button',
        key: opts.key,
        className: ('va-chip' + (opts.on ? ' is-on' : '') + (opts.className ? ' ' + opts.className : '')).trim(),
        onClick: opts.onClick,
        style: opts.style,
        disabled: opts.disabled === true,
        title: opts.title || undefined,
        'aria-label': opts.ariaLabel || asString(label, ''),
        'aria-pressed': opts.on ? 'true' : 'false',
      }, label);
    }
    function iconButtonEl(label, glyph, onClick, key) {
      return h('button', {
        type: 'button',
        key: key,
        className: 'va-iconbtn',
        onClick: onClick,
        title: label,
        'aria-label': label,
      }, glyph);
    }
    function linkButtonEl(label, onClick, ariaLabel, key) {
      return h('button', {
        type: 'button',
        key: key,
        className: 'va-linkbtn',
        onClick: onClick,
        'aria-label': ariaLabel || label,
      }, label);
    }
    function sectionTitleEl(text) {
      return h('h3', { className: 'va-section-title' }, text);
    }
    function noteEl(text, className) {
      return h('p', { className: className || 'va-note' }, text);
    }
    function hintFor(view, action) {
      return keyCaption(mergedKeys(view && view.keys), view && view.keyCaptions, action);
    }

    // Host-provided button copy wins; the literals are only a last-resort fallback.
    function labelFor(view, key, fallback) {
      const labels = view && view.labels && typeof view.labels === 'object' ? view.labels : {};
      return asString(labels[key], '') || fallback;
    }
    function renderStatusBar(view) {
      const status = asString(view && view.status, '');
      if (!status) return null;
      return h('div', { className: 'va-statusbar', role: 'status', 'aria-live': 'polite', title: status }, status);
    }
    function renderHeader(view, api) {
      const screen = asString(view && view.screen, '');
      const learning = ['front', 'back', 'choice', 'choice_back'].indexOf(screen) >= 0;
      const hostTitle = screen === 'welcome' ? '' : asString(view && view.title, '');
      const title = screen === 'building' ? '' : (learning
        ? asString(view && view.studyStatus, '')
        : (hostTitle || SCREEN_TITLES[screen] || '背单词'));
      const nav = NAV_SCREENS.indexOf(screen) >= 0;
      const calls = typeof api.send === 'function' ? api.send : function noopSend() {};
      const studyScreens = ['front', 'back', 'empty', 'choice', 'choice_back'];
      const leftControl = nav
        ? h('button', {
          type: 'button',
          className: 'va-iconbtn va-back',
          onClick: () => calls('back', {}),
          title: '返回',
          'aria-label': '返回上一页',
        }, h('svg', { width: 18, height: 18, viewBox: '0 0 24 24', 'aria-hidden': 'true', focusable: 'false' },
          h('path', { d: 'M15 5 L8 12 L15 19', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' })))
        : (studyScreens.indexOf(screen) >= 0
          ? iconButtonEl('设置', '\u2699', () => calls('settings', {}), 'gear')
          : null);
      const right = [];
      if (screen === 'quiz' && view.canPause !== false) {
        right.push(linkButtonEl(labelFor(view, 'pause', '暂停并退出'), () => calls('quizPause', {}), '暂停测试并退出', 'pause'));
      }
      right.push(iconButtonEl('关闭浮层', '\u2715', () => {
        if (api && typeof api.hide === 'function') api.hide();
      }, 'close'));
      return h('header', {
        className: 'va-head',
        onPointerDown: (event) => {
          if (api && typeof api.beginDrag === 'function') api.beginDrag(event);
        },
      },
      h('div', { className: 'va-head-left' }, leftControl, h('span', { className: 'va-title' }, title)),
      h('div', { className: 'va-head-right' }, right)
      );
    }

    // ---------- welcome ----------
    function screenWelcome(view, api) {
      const bookCount = asNumber(view.bookCount, null);
      const totalWords = asNumber(view.totalWords, null);
      const statsLine = (bookCount !== null && totalWords !== null && (bookCount > 0 || totalWords > 0))
        ? '词库共 ' + formatNumber(bookCount) + ' 本词书 · ' + formatNumber(totalWords) + ' 个词条'
        : '';
      const title = asString(view.title, '') || '先测一下词汇量？';
      const body = asString(view.body, '') || '词频分层与自适应识别测试。结果仅供参考，不改变学习队列。';
      const tip = asString(view.tip, '') || '40–80 题 · 可暂停续测 · 参数未标定';
      return h('div', { className: 'va-screen va-welcome' },
        h('div', { className: 'va-center' },
          h('div', { className: 'va-summary-title' }, title),
          h('div', { className: 'va-sub' }, body),
          h('div', { className: 'va-muted' }, tip),
          statsLine ? h('div', { className: 'va-muted' }, statsLine) : null,
          view.hasProgress === true ? h('div', { className: 'va-muted' }, '已检测到学习进度，测试不会清空它。') : null
        ),
        renderActionBlock(view.actions, api, {
          label: '测试一下',
          onClick: () => api.send('quizStart', { fresh: true }),
        })
      );
    }

    // ---------- brush study: front / back / empty ----------
    function studyCard(view, showMeaning) {
      const word = wordOf(view);
      return h('div', { className: 'va-center' },
        h('div', { className: 'va-word' }, word.caption || '（无词条）'),
        word.ipa ? h('div', { className: 'va-ipa' }, word.ipa) : h('div', { className: 'va-ipa', 'aria-hidden': 'true' }),
        h('div', {
          className: 'va-meaning' + (showMeaning ? '' : ' is-placeholder'),
          style: { whiteSpace: 'pre-wrap' }, 'aria-hidden': showMeaning ? undefined : 'true',
        }, showMeaning ? word.meaning : '')
      );
    }
    function screenFront(view, api) {
      return h('div', { className: 'va-screen va-study' },
        studyCard(view, false),
        h('div', { className: 'va-actions' },
          buttonEl(labelFor(view, 'forget', '不认识'), {
            key: 'front-forget',
            className: 'va-btn-forget',
            keyHint: hintFor(view, 'forget'),
            ariaLabel: labelFor(view, 'forget', '不认识'),
            onClick: () => api.send('answer', { action: 'forget' }),
            tabIndex: -1,
          }),
          buttonEl(labelFor(view, 'remember', '认识'), {
            key: 'front-remember',
            className: 'va-btn-remember',
            keyHint: hintFor(view, 'remember'),
            ariaLabel: labelFor(view, 'remember', '认识'),
            onClick: () => api.send('answer', { action: 'remember' }),
            tabIndex: -1,
          })
        )
      );
    }
    // Correction is one-way and host-authorized: forgotten answers never
    // render a correction placeholder. Their only action is a full-width next.
    function screenBack(view, api) {
      const canCorrect = view.canCorrect === true;
      const nextLabel = labelFor(view, 'next', '下一个');
      return h('div', { className: 'va-screen va-study' },
        studyCard(view, true),
        h('div', { className: 'va-actions va-brush-actions' + (canCorrect ? '' : ' is-single') },
          canCorrect ? buttonEl(labelFor(view, 'wrong', '选错了'), {
            key: 'back-correct',
            className: 'va-btn-correct',
            keyHint: '空格',
            ariaLabel: labelFor(view, 'wrong', '选错了'),
            onClick: () => api.send('correct', {}),
            tabIndex: -1,
          }) : null,
          buttonEl(canCorrect ? nextLabel : h('span', { className: 'va-btn-label' }, nextLabel), {
            key: 'back-next',
            className: 'va-btn-remember va-btn-centered',
            keyHint: canCorrect ? hintFor(view, 'next') : '空格 / Enter',
            ariaLabel: nextLabel,
            onClick: () => api.send('next', {}),
            tabIndex: -1,
          })
        )
      );
    }
    function screenEmpty(view, api) {
      return h('div', { className: 'va-screen va-study' },
        studyCard(view, true),
        h('div', { className: 'va-actions' },
          buttonEl(labelFor(view, 'next', '检查复习'), {
            key: 'empty-next',
            className: 'va-btn-remember',
            keyHint: hintFor(view, 'next'),
            ariaLabel: labelFor(view, 'next', '检查复习'),
            onClick: () => api.send('next', {}),
            tabIndex: -1,
          })
        )
      );
    }

    // ---------- brush study: choice / choice_back ----------
    function screenChoice(view, api) {
      const screen = asString(view.screen, 'choice');
      const word = wordOf(view);
      const options = asArray(view.options);
      const locked = view.locked === true;
      const unavailable = view.unavailable === true;
      const answered = locked || screen === 'choice_back';
      const letterFor = function (index) {
        return index >= 0 && index < 26 ? String.fromCharCode(65 + index) : '?';
      };
      const optionNodes = options.length
        ? options.map(function (option, position) {
          const raw = option && typeof option === 'object' ? option : {};
          const index = asNumber(raw.index, position);
          const text = asString(raw.text, '');
          const state = asString(raw.state, '');
          const keyHint = keyCaption(mergedKeys(view.keys), view.keyCaptions, 'choice' + (index + 1));
          return h('button', {
            type: 'button',
            key: 'opt-' + index,
            className: 'va-opt' + optionStateClass(state),
            disabled: locked || screen === 'choice_back',
            onClick: () => api.send('choice', { index: index }),
            'aria-label': '选项 ' + letterFor(index) + ' ' + text,
            'aria-pressed': (state === 'ok' || state === 'bad' || state === 'picked') ? 'true' : undefined,
            tabIndex: -1,
          },
          h('span', { className: 'va-letter' }, letterFor(index)),
          h('span', { className: 'va-opt-text' }, text || '（空选项）'),
          h('span', { className: 'va-key', 'aria-hidden': 'true' }, '[' + keyHint + ']')
          );
        })
        : [h('p', { className: 'va-note', key: 'no-options' },
          unavailable ? '当前没有可用的四选一题目，可跳过' : '暂无选项')];
      const bottom = answered
        ? buttonEl(labelFor(view, 'next', '下一个'), {
          key: 'choice-next',
          className: 'va-btn-remember',
          keyHint: (screen === 'choice_back' || unavailable) ? '空格 / Enter' : hintFor(view, 'next'),
          ariaLabel: labelFor(view, 'next', '下一个'),
          onClick: () => api.send('next', {}),
          tabIndex: -1,
        })
        : buttonEl(labelFor(view, 'dontknow', '不认识'), {
          key: 'choice-dontknow',
          className: 'va-btn-dk',
          keyHint: hintFor(view, 'unknown'),
          ariaLabel: labelFor(view, 'dontknow', '不认识'),
          onClick: () => api.send('dontknow', {}),
          tabIndex: -1,
        });
      return h('div', { className: 'va-screen va-choice' },
        h('div', { className: 'va-quiz-word' }, word.caption || '（无词条）'),
        h('div', { className: 'va-ipa va-ipa-block' }, word.ipa || ''),
        h('div', { className: 'va-options' }, optionNodes),
        h('div', { className: 'va-actions' }, bottom)
      );
    }

    // ---------- settings ----------
    function screenSettings(view, api) {
      const theme = asString(view.theme, DEFAULT_THEME);
      const studyMode = asString(view.studyMode, 'brush');
      const schoolLevel = asString(view.school, 'off');
      const book = view.book && typeof view.book === 'object' ? view.book : {};
      const quiz = view.quiz && typeof view.quiz === 'object' ? view.quiz : {};
      const hasSession = quiz.hasSession === true;
      const days = asNumber(quiz.remainingDays, null);
      const themeChips = THEME_ORDER.map(function (key) {
        return chipEl(THEME_NAMES[key] || key, {
          key: 'theme-' + key,
          on: key === theme,
          onClick: () => api.send('theme', { key: key }),
          ariaLabel: '背景主题：' + (THEME_NAMES[key] || key),
        });
      });
      const modeChips = [['brush', '刷词模式'], ['choice', '选择题模式']].map(function (pair) {
        return chipEl(pair[1], {
          key: 'mode-' + pair[0],
          on: studyMode === pair[0],
          onClick: () => api.send('studyMode', { key: pair[0] }),
          ariaLabel: '学习模式：' + pair[1],
        });
      });
      const schoolChips = SCHOOL_LEVELS.map(function (pair) {
        return chipEl(pair[1], {
          key: 'school-' + pair[0],
          on: schoolLevel === pair[0],
          onClick: () => api.send('school', { level: pair[0] }),
          ariaLabel: '已认识词汇范围：' + pair[1],
        });
      });
      const bookPath = asString(book.path, '') || asString(book.name, '') || '未选择词书';
      const learned = asNumber(book.num, null);
      const bookTotal = asNumber(book.total, null);
      const bookNumText = asString(book.numText, '')
        || (learned !== null && bookTotal !== null
          ? '已学 ' + formatNumber(learned) + ' / ' + formatNumber(bookTotal)
          : '');
      return h('div', { className: 'va-screen va-settings-screen' },
        h('div', { className: 'va-scroll' },
          h('section', { className: 'va-section', key: 'theme' },
            sectionTitleEl('背景'),
            h('div', { className: 'va-chips' }, themeChips)
          ),
          h('section', { className: 'va-section', key: 'mode' },
            sectionTitleEl('学习模式'),
            h('div', { className: 'va-chips' }, modeChips)
          ),
          h('section', { className: 'va-section', key: 'school' },
            sectionTitleEl('已认识词汇范围—开启后跳过对应词汇的学习'),
            h('div', { className: 'va-chips' }, schoolChips)
          ),
          h('section', { className: 'va-section', key: 'book' },
            sectionTitleEl('词书'),
            h('div', { className: 'va-row-grow' },
              h('span', { className: 'va-strong va-grow', title: bookPath }, bookPath),
              bookNumText ? h('span', { className: 'va-muted' }, bookNumText) : null,
              chipEl('更换', {
                key: 'change-book',
                onClick: () => api.send('books', { from: 'settings' }),
                ariaLabel: '更换词书',
              })
            )
          ),
          h('section', { className: 'va-section', key: 'quiz' },
            sectionTitleEl('词汇量测试'),
            h('div', { className: 'va-chips' },
              chipEl('历史记录', { key: 'history', onClick: () => api.send('history', {}), ariaLabel: '历史记录' }),
              hasSession
                ? chipEl(days !== null && days > 0 ? '继续上次测试（剩余' + days + '天）' : '继续上次测试', {
                  key: 'continue-quiz',
                  onClick: () => api.send('quizStart', { fresh: false }),
                  ariaLabel: '继续上次词汇量测试',
                })
                : null,
              chipEl('开始新的测试', {
                key: 'new-quiz',
                onClick: () => api.send('quizStart', { fresh: true }),
                ariaLabel: '开始新的词汇量测试',
              })
            )
          ),
          asString(view.storageNote, '') || asString(view.version, '')
            ? h('p', { className: 'va-storage' },
              (asString(view.version, '') ? 'V' + asString(view.version, '') : '')
              + (asString(view.storageNote, '') ? '\n' + asString(view.storageNote, '') : ''))
            : null
        )
      );
    }

    // ---------- books ----------
    function bookRowFromItem(item) {
      const raw = item && typeof item === 'object' ? item : {};
      return {
        kind: asString(raw.kind, 'book') || 'book',
        id: asString(raw.id, ''),
        text: asString(raw.name, '') || asString(raw.display, '') || asString(raw.text, '') || asString(raw.id, ''),
        count: asNumber(raw.count, null),
      };
    }

    // CONTRACT §4 minimum shape (mains -> groups) folded into the host's row
    // shape, so one renderer handles old and new hosts.
    function booksRowsFromMains(view) {
      const mains = asArray(view.mains);
      const rows = [];
      if (mains.length) {
        mains.forEach(function (main) {
          const rawMain = main && typeof main === 'object' ? main : {};
          const groups = asArray(rawMain.groups);
          if (!groups.length) {
            if (asString(rawMain.id, '')) rows.push(bookRowFromItem(rawMain));
            return;
          }
          rows.push({ kind: 'section', text: asString(rawMain.name, '') });
          groups.forEach(function (group) {
            const rawGroup = group && typeof group === 'object' ? group : {};
            const nested = asArray(rawGroup.books).length ? asArray(rawGroup.books) : asArray(rawGroup.items);
            if (nested.length) {
              rows.push({ kind: 'section', text: asString(rawGroup.name, '') });
              nested.forEach(function (entry) { rows.push(bookRowFromItem(entry)); });
            } else {
              rows.push(bookRowFromItem(rawGroup));
            }
          });
        });
        return rows;
      }
      const flat = asArray(view.books).length ? asArray(view.books) : asArray(view.items);
      flat.forEach(function (item) { rows.push(bookRowFromItem(item)); });
      return rows;
    }

    // Host rows shape (preferred): kind:'section'|'main'|'group'|'book'|'union'.
    function screenBooks(view, api) {
      const rows = asArray(view.rows).length ? asArray(view.rows) : booksRowsFromMains(view);
      const selected = asString(view.selected, '');
      const order = (asString(api.pendingOrder, '') || asString(view.order, 'seq')) === 'shuffle' ? 'shuffle' : 'seq';
      const navLevel = asNumber(view.navLevel, 1);
      const lead = asString(view.lead, '') || (navLevel === 1 ? '选择主类' : '选择词书');
      const stats = view.stats && typeof view.stats === 'object' ? view.stats : {};
      const total = asNumber(stats.total, null);
      const learned = asNumber(stats.learned, null);
      const statLine = asString(view.bookStat, '') || (selected && learned !== null && total !== null
        ? '已学 ' + formatNumber(learned) + ' / ' + formatNumber(total) + ' 词'
        : '');
      const nodes = rows.length ? rows.map(function (row, index) {
        const raw = row && typeof row === 'object' ? row : {};
        const kind = asString(raw.kind, 'book');
        const id = asString(raw.id, '');
        const text = asString(raw.text, '') || asString(raw.name, '') || id || '未命名';
        const count = asNumber(raw.count, null);
        const countText = asString(raw.countText, '');
        if (kind === 'section') {
          return h('div', { className: 'va-main-title', key: 'bsec-' + index }, text);
        }
        const isOn = id !== '' && id === selected;
        const isBranch = kind === 'main' || kind === 'group';
        return h('button', {
          type: 'button',
          key: 'brow-' + index,
          className: 'va-bookbtn' + (isOn ? ' is-on' : ''),
          onClick: () => api.send('book', { id: id }),
          'aria-pressed': isOn ? 'true' : undefined,
          'aria-label': (isBranch ? '进入 ' : '选择 ') + text,
          title: text,
        },
        h('span', { className: 'va-grow' }, text),
        !isBranch && (countText || count !== null) ? h('span', { className: 'va-count' }, countText || (formatNumber(count) + ' 词')) : null,
        isBranch ? h('span', { className: 'va-count', 'aria-hidden': 'true' }, '\u203a') : null
        );
      }) : [h('p', { className: 'va-note', key: 'no-books' }, '宿主还没有返回词书列表。')];
      return h('div', { className: 'va-screen va-books-screen' },
        h('p', { className: 'va-lead va-books-lead' }, lead),
        h('div', { className: 'va-scroll va-books-list' }, nodes),
        statLine ? h('p', { className: 'va-muted va-books-stats', title: statLine }, statLine) : null,
        h('div', { className: 'va-books-toolbar' },
          h('div', { className: 'va-books-order' },
            h('span', { className: 'va-muted' }, '词序'),
            chipEl('顺序', {
              key: 'order-seq', on: order === 'seq', ariaLabel: '词序：顺序',
              onClick: () => {
                if (typeof api.setOrder === 'function') api.setOrder('seq');
                else api.send('book', { order: 'seq' });
              },
            }),
            chipEl('乱序', {
              key: 'order-shuffle', on: order === 'shuffle', ariaLabel: '词序：乱序',
              onClick: () => {
                if (typeof api.setOrder === 'function') api.setOrder('shuffle');
                else api.send('book', { order: 'shuffle' });
              },
            })
          ),
          h('span', { className: 'va-books-spacer', 'aria-hidden': 'true' }),
          h('div', { className: 'va-books-actions' },
            buttonEl('浏览词条', {
              key: 'catalog-open', className: 'va-btn-plain',
              style: { height: '36px', minHeight: '36px', minWidth: 0 },
              onClick: () => api.send('catalog', {}), disabled: !selected,
              ariaLabel: '浏览当前词书内容',
            }),
            buttonEl('用这本书开始', {
              key: 'start-book', className: 'va-btn-remember',
              style: { height: '36px', minHeight: '36px', minWidth: 0 },
              disabled: !selected || view.canStart === false,
              ariaLabel: '用这本书开始学习',
              onClick: () => {
                if (typeof api.startBook === 'function') api.startBook();
                else api.send('start', {});
              },
            })
          )
        )
      );
    }

    // ---------- catalog ----------
    function screenCatalog(view, api) {
      const book = view.book && typeof view.book === 'object' ? view.book : {};
      const rows = asArray(view.rows);
      const counts = view.counts && typeof view.counts === 'object' ? view.counts : {};
      const filter = asString(view.filter, 'all') || 'all';
      const serverQuery = asString(view.query, '');
      const draft = api.catalogDraft === undefined || api.catalogDraft === null
        ? serverQuery
        : asString(api.catalogDraft, '');
      const query = draft;
      const bookLine = (asString(book.path, '') || asString(book.name, '') || '当前词书')
        + (asNumber(book.count, null) !== null ? ' · ' + formatNumber(book.count) + ' 词' : '');
      const titleText = asString(view.title, '');
      const hasBookPath = Boolean(asString(book.path, '') || asString(book.name, ''));
      const leadLine = hasBookPath ? bookLine : (titleText || bookLine);
      const categories = asArray(view.categories).length
        ? asArray(view.categories)
        : CATEGORIES.map(function (pair) { return { key: pair[0], label: pair[1] }; });
      const filterChips = categories.map(function (category, index) {
        const raw = category && typeof category === 'object' ? category : {};
        const key = asString(raw.key, '') || (CATEGORIES[index] ? CATEGORIES[index][0] : 'all');
        const label = asString(raw.label, '') || (CATEGORIES[index] ? CATEGORIES[index][1] : key);
        const count = asNumber(raw.count, asNumber(counts[key], 0));
        return chipEl(label + ' ' + formatNumber(count), {
          key: 'filter-' + key,
          on: filter === key,
          onClick: () => api.send('catalogFilter', { category: key, query: query }),
          ariaLabel: '筛选：' + label,
        });
      });
      const rowNodes = rows.map(function (row, index) {
        const raw = row && typeof row === 'object' ? row : {};
        const caption = asString(raw.caption, '') || asString(raw.key, '');
        const meaning = asString(raw.meaning, '');
        const level = asNumber(raw.level, null);
        const memory = asString(raw.memory, '') || (level !== null ? 'Lv' + level : '待学习');
        return h('div', { className: 'va-tr', key: 'row-' + index, role: 'listitem' },
          h('span', { className: 'va-cell caption', title: caption }, caption),
          h('span', { className: 'va-cell meaning', title: meaning }, meaning),
          h('span', { className: 'va-cell level', title: memory }, memory)
        );
      });
      return h('div', { className: 'va-screen va-catalog' },
        h('p', { className: 'va-lead', title: leadLine }, leadLine),
        h('div', { className: 'va-chips' }, filterChips),
        h('input', {
          type: 'search',
          className: 'va-search-input',
          value: draft,
          placeholder: '搜索单词、词组或释义',
          maxLength: 200,
          'aria-label': '搜索单词、词组或释义',
          onChange: (event) => {
            if (typeof api.onCatalogQuery === 'function') api.onCatalogQuery(event.target.value);
          },
          onKeyDown: (event) => {
            if (event.key === 'Enter' && typeof api.commitCatalogQuery === 'function') {
              event.preventDefault();
              api.commitCatalogQuery();
            }
          },
        }),
        h('div', { className: 'va-table' },
          h('div', { className: 'va-thead', 'aria-hidden': 'true' },
            h('span', null, '单词 / 词组'),
            h('span', null, '释义'),
            h('span', { style: { textAlign: 'right' } }, '记忆等级')
          ),
          rows.length
            ? h(VirtualList, {
              items: rowNodes,
              rowHeight: 42,
              ariaLabel: '词书内容列表，共 ' + rows.length + ' 条',
              emptyText: '没有符合条件的词条',
            })
            : h('div', { className: 'va-chart-empty', style: { flex: '1' } }, '没有符合条件的词条')
        )
      );
    }

    // ---------- shared line chart (history + result) ----------
    function renderChartBlock(points, titleText) {
      const data = [];
      asArray(points).forEach(function (point, index) {
        const raw = point && typeof point === 'object' ? point : {};
        const ts = asNumber(raw.ts, null);
        const vocab = asNumber(raw.vocab, null);
        if (ts === null || vocab === null) return;
        data.push({ ts: ts, vocab: vocab, order: index });
      });
      data.sort(function (a, b) { return a.ts - b.ts; });
      const titleLabel = asString(titleText, '') || '同题库、同量尺的完成测验趋势';
      const title = titleText === false ? null : h('p', { className: 'va-note', key: 'chart-title' }, titleLabel);
      if (data.length < 2) {
        return h('div', { className: 'va-chart-wrap', key: 'chart-wrap' }, title,
          h('div', { className: 'va-chart' },
            h('div', { className: 'va-chart-empty' }, data.length ? '只有一次有效记录，暂不画趋势' : '暂无完成测验记录')
          ));
      }
      const width = 300;
      const height = 108;
      const pad = { left: 30, right: 10, top: 10, bottom: 18 };
      let minVocab = data[0].vocab;
      let maxVocab = data[0].vocab;
      data.forEach(function (item) {
        if (item.vocab < minVocab) minVocab = item.vocab;
        if (item.vocab > maxVocab) maxVocab = item.vocab;
      });
      if (maxVocab === minVocab) {
        maxVocab += 1;
        minVocab = Math.max(0, minVocab - 1);
      }
      const firstTs = data[0].ts;
      const lastTs = data[data.length - 1].ts;
      const spanTs = lastTs === firstTs ? 1 : lastTs - firstTs;
      const innerW = width - pad.left - pad.right;
      const innerH = height - pad.top - pad.bottom;
      const xOf = function (ts) { return pad.left + ((ts - firstTs) / spanTs) * innerW; };
      const yOf = function (vocab) {
        return pad.top + innerH - ((vocab - minVocab) / (maxVocab - minVocab)) * innerH;
      };
      const linePoints = data.map(function (item) {
        return xOf(item.ts).toFixed(1) + ',' + yOf(item.vocab).toFixed(1);
      }).join(' ');
      const children = [
        h('line', { key: 'grid-mid', x1: pad.left, y1: pad.top + innerH / 2, x2: pad.left + innerW, y2: pad.top + innerH / 2, stroke: 'var(--va-chart-grid)', strokeWidth: 1 }),
        h('polyline', { key: 'line', points: linePoints, fill: 'none', stroke: 'var(--va-chart-line)', strokeWidth: 2, strokeLinejoin: 'round', strokeLinecap: 'round' }),
        h('text', { key: 'max', x: pad.left - 4, y: pad.top + 8, textAnchor: 'end', fontSize: 8, fill: 'var(--va-chart-text)' }, formatNumber(maxVocab)),
        h('text', { key: 'min', x: pad.left - 4, y: pad.top + innerH + 2, textAnchor: 'end', fontSize: 8, fill: 'var(--va-chart-text)' }, formatNumber(minVocab)),
        h('text', { key: 'from', x: pad.left, y: height - 5, fontSize: 8, fill: 'var(--va-chart-date)' }, dateLabel(firstTs)),
        h('text', { key: 'to', x: pad.left + innerW, y: height - 5, textAnchor: 'end', fontSize: 8, fill: 'var(--va-chart-date)' }, dateLabel(lastTs)),
      ];
      data.forEach(function (item, index) {
        children.push(h('circle', { key: 'dot-' + index, cx: xOf(item.ts), cy: yOf(item.vocab), r: 2.4, fill: 'var(--va-chart-line)' }));
      });
      return h('div', { className: 'va-chart-wrap', key: 'chart-wrap' }, title,
        h('div', { className: 'va-chart' },
          h('svg', { viewBox: '0 0 ' + width + ' ' + height, width: '100%', height: '100%', role: 'img', 'aria-label': '完成测验词汇量趋势折线图' }, children)
        ));
    }
    function historyDetailLines(row) {
      const raw = row && typeof row === 'object' ? row : {};
      const right = asNumber(raw.right, null);
      const total = asNumber(raw.total, null);
      const dontknow = asNumber(raw.dontknow, null);
      const interval = asArray(raw.interval);
      const lo = asNumber(interval[0], null);
      const hi = asNumber(interval[1], null);
      const lines = [];
      if (right !== null) lines.push('答对 ' + formatNumber(right) + (total !== null ? ' / ' + formatNumber(total) : '') + ' 题');
      else if (total !== null) lines.push('已答 ' + formatNumber(total) + ' 题');
      if (dontknow !== null) lines.push('不认识 ' + formatNumber(dontknow) + ' 题');
      if (lo !== null && hi !== null) lines.push('参考范围 ' + formatNumber(lo) + '–' + formatNumber(hi) + ' 词');
      if (!lines.length) lines.push('该记录没有可展示的明细。');
      return lines;
    }
    function screenHistory(view, api) {
      const source = asArray(view.rows);
      const shown = source.slice(0, 300);
      const listNodes = shown.map(function (row, position) {
        const raw = row && typeof row === 'object' ? row : {};
        const originalIndex = asNumber(raw.index, null);
        const stamp = asString(raw.tsText, '') || dateLabel(raw.ts);
        const available = raw.available !== false;
        const vocab = asNumber(raw.vocab, null);
        const title = asString(raw.title, '')
          || (stamp || '未知日期') + (available && vocab !== null ? '  ·  ' + formatNumber(vocab) + ' 词' : '  ·  样本不足');
        const detail = asString(raw.detail, '');
        const bodyLines = (detail ? detail.split('\n') : historyDetailLines(raw)).map(function (line, lineIndex) {
          return h('div', { key: 'line-' + lineIndex }, line);
        });
        const deleteButton = originalIndex !== null ? h('button', {
            type: 'button',
            key: 'delete',
            className: 'va-hist-delete',
            'aria-label': '删除这条测试记录',
            onClick: function () {
              const confirmed = typeof window !== 'undefined' && typeof window.confirm === 'function'
                ? window.confirm('删除这条测试记录？该操作不可撤销。')
                : true;
              if (confirmed) api.send('deleteHistory', { index: originalIndex });
            },
          }, '删除') : null;
        // A sibling button remains visible when collapsed and cannot toggle details.
        return h('div', { className: 'va-hist-row' + (deleteButton ? ' has-delete' : ''), key: 'hist-' + position },
          h('details', { className: 'va-hist' },
            h('summary', null, h('span', { className: 'va-hist-value', style: { marginLeft: 0, flex: '1' } }, title)),
            h('div', { className: 'va-hist-body' }, bodyLines)
          ),
          deleteButton
        );
      });
      return h('div', { className: 'va-screen va-history' },
        h('div', { className: 'va-scroll' },
          renderChartBlock(view.points, false),
          source.length
            ? listNodes
            : noteEl('还没有保存的测试记录。'),
          source.length > shown.length
            ? noteEl('仅显示最近 ' + shown.length + ' 条记录。', 'va-muted')
            : null
        )
      );
    }

    // ---------- quiz ----------
    function screenQuiz(view, api) {
      const word = wordOf(view), options = asArray(view.options);
      const locked = view.locked === true, unknownPicked = view.unknownPicked === true;
      const index = asNumber(view.index, 0), total = asNumber(view.total, 0);
      const percent = total > 0 ? clamp((index / total) * 100, 0, 100) : 0;
      const optionNodes = options.length ? options.map(function (option, position) {
        const raw = option && typeof option === 'object' ? option : {};
        const optionIndex = asNumber(raw.index, position), text = asString(raw.text, ''), state = asString(raw.state, '');
        const letter = optionIndex >= 0 && optionIndex < 26 ? String.fromCharCode(65 + optionIndex) : '?';
        return h('button', {
          type: 'button', key: 'quiz-opt-' + optionIndex,
          className: 'va-opt' + optionStateClass(state), disabled: locked,
          onClick: () => { if (!locked) api.send('quizAnswer', { index: optionIndex }); },
          'aria-label': '选项 ' + letter + ' ' + text,
          'aria-pressed': state === 'picked' ? 'true' : undefined, tabIndex: -1,
        },
        h('span', { className: 'va-letter' }, letter),
        h('span', { className: 'va-opt-text' }, text || '（空选项）'),
        h('span', { className: 'va-key', 'aria-hidden': 'true' },
          '[' + keyCaption(mergedKeys(view.keys), view.keyCaptions, 'choice' + (optionIndex + 1)) + ']')
        );
      }) : [h('p', { className: 'va-note', key: 'no-options' }, '暂无选项')];
      optionNodes.push(h('button', {
        type: 'button', key: 'quiz-dontknow',
        className: 'va-opt va-opt-unknown' + (unknownPicked ? ' is-picked' : ''),
        disabled: locked, tabIndex: -1,
        'aria-label': labelFor(view, 'dontknow', '不认识'), 'aria-pressed': unknownPicked ? 'true' : 'false',
        onClick: () => { if (!locked) api.send('quizDontknow', {}); },
      }, h('span', { className: 'va-unknown-label' },
        labelFor(view, 'dontknow', '不认识'),
        h('span', { className: 'va-key', 'aria-hidden': 'true' }, '[' + hintFor(view, 'unknown') + ']')
      )));
      return h('div', { className: 'va-screen va-quiz' },
        h('div', { className: 'va-progress', role: 'progressbar', 'aria-label': '已保存的回答数量', 'aria-valuemin': 0, 'aria-valuemax': total || 0, 'aria-valuenow': index || 0 },
          h('div', { className: 'va-progress-fill', style: { width: percent + '%' } })
        ),
        h('div', { className: 'va-quiz-word' }, word.caption || '（无词条）'),
        h('div', { className: 'va-options' }, optionNodes),
        locked ? h('div', { className: 'va-quiz-actions' },
          buttonEl('下一个', {
            key: 'quiz-next', className: 'va-btn-remember', ariaLabel: '下一个题目',
            onClick: () => api.send('next', {}), tabIndex: -1,
          })
        ) : null
      );
    }

    // ---------- shared welcome / result / summary action blocks ----------
    function actionSpec(item) {
      if (typeof item === 'string') return { label: item, textOnly: true, type: '' };
      if (!item || typeof item !== 'object') return null;
      const label = asString(item.label, '') || asString(item.caption, '') || asString(item.text, '') || asString(item.name, '');
      const type = asString(item.type, '') || asString(item.action, '');
      if (['back', 'books', 'quizStart', 'prediction', 'bands', 'settings'].indexOf(type) < 0) return null;
      const style = asString(item.style, '') || asString(item.kind, '');
      if (!label && !type) return null;
      return {
        label: label || type,
        type: type,
        payload: item.payload && typeof item.payload === 'object' ? item.payload : {},
        style: style,
        primary: item.primary === true || style === 'primary',
        link: style === 'link',
        strategies: asArray(item.strategies).filter(function (strategy) { return typeof strategy === 'string'; }),
        textOnly: false,
      };
    }
    function dispatchActionSpec(spec, api) {
      if (!spec || spec.textOnly || !spec.type) return;
      api.send(spec.type, spec.payload || {});
    }
    function renderActionBlock(actions, api, fallback) {
      const specs = asArray(actions).map(actionSpec).filter(Boolean);
      const nodes = [];
      const textLines = [];
      specs.forEach(function (spec, index) {
        if (spec.textOnly) {
          if (spec.label) textLines.push(spec.label);
          return;
        }
        if (!spec.label) return;
        if (spec.strategies.length) {
          spec.strategies.forEach(function (strategy) {
            nodes.push(chipEl(STRATEGY_LABELS[strategy] || strategy, {
              key: 'action-' + index + '-' + strategy,
              onClick: () => api.send(spec.type, { strategy: strategy }),
              ariaLabel: '预测掌握策略：' + (STRATEGY_LABELS[strategy] || strategy),
            }));
          });
          return;
        }
        if (spec.link) {
          nodes.push(chipEl(spec.label, {
            key: 'action-' + index,
            onClick: () => dispatchActionSpec(spec, api),
            ariaLabel: spec.label,
          }));
          return;
        }
        nodes.push(buttonEl(spec.label, {
          key: 'action-' + index,
          className: spec.primary ? 'va-btn-remember' : 'va-btn-plain',
          ariaLabel: spec.label,
          onClick: () => dispatchActionSpec(spec, api),
        }));
      });
      if (!nodes.length && fallback && fallback.label) {
        nodes.push(buttonEl(fallback.label, {
          key: 'action-fallback',
          className: 'va-btn-remember',
          ariaLabel: fallback.label,
          onClick: fallback.onClick,
        }));
      }
      return h('div', { className: 'va-actions-result' },
        textLines.map(function (line, index) {
          return h('div', { className: 'va-muted', key: 'action-text-' + index }, line);
        }),
        nodes
      );
    }
    function bandInfoLines(bands) {
      const lines = [];
      asArray(bands).forEach(function (band) {
        if (!band || typeof band !== 'object') return;
        const label = asString(band.label, '') || asString(band.title, '') || asString(band.name, '');
        const size = asNumber(band.size, null);
        const answered = asNumber(band.answered, null);
        const correct = asNumber(band.correct, null);
        const unknown = asNumber(band.unknown, null);
        const parts = [];
        if (size !== null) parts.push(formatNumber(size) + ' 词目');
        if (answered !== null) parts.push('已测 ' + formatNumber(answered));
        if (correct !== null) parts.push('答对 ' + formatNumber(correct));
        if (unknown !== null) parts.push('不认识 ' + formatNumber(unknown));
        if (!label && !parts.length) return;
        lines.push((label || '分层样本') + (parts.length ? ' · ' + parts.join(' · ') : ''));
      });
      return lines;
    }
    function screenResult(view, api) {
      const estimate = asNumber(view.estimate, null);
      const interval = asArray(view.interval);
      const lo = asNumber(interval[0], null);
      const hi = asNumber(interval[1], null);
      const available = view.available === false ? false : estimate !== null;
      const big = asString(view.big, '') || (available ? '≈ ' + formatNumber(estimate) + ' 词目' : '样本不足');
      const sub = asString(view.sub, '') || (available
        ? (lo !== null && hi !== null ? '模型95%区间  ' + formatNumber(lo) + ' – ' + formatNumber(hi) + ' 词目' : '已给出估算值')
        : '至少完成40题及分层采样后才显示估算');
      const coverage = asString(view.coverage, '');
      const note = asString(view.note, '') || '题目参数未经实测标定；模型区间不包含全部测量偏差。结果不会改变学习队列或逐词掌握状态。';
      const bands = asArray(view.bands).length ? asArray(view.bands) : asArray(view.rows);
      const bandLines = bandInfoLines(bands);
      const chart = view.chart && typeof view.chart === 'object' ? view.chart : null;
      const chartPoints = chart ? asArray(chart.points) : [];
      const fromWelcome = view.fromWelcome === true;
      const fallback = fromWelcome
        ? { label: '选择词书', onClick: () => api.send('books', { from: 'result' }) }
        : { label: '继续背单词', onClick: () => api.send('back', {}) };
      return h('div', { className: 'va-screen va-result' },
        h('div', { className: 'va-big' }, big),
        h('div', { className: 'va-sub' }, sub),
        coverage ? h('div', { className: 'va-sub' }, coverage) : null,
        bandLines.length
          ? h('ul', { className: 'va-info' }, bandLines.map(function (line, index) {
            return h('li', { key: 'info-' + index }, line);
          }))
          : null,
        chart && chartPoints.length ? renderChartBlock(chartPoints, chart.title) : null,
        h('div', { className: 'va-note', style: { whiteSpace: 'pre-wrap' } }, note),
        renderActionBlock(view.actions, api, fallback)
      );
    }
    function screenSummary(view, api) {
      const title = asString(view.title, '') || '本次测试已完成';
      const body = asArray(view.body);
      const big = asString(view.big, '');
      const lines = big && body.length && body[0] === big ? body.slice(1) : body;
      return h('div', { className: 'va-screen va-summary' },
        h('div', { className: 'va-summary-title' }, title),
        big ? h('div', { className: 'va-big' }, big) : null,
        h('div', { className: 'va-summary-body' },
          lines.length
            ? lines.map(function (line, index) {
              return h('div', { key: 'body-' + index }, asString(line, ''));
            })
            : '没有可展示的说明。'
        ),
        renderActionBlock(view.actions, api, { label: '知道了', onClick: () => api.send('back', {}) })
      );
    }
    function screenBuilding(view, api) {
      const percent = clamp(asNumber(view.percent, 0), 0, 100);
      const title = asString(view.title, '') || '正在构建题库';
      return h('div', { className: 'va-screen va-building', 'aria-busy': 'true' },
        h('div', { className: 'va-building-text', role: 'status' }, title.replace(/[…。\.]+$/, '') + '…'),
        h('div', { className: 'va-progress', role: 'progressbar', 'aria-label': '题库构建进度', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': Math.round(percent) },
          h('div', { className: 'va-progress-fill', style: { width: percent + '%' } })
        )
      );
    }
    function unknownScreen(screen, api) {
      const name = asString(screen, '') || '（缺失）';
      return h('div', { className: 'va-unknown' },
        h('div', { className: 'va-strong' }, '未知页面：' + name),
        h('small', null, '宿主与插件的版本可能不一致，请刷新页面后重试。'),
        h('div', { className: 'va-actions' },
          buttonEl('重试', {
            className: 'va-btn-plain',
            ariaLabel: '重新加载状态',
            onClick: () => {
              if (typeof api.retry === 'function') api.retry();
            },
          })
        )
      );
    }
    function normalizeApi(api) {
      const base = api && typeof api === 'object' ? api : {};
      base.send = typeof base.send === 'function' ? base.send : function noopSend() {};
      base.hide = typeof base.hide === 'function' ? base.hide : function noopHide() {};
      base.retry = typeof base.retry === 'function' ? base.retry : function noopRetry() {};
      return base;
    }
    function renderScreen(view, api) {
      const safeApi = normalizeApi(api);
      if (!view || typeof view !== 'object') {
        return h('div', { className: 'va-loading' }, '正在加载背单词…');
      }
      const screen = asString(view.screen, '');
      try {
        switch (screen) {
          case 'welcome': return screenWelcome(view, safeApi);
          case 'front': return screenFront(view, safeApi);
          case 'back': return screenBack(view, safeApi);
          case 'empty': return screenEmpty(view, safeApi);
          case 'choice': return screenChoice(view, safeApi);
          case 'choice_back': return screenChoice(view, safeApi);
          case 'settings': return screenSettings(view, safeApi);
          case 'books': return screenBooks(view, safeApi);
          case 'catalog': return screenCatalog(view, safeApi);
          case 'history': return screenHistory(view, safeApi);
          case 'quiz': return screenQuiz(view, safeApi);
          case 'result': return screenResult(view, safeApi);
          case 'summary': return screenSummary(view, safeApi);
          case 'building': return screenBuilding(view, safeApi);
          default: return unknownScreen(screen, safeApi);
        }
      } catch (error) {
        if (typeof console !== 'undefined' && console.error) {
          console.error('[vocab-app] screen render failed: ' + screen, error);
        }
        return unknownScreen(screen, safeApi);
      }
    }
    function collectText(node) {
      if (node === null || node === undefined || node === false || node === true) return '';
      if (typeof node === 'string' || typeof node === 'number') return String(node);
      if (Array.isArray(node)) {
        const parts = [];
        for (let i = 0; i < node.length; i += 1) parts.push(collectText(node[i]));
        return parts.join(' ');
      }
      if (typeof node === 'object') {
        let text = '';
        if (node.children !== undefined) text += ' ' + collectText(node.children);
        if (node.props && node.props.children !== undefined && node.children === undefined) {
          text += ' ' + collectText(node.props.children);
        }
        return text;
      }
      return '';
    }

    // ---- Interactive shell: overlay panel, fetch bridge, keyboard, drag ----
    function readViewport() {
      if (typeof window === 'undefined') return { width: 1280, height: 800 };
      return {
        width: asNumber(window.innerWidth, 1280),
        height: asNumber(window.innerHeight, 800),
      };
    }
    function windowPresets() {
      return FALLBACK_WINDOW_PRESETS;
    }
    function currentWindowPreset() {
      return FALLBACK_WINDOW_PRESETS[0];
    }
    function initialGeometry() {
      const viewport = readViewport();
      const preset = currentWindowPreset();
      const width = Math.min(preset.width, Math.max(1, viewport.width - VIEWPORT_PAD * 2));
      const height = Math.min(preset.height, Math.max(1, viewport.height - VIEWPORT_PAD * 2));
      return {
        x: Math.max(VIEWPORT_PAD, viewport.width - EDGE_GAP - width),
        y: Math.max(VIEWPORT_PAD, viewport.height - EDGE_GAP - height),
        w: width,
        h: height,
      };
    }
    // Fixed preset sizes: never user-resizable, always shrunk/clamped into the
    // visible viewport when the window is narrow.
    function fitGeometry(geometry, preset) {
      const viewport = readViewport();
      const maxWidth = Math.max(1, viewport.width - VIEWPORT_PAD * 2);
      const maxHeight = Math.max(1, viewport.height - VIEWPORT_PAD * 2);
      const width = Math.min(Math.max(1, asNumber(preset && preset.width, 520)), maxWidth);
      const height = Math.min(Math.max(1, asNumber(preset && preset.height, 430)), maxHeight);
      const x = clamp(asNumber(geometry && geometry.x, viewport.width - EDGE_GAP - width), VIEWPORT_PAD,
        Math.max(VIEWPORT_PAD, viewport.width - width - VIEWPORT_PAD));
      const y = clamp(asNumber(geometry && geometry.y, viewport.height - EDGE_GAP - height), VIEWPORT_PAD,
        Math.max(VIEWPORT_PAD, viewport.height - height - VIEWPORT_PAD));
      return { x: x, y: y, w: width, h: height };
    }
    // Pure merge of a title-bar pointer delta onto the in-memory geometry.
    function movedGeometry(start, dx, dy) {
      const viewport = readViewport();
      const maxWidth = Math.max(1, viewport.width - VIEWPORT_PAD * 2);
      const maxHeight = Math.max(1, viewport.height - VIEWPORT_PAD * 2);
      const width = Math.min(Math.max(1, asNumber(start.w, 520)), maxWidth);
      const height = Math.min(Math.max(1, asNumber(start.h, 430)), maxHeight);
      const x = clamp(asNumber(start.x, 0) + asNumber(dx, 0), VIEWPORT_PAD,
        Math.max(VIEWPORT_PAD, viewport.width - width - VIEWPORT_PAD));
      const y = clamp(asNumber(start.y, 0) + asNumber(dy, 0), VIEWPORT_PAD,
        Math.max(VIEWPORT_PAD, viewport.height - height - VIEWPORT_PAD));
      return { x: x, y: y, w: width, h: height };
    }
    // One session-only bottom corner anchors both the panel and its bubble.
    // Clamp against the *expanded* panel, even while closed, so reopening can
    // preserve that exact corner without putting the panel off screen.
    function anchorFromGeometry(geometry) {
      const viewport = readViewport();
      const side = geometry.x + geometry.w / 2 <= viewport.width / 2 ? 'left' : 'right';
      return { side: side, x: side === 'left' ? geometry.x : geometry.x + geometry.w, y: geometry.y + geometry.h };
    }
    function initialAnchor() {
      return anchorFromGeometry(initialGeometry());
    }
    function fitAnchor(anchor, preset) {
      const viewport = readViewport();
      const size = fitGeometry(null, preset);
      const side = anchor && anchor.side === 'left' ? 'left' : 'right';
      const minX = side === 'left' ? VIEWPORT_PAD : VIEWPORT_PAD + size.w;
      const maxX = side === 'left' ? Math.max(minX, viewport.width - size.w - VIEWPORT_PAD)
        : Math.max(minX, viewport.width - VIEWPORT_PAD);
      return {
        side: side,
        x: clamp(asNumber(anchor && anchor.x, viewport.width - EDGE_GAP), minX, maxX),
        y: clamp(asNumber(anchor && anchor.y, viewport.height - EDGE_GAP), VIEWPORT_PAD + size.h,
          Math.max(VIEWPORT_PAD + size.h, viewport.height - VIEWPORT_PAD)),
      };
    }
    function geometryFromAnchor(anchor, preset) {
      const point = fitAnchor(anchor, preset);
      const size = fitGeometry(null, preset);
      return { x: point.side === 'left' ? point.x : point.x - size.w, y: point.y - size.h, w: size.w, h: size.h };
    }
    function entryFromAnchor(anchor, preset) {
      const point = fitAnchor(anchor, preset);
      const size = fitGeometry(null, preset);
      const entrySize = Math.min(ENTRY_ICON_SIZE, size.w, size.h);
      return { x: point.side === 'left' ? point.x : point.x - entrySize, y: point.y - entrySize, size: entrySize };
    }
    function anchorFromEntry(position, preset) {
      const viewport = readViewport();
      const size = Math.min(ENTRY_ICON_SIZE, fitGeometry(null, preset).w, fitGeometry(null, preset).h);
      const side = asNumber(position && position.x, 0) + size / 2 <= viewport.width / 2 ? 'left' : 'right';
      return fitAnchor({ side: side, x: asNumber(position && position.x, 0) + (side === 'right' ? size : 0),
        y: asNumber(position && position.y, 0) + size }, preset);
    }
    function reviewDue(view) {
      if (!view || view.screen !== 'empty') return null;
      if (view.due === null || view.due === undefined || view.due === '') return null;
      return asNumber(view.due, null);
    }
    // Only the header itself (blank space / title text) starts a drag; every
    // interactive child keeps its own activation.
    function shouldStartPanelDrag(event) {
      if (!event || (typeof event.button === 'number' && event.button !== 0)) return false;
      const target = event.target;
      if (isEditableTarget(target)) return false;
      if (target && typeof target.closest === 'function') {
        return target.closest('button, a[href], input, select, textarea, [role="button"], [contenteditable="true"]') === null;
      }
      return true;
    }
    function clampEntryPosition(position, viewport) {
      const area = viewport || readViewport();
      const maxX = Math.max(VIEWPORT_PAD, area.width - ENTRY_ICON_SIZE - VIEWPORT_PAD);
      const maxY = Math.max(VIEWPORT_PAD, area.height - ENTRY_ICON_SIZE - VIEWPORT_PAD);
      return {
        x: clamp(asNumber(position && position.x, maxX), VIEWPORT_PAD, maxX),
        y: clamp(asNumber(position && position.y, maxY), VIEWPORT_PAD, maxY),
      };
    }
    function VirtualList(props) {
      const items = asArray(props.items);
      const rowHeight = asNumber(props.rowHeight, 40) || 40;
      const overscan = 6;
      const outerRef = React.useRef(null);
      const viewportState = React.useState(320);
      const scrollState = React.useState(0);
      const currentScroll = scrollState[0];
      const setScroll = scrollState[1];
      const currentViewport = viewportState[0];
      const setViewport = viewportState[1];
      React.useEffect(function () {
        const node = outerRef.current;
        if (!node) return undefined;
        const measure = function () {
          setViewport(node.clientHeight || 320);
        };
        measure();
        if (typeof ResizeObserver !== 'undefined') {
          const observer = new ResizeObserver(measure);
          observer.observe(node);
          return function () { observer.disconnect(); };
        }
        window.addEventListener('resize', measure);
        return function () { window.removeEventListener('resize', measure); };
      }, []);
      React.useEffect(function () {
        const node = outerRef.current;
        if (node) node.scrollTop = 0;
        setScroll(0);
      }, [items.length]);
      const total = items.length;
      const first = Math.max(0, Math.floor(currentScroll / rowHeight) - overscan);
      const count = Math.max(1, Math.ceil(currentViewport / rowHeight) + overscan * 2);
      const last = Math.min(total, first + count);
      const rows = [];
      for (let index = first; index < last; index += 1) {
        rows.push(h('div', {
          className: 'va-vlist-item',
          key: 'vlist-row-' + index,
          style: { top: (index * rowHeight) + 'px', height: rowHeight + 'px' },
        }, items[index]));
      }
      return h('div', {
        className: 'va-vlist',
        ref: outerRef,
        onScroll: function (event) { setScroll(event.currentTarget.scrollTop); },
        role: 'list',
        'aria-label': props.ariaLabel || '列表',
      }, h('div', { className: 'va-vlist-inner', style: { height: (total * rowHeight) + 'px' } }, rows));
    }
    function renderErrorBar(error, handlers) {
      if (!error) return null;
      const info = error.kind === 'info';
      const retry = handlers && typeof handlers.retry === 'function' ? handlers.retry : null;
      const dismiss = handlers && typeof handlers.dismiss === 'function' ? handlers.dismiss : null;
      return h('div', { className: 'va-errorbar' + (info ? ' is-info' : ''), role: 'alert' },
        h('span', { className: 'va-error-text', title: asString(error.message, '') }, asString(error.message, '发生未知错误')),
        !info && retry
          ? h('button', { type: 'button', onClick: retry, 'aria-label': '重试' }, '重试')
          : null,
        dismiss
          ? h('button', { type: 'button', onClick: dismiss, 'aria-label': '关闭提示' }, '关闭')
          : null
      );
    }
    // Closed-state floating entry: pointer movement drags immediately; a
    // meaningful drag suppresses the follow-up click. Position stays in React state.
    function ClosedEntry(props) {
      const [dragging, setDragging] = React.useState(false);
      const suppressRef = React.useRef(false);
      const cleanupRef = React.useRef(null);
      const mountedRef = React.useRef(true);
      React.useEffect(function () {
        mountedRef.current = true;
        return function () {
          mountedRef.current = false;
          if (cleanupRef.current) cleanupRef.current();
        };
      }, []);
      function startPosition() {
        const viewport = readViewport();
        return clampEntryPosition(props.position || {
          x: viewport.width - EDGE_GAP - ENTRY_ICON_SIZE,
          y: viewport.height - EDGE_GAP - ENTRY_ICON_SIZE,
        }, viewport);
      }
      function begin(event) {
        if (!event || (typeof event.button === 'number' && event.button !== 0) || typeof window === 'undefined') return;
        suppressRef.current = false;
        if (cleanupRef.current) cleanupRef.current();
        const start = startPosition();
        const startX = asNumber(event.clientX, 0);
        const startY = asNumber(event.clientY, 0);
        const capture = event.currentTarget || event.target;
        const pointerId = event.pointerId;
        const session = { moved: false };
        if (capture && typeof capture.setPointerCapture === 'function' && pointerId !== undefined) {
          try { capture.setPointerCapture(pointerId); } catch (error) { /* best effort */ }
        }
        if (mountedRef.current) setDragging(true);
        const stop = function () {
          if (typeof window !== 'undefined') {
            window.removeEventListener('pointermove', onMove);
            window.removeEventListener('pointerup', finish);
            window.removeEventListener('pointercancel', cancel);
            window.removeEventListener('blur', cancel);
          }
          if (capture && typeof capture.releasePointerCapture === 'function' && pointerId !== undefined) {
            try { capture.releasePointerCapture(pointerId); } catch (error) { /* released */ }
          }
          cleanupRef.current = null;
          if (mountedRef.current) setDragging(false);
        };
        const onMove = function (moveEvent) {
          if (pointerId !== undefined && moveEvent.pointerId !== undefined && moveEvent.pointerId !== pointerId) return;
          const dx = asNumber(moveEvent.clientX, startX) - startX;
          const dy = asNumber(moveEvent.clientY, startY) - startY;
          const far = Math.abs(dx) > ENTRY_MOVE_TOLERANCE || Math.abs(dy) > ENTRY_MOVE_TOLERANCE;
          if (far) {
            session.moved = true;
            suppressRef.current = true;
          }
          const next = clampEntryPosition({ x: start.x + dx, y: start.y + dy });
          if (typeof props.onMove === 'function') props.onMove(next.x, next.y);
        };
        const finish = function (upEvent) {
          if (pointerId !== undefined && upEvent && upEvent.pointerId !== undefined && upEvent.pointerId !== pointerId) return;
          stop();
        };
        const cancel = function () {
          suppressRef.current = true;
          stop();
        };
        cleanupRef.current = stop;
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', finish);
        window.addEventListener('pointercancel', cancel);
        window.addEventListener('blur', cancel);
      }
      function onClick(event) {
        if (suppressRef.current) {
          suppressRef.current = false;
          if (event && typeof event.preventDefault === 'function') event.preventDefault();
          if (event && typeof event.stopPropagation === 'function') event.stopPropagation();
          return;
        }
        if (typeof props.open === 'function') props.open();
      }
      const style = props.position
        ? { left: props.position.x + 'px', top: props.position.y + 'px' }
        : { right: EDGE_GAP + 'px', bottom: EDGE_GAP + 'px' };
      return h('button', {
        type: 'button',
        className: 'dsh-vocab-reopen' + (dragging ? ' is-dragging' : ''),
        style: style,
        onPointerDown: begin,
        onClick: onClick,
        onContextMenu: function (event) { if (event && typeof event.preventDefault === 'function') event.preventDefault(); },
        onDragStart: function (event) { if (event && typeof event.preventDefault === 'function') event.preventDefault(); },
        title: '打开背单词',
        'aria-label': '打开背单词浮层',
      }, brandIcon(24));
    }
    // Fixed learning shortcuts (no user-editable key map in 0.1.1).
    function matchPhaseKey(event, keys, phaseName) {
      if (!phaseName) return '';
      const actions = phaseName === 'brush'
        ? ['remember', 'forget']
        : (phaseName === 'choice' ? ['choice1', 'choice2', 'choice3', 'choice4', 'unknown'] : ['next']);
      for (let index = 0; index < actions.length; index += 1) {
        if (eventMatchesBinding(event, keys[actions[index]])) return actions[index];
      }
      return '';
    }
    function resolveStudyKey(view, event) {
      if (!view || !event) return '';
      const screen = asString(view.screen, '');
      const keys = mergedKeys(view.keys);
      if (isPlainKey(event, 'Escape')) return 'escape';
      if (normalizeBase(baseFromEvent(event)) === 'Z') {
        const noModifiers = !event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey;
        const ctrlOnly = event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey;
        if (noModifiers && view.canCorrect === true && (screen === 'back' || screen === 'choice_back')) return 'correct';
        if (ctrlOnly && view.canUndo === true) return 'undo';
      }
      if (screen === 'back' && isPlainKey(event, 'Space')) {
        return view.canCorrect === true ? 'correct' : 'next';
      }
      if ((screen === 'back' || screen === 'choice_back' || screen === 'empty') && isPlainKey(event, 'Enter')) return 'next';
      if ((screen === 'choice_back' || screen === 'empty') && isPlainKey(event, 'Space')) return 'next';
      // Host may report a choice screen with no usable four-option item:
      // Space/Enter skips it, numeric/shortcut choice keys must not answer.
      if (screen === 'choice' && view.unavailable === true) {
        return (isPlainKey(event, 'Space') || isPlainKey(event, 'Enter')) ? 'next' : '';
      }
      if (screen === 'quiz' && view.locked === true
          && (isPlainKey(event, 'Enter') || eventMatchesBinding(event, keys.next))) return 'next';
      const phaseName = screen === 'front'
        ? 'brush'
        : ((screen === 'choice' || screen === 'quiz')
          ? 'choice'
          : ((screen === 'back' || screen === 'empty' || screen === 'choice_back') ? 'back' : ''));
      return matchPhaseKey(event, keys, phaseName);
    }

    function VocabApp() {
      const anchorState = React.useState(initialAnchor);
      const anchor = anchorState[0];
      const setAnchor = anchorState[1];
      const viewState = React.useState(null);
      const view = viewState[0];
      const setView = viewState[1];
      const revState = React.useState(0);
      const rev = revState[0];
      const setRev = revState[1];
      const phaseState = React.useState('loading');
      const phase = phaseState[0];
      const setPhase = phaseState[1];
      const quizStartState = React.useState(false);
      const startingQuiz = quizStartState[0];
      const setStartingQuiz = quizStartState[1];
      const buildCompleteState = React.useState(false);
      const buildComplete = buildCompleteState[0];
      const setBuildComplete = buildCompleteState[1];
      const errorState = React.useState(null);
      const error = errorState[0];
      const setError = errorState[1];
      // Start as the existing floating entry on each client mount. Opening is
      // an explicit user action; no persisted preference or learning write.
      const hiddenState = React.useState(true);
      const hidden = hiddenState[0];
      const setHidden = hiddenState[1];
      const [dragging, setDragging] = React.useState(false);
      const catalogState = React.useState(null);
      const catalogDraft = catalogState[0];
      const setCatalogDraft = catalogState[1];
      const orderState = React.useState(null);
      const pendingOrder = orderState[0];
      const setPendingOrder = orderState[1];
      const windowPreset = currentWindowPreset();
      const geometry = geometryFromAnchor(anchor, windowPreset);
      const entryPos = entryFromAnchor(anchor, windowPreset);
      const rootRef = React.useRef(null);
      const anchorRef = React.useRef(anchor);
      anchorRef.current = anchor;
      const geometryRef = React.useRef(geometry);
      geometryRef.current = geometry;
      const hiddenRef = React.useRef(hidden);
      hiddenRef.current = hidden;
      const wakeRef = React.useRef(null);
      const revRef = React.useRef(rev);
      revRef.current = rev;
      const mountedRef = React.useRef(true);
      const busyRef = React.useRef(false);
      const viewRef = React.useRef(view);
      viewRef.current = view;
      const dragCleanupRef = React.useRef(null);
      // Render pending startup immediately; retain the authoritative view/rev
      // for failure recovery and wait for host acknowledgement before polling.
      const displayView = (startingQuiz || buildComplete) && view
        ? Object.assign({}, view, { screen: 'building', title: buildComplete ? '加载完成' : '正在加载测试', status: '', percent: buildComplete ? 100 : 0, busy: true, canPause: false })
        : view;
      const screen = asString(displayView && displayView.screen, '');
      const hostScreen = asString(view && view.screen, '');
      React.useEffect(function () {
        mountedRef.current = true;
        return function () {
          mountedRef.current = false;
          if (dragCleanupRef.current) dragCleanupRef.current();
        };
      }, []);
      React.useEffect(function () {
        loadState(false);
      }, []);
      React.useEffect(function () {
        const fit = function () {
          if (!mountedRef.current) return;
          setAnchor(function (current) { return fitAnchor(current, windowPreset); });
        };
        fit();
        window.addEventListener('resize', fit);
        return function () { window.removeEventListener('resize', fit); };
      }, [windowPreset.key, windowPreset.width, windowPreset.height]);
      // While the host is building the assessment bank, poll GET /state.
      React.useEffect(function () {
        if (startingQuiz || hostScreen !== 'building') return undefined;
        const timer = setInterval(function () {
          loadState(true);
        }, 100);
        return function () { clearInterval(timer); };
      }, [hostScreen, startingQuiz]);
      // Show the final filled bar for one short transition before revealing a cold quiz.
      // The authoritative view/revision has already advanced; this is presentation only.
      React.useEffect(function () {
        if (!buildComplete) return undefined;
        const timer = setTimeout(function () { if (mountedRef.current) setBuildComplete(false); }, 300);
        return function () { clearTimeout(timer); };
      }, [buildComplete]);
      // Original desktop auto-advances 350 ms after a quiz answer; the DSH
      // host has no timer, so the client issues `next` only while displayed.
      // A reload/close must not advance a locked quiz behind the startup icon.
      React.useEffect(function () {
        if (hidden || !view || view.screen !== 'quiz' || view.locked !== true) return undefined;
        const timer = setTimeout(function () {
          if (mountedRef.current && !hiddenRef.current) sendAction('next', {});
        }, 350);
        return function () { clearTimeout(timer); };
      }, [hidden, view && view.screen, view && view.locked, view && view.index]);
      // GET remains read-only; use the normal serialized/revisioned POST next
      // only while visible and empty. Never interrupt an unanswered card.
      React.useEffect(function () {
        if (hidden || screen !== 'empty') return undefined;
        const timer = setInterval(function () { loadState(true); }, 15000);
        return function () { clearInterval(timer); };
      }, [hidden, screen]);
      React.useEffect(function () {
        if (hidden || screen !== 'empty') return undefined;
        let cancelled = false;
        let timer = null;
        let failures = 0;
        function active() {
          const current = viewRef.current;
          return !cancelled && mountedRef.current && !hiddenRef.current
            && current && current.screen === 'empty';
        }
        function schedule(delay) {
          if (timer !== null) clearTimeout(timer);
          timer = null;
          if (active()) timer = setTimeout(tick, Math.max(0, Math.min(60000, delay)));
        }
        function tick() {
          timer = null;
          if (!active()) return;
          const due = reviewDue(viewRef.current);
          if (due === null) return;
          const remaining = due * 1000 - Date.now();
          if (remaining > 0) { schedule(remaining); return; }
          if (busyRef.current) { schedule(250); return; }
          sendAction('next', {}).then(function (ok) {
            if (!active()) return;
            failures = ok ? 0 : Math.min(failures + 1, 4);
            // A successful but still-empty response is throttled too (clock
            // skew / unavailable items), never a tight POST loop.
            schedule(ok ? 15000 : Math.min(15000, 1500 * Math.pow(2, failures - 1)));
          });
        }
        const wake = function () { schedule(0); };
        wakeRef.current = wake;
        tick();
        return function () {
          cancelled = true;
          if (timer !== null) clearTimeout(timer);
          if (wakeRef.current === wake) wakeRef.current = null;
        };
      }, [hidden, screen, view && view.due]);
      // Catalog-only local state must not leak across screens.
      React.useEffect(function () {
        if (screen !== 'catalog') setCatalogDraft(null);
      }, [screen]);
      // Clear the optimistic order once the host echoes it back.
      React.useEffect(function () {
        setPendingOrder(null);
      }, [view && view.order, screen]);
      // Keep the local search box in sync with the host's filter state.
      React.useEffect(function () {
        if (screen === 'catalog') setCatalogDraft(asString(view && view.query, ''));
      }, [screen, view && view.query, view && view.filter]);
      function focusRoot() {
        const node = rootRef.current;
        if (!node || typeof node.focus !== 'function') return;
        try {
          node.focus({ preventScroll: true });
        } catch (focusError) {
          try { node.focus(); } catch (ignored) { /* noop */ }
        }
      }
      function applyBody(body) {
        if (!body || typeof body !== 'object' || !mountedRef.current) return;
        if (body.view && typeof body.view === 'object') {
          if (viewRef.current && viewRef.current.screen === 'building' && body.view.screen === 'quiz') setBuildComplete(true);
          else if (body.view.screen !== 'quiz') setBuildComplete(false);
          viewRef.current = body.view;
          setView(body.view);
        }
        if ((typeof body.rev === 'number' && isFinite(body.rev))
            || (typeof body.rev === 'string' && /^\d+$/.test(body.rev))) {
          revRef.current = Number(body.rev);
          setRev(revRef.current);
        }
      }
      function loadState(silent) {
        if (busyRef.current) return Promise.resolve(false);
        busyRef.current = true;
        setPhase(function (current) { return current === 'ready' ? 'ready' : 'loading'; });
        if (!silent) setError(null);
        return fetch(STATE_URL, {
          method: 'GET',
          credentials: 'same-origin',
          headers: { accept: 'application/json' },
          cache: 'no-store',
        })
          .then(function (response) {
            return response.json().catch(function () { return null; }).then(function (body) {
              return { response: response, body: body };
            });
          })
          .then(function (result) {
            const failureBody = result.body && typeof result.body === 'object' ? result.body : null;
            if (!result.response || !result.response.ok) {
              throw new Error((failureBody && asString(failureBody.message, '')) || ('HTTP ' + (result.response ? result.response.status : '?')));
            }
            const body = result.body;
            if (!body || typeof body !== 'object' || !body.view || typeof body.view !== 'object') {
              throw new Error('返回格式异常');
            }
            if (!mountedRef.current) return false;
            applyBody(body);
            setPhase('ready');
            setError(null);
            return true;
          })
          .catch(function (failure) {
            if (!mountedRef.current) return false;
            if (!silent) {
              setPhase('error');
              setError({
                kind: 'load',
                message: '无法读取背单词状态：' + (failure && failure.message ? failure.message : '请确认 DSH 会话正常后重试。'),
              });
            }
            return false;
          })
          .then(function (value) {
            busyRef.current = false;
            if (mountedRef.current && wakeRef.current) wakeRef.current();
            return value;
          });
      }
      function sendAction(type, payload) {
        const actionType = asString(type, '');
        if (!actionType || busyRef.current || buildComplete) return Promise.resolve(false);
        busyRef.current = true;
        const quizStart = actionType === 'quizStart';
        if (quizStart && mountedRef.current) {
          setError(null);
          setStartingQuiz(true);
        }
        let request = null;
        return Promise.resolve()
          .then(function () {
            if (!mountedRef.current) return false;
            setError(null);
            request = {
              rev: revRef.current,
              type: actionType,
              payload: payload && typeof payload === 'object' ? payload : {},
            };
            return fetch(ACTION_URL, {
              method: 'POST',
              credentials: 'same-origin',
              headers: { 'content-type': 'application/json', accept: 'application/json' },
              body: JSON.stringify(request),
            });
          })
          .then(function (response) {
            return response.json().catch(function () { return null; }).then(function (body) {
              return { response: response, body: body };
            });
          })
          .then(function (result) {
            if (!mountedRef.current) return false;
            const body = result.body;
            if (!body || typeof body !== 'object') {
              throw new Error('HTTP ' + (result.response ? result.response.status : '?'));
            }
            applyBody(body);
            if (body.ok === true) {
              setError(null);
              return true;
            }
            const code = asString(body.code, '');
            const message = asString(body.message, '');
            if (code === 'stale') {
              setError({ kind: 'info', message: message || '状态已在别处更新，已刷新，请重新操作。' });
              return false;
            }
            if (code === 'invalid') {
              setError({ kind: 'info', message: message || '操作无效，请检查输入后重试。' });
              return false;
            }
            const failure = {
              kind: 'retry',
              message: message || ('操作未完成（' + (code || 'failed') + '）'),
              request: { type: actionType, payload: request ? request.payload : {} },
            };
            setError(failure);
            return false;
          })
          .catch(function () {
            if (!mountedRef.current) return false;
            const failure = {
              kind: 'retry',
              message: '无法连接背单词服务，请稍后重试。',
              request: { type: actionType, payload: request ? request.payload : {} },
            };
            setError(failure);
            return false;
          })
          .then(function (ok) {
            busyRef.current = false;
            if (mountedRef.current) {
              if (quizStart) setStartingQuiz(false);
              focusRoot();
            }
            return ok;
          });
      }
      function retryError() {
        const failure = error;
        setError(null);
        if (!failure || failure.kind === 'load' || !failure.request) {
          loadState(false);
          return;
        }
        sendAction(failure.request.type, failure.request.payload);
      }
      function hidePanel() {
        hiddenRef.current = true;
        setHidden(true);
      }
      function showPanel() {
        hiddenRef.current = false;
        setHidden(false);
        if (typeof setTimeout === 'function') setTimeout(focusRoot, 0);
      }
      // ---------- catalog search ----------
      function commitCatalogQuery() {
        const currentView = viewRef.current;
        if (!currentView || currentView.screen !== 'catalog') return;
        const query = asString(catalogDraft !== null && catalogDraft !== undefined ? catalogDraft : currentView.query, '');
        sendAction('catalogFilter', {
          category: asString(currentView.filter, 'all') || 'all',
          query: query,
        });
      }
      React.useEffect(function () {
        if (screen !== 'catalog' || catalogDraft === null) return undefined;
        const serverQuery = asString(view && view.query, '');
        if (catalogDraft === serverQuery) return undefined;
        const timer = setTimeout(function () {
          commitCatalogQuery();
        }, 280);
        return function () { clearTimeout(timer); };
      }, [catalogDraft, screen, view && view.query, view && view.filter]);

      // ---------- books ----------
      function setOrder(order) {
        setPendingOrder(order);
        const currentView = viewRef.current;
        const selected = asString(currentView && currentView.selected, '');
        const payload = { order: order };
        if (selected) payload.id = selected;
        sendAction('book', payload);
      }

      function startBook() {
        sendAction('start', {});
      }

      function dispatchStudyAction(action) {
        const detail = /^choice([1-4])$/.exec(action);
        if (action === 'remember' || action === 'forget') {
          sendAction('answer', { action: action });
        } else if (action === 'next') {
          sendAction('next', {});
        } else if (action === 'unknown') {
          if (screen === 'quiz') sendAction('quizDontknow', {});
          else sendAction('dontknow', {});
        } else if (detail) {
          const index = Number(detail[1]) - 1;
          if (screen === 'quiz') sendAction('quizAnswer', { index: index });
          else sendAction('choice', { index: index });
        }
      }

      function handleKeyDown(event) {
        if (hidden || !view || !event || event.defaultPrevented) return;
        if (isEditableTarget(event.target)) return;
        if (event.repeat || event.isComposing || event.keyCode === 229) return;
        const base = normalizeBase(baseFromEvent(event));
        const target = event.target;
        if (target && typeof target.closest === 'function') {
          const control = target.closest('button, a[href], [role="button"]');
          if (control && control.getAttribute('tabindex') !== '-1'
              && (base === 'ENTER' || base === 'SPACE')) {
            return;
          }
        }
        const action = resolveStudyKey(displayView, event);
        if (!action) return;
        event.preventDefault();
        if (action === 'escape') hidePanel();
        else if (action === 'undo') sendAction('undo', {});
        else if (action === 'correct') sendAction('correct', {});
        else dispatchStudyAction(action);
      }

      function handlePointerDown(event) {
        if (!event || isEditableTarget(event.target)) return;
        focusRoot();
      }

      // ---------- title-bar drag (in-page, memory only) ----------
      function beginDrag(event) {
        if (!shouldStartPanelDrag(event) || typeof window === 'undefined') return;
        event.preventDefault();
        if (dragCleanupRef.current) dragCleanupRef.current();
        const start = geometryRef.current;
        const startX = asNumber(event.clientX, 0);
        const startY = asNumber(event.clientY, 0);
        const capture = event.currentTarget || event.target;
        const pointerId = event.pointerId;
        if (capture && typeof capture.setPointerCapture === 'function' && pointerId !== undefined) {
          try { capture.setPointerCapture(pointerId); } catch (error) { /* pointer already gone */ }
        }
        setDragging(true);
        const onMove = function (moveEvent) {
          if (mountedRef.current) {
            // A resize or a completed settings request may change the fitted
            // size mid-drag. Keep only the starting position, never its size.
            const preset = currentWindowPreset(viewRef.current);
            const fitted = fitGeometry(null, preset);
            const moved = movedGeometry({ x: start.x, y: start.y, w: fitted.w, h: fitted.h },
              asNumber(moveEvent.clientX, startX) - startX,
              asNumber(moveEvent.clientY, startY) - startY);
            const nextAnchor = fitAnchor(anchorFromGeometry(moved), preset);
            anchorRef.current = nextAnchor;
            setAnchor(nextAnchor);
          }
        };
        const cleanup = function () {
          window.removeEventListener('pointermove', onMove);
          window.removeEventListener('pointerup', cleanup);
          window.removeEventListener('pointercancel', cleanup);
          window.removeEventListener('blur', cleanup);
          if (capture && typeof capture.releasePointerCapture === 'function' && pointerId !== undefined) {
            try { capture.releasePointerCapture(pointerId); } catch (error) { /* already released */ }
          }
          dragCleanupRef.current = null;
          if (mountedRef.current) setDragging(false);
        };
        dragCleanupRef.current = cleanup;
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', cleanup);
        window.addEventListener('pointercancel', cleanup);
        window.addEventListener('blur', cleanup);
      }

      // ---------- API handed to the pure renderers ----------
      const api = {
        send: sendAction,
        hide: hidePanel,
        retry: retryError,
        catalogDraft: catalogDraft,
        onCatalogQuery: setCatalogDraft,
        commitCatalogQuery: commitCatalogQuery,
        pendingOrder: pendingOrder,
        setOrder: setOrder,
        startBook: startBook,
        beginDrag: beginDrag,
      };

      const themeKey = asString(view && view.theme, DEFAULT_THEME);
      const rootStyle = themeStyle(themeKey);
      const rootClassName = 'dsh-vocab-root';
      const themeLabel = THEME_NAMES[themeKey] || themeKey;

      if (hidden) {
        return h('div', {
          className: rootClassName,
          style: rootStyle,
          ref: rootRef,
          tabIndex: -1,
          onKeyDown: handleKeyDown,
          role: 'region',
          'aria-label': '背单词浮层（已关闭）',
        }, h(ClosedEntry, {
          position: entryPos,
          open: showPanel,
          onMove: function (x, y) {
            const nextAnchor = anchorFromEntry({ x: x, y: y }, currentWindowPreset(viewRef.current));
            anchorRef.current = nextAnchor;
            setAnchor(nextAnchor);
          },
        }));
      }

      let content = null;
      if (!view) {
        if (phase === 'error') {
          content = h('div', { className: 'va-unknown' },
            h('div', { className: 'va-strong' }, '背单词状态加载失败'),
            h('small', null, error ? asString(error.message, '') : '请稍后重试。'),
            h('div', { className: 'va-actions' },
              buttonEl('重试', {
                className: 'va-btn-plain',
                ariaLabel: '重新加载背单词状态',
                onClick: function () { loadState(false); },
              })
            )
          );
        } else {
          content = h('div', { className: 'va-loading' }, '正在加载背单词…');
        }
      } else {
        content = renderScreen(displayView, api);
      }

      const errorBar = renderErrorBar(error, {
        retry: retryError,
        dismiss: function () { setError(null); },
      });

      return h('div', {
        className: rootClassName,
        style: rootStyle,
        ref: rootRef,
        tabIndex: -1,
        onKeyDown: handleKeyDown,
        onPointerDown: handlePointerDown,
        role: 'region',
        'aria-label': '背单词浮层',
        'data-theme': themeKey,
        'data-screen': screen || 'none',
        'data-theme-label': themeLabel,
      },
      h('section', {
        className: 'dsh-vocab-panel' + (windowPreset.key === 'mini' ? ' va-mini' : '') + (dragging ? ' va-dragging' : ''),
        style: {
          left: geometry.x + 'px',
          top: geometry.y + 'px',
          width: geometry.w + 'px',
          height: geometry.h + 'px',
        },
        role: 'dialog',
        'aria-modal': 'false',
        'aria-label': '背单词',
      },
      view ? renderHeader(displayView, api) : renderHeader({ screen: 'loading', canPause: false }, api),
      view ? renderStatusBar(displayView) : null,
      errorBar,
      h('div', { className: 'va-body' }, content),
      ));
    }

    // ---- Plugin entry ----
    exports.name = 'vocab-app';
    exports.inject = ['slots'];
    function apply(ctx) {
      if (!ctx || typeof ctx !== 'object') return;
      ctx.effect(() => installStyles(), 'vocab-app: styles');
      if (!ctx.slots || typeof ctx.slots.inject !== 'function' || typeof ctx.slots.register !== 'function') {
        if (typeof console !== 'undefined' && console.warn) {
          console.warn('[vocab-app] host has no slots service; overlay not registered');
        }
        return;
      }
      ctx.effect(() => ctx.slots.inject('shell.overlay', () => ctx.slots.register({ name: 'shell.overlay', id: 'vocab-app', order: 45 }, VocabApp)), 'vocab-app: shell overlay');
    }

    exports.apply = apply;

    // Test-only surface: pure helpers and renderers are exposed so a Node test
    // can smoke-render every screen through a minimal React stub.
    exports.__testing = {
      THEMES: THEMES,
      THEME_KEYS: THEME_KEYS,
      DEFAULT_KEYS: DEFAULT_KEYS,
      BINDING_KEYS: BINDING_KEYS,
      renderScreen: renderScreen,
      renderHeader: renderHeader,
      renderStatusBar: renderStatusBar,
      themeStyle: themeStyle,
      eventMatchesBinding: eventMatchesBinding,
      captionOf: captionOf,
      installStyles: installStyles,
      collectText: collectText,
      initialGeometry: initialGeometry,
      fitGeometry: fitGeometry,
      movedGeometry: movedGeometry,
      anchorFromGeometry: anchorFromGeometry,
      fitAnchor: fitAnchor,
      geometryFromAnchor: geometryFromAnchor,
      entryFromAnchor: entryFromAnchor,
      anchorFromEntry: anchorFromEntry,
      reviewDue: reviewDue,
      VocabApp: VocabApp,
      shouldStartPanelDrag: shouldStartPanelDrag,
      clampEntryPosition: clampEntryPosition,
      windowPresets: windowPresets,
      currentWindowPreset: currentWindowPreset,
      resolveStudyKey: resolveStudyKey,
      ClosedEntry: ClosedEntry,
      FALLBACK_WINDOW_PRESETS: FALLBACK_WINDOW_PRESETS,
      ENTRY_MOVE_TOLERANCE: ENTRY_MOVE_TOLERANCE,
      screenNames: ['welcome', 'front', 'back', 'empty', 'choice', 'choice_back', 'settings', 'books', 'catalog', 'history', 'quiz', 'result', 'summary', 'building'],
    };

    return module.exports;
  },
});
