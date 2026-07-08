import path from 'node:path';
import { fetchItem } from './lib/rakuten.js';
import { loadJson, saveJson } from './lib/jsonStore.js';
import { evaluateItem } from './lib/selectDiscounts.js';
import { composeTweet } from './lib/composeTweet.js';
import { createXClient, postTweet } from './lib/xClient.js';

const CONFIG_PATH = path.resolve('config/config.json');
const WATCHLIST_PATH = path.resolve('config/watchlist.json');
const PRICE_HISTORY_PATH = path.resolve('data/price-history.json');
const POST_LOG_PATH = path.resolve('data/post-log.json');

const DRY_RUN = process.env.DRY_RUN === 'true';

async function main() {
  const { RAKUTEN_APP_ID, RAKUTEN_AFFILIATE_ID } = process.env;
  if (!RAKUTEN_APP_ID) {
    throw new Error('RAKUTEN_APP_ID が設定されていません。.env.example を参照してください。');
  }

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

  const candidates = [];

  for (const watchItem of watchlist) {
    if (watchItem.enabled === false) continue;

    let item;
    try {
      item = await fetchItem(watchItem.itemCode, {
        applicationId: RAKUTEN_APP_ID,
        affiliateId: RAKUTEN_AFFILIATE_ID,
      });
    } catch (err) {
      console.error(`[${watchItem.id}] 商品取得エラー: ${err.message}`);
      continue;
    }

    if (!item) {
      console.warn(`[${watchItem.id}] 商品が見つかりませんでした (itemCode: ${watchItem.itemCode})`);
      continue;
    }

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
      `[${watchItem.id}] ¥${item.price} (前回: ${history[item.itemCode]?.lastPrice ?? '未記録'}) -> ${result.reason}`
    );

    if (result.eligible) candidates.push(result);

    history[item.itemCode] = {
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
        postLog[candidate.item.itemCode] = new Date(now).toISOString();
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
