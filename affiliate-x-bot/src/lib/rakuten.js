const ENDPOINT = 'https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601';

/**
 * 楽天市場商品検索APIで itemCode（例: "shop-code:1000001"）を指定して単一商品の
 * 現在価格・商品名・アフィリエイトURL・画像URLを取得する。
 */
export async function fetchItem(itemCode, { applicationId, affiliateId }) {
  const url = new URL(ENDPOINT);
  url.searchParams.set('format', 'json');
  url.searchParams.set('itemCode', itemCode);
  url.searchParams.set('applicationId', applicationId);
  if (affiliateId) url.searchParams.set('affiliateId', affiliateId);
  url.searchParams.set('hits', '1');

  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`楽天APIエラー (${res.status}): ${await res.text()}`);
  }
  const data = await res.json();
  const item = data.Items?.[0]?.Item;
  if (!item) return null;

  return {
    key: `rakuten:${itemCode}`,
    name: item.itemName,
    price: item.itemPrice,
    url: item.affiliateUrl || item.itemUrl,
    imageUrl: item.mediumImageUrls?.[0]?.imageUrl || null,
    shopName: item.shopName || null,
  };
}
