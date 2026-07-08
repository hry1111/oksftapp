# affiliate-x-bot

値下げしたオススメ商品のアフィリエイトリンクを X（旧Twitter）に自動投稿するシステムです。

## 仕組み

1. `config/watchlist.json` に登録した楽天市場の商品を、楽天市場商品検索API（アフィリエイトAPI）で定期的にチェックします。
2. 前回チェック時の価格（`data/price-history.json`）と比較し、値下げ幅が `config/config.json` の `discountThreshold` 以上なら「値下げ商品」と判定します。
3. 値下げ幅が大きい順に最大 `maxPostsPerRun` 件を選び、商品名・値下げ前後の価格・割引率・アフィリエイトリンクを含む文章を組み立てて X に投稿します（商品画像があれば画像付きで投稿）。
4. 同じ商品を連続で投稿しないよう、投稿履歴（`data/post-log.json`）を見て `cooldownDays` 日は再投稿しません。
5. GitHub Actions（`.github/workflows/affiliate-post.yml`）で定期実行し、価格履歴/投稿履歴の更新結果をリポジトリにコミットして状態を保持します。

初回実行時はすべての商品が「前回価格の記録なし」となるため、投稿は行われず基準価格の記録だけが行われます。2回目以降のチェックから値下げ判定が有効になります。

## セットアップ

### 1. 楽天ウェブサービスの登録

- [楽天ウェブサービス](https://webservice.rakuten.co.jp/) で開発者登録し、`アプリID`（`RAKUTEN_APP_ID`）を取得します。
- [楽天アフィリエイト](https://affiliate.rakuten.co.jp/) に登録し、`アフィリエイトID`（`RAKUTEN_AFFILIATE_ID`）を取得します。

### 2. X Developer Portal の設定

- [developer.x.com](https://developer.x.com/) でアプリを作成し、権限を **Read and Write** に設定します。
- OAuth 1.0a の `API Key` / `API Key Secret` と、そのアプリで発行した `Access Token` / `Access Token Secret` を取得します。

### 3. 監視する商品の登録

`config/watchlist.json` に商品を追加します。`itemCode` は楽天市場の商品ページURLや商品検索APIのレスポンスに含まれる `店舗コード:商品コード` 形式の値です。

```json
[
  {
    "id": "vacuum-a",
    "label": "コードレス掃除機 Aモデル",
    "itemCode": "shop-code:10000001",
    "enabled": true,
    "minDiscountRate": 0.15,
    "cooldownDays": 7
  }
]
```

- `minDiscountRate` / `cooldownDays` を省略した場合は `config/config.json` の値が使われます。
- `enabled: false` にすると一時的に監視対象から外せます。

### 4. GitHub Secrets の登録

リポジトリの Settings > Secrets and variables > Actions に以下を登録します。

| Secret名 | 内容 |
|---|---|
| `RAKUTEN_APP_ID` | 楽天ウェブサービスのアプリID |
| `RAKUTEN_AFFILIATE_ID` | 楽天アフィリエイトID |
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
      selectDiscounts.js # 値下げ判定ロジック
      composeTweet.js     # 投稿文の組み立て
      xClient.js           # X投稿クライアント
      jsonStore.js          # JSON読み書きユーティリティ
```
