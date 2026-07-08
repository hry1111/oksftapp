import aws4 from 'aws4';

const PATH = '/paapi5/getitems';
const TARGET = 'com.amazon.paapi5.v1.ProductAdvertisingAPIv1.GetItems';

// 既定はAmazon.co.jp。他国のマーケットプレイスを使う場合は
// AMAZON_HOST / AMAZON_REGION / AMAZON_MARKETPLACE で上書きする。
const DEFAULT_HOST = 'webservices.amazon.co.jp';
const DEFAULT_REGION = 'us-west-2';
const DEFAULT_MARKETPLACE = 'www.amazon.co.jp';

// PA-APIのGetItemsは1リクエストにつき最大10件のASINまで指定できる。
export const MAX_ITEMS_PER_REQUEST = 10;

/**
 * ASINの配列（最大10件）をまとめて1回のGetItemsで取得する。
 * レート制限が厳しい（新規アカウントは1TPSから）ため、可能な限りまとめて呼び出す。
 * 戻り値は { [asin]: 正規化された商品情報 } の形。
 */
export async function fetchItems(asins, credentials) {
  if (!asins.length) return {};
  if (asins.length > MAX_ITEMS_PER_REQUEST) {
    throw new Error(`fetchItemsは一度に最大${MAX_ITEMS_PER_REQUEST}件までしか指定できません。`);
  }

  const {
    accessKey,
    secretKey,
    partnerTag,
    host = DEFAULT_HOST,
    region = DEFAULT_REGION,
    marketplace = DEFAULT_MARKETPLACE,
  } = credentials;

  const body = {
    ItemIds: asins,
    Resources: ['ItemInfo.Title', 'Offers.Listings.Price', 'Images.Primary.Medium'],
    PartnerTag: partnerTag,
    PartnerType: 'Associates',
    Marketplace: marketplace,
  };

  const requestOptions = {
    host,
    path: PATH,
    service: 'ProductAdvertisingAPI',
    region,
    method: 'POST',
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'content-encoding': 'amz-1.0',
      'x-amz-target': TARGET,
    },
    body: JSON.stringify(body),
  };

  aws4.sign(requestOptions, { accessKeyId: accessKey, secretAccessKey: secretKey });

  const res = await fetch(`https://${host}${PATH}`, {
    method: 'POST',
    headers: requestOptions.headers,
    body: requestOptions.body,
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    const message = data?.Errors?.map((e) => `${e.Code}: ${e.Message}`).join(', ') || res.statusText;
    throw new Error(`Amazon PA-APIエラー (${res.status}): ${message}`);
  }

  for (const err of data.Errors ?? []) {
    console.warn(`Amazon PA-API警告 (${err.Code}): ${err.Message}`);
  }

  const result = {};
  for (const item of data.ItemsResult?.Items ?? []) {
    const listing = item.Offers?.Listings?.[0];
    if (!listing) continue; // 在庫切れ等で価格が取得できない商品はスキップ
    result[item.ASIN] = {
      key: `amazon:${item.ASIN}`,
      name: item.ItemInfo?.Title?.DisplayValue || item.ASIN,
      price: listing.Price?.Amount,
      url: item.DetailPageURL,
      imageUrl: item.Images?.Primary?.Medium?.URL || null,
    };
  }
  return result;
}
