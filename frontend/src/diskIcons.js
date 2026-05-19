const KNOWN_DISK_ICON_NAMES = new Set([
  '云岿如我',
  '原始朋克',
  '囚徒手记',
  '如影相随',
  '山大王',
  '折枝剑歌',
  '拂晓生花',
  '月光骑士颂',
  '极地重金属',
  '沧浪行歌',
  '河豚电音',
  '法厄同之歌',
  '流光咏叹',
  '混沌爵士',
  '混沌重金属',
  '激素朋克',
  '炎狱重金属',
  '自由蓝调',
  '雪兔梦游仙境',
  '震星迪斯科',
  '静听嘉音',
]);

function normalizeName(value) {
  return String(value || '').trim().replace(/\s+/g, '');
}

function assetUrl(name) {
  const directory = encodeURIComponent('驱动盘');
  const fileName = `${encodeURIComponent(name)}.png`;
  return new URL(`../../assets/images/${directory}/${fileName}`, window.location.href).href;
}

export function diskIconFor(setName) {
  const normalized = normalizeName(setName);
  if (!KNOWN_DISK_ICON_NAMES.has(normalized)) return '';
  return assetUrl(normalized);
}
