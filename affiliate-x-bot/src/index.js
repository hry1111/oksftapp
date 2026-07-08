import path from 'node:path';
import { fetchItem as fetchRakutenItem } from './lib/rakuten.js';
import { fetchItems as fetchAmazonItems, MAX_ITEMS_PER_REQUEST as AMAZON_BATCH_SIZE } from './lib/amazon.js';
import { loadJson, saveJson } from './lib/jsonStore.js';
import { evaluateItem } from './lib/selectDiscounts.js';
import { composeTweet } from './lib/composeTweet.js';
import { createXClient, postTweet } from './lib/xClient.js';

const CONFIG_PATH = path.resolve('config/config.json');
const WATCHLIST_PATH = path.resolve('config/watchlist.json');
const PRICE_HISTORY_PATH = path.resolve('data/price-history.json');
const POST_LOG_PATH = path.resolve('data/post-log.json');

const DRY_RUN = process.env.DRY_RUN === 'true';

function chunk(arr, size) {
  const chunks = [];
  for (let i = 0; i < arr.length; i += size) chunks.push(arr.slice(i, i + size));
  return chunks;
}

async function fetchRakutenWatchItems(watchItems) {
  const fetched = new Map();
  if (!watchItems.length) return fetched;

  const { RAKUTEN_APP_ID, RAKUTEN_AFFILIATE_ID } = process.env;
  if (!RAKUTEN_APP_ID) {
    throw new Error('RAKUTEN_APP_ID が設定されていません。.env.example を参照してください。');
  }

  for (const watchItem of watchItems) {
    try {
      const item = await fetchRakutenItem(watchItem.itemCode, {
        applicationId: RAKUTEN_APP_ID,
        affiliateId: RAKUTEN_AFFILIATE_ID,
      });
      if (item) fetched.set(watchItem, item);
      else console.warn(`[${watchItem.id}] 商品が見つかりませんでした (itemCode: ${watchItem.itemCode})`);
    } catch (err) {
      console.error(`[${watchItem.id}] 楽天商品取得エラー: ${err.message}`);
    }
  }
  return fetched;
}

async function fetchAmazonWatchItems(watchItems) {
  const fetched = new Map();
  if (!watchItems.length) return fetched;

  const { AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY, AMAZON_PARTNER_TAG, AMAZON_HOST, AMAZON_REGION, AMAZON_MARKETPLACE } =
    process.env;
  if (!AMAZON_ACCESS_KEY || !AMAZON_SECRET_KEY || !AMAZON_PARTNER_TAG) {
    throw new Error(
      'AMAZON_ACCESS_KEY / AMAZON_SECRET_KEY / AMAZON_PARTNER_TAG が設定されていません。.env.example を参照してください。'
    );
  }

  const credentials = {
    accessKey: AMAZON_ACCESS_KEY,
    secretKey: AMAZON_SECRET_KEY,
    partnerTag: AMAZON_PARTNER_TAG,
    host: AMAZON_HOST,
    region: AMAZON_REGION,
    marketplace: AMAZON_MARKETPLACE,
  };

  for (const batch of chunk(watchItems, AMAZON_BATCH_SIZE)) {
    try {
      const results = await fetchAmazonItems(
        batch.map((w) => w.asin),
        credentials
      );
      for (const watchItem of batch) {
        const item = results[watchItem.asin];
        if (item) fetched.set(watchItem, item);
        else console.warn(`[${watchItem.id}] Amazon商品が見つかりませんでした (ASIN: ${watchItem.asin})`);
      }
    } catch (err) {
      console.error(`Amazon商品取得エラー (${batch.map((w) => w.id).join(', ')}): ${err.message}`);
    }
  }
  return fetched;
}

async function main() {
  const config = loadJson(CONFIG_PATH, {
    discountThreshold: 0.15,
    cooldownDays: 7,
    maxPostsPerRun: 2,
    hashtags: ['#PR'],
  });
  const watchlist = loadJson(WATCHLIST_PATH, []);
  const history = loadJson(PRICE_HISTORY_PATH, {});
  const postLog = loadJson(POST_LOG_PATH, {});
  const now = Date.now();

  const enabled = watchlist.filter((w) => w.enabled !== false);
  const rakutenWatchItems = enabled.filter((w) => (w.provider ?? 'rakuten') === 'rakuten');
  const amazonWatchItems = enabled.filter((w) => w.provider === 'amazon');

  const fetched = new Map([
    ...(await fetchRakutenWatchItems(rakutenWatchItems)),
    ...(await fetchAmazonWatchItems(amazonWatchItems)),
  ]);

  const candidates = [];

  for (const [watchItem, item] of fetched) {
    const result = evaluateItem({
      item,
      watchItem,
      history,
      postLog,
      now,
      defaultThreshold: config.discountThreshold,
      defaultCooldownDays: config.cooldownDays,
    });

    console.log(
      `[${watchItem.id}] ¥${item.price} (前回: ${history[item.key]?.lastPrice ?? '未記録'}) -> ${result.reason}`
    );

    if (result.eligible) candidates.push(result);

    history[item.key] = {
      lastPrice: item.price,
      lastCheckedAt: new Date(now).toISOString(),
    };
  }

  candidates.sort((a, b) => b.discountRate - a.discountRate);
  const toPost = candidates.slice(0, config.maxPostsPerRun);

  if (!toPost.length) {
    console.log('本日投稿対象となる値下げ商品はありませんでした。');
  } else {
    const client = DRY_RUN ? null : createXClient();

    for (const candidate of toPost) {
      const text = composeTweet({
        item: candidate.item,
        previousPrice: candidate.previousPrice,
        discountRate: candidate.discountRate,
        hashtags: config.hashtags,
      });

      console.log('--- 投稿予定ツイート ---');
      console.log(text);

      if (DRY_RUN) {
        console.log('(DRY_RUN=true のため実際には投稿していません)');
      } else {
        await postTweet(client, text, candidate.item.imageUrl);
        postLog[candidate.item.key] = new Date(now).toISOString();
        console.log('投稿しました。');
      }
    }
  }

  saveJson(PRICE_HISTORY_PATH, history);
  if (!DRY_RUN) saveJson(POST_LOG_PATH, postLog);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
