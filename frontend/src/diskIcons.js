const iconModules = import.meta.glob('../../assets/images/驱动盘/*.png', {
  eager: true,
  query: '?url',
  import: 'default',
});

const ICON_BY_NAME = Object.fromEntries(
  Object.entries(iconModules).map(([path, url]) => {
    const fileName = path.split('/').pop() || '';
    return [normalizeName(fileName.replace(/\.png$/i, '')), url];
  }),
);

const NAME_ALIASES = {
  搖摆爵士: '摇摆爵士',
};

function normalizeName(value) {
  return String(value || '')
    .trim()
    .replace(/\s+/g, '')
    .replace(/[［【\[]\d+[］】\]]$/g, '');
}

export function diskIconFor(setName) {
  const normalized = normalizeName(setName);
  const canonical = NAME_ALIASES[normalized] || normalized;
  return ICON_BY_NAME[canonical] || '';
}
