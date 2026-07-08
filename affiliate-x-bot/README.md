# affiliate-x-bot

値下げしたオススメ商品のアフィリエイトリンクを X（旧Twitter）に自動投稿するシステムです。
楽天市場と Amazon（PA-API 5.0）の両方に対応しています。

## 仕組み

1. `config/watchlist.json` に登録した商品を、楽天市場商品検索API または Amazon Product Advertising API（PA-API 5.0）で定期的にチェックします。
2. 前回チェック時の価格（`data/price-history.json`）と比較し、値下げ幅が `config/config.json` の `discountThreshold` 以上なら「値下げ商品」と判定します。
3. 値下げ幅が大きい順に最大 `maxPostsPerRun` 件を選び、商品名・値下げ前後の価格・割引率・アフィリエイトリンクを含む文章を組み立てて X に投稿します（商品画像があれば画像付きで投稿）。
4. 同じ商品を連続で投稿しないよう、投稿履歴（`data/post-log.json`）を見て `cooldownDays` 日は再投稿しません。
5. GitHub Actions（`.github/workflows/affiliate-post.yml`）で定期実行し、価格履歴/投稿履歴の更新結果をリポジトリにコミットして状態を保持します。

初回実行時はすべての商品が「前回価格の記録なし」となるため、投稿は行われず基準価格の記録だけが行われます。2回目以降のチェックから値下げ判定が有効になります。

## セットアップ

### 1. 楽天ウェブサービスの登録

- [楽天ウェブサービス](https://webservice.rakuten.co.jp/) で開発者登録し、`アプリID`（`RAKUTEN_APP_ID`）を取得します。
- [楽天アフィリエイト](https://affiliate.rakuten.co.jp/) に登録し、`アフィリエイトID`（`RAKUTEN_AFFILIATE_ID`）を取得します。

### 2. Amazon Product Advertising API (PA-API 5.0) の登録

- [Amazonアソシエイト](https://affiliate.amazon.co.jp/) に登録します（PA-APIの利用にはアソシエイトアカウントが必須です）。
- [Associates Central](https://affiliate.amazon.co.jp/assoc_credentials/home) の「Product Advertising API」から `アクセスキー`（`AMAZON_ACCESS_KEY`）と `シークレットキー`（`AMAZON_SECRET_KEY`）を発行します。
- アソシエイトタグ（`AMAZON_PARTNER_TAG`、例: `yourtag-22`）を確認します。
- **注意点**
  - PA-APIは新規登録直後は使えず、アソシエイト経由で**直近180日以内に3件以上の売上**が発生していないとリクエストが拒否されます（既存の売上実績がないと `TooManyRequests`/`InvalidParameterValue` 系のエラーになります）。
  - リクエスト数の上限（TPS）は売上実績に応じて上がる仕組みなので、`config/watchlist.json` にAmazon商品を大量に登録しすぎないようにしてください（本システムは同時に最大10件ずつバッチ取得することでリクエスト数を抑えています）。
  - Amazon.co.jp以外のマーケットプレイスを使う場合は `.env.example` にある `AMAZON_HOST` / `AMAZON_REGION` / `AMAZON_MARKETPLACE` を対象国に合わせて変更してください。

### 3. X Developer Portal の設定

- [developer.x.com](https://developer.x.com/) でアプリを作成し、権限を **Read and Write** に設定します。
- OAuth 1.0a の `API Key` / `API Key Secret` と、そのアプリで発行した `Access Token` / `Access Token Secret` を取得します。

### 4. 監視する商品の登録

`config/watchlist.json` に商品を追加します。`provider` に `"rakuten"` または `"amazon"` を指定してください（省略時は `"rakuten"` 扱いになります）。

```json
[
  {
    "id": "vacuum-a",
    "label": "コードレス掃除機 Aモデル（楽天市場）",
    "provider": "rakuten",
    "itemCode": "shop-code:10000001",
    "enabled": true,
    "minDiscountRate": 0.15,
    "cooldownDays": 7
  },
  {
    "id": "vacuum-b",
    "label": "コードレス掃除機 Bモデル（Amazon）",
    "provider": "amazon",
    "asin": "B0XXXXXXXX",
    "enabled": true,
    "minDiscountRate": 0.15,
    "cooldownDays": 7
  }
]
```

- 楽天商品の `itemCode` は商品ページURLや商品検索APIのレスポンスに含まれる `店舗コード:商品コード` 形式の値です。
- Amazon商品の `asin` は商品ページURLに含まれる10桁の商品コード（ASIN）です。
- `minDiscountRate` / `cooldownDays` を省略した場合は `config/config.json` の値が使われます。
- `enabled: false` にすると一時的に監視対象から外せます。

### 5. GitHub Secrets の登録

リポジトリの Settings > Secrets and variables > Actions に以下を登録します。楽天・Amazonのどちらか一方しか使わない場合も、`watchlist.json` にそのプロバイダの商品が1件もなければ該当シークレットは未設定のままで構いません（実行時にそのプロバイダのAPIは呼び出されません）。

| Secret名 | 内容 |
|---|---|
| `RAKUTEN_APP_ID` | 楽天ウェブサービスのアプリID |
| `RAKUTEN_AFFILIATE_ID` | 楽天アフィリエイトID |
| `AMAZON_ACCESS_KEY` | Amazon PA-APIのアクセスキー |
| `AMAZON_SECRET_KEY` | Amazon PA-APIのシークレットキー |
| `AMAZON_PARTNER_TAG` | Amazonアソシエイトタグ |
| `X_API_KEY` | X APIキー |
| `X_API_KEY_SECRET` | X APIキーシークレット |
| `X_ACCESS_TOKEN` | Xアクセストークン |
| `X_ACCESS_TOKEN_SECRET` | Xアクセストークンシークレット |

`.github/workflows/affiliate-post.yml` は6時間おきに自動実行されます（`workflow_dispatch` から手動実行も可能。`dryRun: true` を指定すると投稿せずログ確認だけできます）。

## ローカルでの動作確認

```bash
cd affiliate-x-bot
cp .env.example .env   # 値を書き換える
npm install

# 投稿はせず、判定結果と投稿予定文だけ確認する
DRY_RUN=true npm start

# 実際に投稿する
npm start
```

## 広告表示（ステマ規制）について

アフィリエイトリンクを含む投稿は景品表示法の「ステルスマーケティング規制」の対象となり、広告であることが分かるよう明示する必要があります。`config/config.json` の `hashtags` に既定で `#PR` を含めています。表示方法を変更する場合も、広告であることが一目で分かる表記を必ず残してください。

## ディレクトリ構成

```
affiliate-x-bot/
  config/
    config.json      # しきい値・クールダウン・投稿件数・ハッシュタグ
    watchlist.json    # 監視する商品一覧
  data/
    price-history.json  # 商品ごとの直近価格（自動更新）
    post-log.json        # 商品ごとの最終投稿日時（自動更新）
  src/
    index.js          # エントリーポイント
    lib/
      rakuten.js        # 楽天市場商品検索APIクライアント
      amazon.js          # Amazon PA-API 5.0クライアント
      selectDiscounts.js # 値下げ判定ロジック
      composeTweet.js     # 投稿文の組み立て
      xClient.js           # X投稿クライアント
      jsonStore.js          # JSON読み書きユーティリティ
```
