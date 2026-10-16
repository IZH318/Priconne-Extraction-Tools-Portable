import sys
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('master_jp.db')
cur = conn.cursor()

# 1. Legion Special Battle
cur.execute('''
    SELECT 
        "78f58966d683503660b1bcf1a16c07a263e46f71aaa156a54f86efc7f307c7ed" as mode,
        "5947ebe37a17df39d5a465c5c32bf30b297b9129cd9720ac4595ff8df96210f7" as mode_start,
        "a4af869fbcccb7d036df10eb59700f5ea1031dd27a170e6c71d6e1f2e6bdc611" as mode_end
    FROM "v1_bbe45d7d2bbc7785017ae52c0bd42fad765b3bc3ff29a66e897f566aa9cbdf24"
''')
print("Legion Special Battle rows:")
for r in cur.fetchall():
    print(" ", r)

# 2. Byway Battle & Quest Data
cur.execute('''
    SELECT 
        b."4448252e4754c654cb6f95562026254c98081c6ed797fbab5819ea6ed109497e" as quest_id,
        b."39176438fc88fc3015526a437e7858ba0516354388d7a7acd2fdc6c0c8299959" as wavestart,
        b."7cd586b081f6291561e8c1dac038059cfea2fef1027de44f5d0a64669a9d5d00" as waveend,
        q."7f9770643ad7b7fc16eaeae37eede54524169681ca83efc4e9cd0c1c5eeb30af" as quest_name
    FROM "v1_464e8127adaba760d11e792401474f021c5c41f4ceb2338373d0af418caf6bf9" b
    JOIN "v1_9616c136fcccfb44f708d15d3b1cf7b66e3b7116bc83ccdf42edc08867d5c132" q
      ON b."4448252e4754c654cb6f95562026254c98081c6ed797fbab5819ea6ed109497e" = q."970f42e5c1f6b39419d08720396a113882ff4b49728974efbb48980a2f820a82"
''')
print("\nByway Battle rows:")
for r in cur.fetchall():
    print(" ", r)
