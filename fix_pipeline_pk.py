import mysql.connector

conn = mysql.connector.connect(
    host='localhost', port=3306, database='myrecruitment',
    user='root', password='Nu<2406>', autocommit=True
)
cur = conn.cursor()

try:
    cur.execute('ALTER TABLE ats_pipeline DROP PRIMARY KEY')
    print('dropped old PK')
except Exception as e:
    print('drop PK:', e)

try:
    cur.execute('ALTER TABLE ats_pipeline ADD PRIMARY KEY (candidate_id, recruiter_email)')
    print('added composite PK (candidate_id, recruiter_email)')
except Exception as e:
    print('add PK:', e)

try:
    cur.execute("UPDATE ats_pipeline SET recruiter_email='varianeha60100@gmail.com' WHERE recruiter_email='2303031050670@paruluniversity.ac.in'")
    print('migrated rows:', cur.rowcount)
except Exception as e:
    print('migrate:', e)

cur.execute('SELECT candidate_id, recruiter_email, stage FROM ats_pipeline')
for r in cur.fetchall():
    print(r)

cur.close()
conn.close()
