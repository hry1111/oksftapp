function truncate(text, max) {
  if (!text) return '';
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/**
 * X投稿本文を組み立てる。日本語(全角)中心の文章になるため、
 * 実際の重み付き文字数(280)より十分短い商品名80文字を上限にしている。
 */
export function composeTweet({ item, previousPrice, discountRate, hashtags = [] }) {
  const percentOff = Math.round(discountRate * 100);
  const name = truncate(item.name, 80);

  const lines = [
    '🉐値下げ発見！おすすめ商品',
    name,
    `¥${previousPrice.toLocaleString('ja-JP')} → ¥${item.price.toLocaleString('ja-JP')}（${percentOff}%OFF）`,
    item.url,
    hashtags.join(' '),
  ].filter(Boolean);

  return lines.join('\n');
}
