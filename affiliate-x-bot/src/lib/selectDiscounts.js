/**
 * 前回価格と今回価格を比較し、値下げ幅がしきい値以上で、かつ
 * クールダウン期間を過ぎている商品だけを投稿候補として判定する。
 */
export function evaluateItem({ item, watchItem, history, postLog, now, defaultThreshold, defaultCooldownDays }) {
  const prev = history[item.itemCode];
  const threshold = watchItem.minDiscountRate ?? defaultThreshold;
  const cooldownDays = watchItem.cooldownDays ?? defaultCooldownDays;

  if (!prev) {
    return { item, watchItem, eligible: false, reason: 'no-history' };
  }

  if (!Number.isFinite(item.price) || item.price >= prev.lastPrice) {
    return { item, watchItem, eligible: false, reason: 'no-drop' };
  }

  const discountRate = (prev.lastPrice - item.price) / prev.lastPrice;
  if (discountRate < threshold) {
    return { item, watchItem, eligible: false, reason: 'below-threshold', discountRate };
  }

  const lastPostedAt = postLog[item.itemCode];
  if (lastPostedAt) {
    const daysSincePost = (now - new Date(lastPostedAt).getTime()) / 86400000;
    if (daysSincePost < cooldownDays) {
      return { item, watchItem, eligible: false, reason: 'cooldown', discountRate };
    }
  }

  return {
    item,
    watchItem,
    eligible: true,
    reason: 'ok',
    discountRate,
    previousPrice: prev.lastPrice,
  };
}
