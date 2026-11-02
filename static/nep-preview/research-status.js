(() => {
  const target = document.querySelector('[data-site-build-meta]');
  if (!target) return;

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
})();
