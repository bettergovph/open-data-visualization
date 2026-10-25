(() => {
  const dataNode = document.getElementById('mpb-data');
  const select = document.getElementById('mpbMunicipalitySelect');
  const plot = document.getElementById('mpbMunicipalityPlot');
  const summary = document.getElementById('mpbMapSummary');
  const story = document.getElementById('mpbMapStory');
  const projectCard = document.getElementById('mpbMapProjectCard');
  if (!dataNode || !select || !plot || !summary) return;

  const init = boundaryData => {
  const source = JSON.parse(dataNode.textContent).coordinateProximity || {};
  const pairs = source.current || [];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
  const prettyPlace = value => String(value || '').replace(/\b[a-z]/g, ch => ch.toUpperCase());
  const groupName = row => {
    if (row.municipalityGroup) return row.municipalityGroup;
    const parts = String(row.barangay || '').split(' · ');
    return parts.length >= 3 ? `${parts[1]} · ${parts[2]}` : 'Municipality unresolved';
  };
  const groups = new Map();
  for (const row of pairs) {
    const name = groupName(row);
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(row);
  }
  const spread = rows => Math.max(0, ...rows.map(row => Number(row.distanceMeters) || 0));
  const sortedGroups = [...groups.entries()].sort((a, b) => spread(b[1]) - spread(a[1]) || a[0].localeCompare(b[0]));
  const boundaries = new Map((boundaryData?.features || []).map(feature => [feature.municipalityGroup, feature]));
  const projectDetails = source.projectDetails || {};
  function insideBoundary(point, feature) {
    if (!feature?.rings?.length) return null;
    let inside = false;
    for (const ring of feature.rings) {
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [xi, yi] = ring[i], [xj, yj] = ring[j];
        const crosses = (yi > point.lat) !== (yj > point.lat) && point.lon < (xj - xi) * (point.lat - yi) / (yj - yi) + xi;
        if (crosses) inside = !inside;
      }
    }
    return inside;
  }
  if (!sortedGroups.length) {
    select.disabled = true;
    plot.innerHTML = '<p>No same-barangay project pairs have usable coordinates.</p>';
    summary.textContent = 'No coordinate-ready municipality groups are available.';
    return;
  }
  if (story) {
    const farthest = pairs.reduce((best, row) => Number(row.distanceMeters) > Number(best.distanceMeters) ? row : best, pairs[0]);
    const closePairs = pairs.filter(row => Number(row.distanceMeters) < 50).length;
    const place = String(farthest.barangay || 'the same barangay label').split(' · ').map(prettyPlace).join(', ');
    const distanceKm = (Number(farthest.distanceMeters) / 1000).toFixed(1);
    const feature = boundaries.get(farthest.municipalityGroup);
    const outside = feature && (insideBoundary({lat:farthest.leftCoordinates.latitude,lon:farthest.leftCoordinates.longitude},feature) === false || insideBoundary({lat:farthest.rightCoordinates.latitude,lon:farthest.rightCoordinates.longitude},feature) === false);
    const boundaryNote = outside ? ' At least one printed point also plots outside the named municipality outline.' : '';
    story.innerHTML = `<article class="mpb-story-lead"><div><span class="mpb-story-kicker">A location mismatch to check · HGAB 3rd</span><h4>Both entries name ${esc(place)}. Their listed points are ${distanceKm} km apart.</h4><p>The coordinates printed in these two project titles are ${esc(formatDistance(farthest.distanceMeters))} apart in a straight line.${boundaryNote} Check their source schedule before deciding whether either location is wrong.</p><ol><li>${esc(farthest.projectName)} <small>${esc(farthest.sourceLabel)}</small></li><li>${esc(farthest.otherProject)} <small>${esc(farthest.otherSource)}</small></li></ol></div><strong class="mpb-story-distance">${distanceKm}<span>km apart</span></strong></article><aside class="mpb-nearby-lead"><strong>${closePairs}</strong><span>pairs have printed locations less than 50 m apart. They may refer to one site, separate nearby buildings, or copied coordinates; the project scope needs review.</span></aside>`;
  }
  for (const [name, rows] of sortedGroups) {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = `${prettyPlace(name)} · ${rows.length} pair${rows.length === 1 ? '' : 's'} · max ${formatDistance(spread(rows))}`;
    select.append(option);
  }
  const requestedPlace = new URLSearchParams(location.search).get('place');
  select.value = groups.has(requestedPlace) ? requestedPlace : sortedGroups[0][0];

  function shareUrl() {
    const url = new URL(location.href);
    url.searchParams.set('place', select.value);
    url.hash = 'mpb-coordinate-proximity';
    return url.href;
  }
  const facebookLink = document.getElementById('mpbMapFacebook');
  const shareStatus = document.getElementById('mpbMapShareStatus');
  const updateShareLinks = () => {
    if (facebookLink) facebookLink.href = `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl())}`;
  };
  updateShareLinks();
  document.getElementById('mpbMapCopyLink')?.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(shareUrl());
      if (shareStatus) shareStatus.textContent = 'Map link copied.';
    } catch {
      const field = document.createElement('textarea');
      field.value = shareUrl(); document.body.append(field); field.select();
      const copied = document.execCommand('copy'); field.remove();
      if (shareStatus) shareStatus.textContent = copied ? 'Map link copied.' : 'Copy failed; copy the page address from your browser.';
    }
  });

  function showProject(projectId) {
    const detail = projectDetails[projectId];
    if (!projectCard || !detail) return;
    const memberCard = member => {
      const name = member.name || member.officialName || 'Representative not resolved';
      const portrait = member.photoUrl
        ? `<a class="mpb-member-portrait-link" href="${esc(member.profileUrl || '#')}" target="_blank" rel="noopener" aria-label="Open official House profile for ${esc(name)}"><img class="mpb-member-portrait" src="${esc(member.photoUrl)}" alt="Portrait of ${esc(name)}" loading="lazy"></a>`
        : '<span class="mpb-member-portrait-empty">Portrait unavailable</span>';
      if (member.resolutionStatus === 'ambiguous_multiple_listed') {
        return `<div class="mpb-member-association"><strong>${esc(member.district)}</strong><p class="mpb-member-caution">The source lists multiple candidates for this seat; none is selected.</p><div class="mpb-member-candidates">${(member.candidates || []).map(candidate => `<article>${candidate.photoUrl ? `<a href="${esc(candidate.profileUrl || '#')}" target="_blank" rel="noopener"><img class="mpb-member-portrait" src="${esc(candidate.photoUrl)}" alt="Portrait of ${esc(candidate.name)}" loading="lazy"></a>` : ''}<span>${esc(candidate.name)}</span></article>`).join('')}</div></div>`;
      }
      return `<div class="mpb-member-association">${portrait}<div><strong>${esc(name)}</strong><span>${esc(member.district || '')}</span>${member.officialName && member.officialName !== name ? `<small>Official roster name: ${esc(member.officialName)}</small>` : ''}${member.profileUrl ? `<a href="${esc(member.profileUrl)}" target="_blank" rel="noopener">House profile ↗</a>` : ''}${member.resolutionStatus === 'no_exact_csiiiv_seat_match' ? '<small>Portrait not matched to a seat in the CSIIIV profile snapshot.</small>' : ''}</div></div>`;
    };
    const place = detail.place || 'Place unresolved';
    const point = detail.coordinate ? `${detail.coordinate.latitude}, ${detail.coordinate.longitude}` : 'No usable printed coordinate';
    projectCard.innerHTML = `<div class="mpb-map-project-head"><div><span class="mpb-map-project-kicker">Selected MPB project · ${esc(projectId)}</span><h4>${esc(detail.projectName)}</h4></div><button type="button" class="mpb-map-project-close" aria-label="Close project details">×</button></div><dl class="mpb-map-project-facts"><dt>Allocation</dt><dd>₱${Number(detail.amountPesos || 0).toLocaleString('en-PH')}</dd><dt>Implementing office</dt><dd>${esc(detail.office || 'Not stated')}</dd><dt>Listed location</dt><dd>${esc(place)} <small>${esc(detail.placeEvidence || '')}</small></dd><dt>Printed coordinate</dt><dd>${esc(point)}</dd><dt>NEP comparison</dt><dd>${esc(detail.insertionStatus)}</dd><dt>Source</dt><dd>${esc(detail.sourceVolume || 'HGAB 3rd reading')} · p. ${esc(detail.sourcePage || 'not recorded')}</dd></dl><h5>Geographic congressional association</h5><p class="mpb-map-project-caution">District association follows the project location in the PH location DB. It describes geographic coverage; it does not imply sponsorship or control.</p>${detail.representativeCards?.length ? `<div class="mpb-member-associations">${detail.representativeCards.map(memberCard).join('')}</div>` : '<p>No unique legislative district was resolved for this project.</p>'}<p class="mpb-profile-source">Representative portraits and House profile links: <a href="https://github.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS/tree/main/DEO2LEG" target="_blank" rel="noopener">CSIIIV DEO2LEG source</a> · ${esc(source.representativeProfileSource?.commit || '')}</p>`;
    projectCard.hidden = false;
    projectCard.querySelector('.mpb-map-project-close').addEventListener('click', () => { projectCard.hidden = true; });
    requestAnimationFrame(() => projectCard.scrollIntoView({block: 'center', behavior: 'smooth'}));
  }

  function formatDistance(meters) {
    return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${Math.round(meters)} m`;
  }
  function lineColor(meters) {
    if (meters < 50) return '#bd3e3e';
    if (meters < 1000) return '#d78a0d';
    if (meters >= 10000) return '#7839a8';
    return '#168277';
  }
  function render() {
    const group = groups.get(select.value) || [];
    const pointsBySource = new Map();
    const addPoint = (row, side) => {
      const sourceId = side === 'left' ? row.sourceLabel : row.otherSource;
      const key = `${sourceId}\n${side === 'left' ? row.projectName : row.otherProject}`;
      if (!pointsBySource.has(key)) {
        const coord = side === 'left' ? row.leftCoordinates : row.rightCoordinates;
        pointsBySource.set(key, {
          key, sourceId, hgabId: sourceId.split(' · ', 1)[0],
          title: side === 'left' ? row.projectName : row.otherProject,
          amount: side === 'left' ? row.currentAllocationPesos : row.otherAllocationPesos,
          lat: Number(coord.latitude), lon: Number(coord.longitude), raw: coord.raw
        });
      }
      return key;
    };
    const plottedPairs = group.map(row => ({
      row, leftKey: addPoint(row, 'left'), rightKey: addPoint(row, 'right')
    }));
    const points = [...pointsBySource.values()].filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lon));
    const boundary = boundaries.get(select.value);
    points.forEach((point, i) => { point.number = i + 1; });
    points.forEach(point => { point.insideBoundary = insideBoundary(point, boundary); });
    const pointByKey = new Map(points.map(point => [point.key, point]));
    const centerLat = points.reduce((sum, point) => sum + point.lat, 0) / points.length;
    const centerLon = points.reduce((sum, point) => sum + point.lon, 0) / points.length;
    const metersPerLonDegree = 111320 * Math.cos(centerLat * Math.PI / 180);
    for (const point of points) {
      point.east = (point.lon - centerLon) * metersPerLonDegree;
      point.north = (point.lat - centerLat) * 111320;
    }
    const outline = (boundary?.rings || []).flatMap(ring => ring.map(([lon,lat]) => ({east:(lon-centerLon)*metersPerLonDegree,north:(lat-centerLat)*111320})));
    const mapExtent = [...points, ...outline];
    const minX = Math.min(...mapExtent.map(p => p.east)), maxX = Math.max(...mapExtent.map(p => p.east));
    const minY = Math.min(...mapExtent.map(p => p.north)), maxY = Math.max(...mapExtent.map(p => p.north));
    const rangeX = Math.max(1, maxX - minX), rangeY = Math.max(1, maxY - minY);
    const box = { x: 70, y: 72, w: 700, h: 340 };
    const scale = Math.min(box.w / rangeX, box.h / rangeY);
    const usedW = rangeX * scale, usedH = rangeY * scale;
    const left = box.x + (box.w - usedW) / 2, top = box.y + (box.h - usedH) / 2;
    const xy = p => ({ x: left + (p.east - minX) * scale, y: top + (maxY - p.north) * scale });
    const coordinates = points.map(p => ({ p, ...xy(p) }));
    const boundaryPath = (boundary?.rings || []).map(ring => ring.map(([lon,lat],index) => {
      const q=xy({east:(lon-centerLon)*metersPerLonDegree,north:(lat-centerLat)*111320});
      return `${index?'L':'M'}${q.x.toFixed(1)},${q.y.toFixed(1)}`;
    }).join(' ')+' Z').join(' ');
    const boundarySvg = boundaryPath ? `<path d="${boundaryPath}" fill="#dcece7" fill-rule="evenodd" stroke="#3e8d80" stroke-width="1.5"><title>${esc(prettyPlace(boundary.municipality))}, ${esc(prettyPlace(boundary.province))} municipal boundary</title></path>` : '';
    const lines = plottedPairs.map(({ row, leftKey, rightKey }) => {
      const a = pointByKey.get(leftKey), b = pointByKey.get(rightKey);
      if (!a || !b) return '';
      const A = xy(a), B = xy(b), distance = Number(row.distanceMeters) || 0;
      return `<line x1="${A.x.toFixed(1)}" y1="${A.y.toFixed(1)}" x2="${B.x.toFixed(1)}" y2="${B.y.toFixed(1)}" stroke="${lineColor(distance)}" stroke-width="${distance < 50 ? 3.5 : 2}" opacity=".72"><title>${esc(formatDistance(distance))}: ${esc(a.title)} ↔ ${esc(b.title)}</title></line>`;
    }).join('');
    const dots = coordinates.map(({ p, x, y }) => {
      const fill = p.insideBoundary === false ? '#bd3e3e' : '#173b49';
      const status = p.insideBoundary === false ? 'Outside selected municipal boundary · verify' : p.insideBoundary === true ? 'Inside selected municipal boundary' : 'No matching municipal boundary available';
      return `<g class="mpb-map-marker" data-project-id="${esc(p.hgabId)}" tabindex="0" role="button" aria-label="Open MPB project details: ${esc(p.title)}"><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="9" fill="${fill}" stroke="#fff" stroke-width="2"><title>${esc(status)} · ${esc(p.title)} · ${esc(p.sourceId)} · ${esc(p.raw)}</title></circle><text x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="middle" fill="#fff" font-size="10" font-weight="700">${p.number}</text></g>`;
    }).join('');
    const maxPair = [...group].sort((a, b) => Number(b.distanceMeters) - Number(a.distanceMeters))[0];
    const minPair = [...group].sort((a, b) => Number(a.distanceMeters) - Number(b.distanceMeters))[0];
    const distinctBarangs = [...new Set(group.map(row => row.barangay).filter(Boolean))];
    const visibleLabel = prettyPlace(select.value);
    const outsideCount = points.filter(point => point.insideBoundary === false).length;
    summary.textContent = `${visibleLabel}: ${points.length} points, ${group.length} pair${group.length === 1 ? '' : 's'}; farthest ${formatDistance(maxPair.distanceMeters)}, closest ${formatDistance(minPair.distanceMeters)}.${outsideCount ? ` ${outsideCount} point${outsideCount===1?'':'s'} plot outside the municipal outline and need checking.` : ''}`;
    const major = Math.max(rangeX, rangeY);
    const target = major / 4;
    const magnitude = Math.pow(10, Math.floor(Math.log10(Math.max(1, target))));
    const unit = target / magnitude;
    const nice = (unit >= 5 ? 5 : unit >= 2 ? 2 : 1) * magnitude;
    const barPx = nice * scale;
    const unitLabel = nice >= 1000 ? `${(nice / 1000).toFixed(nice % 1000 ? 1 : 0)} km` : `${Math.round(nice)} m`;
    const svg = `<svg viewBox="0 0 820 480" role="img" aria-label="${esc(visibleLabel)}: municipality outline, ${points.length} MPB project coordinates and ${group.length} pairwise distances"><title>${esc(visibleLabel)} MPB coordinate view</title><rect x="0" y="0" width="820" height="480" fill="#fff"/><text x="20" y="28" font-size="17" font-weight="700" fill="#18303b">${esc(visibleLabel)}</text><text x="20" y="49" font-size="12" fill="#526773">Municipal outline and project locations from printed coordinates</text><path d="M 785 70 L 785 38 M 785 38 L 779 48 M 785 38 L 791 48" fill="none" stroke="#18303b" stroke-width="2"/><text x="785" y="28" text-anchor="middle" font-size="11" fill="#18303b">N</text><rect x="${box.x}" y="${box.y}" width="${box.w}" height="${box.h}" rx="8" fill="#f7faf9" stroke="#d3dfdc"/>${boundarySvg}${lines}${dots}<line x1="82" y1="448" x2="${(82 + Math.max(15, barPx)).toFixed(1)}" y2="448" stroke="#18303b" stroke-width="4"/><line x1="82" y1="442" x2="82" y2="454" stroke="#18303b" stroke-width="2"/><line x1="${(82 + Math.max(15, barPx)).toFixed(1)}" y1="442" x2="${(82 + Math.max(15, barPx)).toFixed(1)}" y2="454" stroke="#18303b" stroke-width="2"/><text x="${(90 + Math.max(15, barPx)).toFixed(1)}" y="452" font-size="11" fill="#18303b">${unitLabel}</text><text x="770" y="452" text-anchor="end" font-size="11" fill="#526773">${points.length} plotted points</text></svg>`;
    const pairRows = [...group].sort((a, b) => Number(b.distanceMeters) - Number(a.distanceMeters)).map(row => `<tr><td>${esc(row.sourceLabel)}<br>${esc(row.projectName)}</td><td>${esc(row.otherSource)}<br>${esc(row.otherProject)}</td><td>${esc(formatDistance(row.distanceMeters))}</td><td>${esc(row.municipalityEvidence || row.barangayEvidence || '')}</td></tr>`).join('');
    const pointRows = points.map(point => `<tr><td>${point.number}</td><td>${esc(point.sourceId)}</td><td><button class="mpb-point-open" type="button" data-project-id="${esc(point.hgabId)}">${esc(point.title)}</button></td><td>${esc(point.raw)}</td><td>${point.insideBoundary === false ? 'Outside municipal outline · verify' : point.insideBoundary === true ? 'Inside municipal outline' : 'Boundary unavailable'}</td></tr>`).join('');
    plot.innerHTML = `${svg}<table class="mpb-project-list"><thead><tr><th>Source point</th><th>Project</th><th>Printed coordinate pair</th><th>Boundary check</th></tr></thead><tbody>${pointRows}</tbody></table><h4>Pair distances · farthest first</h4><table class="mpb-project-list"><thead><tr><th>First project · source</th><th>Second project · source</th><th>Straight-line separation</th><th>Place evidence</th></tr></thead><tbody>${pairRows}</tbody></table>`;
    plot.querySelectorAll('[data-project-id]').forEach(marker => {
      marker.addEventListener('click', () => showProject(marker.dataset.projectId));
      marker.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); showProject(marker.dataset.projectId); }
      });
    });
  }
  select.addEventListener('change', () => { updateShareLinks(); render(); });
  render();
  };
  fetch('mpb-municipality-boundaries.json?v=20261025-boundary-view')
    .then(response => { if (!response.ok) throw new Error('Boundary data unavailable'); return response.json(); })
    .then(init)
    .catch(() => init(null));
})();
