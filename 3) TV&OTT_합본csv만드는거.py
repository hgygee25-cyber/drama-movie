import pandas as pd
import os

TV_FILE = 'tv_crawling.csv'
OTT_FILE = 'ott_crawling.csv'
FINAL_FILE = 'final_crawling.csv'


def combine_data_files():
    print("====================================")

    # ============================
    # 1) TV 데이터 로드
    # ============================
    if os.path.exists(TV_FILE):
        df_tv = pd.read_csv(TV_FILE, encoding='utf-8-sig')
        df_tv['source'] = 'TV'
        df_tv['platform'] = 'Cable'
        df_tv['rank'] = ''
        df_tv['rank_change'] = ''
        df_tv['synopsis'] = df_tv.get('plot', '')

        # TV 컬럼명 통일
        df_tv['poster_url'] = df_tv.get('poster_url', '')
        df_tv['runtime'] = df_tv.get('runtime_or_episode', '')

        print(f"✅ TV 데이터 {len(df_tv)}건 로드")
    else:
        print(f"❌ '{TV_FILE}' 없음")
        df_tv = pd.DataFrame()

    # ============================
    # 2) OTT 데이터 로드
    # ============================
    if os.path.exists(OTT_FILE):
        df_ott = pd.read_csv(OTT_FILE, encoding='utf-8-sig')
        df_ott['source'] = 'OTT'
        df_ott['channel'] = ''
        df_ott['broadcast_date'] = ''
        df_ott['broadcast_time'] = ''
        df_ott['plot'] = df_ott.get('synopsis', '')

        # OTT 포스터명 통합
        df_ott['poster_url'] = df_ott.get('poster_image', '')
        df_ott['runtime'] = df_ott.get('running_time', '')

        print(f"✅ OTT 데이터 {len(df_ott)}건 로드")
    else:
        print(f"❌ '{OTT_FILE}' 없음")
        df_ott = pd.DataFrame()

    # ============================
    # 3) 최종 컬럼 구조
    # ============================
    final_columns = [
        'source', 'platform', 'channel',
        'broadcast_date', 'broadcast_time',
        'title', 'plot', 'genre', 'cast', 'director',
        'poster_url', 'age_rating', 'runtime',
        'rank', 'rank_change',
    ]

    # ============================
    # 4) 누락 컬럼 보완
    # ============================
    for col in final_columns:
        if col not in df_tv.columns:
            df_tv[col] = ''
        if col not in df_ott.columns:
            df_ott[col] = ''

    # ============================
    # 5) 통합
    # ============================
    df_final = pd.concat([
        df_tv[final_columns],
        df_ott[final_columns]
    ], ignore_index=True)

    # ============================
    # 6) 저장
    # ============================
    df_final.to_csv(FINAL_FILE, index=False, encoding='utf-8-sig')

    print(f"\n🎉 합본 생성 완료! 총 {len(df_final)}건 → '{FINAL_FILE}' 저장")


if __name__ == "__main__":
    combine_data_files()
