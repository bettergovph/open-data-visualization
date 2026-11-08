(() => {
  const target = document.querySelector('[data-site-build-meta]');
  if (target) {
    fetch('/static/nep-preview/site-build-info.json', { cache: 'no-store' })
      .then(response => {
        if (!response.ok) throw new Error('Build metadata is unavailable');
        return response.json();
      })
      .then(info => {
        if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(info.deployedAtUtc || '') || !/^[0-9a-f]{40}$/i.test(info.commit || '')) {
          throw new Error('Build metadata is invalid');
        }
        target.replaceChildren(document.createTextNode(`Deployed ${info.deployedAtUtc.replace('T', ' ').replace('Z', ' UTC')} · `));
        const link = document.createElement('a');
        link.href = `https://github.com/bettergovph/open-data-visualization/commit/${info.commit}`;
        link.textContent = info.commit.slice(0, 10);
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.setAttribute('aria-label', `View deployed source commit ${info.commit}`);
        target.append(link);
      })
      .catch(() => {
        target.textContent = 'Deployment build information unavailable';
      });
  }

  // Satirical disclaimer banner: no cookies are used. Dismissal is remembered
  // in sessionStorage for this tab so it stays closed while browsing reports.
  const disclaimer = document.getElementById('report-evidence-notice');
  if (!disclaimer || document.getElementById('disclaimer-cookie-satire')) return;
  const dismissalKey = 'bettergov-disclaimer-banner-dismissed';
  try {
    if (window.sessionStorage.getItem(dismissalKey) === '1') return;
  } catch (_) {
    // If browser storage is unavailable, keep the banner dismissible per page.
  }

  const style = document.createElement('style');
  style.id = 'disclaimer-cookie-satire-style';
  style.textContent = `
    #disclaimer-cookie-satire{position:fixed;z-index:10000;inset:auto 18px 18px;box-sizing:border-box;width:min(620px,calc(100vw - 36px));max-height:min(78vh,720px);overflow:auto;margin:0;padding:0;border:1px solid #b8c5d8;border-radius:14px;background:#fff;color:#212121;box-shadow:0 14px 48px #001b4d38;font:14px/1.5 system-ui,sans-serif}
    #disclaimer-cookie-satire *{box-sizing:border-box}
    #disclaimer-cookie-satire .dcs-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 17px;background:#00246A;color:#fff;border-bottom:3px solid #FCD116}
    #disclaimer-cookie-satire .dcs-head strong{font-size:15px}
    #disclaimer-cookie-satire .dcs-body{padding:15px 17px}
    #disclaimer-cookie-satire p{margin:0 0 10px}
    #disclaimer-cookie-satire .dcs-fact{font-weight:650}
    #disclaimer-cookie-satire .dcs-punchline{margin-top:12px;padding-top:10px;border-top:1px solid #e0e0e0;font-weight:750}
    #disclaimer-cookie-satire details{margin:10px 0}
    #disclaimer-cookie-satire summary{color:#0038A8;font-weight:700;cursor:pointer}
    #disclaimer-cookie-satire .dcs-full{max-height:32vh;overflow:auto;margin-top:8px;padding:10px;border-left:3px solid #FCD116;background:#f5f7fa;font-size:12px}
    #disclaimer-cookie-satire .dcs-full>*{max-width:none!important}
    #disclaimer-cookie-satire .dcs-actions{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:12px}
    #disclaimer-cookie-satire button{min-height:42px;padding:9px 16px;border:0;border-radius:8px;background:#0038A8;color:#fff;font:700 14px/1.2 system-ui,sans-serif;cursor:pointer}
    #disclaimer-cookie-satire button:hover{background:#00246A}
    #disclaimer-cookie-satire button:focus-visible,#disclaimer-cookie-satire summary:focus-visible{outline:3px solid #FCD116;outline-offset:2px}
    #disclaimer-cookie-satire .dcs-note{color:#616161;font-size:11px}
    @media(max-width:560px){#disclaimer-cookie-satire{inset:auto 8px 8px;width:calc(100vw - 16px);max-height:82vh}#disclaimer-cookie-satire .dcs-head,#disclaimer-cookie-satire .dcs-body{padding:12px}}
  `;
  document.head.append(style);

  const banner = document.createElement('aside');
  banner.id = 'disclaimer-cookie-satire';
  banner.setAttribute('role', 'region');
  banner.setAttribute('aria-label', 'Disclaimer notice');

  const head = document.createElement('div');
  head.className = 'dcs-head';
  const heading = document.createElement('strong');
  heading.textContent = 'Cookie preferences';
  head.append(heading);

  const body = document.createElement('div');
  body.className = 'dcs-body';
  const fact = document.createElement('p');
  fact.className = 'dcs-fact';
  fact.textContent = 'These are preliminary, document-based observations—not findings of wrongdoing. A flag, missing match, repeated title, or outlier is a prompt for review. Source coverage, parsing, matching, and context may be incomplete or wrong. Check the cited records and share corrections.';
  const fullDetails = document.createElement('details');
  const summary = document.createElement('summary');
  summary.textContent = 'Read the full page disclaimer';
  const fullCopy = document.createElement('div');
  fullCopy.className = 'dcs-full';
  const copy = disclaimer.cloneNode(true);
  copy.removeAttribute('id');
  fullCopy.append(copy);
  fullDetails.append(summary, fullCopy);
  const punchline = document.createElement('p');
  punchline.className = 'dcs-punchline';
  punchline.textContent = 'This disclaimer is good enough for an Inquirer opinion piece.';
  const actions = document.createElement('div');
  actions.className = 'dcs-actions';
  const note = document.createElement('span');
  note.className = 'dcs-note';
  note.textContent = 'No need to accept any cookies—we have none.';
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = 'Accept none';
  button.addEventListener('click', () => {
    try {
      window.sessionStorage.setItem(dismissalKey, '1');
    } catch (_) {
      // Dismissal still works on this page when browser storage is unavailable.
    }
    banner.remove();
  });
  actions.append(note, button);
  body.append(fact, fullDetails, punchline, actions);
  banner.append(head, body);
  document.body.append(banner);
})();
