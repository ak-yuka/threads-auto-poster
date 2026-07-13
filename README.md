# threads-auto-poster

Googleスプレッドシートに用意した文章を、1日4回(7:00 / 12:00 / 18:00 / 21:00 JST)
Threadsへ自動投稿する。各時間帯には固定のグループがあり、グループ内の未投稿の文章から
ランダムに1つ選んで投稿する。グループ内を全て投稿し終えたら自動的にリセットされ、
再度そのグループ内でランダム投稿を繰り返す。

## スプレッドシートの形式

1行目はヘッダー。A列=Group、B列=Text、C列=Posted。

| Group | Text           | Posted |
|-------|----------------|--------|
| 7     | おはよう文章1  | FALSE  |
| 7     | おはよう文章2  | FALSE  |
| 12    | お昼の文章1    | FALSE  |
| 18    | 夕方の文章1    | FALSE  |
| 21    | 夜の文章1      | FALSE  |

- Group列は必ず `7` / `12` / `18` / `21` のいずれか(投稿する時間と対応)
- Posted列は空欄でもOK(スクリプトがFALSE扱いする形にはしていないので、
  最初は必ず `FALSE` を入れておくこと)
- 各グループに最低1行は必要

## セットアップ手順

### 1. Googleスプレッドシート側の準備(サービスアカウント)

1. https://console.cloud.google.com/ でプロジェクトを作成
2. 「APIとサービス」→「ライブラリ」で **Google Sheets API** を有効化
3. 「認証情報」→「認証情報を作成」→「サービスアカウント」を作成
4. 作成したサービスアカウントの「キー」タブから JSON キーを作成・ダウンロード
   (このJSONファイルの中身をあとで `GOOGLE_CREDENTIALS_JSON` として使う)
5. ダウンロードしたJSON内の `client_email` の値をコピー
6. 投稿用スプレッドシートを開き、「共有」からその `client_email` を
   **編集者** 権限で共有する
7. スプレッドシートのURL `https://docs.google.com/spreadsheets/d/【ここ】/edit`
   の【ここ】部分が `SHEET_ID`

### 2. Threads API側の準備

1. https://developers.facebook.com/ で開発者アカウント登録、アプリを新規作成
2. アプリのユースケースに **Threads API** を追加
3. 自分のThreadsアカウント(プロ/ビジネスアカウントである必要あり)で
   アプリへのアクセスを許可し、アクセストークンを取得
4. 取得したトークンは有効期限が短いため、Threads APIの
   `GET /access_token?grant_type=th_exchange_token` を使って
   **長期アクセストークン(60日)** に交換する
5. `GET https://graph.threads.net/v1.0/me?fields=id&access_token=<トークン>`
   を叩いて `THREADS_USER_ID` を取得
6. 長期トークンは60日で失効するので、期限が切れる前に
   `GET /refresh_access_token` で更新が必要(このリポジトリでは未自動化。
   必要なら追加で実装する)

### 3. GitHubリポジトリの準備

1. このフォルダをGitHubリポジトリとしてpush
2. リポジトリの Settings → Secrets and variables → Actions →
   New repository secret で以下を登録

   | Secret名 | 値 |
   |---|---|
   | `SHEET_ID` | スプレッドシートのID |
   | `THREADS_USER_ID` | ThreadsのユーザーID |
   | `THREADS_ACCESS_TOKEN` | Threadsの長期アクセストークン |
   | `GOOGLE_CREDENTIALS_JSON` | サービスアカウントJSONファイルの中身をそのまま貼り付け |

3. Actionsタブ →「Post to Threads」→「Run workflow」で
   手動実行してテストする(group欄に `7`/`12`/`18`/`21` のいずれかを入力)

## 投稿スケジュール

`.github/workflows/post.yml` のcronはUTC基準(JST-9時間)で設定済み。

| JST | UTC (cron) | Group |
|---|---|---|
| 7:00  | 22:00(前日) | 7  |
| 12:00 | 3:00        | 12 |
| 18:00 | 9:00        | 18 |
| 21:00 | 12:00       | 21 |

GitHub Actionsのscheduleは数分〜数十分の遅延が発生することがある。

## ローカルでのテスト

```
pip install -r requirements.txt
set SHEET_ID=...
set THREADS_USER_ID=...
set THREADS_ACCESS_TOKEN=...
set GOOGLE_CREDENTIALS_JSON={...JSONの中身...}
set POST_GROUP=7
python scripts/post_to_threads.py
```
