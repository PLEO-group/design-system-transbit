export function isTokenNode(node) {
  return (
    node &&
    typeof node === 'object' &&
    (Object.prototype.hasOwnProperty.call(node, '$value') ||
      Object.prototype.hasOwnProperty.call(node, 'value'))
  );
}

export function tokenValue(node) {
  return Object.prototype.hasOwnProperty.call(node, '$value') ? node.$value : node.value;
}

export function tokenType(node) {
  return Object.prototype.hasOwnProperty.call(node, '$type') ? node.$type : node.type;
}

export function toKebab(value) {
  return String(value)
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/[\s_./]+/g, '-')
    .replace(/-+/g, '-')
    .toLowerCase();
}

export function cssVarName(path, options = {}) {
  const parts = path.map(toKebab).filter(Boolean);

  if (options.type === 'color' && parts[0] !== 'color') {
    parts.unshift('color');
  }

  return `--${parts.join('-')}`;
}

export function referenceToCssVar(value, type) {
  if (typeof value !== 'string' || !value.startsWith('{') || !value.endsWith('}')) {
    return value;
  }

  return `var(${cssVarName(value.slice(1, -1).split('.'), { type })})`;
}

export function flattenTokens(obj, prefix = []) {
  if (isTokenNode(obj)) {
    const type = tokenType(obj);
    const value = tokenValue(obj);

    return [
      {
        path: prefix,
        name: cssVarName(prefix, { type }),
        type,
        value,
        cssValue: referenceToCssVar(value, type),
      },
    ];
  }

  if (!obj || typeof obj !== 'object') {
    return [];
  }

  return Object.entries(obj).flatMap(([key, value]) => {
    if (key.startsWith('$')) {
      return [];
    }

    return flattenTokens(value, [...prefix, key]);
  });
}

export function sortTokens(tokens) {
  return [...tokens].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
}

export function groupByFirstSegment(tokens) {
  return tokens.reduce((acc, token) => {
    const group = token.path[0] || 'tokens';
    acc[group] = acc[group] || [];
    acc[group].push(token);
    return acc;
  }, {});
}
