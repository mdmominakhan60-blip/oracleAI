export class ChartRenderer {
  line(element, days, series) {
    const width = 700;
    const height = 190;
    const pad = { left: 34, right: 8, top: 12, bottom: 20 };
    const max = Math.max(1, ...series.flatMap((item) => item.values));
    const x = (index) => pad.left + (index * (width - pad.left - pad.right)) / Math.max(1, days.length - 1);
    const y = (value) => pad.top + (1 - value / max) * (height - pad.top - pad.bottom);

    let svg = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">`;
    for (let grid = 0; grid <= 3; grid += 1) {
      const gridY = pad.top + (grid * (height - pad.top - pad.bottom)) / 3;
      const label = Math.round(max - (grid * max) / 3);
      svg += `<line x1="${pad.left}" y1="${gridY}" x2="${width - pad.right}" y2="${gridY}" stroke="rgba(255,255,255,.07)"/>`;
      svg += `<text x="${pad.left - 6}" y="${gridY + 3}" text-anchor="end" font-size="9" fill="#9c94bd">${label}</text>`;
    }
    series.forEach((item) => {
      const points = item.values.map((value, index) => `${x(index)},${y(value)}`).join(' ');
      if (item.fill) svg += `<polygon points="${pad.left},${y(0)} ${points} ${x(days.length - 1)},${y(0)}" fill="${item.color}" opacity=".12"/>`;
      svg += `<polyline points="${points}" fill="none" stroke="${item.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    });
    const step = Math.max(1, Math.ceil(days.length / 7));
    days.forEach((day, index) => {
      if (index % step && index !== days.length - 1) return;
      svg += `<text x="${x(index)}" y="${height - 4}" text-anchor="middle" font-size="9" fill="#9c94bd">${day.slice(8, 10)}.${day.slice(5, 7)}</text>`;
    });
    element.innerHTML = `${svg}</svg>`;
  }

  bar(element, days, values, color = '#e8c56b') {
    const width = 700;
    const height = 190;
    const pad = { left: 34, right: 8, top: 12, bottom: 20 };
    const max = Math.max(1, ...values);
    const barWidth = Math.max(2, (width - pad.left - pad.right) / Math.max(1, values.length) - 2);
    let svg = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">`;
    for (let grid = 0; grid <= 3; grid += 1) {
      const gridY = pad.top + (grid * (height - pad.top - pad.bottom)) / 3;
      svg += `<line x1="${pad.left}" y1="${gridY}" x2="${width - pad.right}" y2="${gridY}" stroke="rgba(255,255,255,.07)"/>`;
      svg += `<text x="${pad.left - 6}" y="${gridY + 3}" text-anchor="end" font-size="9" fill="#9c94bd">${Math.round(max - (grid * max) / 3)}</text>`;
    }
    values.forEach((value, index) => {
      const barHeight = (value / max) * (height - pad.top - pad.bottom);
      const barX = pad.left + (index * (width - pad.left - pad.right)) / Math.max(1, values.length);
      svg += `<rect x="${barX}" y="${height - pad.bottom - barHeight}" width="${barWidth}" height="${barHeight}" rx="2" fill="${color}" opacity="${value ? .85 : .2}"/>`;
    });
    const step = Math.max(1, Math.ceil(days.length / 7));
    days.forEach((day, index) => {
      if (index % step && index !== days.length - 1) return;
      const barX = pad.left + (index * (width - pad.left - pad.right)) / Math.max(1, values.length);
      svg += `<text x="${barX + barWidth / 2}" y="${height - 4}" text-anchor="middle" font-size="9" fill="#9c94bd">${day.slice(8, 10)}.${day.slice(5, 7)}</text>`;
    });
    element.innerHTML = `${svg}</svg>`;
  }
}

export const charts = new ChartRenderer();
