import { TwitterApi } from 'twitter-api-v2';

export function createXClient() {
  const { X_API_KEY, X_API_KEY_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET } = process.env;
  if (!X_API_KEY || !X_API_KEY_SECRET || !X_ACCESS_TOKEN || !X_ACCESS_TOKEN_SECRET) {
    throw new Error('X (Twitter) の認証情報が環境変数に設定されていません。.env.example を参照してください。');
  }
  return new TwitterApi({
    appKey: X_API_KEY,
    appSecret: X_API_KEY_SECRET,
    accessToken: X_ACCESS_TOKEN,
    accessSecret: X_ACCESS_TOKEN_SECRET,
  });
}

/**
 * テキストを投稿する。imageUrl が指定できて取得に成功した場合は画像付きで投稿する。
 * 画像の取得/アップロードに失敗した場合はテキストのみで投稿を続行する。
 */
export async function postTweet(client, text, imageUrl) {
  let mediaId;
  if (imageUrl) {
    try {
      const res = await fetch(imageUrl);
      if (res.ok) {
        const buffer = Buffer.from(await res.arrayBuffer());
        mediaId = await client.v1.uploadMedia(buffer, {
          mimeType: res.headers.get('content-type') || 'image/jpeg',
        });
      }
    } catch (err) {
      console.warn('画像の取得/アップロードに失敗したためテキストのみ投稿します:', err.message);
    }
  }

  const payload = mediaId ? { text, media: { media_ids: [mediaId] } } : { text };
  return client.v2.tweet(payload);
}
